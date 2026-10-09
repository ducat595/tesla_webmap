"""Ephemeral location relay. Python standard library only; one process."""
import json, math, os, secrets, threading, time
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import tesla_bridge
import device_auth
import tesla_oauth
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

sessions = {}
lock = threading.Lock()
vehicle_lock = threading.Lock()
attempts={}
TTL = 3600
origins = set(x.strip() for x in os.getenv('ALLOWED_ORIGINS', '').split(',') if x.strip())

def valid_location(p):
    for k, lo, hi in [('latitude', -90, 90), ('longitude', -180, 180), ('accuracy', 0, 100000)]:
        v = p.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
            return False
    return True

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log credentials or coordinates.

    def reply(self, code, data):
        self.send_response(code)
        origin = self.headers.get('Origin')
        if origin in origins:
            self.send_header('Access-Control-Allow-Origin', origin)
        self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Tesla-Owner-Key, X-Tesla-Device-Token')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.reply(204, {})

    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()
    def do_PUT(self): self.handle_request()
    def do_DELETE(self): self.handle_request()

    def handle_request(self):
        path = urlsplit(self.path).path
        if path == '/health' and self.command == 'GET':
            return self.reply(200, {'ok': True})
        if path in ('/auth/tesla/callback','/auth/tesla/launch') and self.command == 'GET':
            return self.oauth_browser(path)
        if self.headers.get('Origin') and self.headers['Origin'] not in origins:
            return self.reply(403, {'error': '許可されていない公開元です。ALLOWED_ORIGINSを確認してください。'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 20000: raise ValueError()
            payload = json.loads(self.rfile.read(length)) if length else {}
            if not isinstance(payload, dict): raise ValueError()
        except (ValueError, json.JSONDecodeError):
            return self.reply(400, {'error': '不正なリクエストです'})
        if path == '/auth/tesla/start' and self.command == 'POST':
            try:
                url=tesla_oauth.begin(self.headers.get('X-Tesla-Device-Token',''))
                return self.reply(200, {'url':url})
            except tesla_oauth.OAuthError as e:return self.reply(400,{'error':str(e)})
        with lock:
            now = time.time()
            for code in list(sessions):
                if sessions[code]['expires'] < now: del sessions[code]
            if path == '/sessions' and self.command == 'POST':
                if len(sessions) >= 200: return self.reply(429, {'error': '利用数上限です。後でお試しください'})
                code = f'{secrets.randbelow(10000):04d}'
                while code in sessions: code = f'{secrets.randbelow(10000):04d}'
                token = secrets.token_urlsafe(32)
                sessions[code] = {'token': token, 'expires': now + TTL, 'location': None, 'destination': None, 'destinationVersion': 0, 'waypoints': [], 'teslaRequests': {}, 'pairs': {}, 'pairExpires': now+600, 'ownerDevice': self.headers.get('X-Tesla-Device-Token','')}
                return self.reply(201, {'code': code, 'token': token, 'expiresAt': now + TTL, 'ownerAuthorized':device_auth.valid(sessions[code]['ownerDevice'])})
            if path == '/owner-device' and self.command == 'POST':
                if not self.rate_ok('owner',now,10): return self.reply(429,{'error':'所有者確認の試行回数上限です。1分後に再試行してください。'})
                supplied=payload.get('key','')
                if not isinstance(supplied,str) or len(device_auth.secret())<32 or not secrets.compare_digest(device_auth.secret().encode(),supplied.encode()):
                    return self.reply(403,{'error':'所有者キーが一致しません。'})
                return self.reply(200,{'deviceToken':device_auth.issue(),'days':30})
            parts = path.strip('/').split('/')
            if len(parts)==3 and parts[0]=='sessions' and parts[2] in ('pair','pair-status','pending','approve','authorize'):
                return self.pairing(parts[1],parts[2],payload,now)
            if len(parts) == 3 and parts[0] == 'sessions' and parts[2] == 'tesla-navigate' and self.command == 'POST':
                return self.tesla_navigate(parts[1].upper(),payload,now)
            if len(parts) != 2 or parts[0] != 'sessions':
                return self.reply(404, {'error': '見つかりません'})
            code = parts[1].upper()
            session = sessions.get(code)
            if not session: return self.reply(404, {'error': '接続コードが違うか、期限切れ・サーバー再起動です'})
            if self.command == 'GET':
                if not self.reader(session): return self.reply(403,{'error':'iPhone側で接続を許可してください。'})
                return self.reply(200, {'location': session['location'], 'expiresAt': session['expires'], 'destination': session['destination'], 'destinationVersion': session['destinationVersion'], 'waypoints': session['waypoints'], 'teslaConfigured': tesla_bridge.configuration_ready(), 'ownerAuthorized':device_auth.valid(session['ownerDevice'])})
            auth = self.headers.get('Authorization', '')
            if not secrets.compare_digest(auth.encode(), ('Bearer ' + session['token']).encode()):
                return self.reply(403, {'error': '送信権限がありません'})
            if self.command == 'DELETE':
                del sessions[code]
                return self.reply(200, {'ok': True})
            if self.command == 'PUT':
                if 'destination' in payload or 'waypoints' in payload:
                    d = payload.get('destination',session['destination'])
                    w = payload.get('waypoints',session['waypoints'])
                    def valid_stop(stop):
                        return isinstance(stop,dict) and valid_location({**stop,'accuracy':0}) and isinstance(stop.get('name'),str) and 1 <= len(stop['name']) <= 300 and ('placeId' not in stop or isinstance(stop['placeId'],str) and len(stop['placeId']) <= 300)
                    if (d is not None and not valid_stop(d)) or not isinstance(w,list) or len(w)>8 or not all(valid_stop(x) for x in w) or (d is None and w):
                        return self.reply(400, {'error': '目的地・経由地が不正です（経由地は最大8件）。'})
                    session['destination'] = d
                    session['waypoints'] = w
                    session['destinationVersion'] += 1
                else:
                    if not valid_location(payload): return self.reply(400, {'error': '位置情報が不正です'})
                    session['location'] = {k: payload[k] for k in ('latitude', 'longitude', 'accuracy')}
                    session['location']['receivedAt'] = now
                return self.reply(200, {'ok': True, 'destinationVersion':session['destinationVersion']})
            return self.reply(405, {'error': '未対応の操作です'})



    def oauth_browser(self,path):
        query=parse_qs(urlsplit(self.path).query)
        cookie='tesla_oauth=; Path=/auth/tesla/; Secure; HttpOnly; SameSite=Lax; Max-Age=0'
        try:
            if path.endswith('/launch'):
                url,value=tesla_oauth.launch(query)
                self.send_response(303);self.send_header('Location',url)
                self.send_header('Set-Cookie','tesla_oauth='+value+'; Path=/auth/tesla/; Secure; HttpOnly; SameSite=Lax; Max-Age=600')
                self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.end_headers();return
            tesla_oauth.callback(query,self.headers.get('Cookie',''))
            code=200;message='Teslaログインが完了しました。下のリンクからアプリへ戻り、位置共有を開始し直してください。署名プロキシ・車両仮想キーの設定は別途必要です。認証情報はサーバー再起動または有効期限で失われます。'
        except tesla_oauth.OAuthError as e:code=400;message=str(e)
        self.send_response(code);self.send_header('Set-Cookie',cookie)
        self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store')
        self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tesla認証</title><body style="font-family:sans-serif;padding:32px;line-height:1.8"><h1>Tesla認証</h1><p>'+escape(message)+'</p><p><a href="https://ducat595.github.io/tesla_webmap/frontend/">アプリへ戻る</a></p></body></html>').encode())

    def rate_ok(self, kind, now, limit):
        key=(self.client_address[0],kind)
        for k,(started,_) in list(attempts.items()):
            if started<now-60: del attempts[k]
        started,count=attempts.get(key,(now,0))
        attempts[key]=(started,count+1)
        return count<limit

    def bearer(self):
        return self.headers.get('Authorization','').removeprefix('Bearer ')

    def sender(self,s): return secrets.compare_digest(self.bearer().encode(),s['token'].encode())

    def reader(self,s):
        if self.sender(s):return True
        token=self.bearer()
        return any(p['approved'] and secrets.compare_digest(token.encode(),p['token'].encode()) for p in s['pairs'].values())

    def pairing(self,code,action,payload,now):
        if action=='pair' and not self.rate_ok('pair',now,20): return self.reply(429,{'error':'接続試行が多すぎます。1分後に再試行してください。'})
        s=sessions.get(code)
        if not s:return self.reply(404,{'error':'コードが違うか、期限切れです。'})
        if action=='pair' and self.command=='POST':
            if now>s['pairExpires']:return self.reply(410,{'error':'4桁コードの受付期限（10分）が過ぎました。iPhoneで共有し直してください。'})
            for k in list(s['pairs']):
                if not s['pairs'][k]['approved'] and s['pairs'][k]['expires']<now:del s['pairs'][k]
            if len(s['pairs'])>=5:return self.reply(429,{'error':'接続要求数の上限です。iPhoneで不要な要求を拒否してください。'})
            identifier=secrets.token_hex(4).upper();token=secrets.token_urlsafe(32)
            s['pairs'][identifier]={'token':token,'approved':False,'expires':now+120}
            return self.reply(201,{'pairId':identifier,'viewerToken':token})
        if action=='pair-status' and self.command=='GET':
            token=self.bearer()
            for p in s['pairs'].values():
                if secrets.compare_digest(p['token'].encode(),token.encode()):
                    if not p['approved'] and p['expires']<now:return self.reply(410,{'error':'接続要求が期限切れです。再接続してください。'})
                    return self.reply(200,{'approved':p['approved']})
            return self.reply(403,{'error':'接続要求が拒否・解除されました。'})
        if not self.sender(s):return self.reply(403,{'error':'iPhone送信端末だけが接続を許可できます。'})
        if action=='pending' and self.command=='GET':
            return self.reply(200,{'ownerAuthorized':device_auth.valid(s['ownerDevice']), 'teslaConfigured':tesla_bridge.configuration_ready(), 'pending':[{'pairId':k,'secondsLeft':int(p['expires']-now)} for k,p in s['pairs'].items() if not p['approved'] and p['expires']>now]})
        if action=='approve' and self.command=='POST':
            p=s['pairs'].get(payload.get('pairId'))
            if not p or p['expires']<now:return self.reply(410,{'error':'接続要求が期限切れです。'})
            if payload.get('allow') is True:p['approved']=True
            else:del s['pairs'][payload['pairId']]
            return self.reply(200,{'ok':True})
        if action=='authorize' and self.command=='POST':
            token=self.headers.get('X-Tesla-Device-Token','')
            if not device_auth.valid(token):return self.reply(403,{'error':'初回の所有者確認が必要です。'})
            s['ownerDevice']=token
            return self.reply(200,{'ownerAuthorized':True})
        return self.reply(405,{'error':'未対応の操作です。'})

    def tesla_navigate(self, code, payload, now):
        session=sessions.get(code)
        if not session: return self.reply(404,{'error':'接続コードが違うか、期限切れです'})
        if not self.reader(session) or not device_auth.valid(session['ownerDevice']):
            return self.reply(403,{'error':'iPhoneで初回の所有者確認を済ませ、この端末の接続を許可してください。'})
        if payload.get('version') != session['destinationVersion']:
            return self.reply(409,{'error':'地点一覧が更新されています。最新の共有内容で送信してください。'})
        if not session['destination']: return self.reply(400,{'error':'目的地がありません'})
        request_id=payload.get('requestId')
        if not isinstance(request_id,str) or not 16 <= len(request_id) <= 100:
            return self.reply(400,{'error':'送信識別子が不正です'})
        requests=session['teslaRequests']
        if request_id in requests:
            previous=requests[request_id]
            return self.reply(previous[0],previous[1])
        if len(requests)>=30: return self.reply(429,{'error':'この接続での送信回数上限です'})
        if not vehicle_lock.acquire(blocking=False): return self.reply(409,{'error':'Teslaへ送信処理中です。完了を待ってください。'})
        stops=[dict(x) for x in session['waypoints']]+[dict(session['destination'])]
        requests[request_id]=(409,{'error':'この送信は処理中です。車載ナビを確認してください。'})
        lock.release()
        try:
            try: result=(200,tesla_bridge.send_waypoints(stops))
            except tesla_bridge.BridgeError as e: result=(e.code,{'error':e.message})
            except Exception: result=(502,{'error':'送信結果を確認できません。車載ナビを確認してください。'})
        finally:
            lock.acquire()
            vehicle_lock.release()
        requests[request_id]=result
        return self.reply(*result)

if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '8000'))), Handler).serve_forever()

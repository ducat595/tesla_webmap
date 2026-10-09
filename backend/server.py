"""Ephemeral location relay. Python standard library only; one process."""
import json, math, os, secrets, threading, time
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import tesla_bridge
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

sessions = {}
lock = threading.Lock()
vehicle_lock = threading.Lock()
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
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Tesla-Owner-Key')
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
        if self.headers.get('Origin') and self.headers['Origin'] not in origins:
            return self.reply(403, {'error': '許可されていない公開元です。ALLOWED_ORIGINSを確認してください。'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 20000: raise ValueError()
            payload = json.loads(self.rfile.read(length)) if length else {}
            if not isinstance(payload, dict): raise ValueError()
        except (ValueError, json.JSONDecodeError):
            return self.reply(400, {'error': '不正なリクエストです'})
        with lock:
            now = time.time()
            for code in list(sessions):
                if sessions[code]['expires'] < now: del sessions[code]
            if path == '/sessions' and self.command == 'POST':
                if len(sessions) >= 200: return self.reply(429, {'error': '利用数上限です。後でお試しください'})
                code = secrets.token_hex(8).upper()
                while code in sessions: code = secrets.token_hex(8).upper()
                token = secrets.token_urlsafe(32)
                sessions[code] = {'token': token, 'expires': now + TTL, 'location': None, 'destination': None, 'destinationVersion': 0, 'waypoints': [], 'teslaRequests': {}}
                return self.reply(201, {'code': code, 'token': token, 'expiresAt': now + TTL})
            parts = path.strip('/').split('/')
            if len(parts) == 3 and parts[0] == 'sessions' and parts[2] == 'tesla-navigate' and self.command == 'POST':
                return self.tesla_navigate(parts[1].upper(),payload,now)
            if len(parts) != 2 or parts[0] != 'sessions':
                return self.reply(404, {'error': '見つかりません'})
            code = parts[1].upper()
            session = sessions.get(code)
            if not session: return self.reply(404, {'error': '接続コードが違うか、期限切れ・サーバー再起動です'})
            if self.command == 'GET':
                return self.reply(200, {'location': session['location'], 'expiresAt': session['expires'], 'destination': session['destination'], 'destinationVersion': session['destinationVersion'], 'waypoints': session['waypoints'], 'teslaConfigured': tesla_bridge.configuration_ready()})
            auth = self.headers.get('Authorization', '')
            if not secrets.compare_digest(auth, 'Bearer ' + session['token']):
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


    def tesla_navigate(self, code, payload, now):
        session=sessions.get(code)
        if not session: return self.reply(404,{'error':'接続コードが違うか、期限切れです'})
        configured=tesla_bridge.settings()['TESLA_OWNER_SECRET']
        supplied=self.headers.get('X-Tesla-Owner-Key','')
        if len(configured)<32 or not secrets.compare_digest(configured.encode(),supplied.encode()):
            return self.reply(403,{'error':'Tesla所有者キーが未設定、または一致しません。位置共有コードだけでは送信できません。'})
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

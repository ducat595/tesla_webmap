"""Owner-only OAuth, browser-bound state, memory-only tokens; single instance."""
import os, secrets, threading, time, json, urllib.request
from urllib.parse import urlencode, urlsplit
from http.cookies import SimpleCookie
import device_auth
pending={}; mutex=threading.Lock(); tokens={}
class OAuthError(Exception): pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None

def config():
    c={k:os.getenv(k,'').strip() for k in ('TESLA_CLIENT_ID','TESLA_CLIENT_SECRET','TESLA_REDIRECT_URI')}
    u=urlsplit(c['TESLA_REDIRECT_URI'])
    if not all(c.values()) or u.scheme!='https' or not u.netloc or u.username or u.password or u.query or u.fragment or u.path!='/auth/tesla/callback':
        raise OAuthError('RenderのTESLA_CLIENT_ID・TESLA_CLIENT_SECRET・TESLA_REDIRECT_URIを設定してください。')
    return c

def begin(ticket):
    if not device_auth.valid(ticket):raise OAuthError('iPhoneで所有者端末を登録してからログインしてください。')
    c=config();state=secrets.token_urlsafe(32);launch=secrets.token_urlsafe(32)
    with mutex:
        for k in list(pending):
            if pending[k]['expires']<time.time():del pending[k]
        if len(pending)>=100:raise OAuthError('認証要求が多すぎます。10分後に再試行してください。')
        pending[state]={'launch':launch,'cookie':secrets.token_urlsafe(32),'expires':time.time()+600,'ticket':ticket,'launched':False}
    return c['TESLA_REDIRECT_URI'].removesuffix('/callback')+'/launch?'+urlencode({'state':state,'launch':launch})

def launch(query):
    state=query.get('state',[''])[0];key=query.get('launch',[''])[0]
    with mutex:
        p=pending.get(state)
        if not p or p['expires']<time.time() or p['launched'] or not secrets.compare_digest(key,p['launch']) or not device_auth.valid(p['ticket']):raise OAuthError('認証開始リンクが無効です。アプリからやり直してください。')
        p['launched']=True;cookie=p['cookie']
    c=config()
    url='https://auth.tesla.com/oauth2/v3/authorize?'+urlencode({'client_id':c['TESLA_CLIENT_ID'],'redirect_uri':c['TESLA_REDIRECT_URI'],'response_type':'code','scope':'openid offline_access vehicle_cmds','state':state,'locale':'ja-JP'})
    return url,cookie

def exchange(fields):
    req=urllib.request.Request('https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token',data=urlencode(fields).encode(),headers={'Content-Type':'application/x-www-form-urlencoded'},method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=20) as r:result=json.loads(r.read(65536))
        if not isinstance(result.get('access_token'),str) or not result['access_token']:raise ValueError()
        seconds=int(result['expires_in'])
        if not 0<seconds<=86400:raise ValueError()
        return {'access':result['access_token'],'expires':time.time()+seconds,'refresh':result.get('refresh_token','')}
    except Exception:raise OAuthError('Teslaとの認証に失敗しました。設定を確認し、ログインをやり直してください。') from None

def callback(query,cookie_header):
    state=query.get('state',[''])[0];jar=SimpleCookie()
    try:jar.load(cookie_header)
    except Exception:raise OAuthError('認証Cookieが無効です。')
    cookie=jar.get('tesla_oauth')
    with mutex:
        p=pending.get(state)
        if not p or not p['launched'] or p['expires']<time.time() or not cookie or not secrets.compare_digest(cookie.value,p['cookie']) or not device_auth.valid(p['ticket']):raise OAuthError('認証が期限切れか、開始したブラウザと異なります。アプリからやり直してください。')
        del pending[state]
    if 'error' in query:raise OAuthError('Teslaログインがキャンセルされました。')
    code=query.get('code',[''])[0]
    if not code or len(code)>4096:raise OAuthError('認証コードがありません。アプリからログインを開始してください。')
    c=config();new=exchange({'grant_type':'authorization_code','client_id':c['TESLA_CLIENT_ID'],'client_secret':c['TESLA_CLIENT_SECRET'],'code':code,'redirect_uri':c['TESLA_REDIRECT_URI'],'audience':'https://fleet-api.prd.na.vn.cloud.tesla.com'})
    with mutex:tokens.clear();tokens.update(new,owner_secret=device_auth.secret())

def access_token():
    with mutex:
        if tokens.get('owner_secret')!=device_auth.secret():tokens.clear()
        return tokens.get('access','') if tokens.get('expires',0)>time.time()+30 else ''

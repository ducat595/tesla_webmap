"""One ordered waypoints command to a configured signing proxy. No automatic retries."""
import json, os, re, urllib.error, urllib.request
import tesla_oauth
from urllib.parse import urlsplit

class BridgeError(Exception):
    def __init__(self, code, message): self.code, self.message = code, message

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args): return None

def settings():
    s={k: os.getenv(k, '').strip() for k in ('TESLA_COMMAND_PROXY_URL','TESLA_ACCESS_TOKEN','TESLA_VIN','TESLA_OWNER_SECRET')}
    s['TESLA_ACCESS_TOKEN']=tesla_oauth.access_token() or s['TESLA_ACCESS_TOKEN']
    return s

def configuration_ready():
    s = settings()
    return bool(s['TESLA_COMMAND_PROXY_URL'] and s['TESLA_ACCESS_TOKEN'] and re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}',s['TESLA_VIN']) and len(s['TESLA_OWNER_SECRET']) >= 32)

def build_payload(stops):
    ids=[]
    for index, stop in enumerate(stops):
        place_id=stop.get('placeId','')
        if not isinstance(place_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{5,300}',place_id):
            raise BridgeError(400, f'{index+1}番目の地点にGoogle Place IDがありません。Google地図で検索し直すかPlace IDを入力してください。')
        ids.append('refId:'+place_id)
    return {'waypoints': ','.join(ids)}

def send_waypoints(stops):
    s=settings()
    if not configuration_ready(): raise BridgeError(503,'Tesla API未設定です。認証・署名プロキシ・所有者キーの設定が必要です。')
    u=urlsplit(s['TESLA_COMMAND_PROXY_URL'])
    local=u.hostname in ('localhost','127.0.0.1')
    if (u.scheme!='https' and not (u.scheme=='http' and local)) or u.username or u.password or u.query or u.fragment:
        raise BridgeError(503,'署名プロキシURLの設定が不正です。HTTPSの信頼できるプロキシを設定してください。')
    payload=build_payload(stops)
    url=s['TESLA_COMMAND_PROXY_URL'].rstrip('/')+'/api/1/vehicles/'+s['TESLA_VIN']+'/command/navigation_waypoints_request'
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+s['TESLA_ACCESS_TOKEN']},method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=35) as response:
            result=json.loads(response.read(65536))
    except urllib.error.HTTPError as e:
        if e.code in (401,403): raise BridgeError(502,'Teslaの認証・車両権限・仮想キーを確認してください。') from None
        raise BridgeError(502,'署名プロキシが送信を拒否しました（HTTP '+str(e.code)+'）。経由地コマンドへの対応と車両状態を確認してください。') from None
    except (OSError,ValueError):
        raise BridgeError(504,'Teslaへの送信結果を確認できません。車載ナビを確認してください。自動再送はしません。') from None
    r=result.get('response') if isinstance(result,dict) else None
    if not isinstance(r,dict) or r.get('result') is not True:
        raise BridgeError(502,'Teslaの受付成功を確認できません。車載ナビと署名プロキシの対応を確認してください。')
    return {'accepted': True,'stopCount':len(stops),'message':'Teslaが地点一覧を受け付けました。車載ナビで順序を確認してください。'}

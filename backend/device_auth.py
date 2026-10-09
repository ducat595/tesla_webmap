"""30-day signed owner-device tickets. Rotating owner secret revokes all tickets."""
import base64, hashlib, hmac, json, os, secrets, time
TTL=30*86400

def secret(): return os.getenv('TESLA_OWNER_SECRET','').strip()
def issue():
    key=secret()
    if len(key)<32: raise ValueError('所有者キーが未設定です')
    body=base64.urlsafe_b64encode(json.dumps({'expires':int(time.time())+TTL,'nonce':secrets.token_urlsafe(24)},separators=(',',':')).encode()).decode().rstrip('=')
    sig=hmac.new(key.encode(),body.encode(),hashlib.sha256).hexdigest()
    return body+'.'+sig

def valid(token):
    try:
        if not isinstance(token,str) or len(token)>1024 or len(secret())<32:return False
        body,sig=token.split('.')
        expected=hmac.new(secret().encode(),body.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,sig):return False
        payload=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
        return time.time()<payload['expires']<=time.time()+TTL+60
    except (ValueError,TypeError,KeyError):return False

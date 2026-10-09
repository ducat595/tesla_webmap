"""Ephemeral location relay. Python standard library only; one process."""
import json, math, os, secrets, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

sessions = {}
lock = threading.Lock()
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
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
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
            if not 0 <= length <= 4096: raise ValueError()
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
                sessions[code] = {'token': token, 'expires': now + TTL, 'location': None}
                return self.reply(201, {'code': code, 'token': token, 'expiresAt': now + TTL})
            parts = path.strip('/').split('/')
            if len(parts) != 2 or parts[0] != 'sessions':
                return self.reply(404, {'error': '見つかりません'})
            code = parts[1].upper()
            session = sessions.get(code)
            if not session: return self.reply(404, {'error': '接続コードが違うか、期限切れ・サーバー再起動です'})
            if self.command == 'GET':
                return self.reply(200, {'location': session['location'], 'expiresAt': session['expires']})
            auth = self.headers.get('Authorization', '')
            if not secrets.compare_digest(auth, 'Bearer ' + session['token']):
                return self.reply(403, {'error': '送信権限がありません'})
            if self.command == 'DELETE':
                del sessions[code]
                return self.reply(200, {'ok': True})
            if self.command == 'PUT':
                if not valid_location(payload): return self.reply(400, {'error': '位置情報が不正です'})
                session['location'] = {k: payload[k] for k in ('latitude', 'longitude', 'accuracy')}
                session['location']['receivedAt'] = now
                return self.reply(200, {'ok': True})
            return self.reply(405, {'error': '未対応の操作です'})

if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '8000'))), Handler).serve_forever()

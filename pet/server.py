"""Single-user loopback server, stdlib only. JSON replay saves, no pickle."""
import argparse
import copy
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import tempfile
import webbrowser
from .engine import Session

STATIC = Path(__file__).parent / 'static'

def save_atomic(path, session):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.pet-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(session.archive(), f, ensure_ascii=False, separators=(',',':'))
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def create_server(path, port=8765):
    path = Path(path)
    # Fail visibly on corruption; never silently reset or overwrite an old pet.
    if path.exists():
        if path.stat().st_size > 2_000_000:
            raise ValueError('存档过大')
        session = Session.restore(json.loads(path.read_text(encoding='utf-8')))
    else:
        session = Session()
        save_atomic(path, session)
    token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, data, mime='application/json; charset=utf-8', download=False):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'")
            if download:
                self.send_header('Content-Disposition', 'attachment; filename="lifeengine-save.json"')
            self.end_headers()
            self.wfile.write(body)

        def trusted(self):
            host = self.headers.get('Host','')
            valid = {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            return host in valid

        def do_GET(self):
            if not self.trusted():
                return self.reply(403, {'error':'仅允许本机访问'})
            if self.path == '/api/state':
                return self.reply(200, {'state':self.server.session.view(), 'token':token})
            if self.path == '/api/export':
                return self.reply(200,self.server.session.archive(),download=True)
            files = {'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
            if self.path not in files:
                return self.reply(404,{'error':'Not found'})
            filename, mime = files[self.path]
            self.reply(200,(STATIC/filename).read_bytes(),mime)

        def do_POST(self):
            if not self.trusted() or self.headers.get('X-Pet-Token') != token:
                return self.reply(403,{'error':'请刷新页面后重试'})
            if self.path not in ('/api/command','/api/import'):
                return self.reply(404,{'error':'Not found'})
            try:
                size = int(self.headers.get('Content-Length','0'))
                if not 0 < size <= 2_000_000:
                    raise ValueError('请求大小无效')
                data = json.loads(self.rfile.read(size))
                # Transaction: failed commands/saves leave the live pet untouched.
                if self.path == '/api/import':
                    candidate = Session.restore(data)
                    save_atomic(path.with_suffix('.before-import.json'), self.server.session)
                else:
                    candidate = copy.deepcopy(self.server.session)
                    candidate.apply(data)
                save_atomic(path, candidate)
                self.server.session = candidate
                self.reply(200, {'state':candidate.view(), 'token':token})
            except (ValueError, TypeError, KeyError) as exc:
                self.reply(400, {'error':str(exc)})
            except OSError:
                self.reply(500, {'error':'存档写入失败，操作未提交。请检查目录权限或磁盘空间。'})
    server = HTTPServer(('127.0.0.1',port),Handler)
    server.session = session
    return server

def main():
    parser = argparse.ArgumentParser(description='Life Engine local playable prototype')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--save',type=Path,default=Path(__file__).parent/'data'/'pet.json')
    parser.add_argument('--no-browser',action='store_true')
    args = parser.parse_args()
    try:
        server = create_server(args.save,args.port)
    except (OSError,ValueError) as exc:
        parser.exit(1, f'Cannot start / 无法启动: {exc}\nOriginal save is untouched. Try another --port or --save path.\n')
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'Life Engine: {url}\nSave / 存档: {args.save.resolve()}\nCtrl+C to stop. Closing the page pauses time.',flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

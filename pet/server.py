"""Single-user loopback server, stdlib only. JSON replay saves, no pickle."""
import argparse
import copy
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import tempfile
import time
import webbrowser
from .engine import LimitReached, Session

STATIC = Path(__file__).parent / 'static'
# Real time keeps passing while the page or server is closed. Longer absences
# are capped so a forgotten pet does not jump weeks ahead in one request.
AWAY_CAP_HOURS = 48

def save_atomic(path, session, last_seen=None):
    data = session.archive()
    if last_seen is not None:
        data['last_seen'] = last_seen
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.pet-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',',':'))
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def split_clock(data):
    """Separate the server's wall-clock stamp from the engine archive."""
    last_seen = data.pop('last_seen', None) if isinstance(data, dict) else None
    if type(last_seen) not in (int, float) or last_seen > time.time():
        last_seen = time.time()
    return data, last_seen

def hours_owed(last_seen, now, speed):
    """Whole game hours earned by real time since last_seen, and the new stamp.

    Leftover minutes stay on the clock, so frequent requests lose no time."""
    step = 3600 / speed
    hours = int(max(0, now - last_seen) // step)
    if hours > AWAY_CAP_HOURS:
        return AWAY_CAP_HOURS, now
    return hours, last_seen + hours * step

def catch_up(session, hours):
    """Advance owed time through normal commands, so replayed saves stay identical.

    Runs inside the caller's transaction. When the prototype's tick or command budget
    cannot cover all owed hours, the largest steps that still fit are applied (fewest
    commands) and the rest is reported as skipped: the pet stops at the limit, and the
    request never half-applies and then fails."""
    if hours <= 0:
        return None
    start_tick, first_event = session.tick, len(session.events)
    before = dict(session.agent.traits)
    left = hours
    for step in (24, 6, 1):
        while left >= step and session.limits()['commands_left'] > 0 and session.limits()['ticks_left'] >= step:
            session.apply({'kind':'advance','value':step})
            left -= step
    counts = {}
    new = session.events[first_event:]
    for e in new:
        if e['kind'] == 'action':
            counts[e['title']] = counts.get(e['title'], 0) + 1
    limits = session.limits()
    reason = None if not left else ('commands' if limits['commands_left'] == 0 else 'ticks')
    return {'hours': session.tick - start_tick, 'skipped_hours': left, 'limit': reason, 'counts': counts,
            'highlights': [{'id':e['id'],'title':e['title'],'text':e['text']} for e in new if e['kind'] != 'action'][-5:],
            'traits': {t: round(v - before[t], 1) for t, v in session.agent.traits.items()}}

def create_server(path, port=8765, speed=1.0):
    path = Path(path)
    # Fail visibly on corruption; never silently reset or overwrite an old pet.
    if path.exists():
        if path.stat().st_size > 2_000_000:
            raise ValueError('存档过大')
        data, last_seen = split_clock(json.loads(path.read_text(encoding='utf-8')))
        session = Session.restore(data)
    else:
        session, last_seen = Session(), time.time()
        save_atomic(path, session, last_seen)
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

        def commit(self, command=None):
            """Catch up on real time, then apply an optional command, as one transaction."""
            hours, last_seen = hours_owed(self.server.last_seen, time.time(), speed)
            if not hours and command is None:
                return None
            candidate = copy.deepcopy(self.server.session)
            away = catch_up(candidate, hours)
            if command is not None:
                candidate.apply(command)
            save_atomic(path, candidate, last_seen)
            self.server.session, self.server.last_seen = candidate, last_seen
            return away

        def answer(self, away, status=200, error=None):
            data = {'state':self.server.session.view(), 'token':token, 'away':away}
            if error:
                data.update(error=error, limit=True)
            self.reply(status, data)

        def do_GET(self):
            if not self.trusted():
                return self.reply(403, {'error':'仅允许本机访问'})
            if self.path == '/api/state':
                try:
                    return self.answer(self.commit())
                except LimitReached as exc:
                    # catch_up stops at the limits, so this is only a safety net; the
                    # committed pet is untouched and still viewable/exportable.
                    return self.answer(None, 409, str(exc))
                except OSError:
                    return self.reply(500, {'error':'存档写入失败，操作未提交。请检查目录权限或磁盘空间。'})
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
                    candidate = Session.restore(split_clock(data)[0])
                    save_atomic(path.with_suffix('.before-import.json'), self.server.session, self.server.last_seen)
                    # An imported pet starts its real-time clock now.
                    last_seen = time.time()
                    save_atomic(path, candidate, last_seen)
                    self.server.session, self.server.last_seen = candidate, last_seen
                    away = None
                else:
                    away = self.commit(data)
                self.answer(away)
            except LimitReached as exc:
                self.answer(None, 409, str(exc))
            except (ValueError, TypeError, KeyError) as exc:
                self.reply(400, {'error':str(exc)})
            except OSError:
                self.reply(500, {'error':'存档写入失败，操作未提交。请检查目录权限或磁盘空间。'})
    server = HTTPServer(('127.0.0.1',port),Handler)
    server.session, server.last_seen = session, last_seen
    return server

def main():
    parser = argparse.ArgumentParser(description='Life Engine local playable prototype')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--save',type=Path,default=Path(__file__).parent/'data'/'pet.json')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--speed',type=float,default=1.0,help='game hours per real hour while away (default 1)')
    args = parser.parse_args()
    if not args.speed > 0:
        parser.exit(1, '--speed must be > 0\n')
    try:
        server = create_server(args.save,args.port,args.speed)
    except (OSError,ValueError) as exc:
        parser.exit(1, f'Cannot start / 无法启动: {exc}\nOriginal save is untouched. Try another --port or --save path.\n')
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'Life Engine: {url}\nSave / 存档: {args.save.resolve()}\nCtrl+C to stop. Real time keeps passing for the pet, even when closed.',flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

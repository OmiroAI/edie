"""Bearer-authenticated management API; never executes caller-provided commands."""
import hmac
import json
import os
import shutil
from http.server import BaseHTTPRequestHandler, HTTPServer
from .core import Store, source
from .tasks import Tasks


def handler(root, token):
    if len(token) < 32:
        raise ValueError('EDIE_API_TOKEN must contain at least 32 characters')

    class API(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Request paths and bodies may contain private editorial context.

        def respond(self, code, payload):
            body = json.dumps(payload, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def dispatch(self):
            self.connection.settimeout(10)
            if not hmac.compare_digest(self.headers.get('Authorization', '').encode(), ('Bearer '+token).encode()):
                return self.respond(401, {'error': 'Unauthorised'})
            store = Store(root)
            try:
                tasks = Tasks(store.db)
                path = self.path.strip('/').split('/')
                if self.command == 'GET':
                    if path == ['health']:
                        return self.respond(200, {'status': 'ok'})
                    if len(path) == 3 and path[0] == 'tasks' and path[2] == 'artifact':
                        task = tasks.get(path[1])
                        if task['state'] != 'completed' or not task['result']:
                            raise ValueError('No completed artifact')
                        artifact = source(store.root, task['result']['path'])
                        self.send_response(200)
                        self.send_header('Content-Type', 'video/mp4')
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('Content-Length', str(artifact.stat().st_size))
                        self.end_headers()
                        with artifact.open('rb') as stream:
                            shutil.copyfileobj(stream, self.wfile)
                        return
                    if len(path) == 2 and path[0] == 'tasks':
                        return self.respond(200, tasks.get(path[1]))
                    kinds = {'jobs': 'job', 'revisions': 'revision'}
                    if len(path) == 2 and path[0] in kinds:
                        return self.respond(200, store.get(path[1], kinds[path[0]]))
                    if len(path) == 1 and path[0] in kinds:
                        rows = store.db.execute('SELECT id,body FROM records WHERE kind=?', (kinds[path[0]],)).fetchall()
                        return self.respond(200, [{'id': r[0], **json.loads(r[1])} for r in rows])
                elif self.command == 'POST':
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 1024*1024:
                        return self.respond(413, {'error': 'Body required; maximum 1 MiB'})
                    body = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite number')))
                    if not isinstance(body, dict):
                        raise ValueError('Object body required')
                    if path == ['jobs']:
                        if 'project' in body:
                            raise ValueError('Projects are not supported')
                        identifier = store.job(body['brief'])
                    elif path == ['revisions']:
                        identifier = store.revision(body['job'], body['clips'])
                    elif path == ['feedback']:
                        identifier = store.feedback(body['job'], body['revision'], body['text'], body['timestamp'])
                    elif path == ['approvals']:
                        identifier = store.approve(body['job'], body['revision'])
                    elif path == ['tasks']:
                        revision = store.get(body['revision'], 'revision')
                        if revision['job'] != body['job']:
                            raise ValueError('Revision belongs to another job')
                        identifier = tasks.submit(body['job'], self.headers.get('Idempotency-Key', ''), {'action': 'render', 'revision': body['revision']})
                    elif len(path) == 3 and path[0] == 'tasks':
                        return self.respond(200, tasks.control(path[1], path[2]))
                    else:
                        return self.respond(404, {'error': 'Route not found'})
                    return self.respond(201, {'id': identifier})
                return self.respond(404, {'error': 'Route not found'})
            except (ValueError, KeyError, TypeError, OverflowError):
                return self.respond(400, {'error': 'Invalid request or state conflict'})
            finally:
                store.db.close()

        do_GET = dispatch
        do_POST = dispatch
    return API


def main():
    server = HTTPServer((os.getenv('EDIE_BIND', '127.0.0.1'), int(os.getenv('EDIE_PORT', '8080'))),
                        handler(os.getenv('EDIE_STATE', 'state'), os.getenv('EDIE_API_TOKEN', '')))
    server.serve_forever()


if __name__ == '__main__':
    main()

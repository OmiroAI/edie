"""Bearer-authenticated management API; never executes caller-provided commands."""
import hmac
import json
import os
import shutil
import threading
from pathlib import Path
from .workflow import Workflow, identity
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .core import Store, source, digest
from .tasks import Tasks
from .index import Catalogue


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

        def media(self, artifact):
            # Single byte ranges allow authenticated clients to request bounded segments.
            size=artifact.stat().st_size; start=0; end=size-1; status=200
            requested=self.headers.get('Range')
            if requested:
                import re
                match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
                if not match or not any(match.groups()):
                    self.send_response(416); self.send_header('Content-Range',f'bytes */{size}'); self.send_header('Content-Length','0'); self.end_headers(); return
                left,right=match.groups()
                if left:start=int(left); end=min(int(right),end) if right else end
                else:start=max(0,size-int(right))
                if start>end or start>=size:
                    self.send_response(416); self.send_header('Content-Range',f'bytes */{size}'); self.send_header('Content-Length','0'); self.end_headers(); return
                status=206
            self.send_response(status); self.send_header('Content-Type','video/mp4');self.send_header('Cache-Control','no-store')
            self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1))
            if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            with artifact.open('rb') as stream:
                stream.seek(start);remaining=end-start+1
                while remaining:
                    block=stream.read(min(262144,remaining))
                    if not block:break
                    self.wfile.write(block);remaining-=len(block)

        def dispatch(self):
            self.connection.settimeout(10)
            if self.command == 'GET' and self.path == '/dashboard':
                page = Path(__file__).with_name('dashboard.html').read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
                self.send_header('Content-Length', str(len(page)))
                self.end_headers(); self.wfile.write(page); return
            if not hmac.compare_digest(self.headers.get('Authorization', '').encode(), ('Bearer '+token).encode()):
                return self.respond(401, {'error': 'Unauthorised'})
            store = Store(root)
            try:
                tasks = Tasks(store.db)
                path = self.path.strip('/').split('/')
                if self.command == 'GET':
                    if path == ['workspaces']:
                        return self.respond(200,json.loads(os.getenv('EDIE_REVIEW_WORKSPACES','[{"label":"Edie","prefix":""}]')))
                    if len(path)==3 and path[0]=='jobs' and path[2]=='footage':
                        from .editorial import footage
                        store.get(path[1],'job')
                        return self.respond(200,footage(store,path[1]))
                    if len(path)==3 and path[0]=='jobs' and path[2]=='tasks':
                        store.get(path[1],'job')
                        return self.respond(200,[tasks.get(r[0]) for r in store.db.execute('SELECT id FROM tasks WHERE job=? ORDER BY rowid DESC',(path[1],)).fetchall()])
                    if path == ['sources']:

                        return self.respond(200, Catalogue(store).list())
                    if path == ['health']:
                        return self.respond(200, {'status': 'ok'})
                    if len(path) == 3 and path[0] == 'tasks' and path[2] == 'artifact':
                        task = tasks.get(path[1])
                        if task['state'] != 'completed' or not task['result'] or task['result'].get('kind') not in ('reference_preview','source_preview'):
                            raise ValueError('No completed artifact')
                        return self.media(source(store.root, task['result']['path']))
                    if len(path) == 2 and path[0] == 'tasks':
                        return self.respond(200, tasks.get(path[1]))
                    if len(path) >= 4 and path[0] == 'jobs' and path[2] == 'delivery':
                        from urllib.parse import unquote, quote
                        import mimetypes
                        state = Workflow(store).get(path[1])
                        if not state['delivery']:raise ValueError('No delivery candidate')
                        folder = store.root/state['delivery']['path']
                        manifest_path = source(folder, 'manifest.json')
                        if digest(manifest_path) != state['delivery']['manifest_hash']:raise ValueError('Package manifest changed')
                        manifest = json.loads(manifest_path.read_text())
                        if path[3:] == ['manifest']:
                            return self.respond(200, manifest)
                        if path[3] != 'files' or len(path) < 5:raise ValueError('Invalid artifact route')
                        relative = unquote('/'.join(path[4:]))
                        item = next((f for f in manifest['files'] if f['path'] == relative), None)
                        if not item:raise ValueError('Artifact not in manifest')
                        artifact = source(folder, relative)
                        if digest(artifact) != item['sha256']:raise ValueError('Artifact changed')
                        self.send_response(200)
                        self.send_header('Content-Type', mimetypes.guess_type(artifact.name)[0] or 'application/octet-stream')
                        self.send_header('Content-Disposition', "attachment; filename*=UTF-8''"+quote(artifact.name))
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('Content-Length', str(artifact.stat().st_size))
                        self.end_headers()
                        with artifact.open('rb') as stream:shutil.copyfileobj(stream, self.wfile)
                        return
                    if len(path) == 3 and path[0] == 'jobs' and path[2] == 'usage':
                        from .usage import summary
                        state=Workflow(store).get(path[1])
                        review=(state.get('validation') or {}).get('visual_review') or {}
                        return self.respond(200,{'decisions':summary(state['usage']),'render_review':summary([review['usage']]) if review.get('usage') else None,'shared_indexing':'See deployment source index usage; it is reusable and not charged again per story','subscription_allocation_cost':'unknown','metered_routes':'disabled'})
                    if len(path) == 3 and path[0] == 'jobs' and path[2] == 'workflow':
                        state = Workflow(store).get(path[1])
                        from .usage import summary
                        state['usage_summary'] = summary(state['usage'])
                        from .classification import review_state
                        state['footage_review']=review_state(store,path[1])
                        state['footage_review']['confirmed']=state.get('footage_confirmation')==state['footage_review']['candidate']

                        proposals=list(state.get('script_proposals',[]))
                        if state.get('script') and not any(identity(p)==identity(state['script']) for p in proposals):proposals.append(state['script'])
                        state['script_proposals']=proposals
                        state['script_proposal_hashes']=[identity(p) for p in proposals]
                        state['candidate_hashes'] = {scope: identity(state[field]) if state[field] else None for scope, field in [('script','script'),('main','revision'),('final','delivery')]}
                        return self.respond(200, state)
                    if len(path) == 3 and path[0] == 'jobs' and path[2] == 'events':
                        Workflow(store)
                        rows = store.db.execute('SELECT body FROM events WHERE job=? ORDER BY rowid', (path[1],)).fetchall()
                        return self.respond(200, [json.loads(row[0]) for row in rows])
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
                    if len(path)==5 and path[0]=='jobs' and path[2]=='sources' and path[4]=='classification':
                        from .editorial import indexes
                        from .classification import Classifications
                        from urllib.parse import unquote
                        entry=indexes(store,path[1])[unquote(path[3])]['source']
                        if body['source_version']!=entry['version'] or body['source_sha256']!=entry['sha256']:raise ValueError('Source version changed')
                        value=None if body.get('reset') is True else dict(labels=body['labels'],reason=body['reason'],origin='human')
                        return self.respond(200,Classifications(store).save(path[1],entry,value,body['expected_revision'],human=True,actor='dashboard-operator'))
                    if len(path)==5 and path[0]=='jobs' and path[2]=='sources' and path[4]=='proxy':
                        from .editorial import request_proxy
                        from urllib.parse import unquote
                        return self.respond(202,request_proxy(store,path[1],unquote(path[3])))
                    if len(path) == 3 and path[0] == 'jobs' and path[2] == 'run':
                        flow = Workflow(store); state = flow.start(path[1])
                        return self.respond(202, flow.update(path[1], body['expected_state_version'], {'requested_run': True}))
                    if len(path) == 3 and path[0] == 'jobs' and path[2] == 'events':
                        return self.respond(201, Workflow(store).event(path[1], body['event_id'], body['expected_state_version'], body['type'], body['payload'], body['actor']))
                    if path == ['sources']:
                        return self.respond(201, Catalogue(store).ingest(body['sources'], os.getenv('EDIE_MEDIA','/media')))
                    if path == ['index-tasks']:
                        store.get(body['job'],'job')
                        if not isinstance(body['sources'],list) or not 1 <= len(body['sources']) <= 500:raise ValueError('Bounded source list required')
                        catalogue=Catalogue(store)
                        for ref in body['sources']:catalogue.get(ref['source_id'],ref['version'])
                        identifier=tasks.submit(body['job'],self.headers.get('Idempotency-Key',''),{'action':'index','sources':body['sources']})
                        flow=Workflow(store);state=flow.start(body['job'])
                        pending=list(dict.fromkeys(state.get('pending_index_tasks',[])+[identifier]))
                        flow.update(body['job'],state['version'],{'pending_index_tasks':pending})
                        return self.respond(201,{'id':identifier})
                    if path == ['jobs']:
                        if 'project' in body:
                            raise ValueError('Projects are not supported')
                        identifier = store.job(body['brief'])
                    elif path == ['subtitle-revisions']:
                        from .subtitles import revise
                        flow=Workflow(store);state=flow.get(body['job'])
                        if state['version']!=body['expected_state_version'] or state['revision']!=body['revision']:raise ValueError('Stale subtitle revision')
                        identifier=revise(store,body['revision'],body['language'],body['edits'],author='human')
                        flow.update(body['job'],state['version'],{'revision':identifier,'validation':None,'delivery':None,'stage':'editing','requested_run':True,'approvals':{k:v for k,v in state['approvals'].items() if k=='script'}})
                    elif path == ['derivatives']:
                        identifier = store.derivative(body['parent_job'], body['brief'])
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



class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self,*args,**kwargs):
        self.slots=threading.BoundedSemaphore(32)
        super().__init__(*args,**kwargs)

    def get_request(self):
        connection,address=super().get_request()
        connection.settimeout(10)
        return connection,address

    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request);return
        try:super().process_request(request,address)
        except Exception:
            self.slots.release();raise

    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()


def main():
    server = Server((os.getenv('EDIE_BIND', '127.0.0.1'), int(os.getenv('EDIE_PORT', '8080'))),
                        handler(os.getenv('EDIE_STATE', 'state'), os.getenv('EDIE_API_TOKEN', '')))
    server.serve_forever()


if __name__ == '__main__':
    main()

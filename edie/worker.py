"""Render worker with leases and process-group cancellation; no model credentials."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from .core import Store, digest, render
from .tasks import Tasks


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def run_once(root, media, action="render", routes=None, classification_socket=None):
    store = Store(root)
    tasks = Tasks(store.db)
    owner = uuid.uuid4().hex
    task = tasks.claim(owner, action=action)
    if task is None:
        store.db.close()
        return False
    process = None
    try:
        payload = task['payload']
        attempt = uuid.uuid4().hex
        if action == 'render':
            revision = store.get(payload['revision'], 'revision')
            if payload['action'] != 'render' or revision['job'] != task['job']:
                raise ValueError('Invalid task payload')
            command = [sys.executable, '-m', 'edie.worker', '--state', str(store.root),
                       '--media', str(Path(media).resolve()), '--render', payload['revision'], '--attempt', attempt]
        elif action in ('sync_index','sync_preview','sync_waveform'):
            command=[sys.executable,'-m','edie.capture','--state',str(store.root),'--task',task['id']]
        elif action == 'review_proxy':
            store.get(task['job'], 'job')
            command = [sys.executable, '-m', 'edie.editorial', '--state', str(store.root),
                       '--media', str(Path(media).resolve()), '--task', task['id']]
        elif action == 'segment_index' and classification_socket:
            store.get(task['job'], 'job')
            command = [sys.executable, '-m', 'edie.segments', '--state', str(store.root), '--socket', classification_socket, '--task', task['id']]
        elif action in ('index','visual_index') and routes:
            store.get(task['job'], 'job')
            command = [sys.executable, '-m', 'edie.index_worker', '--state', str(store.root),
                       '--media', str(Path(media).resolve()), '--routes', str(Path(routes).resolve()), '--task', task['id']]
        else:
            raise ValueError('Unsupported worker capability')
        # No raw FFmpeg output is retained; it may include private source names.
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(command, stdout=output, stderr=subprocess.DEVNULL,
                                       start_new_session=True, env={k: v for k, v in os.environ.items() if k in ('PATH', 'LANG', 'PYTHONPATH', 'EDIE_CONFIG_DIR')})
            while True:
                state = tasks.heartbeat(task['id'], owner)
                if state in ('pause_requested', 'cancel_requested'):
                    stop(process)
                    tasks.stopped(task['id'], owner, 'paused' if state == 'pause_requested' else 'cancelled')
                    return True
                if process.poll() is not None:
                    break
                time.sleep(0.5)
            if process.returncode:
                code=action+'_failed'
                if action=='segment_index':
                    from .failures import SAFE_CODES
                    output.seek(0)
                    try:
                        diagnostic=json.loads(output.read(4096))
                        if isinstance(diagnostic,dict) and diagnostic.get('error') in SAFE_CODES:code=diagnostic['error']
                    except (ValueError,TypeError):pass
                tasks.stopped(task['id'], owner, 'failed', {'error': code})
                return True
            output.seek(0)
            artifact = json.loads(output.read(1024*1024))
            # Only a live owner can publish the already validated artifact.
            tasks.finish(task['id'], owner, artifact)
    except Exception:
        if process is not None:
            stop(process)
        try:
            state = tasks.get(task['id'])['state']
            stopped = {'pause_requested': 'paused', 'cancel_requested': 'cancelled'}.get(state, 'failed')
            tasks.stopped(task['id'], owner, stopped, {'error': 'worker_failed'} if stopped == 'failed' else None)
        except ValueError:
            pass  # Lost lease or a concurrent control request: never overwrite it.
    finally:
        if process is not None:
            stop(process)
        store.db.close()
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', default=os.getenv('EDIE_STATE', 'state'))
    parser.add_argument('--media', default=os.getenv('EDIE_MEDIA', '/media'))
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--render')
    parser.add_argument('--attempt')
    args = parser.parse_args()
    if args.render:
        store = Store(args.state)
        try:
            path = Path(render(store, args.render, args.media, args.attempt))
            print(json.dumps({'revision': args.render, 'path': str(path.relative_to(store.root)),
                              'sha256': digest(path), 'bytes': path.stat().st_size, 'kind': 'reference_preview'}))
        finally:
            store.db.close()
        return
    while True:
        worked = run_once(args.state, args.media)
        if args.once:
            return
        if not worked:
            time.sleep(2)


if __name__ == '__main__':
    main()

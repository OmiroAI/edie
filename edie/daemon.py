"""Wake agent turns on explicit requests or completed render tasks."""
import argparse
import json
from pathlib import Path
import time
from .agent import Agent
from .codex import CodexSocket
from .core import Store
from .workflow import Workflow
from .tasks import Tasks


def tick(root,config,media,socket,routes=None):
    store=Store(root,config);flow=Workflow(store);tasks=Tasks(store.db)
    try:
        for job, in store.db.execute('SELECT job FROM workflows').fetchall():
            state=flow.get(job)
            ready=state.get('requested_run',False)
            if state['stage']=='rendering' and state.get('pending_task'):
                ready=tasks.get(state['pending_task'])['state']=='completed'
            if not ready or state['control']!='active':continue
            try:
                Agent(store,media,CodexSocket(socket),routes).run(job)
                after=flow.get(job)
                flow.update(job,after['version'],dict(requested_run=False))
            except BlockingIOError:continue
            except Exception as error:
                after=flow.get(job)
                flow.update(job,after['version'],dict(requested_run=False,last_failure=type(error).__name__,stage='blocked'))
    finally:store.db.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--state',required=True);p.add_argument('--config',required=True);p.add_argument('--media',required=True);p.add_argument('--socket',required=True);p.add_argument('--routes',required=True);p.add_argument('--once',action='store_true');a=p.parse_args()
    routes=json.loads(Path(a.routes).read_text())
    while True:
        tick(a.state,a.config,a.media,a.socket,routes)
        if a.once:return
        time.sleep(2)

if __name__=='__main__':main()

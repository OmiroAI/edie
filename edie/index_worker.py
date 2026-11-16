"""Queued indexing with the same lease, cancellation and recovery as rendering."""
import argparse
import json
from pathlib import Path
import time
from .core import Store
from .index import Catalogue
from .analysis import analyse
from .tasks import Tasks
from .worker import run_once


def main():
    p=argparse.ArgumentParser();p.add_argument('--state',required=True);p.add_argument('--media',required=True);p.add_argument('--routes',required=True);p.add_argument('--task');p.add_argument('--once',action='store_true');a=p.parse_args()
    if a.task:
        import os
        store=Store(a.state);task=Tasks(store.db).get(a.task)
        os.environ['EDIE_USAGE_FILE']=str(store.root/'usage.jsonl')
        routes=json.loads(Path(a.routes).read_text());catalogue=Catalogue(store)
        results=[]
        previous={}
        if task['payload']['action']=='visual_index':
            from .editorial import indexes
            previous=indexes(store,task['job'])
        for reference in task['payload']['sources']:
            entry=catalogue.get(reference['source_id'],reference['version'])
            if task['payload']['action']=='visual_index':
                from .adaptive import upgrade
                prior=previous[entry['source_id']]
                if prior['source']['version']!=entry['version'] or prior['source']['sha256']!=entry['sha256']:raise ValueError('Prior transcript source version mismatch')
                result=upgrade(store,prior,a.media,routes['vision'])
            else:result=analyse(store,entry,a.media,routes)
            results.append(dict(source_id=entry['source_id'],version=entry['version'],sha256=entry['sha256'],segments=len(result['transcript']),visual_samples=sum(len(v['sampled_times']) for v in result['visual'])))
        print(json.dumps(dict(kind='footage_index',sources=results)));store.db.close();return
    while True:
        worked=run_once(a.state,a.media,'visual_index',a.routes) or run_once(a.state,a.media,'index',a.routes)
        if a.once:return
        if not worked:time.sleep(2)

if __name__=='__main__':main()

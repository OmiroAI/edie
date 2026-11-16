"""Versioned editorial ranges. Originals and source-level overrides remain untouched."""
import copy
import json
import math
import uuid
from .workflow import identity
from .classification import LABELS


def propose(index):
    """Conservative boundaries at speech pauses/scenes, never inside valid speech."""
    duration=index['duration'];speech=[c for c in index['transcript'] if c.get('timing_valid',True) and 0<=c['start']<c['end']<=duration]
    candidates=[c['end'] for i,c in enumerate(speech[:-1]) if speech[i+1]['start']-c['end']>=0.4]
    candidates += [c['seconds'] for c in index.get('cut_candidates',[]) if c.get('kind')=='scene_change']
    # Sentence ends are useful fallbacks for continuous dialogue, without fixed-time cuts.
    candidates += [c['end'] for c in speech if c['text'].rstrip().endswith(('.', '?', '!'))]
    cuts=[0.0]
    for t in sorted(set(candidates)):
        if t-cuts[-1]<6 or duration-t<3 or any(c['start']<t<c['end'] for c in speech):continue
        cuts.append(float(t))
    cuts.append(float(duration))
    return [dict(id=identity([index['source']['source_id'],index['source']['version'],a,b])[:24],start=a,end=b,
                 title=' '.join(c['text'] for c in speech if c['start']<b and c['end']>a)[:120] or 'Visual sequence',
                 labels=['needs_review'],score=0,reason='Suggested boundary; review the complete thought or action.',origin='boundary_proposal')
            for a,b in zip(cuts,cuts[1:])]


class Segments:
    def __init__(self,store):
        self.store=store;self.db=store.db
        self.db.execute('CREATE TABLE IF NOT EXISTS segments(job TEXT, source_key TEXT, revision INTEGER, body TEXT, PRIMARY KEY(job,source_key))')
        self.db.execute('CREATE TABLE IF NOT EXISTS segment_events(id INTEGER PRIMARY KEY, job TEXT, source_key TEXT, revision INTEGER, body TEXT)')

    def key(self,entry):return identity([entry['source_id'],entry['version'],entry['sha256']])

    def get(self,job,entry):
        row=self.db.execute('SELECT revision,body FROM segments WHERE job=? AND source_key=?',(job,self.key(entry))).fetchone()
        return dict(revision=row[0],**json.loads(row[1])) if row else dict(revision=0,items=[],human=False)

    def save(self,job,index,items,expected,human=True):
        if not isinstance(expected,int) or isinstance(expected,bool):raise ValueError('Segment revision required')
        if not isinstance(items,list) or not 1<=len(items)<=2000:raise ValueError('Invalid segment count')
        last=0;ids=set()
        for item in items:
            a,b=item['start'],item['end']
            if any(isinstance(t,bool) or not isinstance(t,(int,float)) or not math.isfinite(t) for t in (a,b)) or not 0<=a<b<=index['duration'] or abs(a-last)>0.001:raise ValueError('Segments must partition the source without gaps or overlaps')
            if not isinstance(item['id'],str) or not item['id'] or item['id'] in ids:raise ValueError('Unique segment IDs required')
            if not isinstance(item['labels'],list) or len(set(item['labels']))!=len(item['labels']) or any(x not in LABELS for x in item['labels']) or {'star','throw_away'}<=set(item['labels']):raise ValueError('Invalid segment labels')
            if not isinstance(item['score'],int) or isinstance(item['score'],bool) or not 0<=item['score']<=100:raise ValueError('Invalid segment score')
            if any(not isinstance(item[k],str) or not item[k].strip() or len(item[k])>4000 for k in ('reason','title')):raise ValueError('Segment title and reason required')
            ids.add(item['id']);last=b
        if abs(last-index['duration'])>0.001:raise ValueError('Segments must cover the full source')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old=self.get(job,index['source'])
            if old['revision']!=expected:raise ValueError('Stale segment review; refresh first')
            if not human and old['human']:raise ValueError('Human segment edits must be preserved')
            body=json.dumps(dict(items=items,human=human),allow_nan=False);key=self.key(index['source'])
            self.db.execute('INSERT OR REPLACE INTO segments VALUES (?,?,?,?)',(job,key,expected+1,body))
            self.db.execute('INSERT INTO segment_events(job,source_key,revision,body) VALUES (?,?,?,?)',(job,key,expected+1,body))
        return self.get(job,index['source'])

    def edit(self,job,index,body):
        current=self.get(job,index['source']);items=copy.deepcopy(current['items'])
        if current['revision']!=body['expected_revision']:raise ValueError('Stale segment review')
        n=next((n for n,s in enumerate(items) if s['id']==body['segment_id']),None)
        if n is None:raise ValueError('Unknown segment')
        item=items[n];action=body['action']
        if action=='label':
            item.update(labels=body['labels'],reason=body['reason'],origin='human')
        elif action=='split':
            t=body['seconds']
            if isinstance(t,bool) or not isinstance(t,(int,float)) or not item['start']<t<item['end']:raise ValueError('Split must be inside segment')
            left={**item,'end':t,'id':uuid.uuid4().hex,'origin':'human'};right={**item,'start':t,'id':uuid.uuid4().hex,'origin':'human'}
            items[n:n+1]=[left,right]
        elif action=='merge_next':
            if n+1==len(items):raise ValueError('No adjacent segment')
            other=items[n+1]
            items[n:n+2]=[{**item,'id':uuid.uuid4().hex,'end':other['end'],'labels':['needs_review'],'score':0,'reason':'Merged by editor; review labels.','origin':'human'}]
        elif action=='boundary':
            if n+1==len(items):raise ValueError('No following boundary')
            t=body['seconds']
            if isinstance(t,bool) or not isinstance(t,(int,float)) or not item['start']<t<items[n+1]['end']:raise ValueError('Invalid boundary')
            item['end']=t;items[n+1]['start']=t
            for s in (item,items[n+1]):s.update(labels=['needs_review'],reason='Boundary adjusted; review labels.',origin='human')
        else:raise ValueError('Unknown segment action')
        return self.save(job,index,items,body['expected_revision'])


def allowed(store,job,index,begin,end):
    items=Segments(store).get(job,index['source'])['items']
    return not any('throw_away' in s['labels'] and s['start']<end and s['end']>begin for s in items)


def generate(store,job,decider):
    from .editorial import indexes
    from .classification import PROMPT,SCHEMA
    from .usage import record
    from jsonschema import validate
    repo=Segments(store);count=0
    for index in indexes(store,job).values():
        old=repo.get(job,index['source'])
        if old['items']:continue  # Restart safe; never replace a reviewed source partition.
        items=propose(index)
        for offset in range(0,len(items),4):
            batch=items[offset:offset+4];sources=[]
            for s in batch:
                cues=[c for c in index['transcript'] if c['start']<s['end'] and c['end']>s['start']]
                visual=[v for v in index['visual'] if any(s['start']<=t<s['end'] for t in v.get('sampled_times',[]))]
                sources.append(dict(source_id=s['id'],start=s['start'],end=s['end'],transcript=[{k:c[k] for k in ('start','end','text')} for c in cues][:60],visual=visual[:24]))
            context=store.job_context(job) if store.context and store.get(job,'job').get('context') else {}
            prompt=PROMPT+'\nEach source here is one editorial segment. Judge only its supplied time range. Do not invent finer boundaries.\n'+json.dumps(dict(brief=store.get(job,'job')['brief'],private_style_context=str(context)[:14000],sources=sources))
            result,usage=decider.decide(prompt,SCHEMA);record(store.root/'usage.jsonl',dict(stage='segment_classification',job=job,**usage));validate(result,SCHEMA)
            if sorted(c['source_id'] for c in result['clips'])!=sorted(s['id'] for s in batch):raise ValueError('Segment response mismatch')
            by_id={c['source_id']:c for c in result['clips']}
            for s in batch:
                c=by_id[s['id']];s.update(labels=c['labels'],score=c['score'],reason=c['reason'],origin='agent')
        try:repo.save(job,index,items,old['revision'],human=False)
        except ValueError:
            if not repo.get(job,index['source'])['human']:raise
        count+=len(items)
    return dict(kind='segment_index',new_segments=count)


def main():
    import argparse,time
    from .core import Store
    from .tasks import Tasks
    p=argparse.ArgumentParser();p.add_argument('--state',required=True);p.add_argument('--media',default='/media');p.add_argument('--socket',required=True);p.add_argument('--task');p.add_argument('--once',action='store_true');a=p.parse_args()
    if a.task:
        from .codex import CodexSocket
        store=Store(a.state);task=Tasks(store.db).get(a.task)
        # Wait for source evidence, with lease/cancellation managed by parent worker.
        while any(t['state'] in ('queued','running','pause_requested','paused','interrupted','failed') for t in [Tasks(store.db).get(r[0]) for r in store.db.execute('SELECT id FROM tasks WHERE job=?',(task['job'],)).fetchall()] if t['payload'].get('action') in ('index','visual_index')):time.sleep(10)
        from .editorial import indexes
        current=indexes(store,task['job'])
        for ref in task['payload'].get('sources',[]):
            if ref['source_id'] not in current or any(current[ref['source_id']]['source'][k]!=ref[k] for k in ('version','sha256')):raise ValueError('Queued segment source changed')
        print(json.dumps(generate(store,task['job'],CodexSocket(a.socket))));return
    from .worker import run_once
    while True:
        worked=run_once(a.state,a.media,'segment_index',classification_socket=a.socket)
        if a.once:return
        if not worked:time.sleep(2)

if __name__=='__main__':main()

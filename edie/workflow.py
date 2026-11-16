"""Coordinator-owned lifecycle, event deduplication and exact-candidate approvals."""
import hashlib
import json
import time
import uuid
from .context import canonical


def identity(value):return hashlib.sha256(canonical(value)).hexdigest()


class Workflow:
    def __init__(self,store):
        self.store=store;self.db=store.db
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS workflows(job TEXT PRIMARY KEY, version INTEGER NOT NULL, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,job TEXT NOT NULL,input_hash TEXT NOT NULL,body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS invocations(job TEXT,request_key TEXT,input_hash TEXT,state TEXT,result TEXT,PRIMARY KEY(job,request_key));
        ''')

    def start(self,job,limits=None):
        self.store.get(job,'job')
        body=dict(stage='indexing',requested_run=False,run_id=uuid.uuid4().hex,plan=[],script=None,revision=None,delivery=None,
                  approvals={},accepted_master=None,accepted_revision=None,feedback=[],turns=0,usage=[],limits=limits or dict(turns=30,cost_micro_usd=20000000),control='active')
        with self.db:self.db.execute('INSERT OR IGNORE INTO workflows VALUES (?,0,?)',(job,json.dumps(body)))
        return self.get(job)

    def get(self,job):
        row=self.db.execute('SELECT version,body FROM workflows WHERE job=?',(job,)).fetchone()
        if not row:raise ValueError('Workflow not found')
        return dict(job=job,version=row[0],**json.loads(row[1]))

    def update(self,job,expected,changes):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            current=self.get(job)
            if current['version']!=expected:raise ValueError('Stale workflow state')
            current.pop('job');current.pop('version');current.update(changes)
            self.db.execute('UPDATE workflows SET version=version+1,body=? WHERE job=?',(json.dumps(current),job))
        return self.get(job)

    def event(self,job,event_id,expected,kind,payload,actor="operator-cli"):
        if not isinstance(expected,int) or isinstance(expected,bool) or expected<0:raise ValueError('Invalid state version')
        if not isinstance(event_id,str) or not 1<=len(event_id)<=200:raise ValueError('Event ID required')
        if not isinstance(payload,dict):raise ValueError('Event payload must be object')
        if not isinstance(actor,str) or not actor.strip():raise ValueError("Actor provenance required")
        from .tasks import Tasks
        Tasks(self.db)
        request=dict(job=job,expected=expected,kind=kind,payload=payload,actor=actor);key=identity(request)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            existing=self.db.execute('SELECT input_hash,body FROM events WHERE id=?',(event_id,)).fetchone()
            if existing:
                if existing[0]!=key:raise ValueError('Event ID reused')
                return json.loads(existing[1])
            current=self.get(job)
            if current['version']!=expected:raise ValueError('Stale human event')
            if kind=='approve':
                if current.get('script_changes_pending'):raise ValueError('Review the reconciled script before approving')
                scope=payload['scope'];candidate=payload['candidate']
                field={'script':'script','main':'revision','final':'delivery'}.get(scope)
                if not field or not current[field] or identity(current[field])!=candidate:raise ValueError('Approval does not match candidate')
                if scope in ('main','final') and (not current.get('validation') or current['validation'].get('decode')!='passed'):raise ValueError('Validation required')
                prerequisite={'main':'script','final':'main'}.get(scope)
                if prerequisite and prerequisite not in current['approvals']:raise ValueError('Prior approval required')
                if scope=='main':
                    revision=self.store.get(current['revision'],'revision')
                    current['accepted_revision']=current['revision']
                    current['accepted_master']=revision.get('master')
                current['approvals'][scope]=candidate
                current['stage']={'script':'editing','main':'delivery','final':'awaiting_receipt'}[scope]
            elif kind in ('select_script','arrange_script'):
                if current.get('revision') or current.get('accepted_revision') or current['stage'] not in ('review_script','reconciling'):
                    raise ValueError('Existing edit requires an agent revision request')
                history=current.get('script_proposals',[])
                if current.get('script') and not any(identity(p)==identity(current['script']) for p in history):history.append(current['script'])
                if kind=='select_script':
                    selected=next((p for p in history if identity(p)==payload['candidate']),None)
                    if selected is None:raise ValueError('Unknown proposal')
                else:
                    if identity(current['script'])!=payload['candidate']:raise ValueError('Stale script')
                    order=payload['order'];clips=current['script']['clips']
                    if not isinstance(order,list) or any(type(n)!=int for n in order) or sorted(order)!=list(range(len(clips))):raise ValueError('Expected clip permutation')
                    if current['script'].get('overlays') or current['script'].get('titles') or current['script'].get('transitions'):raise ValueError('Ask agent to reconcile dependent graphics and B-roll')
                    selected={**current['script'],'clips':[clips[n] for n in order],'arranged_by':actor}
                    selected.pop('evaluation',None)
                    if not any(identity(p)==identity(selected) for p in history):history.append(selected)
                current.update(script=selected,script_proposals=history,script_changes_pending=False,approvals={},stage='review_script',validation=None,delivery=None)
            elif kind=='feedback':
                revision=payload['revision']
                if self.store.get(revision,'revision')['job']!=job:raise ValueError('Wrong feedback job')
                if not isinstance(payload['text'],str) or not payload['text'].strip():raise ValueError('Feedback required')
                import math
                timestamp=payload.get('timestamp',0)
                if isinstance(timestamp,bool) or not isinstance(timestamp,(int,float)) or not math.isfinite(timestamp) or timestamp<0:raise ValueError('Invalid feedback timestamp')
                current['feedback'].append(payload)
                current['stage']='revising'
            elif kind=='instruction':
                if not isinstance(payload.get('text'),str) or not payload['text'].strip():raise ValueError('Instruction text required')
                current.setdefault('instructions',[]).append({'event_id':event_id,'text':payload['text'],'actor':actor})
                if payload.get('supplied_script') is not None:
                    if not isinstance(payload['supplied_script'],str) or not payload['supplied_script'].strip():raise ValueError('Script must be nonempty text')
                    current['supplied_script']=payload['supplied_script']
                    current['script_changes_pending']=True
                    current['approvals']={}
                if current.get('script') and not current.get('revision'):
                    current['script_changes_pending']=True
                    current['approvals']={}
                current['question']=None;current['stage']='reconciling'
            elif kind=='human_return':
                revision=self.store.get(payload['revision'],'revision')
                if revision['job']!=job or revision.get('author')!='human':raise ValueError('Verified human return required')
                if revision['parent']!=current['revision']:raise ValueError('Return targets stale base revision')
                current['revision']=payload['revision'];current['validation']=revision.get('validation')
                current['delivery']=None;current['stage']='review_main' if revision.get('master') else 'editing'
                current['approvals']={k:v for k,v in current['approvals'].items() if k=='script'}
            elif kind=='receipt':
                if current['approvals'].get('final')!=identity(current['delivery']) or payload['manifest_hash']!=current['delivery']['manifest_hash']:raise ValueError('Unapproved delivery receipt')
                current['stage']='finished'
            elif kind in ('pause','resume','cancel'):
                transitions={'pause':('active','paused'),'resume':('paused','active'),'cancel':('active','cancelled')}
                before,after=transitions[kind]
                if current['control']!=before:raise ValueError('Invalid workflow control')
                current['control']=after
                if current.get('pending_task'):
                    task=self.db.execute('SELECT state FROM tasks WHERE id=?',(current['pending_task'],)).fetchone()
                    mapping={'pause':{'queued':'paused','running':'pause_requested'},'resume':{'paused':'queued'},'cancel':{'queued':'cancelled','paused':'cancelled','running':'cancel_requested','pause_requested':'cancel_requested'}}[kind]
                    if task and task[0] in mapping:self.db.execute('UPDATE tasks SET state=? WHERE id=?',(mapping[task[0]],current['pending_task']))
            elif kind=='recover':
                key_to_recover=payload['request_key']
                row=self.db.execute('SELECT state FROM invocations WHERE job=? AND request_key=?',(job,key_to_recover)).fetchone()
                if not row or row[0] not in ('running','uncertain'):raise ValueError('No uncertain invocation to reconcile')
                if payload.get('acknowledge_unknown_usage') is not True:raise ValueError('Unknown completion/usage must be acknowledged')
                self.db.execute("UPDATE invocations SET state='abandoned' WHERE job=? AND request_key=?",(job,key_to_recover))
                current['turns']+=1;current['stage']='reconciling'
            elif kind=='revoke':
                scope=payload['scope']
                if scope not in current['approvals']:raise ValueError('Approval absent')
                order=['script','main','final']
                for item in order[order.index(scope):]:current['approvals'].pop(item,None)
                current['stage']='review_'+scope
            else:raise ValueError('Unknown human event')
            current['requested_run']=kind in ('approve','feedback','resume','recover','human_return','instruction')
            current.pop('job');current.pop('version')
            result={'id':event_id,'job':job,'version':expected+1,'kind':kind,'payload':payload,'received_at':time.time(),'actor':actor}
            self.db.execute('INSERT INTO events VALUES (?,?,?,?)',(event_id,job,key,json.dumps(result)))
            self.db.execute('UPDATE workflows SET version=version+1,body=? WHERE job=?',(json.dumps(current),job))
        return result

    def reserve(self,job,request_key,arguments):
        key=identity(arguments)
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO invocations VALUES (?,?,?,\'reserved\',NULL)',(job,request_key,key))
            row=self.db.execute('SELECT input_hash,state,result FROM invocations WHERE job=? AND request_key=?',(job,request_key)).fetchone()
            if row[0]!=key:raise ValueError('Invocation key conflict')
        return row[1],json.loads(row[2]) if row[2] else None

    def mark(self,job,key,state,result=None):
        with self.db:self.db.execute('UPDATE invocations SET state=?,result=? WHERE job=? AND request_key=?',(state,json.dumps(result),job,key))

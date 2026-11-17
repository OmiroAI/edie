"""Independent output workflows under one job and shared source selection."""
import json
import time
import uuid
from .workflow import Workflow,identity
from .scope import library_job


def listing(store,job):
    root=library_job(store,job);flow=Workflow(store);result=[]
    for identifier,raw in store.db.execute("SELECT id,body FROM records WHERE kind='job' ORDER BY rowid").fetchall():
        record=json.loads(raw)
        if record.get('output_of')!=root:continue
        state=flow.get(identifier)
        result.append(dict(id=identifier,name=record['output_name'],brief=record['brief'],stage=state['stage'],revision=state.get('revision'),script_title=(state.get('script') or {}).get('title'),approvals=state['approvals'],control=state['control']))
    return result


def create(store,job,body):
    from .classification import Classifications,review_state
    from .segments import Segments,reference,allowed
    from .editorial import indexes
    root=library_job(store,job);parent=store.get(root,'job');flow=Workflow(store)
    repo=Classifications(store);Segments(store)
    if set(body)!={'request_id','name','script_candidate'}:raise ValueError('Unknown or missing output fields')
    if not isinstance(body['name'],str) or not isinstance(body['script_candidate'],str):raise ValueError('Output name and candidate must be text')
    request_id=body['request_id'];name=body['name'].strip()
    if not isinstance(request_id,str) or not 1<=len(request_id)<=100 or not 1<=len(name)<=120:raise ValueError('Output name and request ID required')
    request_hash=identity(body)
    store.db.execute('CREATE TABLE IF NOT EXISTS output_requests(job TEXT,request_id TEXT,hash TEXT,output TEXT,PRIMARY KEY(job,request_id))')
    values=indexes(store,root)
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        previous=store.db.execute('SELECT hash,output FROM output_requests WHERE job=? AND request_id=?',(root,request_id)).fetchone()
        if previous:
            if previous[0]!=request_hash:raise ValueError('Output request reused with different input')
            return dict(id=previous[1],output_of=root)
        heads={r[0]:(r[1],r[2]) for r in store.db.execute('SELECT s.source_id,s.version,s.hash FROM sources s JOIN source_heads h ON s.source_id=h.source_id AND s.version=h.version').fetchall()}
        scope=parent['brief'].get('source_ids')
        if heads:
            expected={k:v for k,v in heads.items() if scope is None or k in scope}
            if set(expected)!=set(values) or any((values[k]['source']['version'],values[k]['source']['sha256'])!=v for k,v in expected.items()):raise ValueError('Source catalogue changed; refresh the library')
        state=flow.get(root);review=review_state(store,root,values,repo)
        if not review['ready'] or state.get('footage_confirmation')!=review['candidate']:raise ValueError('Confirm current file and segment selection first')
        if state.get('needs_story_options') or state.get('script_changes_pending'):raise ValueError('Story proposals are not ready')
        options=[*state.get('script_proposals',[]),state.get('script')]
        script=next((p for p in options if p and identity(p)==body['script_candidate']),None)
        if script is None:raise ValueError('Unknown script candidate')
        from .layers import validate_sync
        validate_sync(store,root,script)
        for clip in script['clips']+script.get('overlays',[]):
            if clip['source_id'] in review['excluded'] or clip['source_id'] not in values:raise ValueError('Excluded source')
            index=values[clip['source_id']]
            if clip.get('sha256')!=index['source']['sha256'] or clip.get('version')!=index['source']['version']:raise ValueError('Script source changed')
            reference(store,root,index,clip,require=True)
            if not allowed(store,root,index,clip['in'],clip['out']):raise ValueError('Rejected segment')
        identifier=uuid.uuid4().hex
        record=dict(brief=parent['brief'],context=parent.get('context'),output_of=root,output_name=name,source_script_candidate=body['script_candidate'],created_at=time.time())
        store.db.execute('INSERT INTO records VALUES (?,?,?)',(identifier,'job',json.dumps(record)))
        output=dict(footage_review_required=True,stage='review_script',requested_run=False,run_id=uuid.uuid4().hex,plan=[],
                    script=script,script_proposals=[script],revision=None,delivery=None,validation=None,approvals={},accepted_master=None,
                    accepted_revision=None,feedback=[],turns=0,usage=[],limits=state['limits'],control='active',
                    footage_confirmation=review['candidate'],needs_story_options=False,script_changes_pending=False)
        store.db.execute('INSERT INTO workflows VALUES (?,0,?)',(identifier,json.dumps(output)))
        store.db.execute('INSERT INTO output_requests VALUES (?,?,?,?)',(root,request_id,request_hash,identifier))
    return dict(id=identifier,output_of=root)

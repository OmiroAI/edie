"""Visible, reversible proposals from final accepted feedback only."""
from .workflow import Workflow,identity


def propose(store,job,event_ids,text):
    state=Workflow(store).get(job)
    if state['stage']!='finished' or not state['approvals'].get('final'):raise ValueError('Finalised approved delivery required for learning')
    if not isinstance(text,str) or not text.strip() or len(text)>20000:raise ValueError('Bounded lesson text required')
    if not event_ids:raise ValueError('Accepted feedback references required')
    import json
    feedback=[]
    for event in event_ids:
        row=store.db.execute('SELECT body FROM events WHERE id=? AND job=?',(event,job)).fetchone()
        if not row:raise ValueError('Feedback event missing')
        value=json.loads(row[0])
        if value['kind']!='feedback' or not value['payload'].get('accepted_for_learning'):raise ValueError('Feedback not explicitly accepted for learning')
        feedback.append(event)
    return store.put('context_proposal',dict(job=job,context=store.get(job,'job')['context'],feedback=feedback,text=text,status='proposed',delivery=state['delivery']))


def apply(store,proposal_id):
    proposal=store.get(proposal_id,'context_proposal')
    state=Workflow(store).get(proposal['job'])
    if state['stage']!='finished' or state['delivery']!=proposal['delivery']:raise ValueError('Accepted delivery changed')
    context=store.context
    if not context:raise ValueError('Private configuration required')
    active=context.active()['hash']
    if active!=proposal['context']['hash']:raise ValueError('Context changed; reconcile proposal first')
    document=context.load(active)
    working=context.root/'context'/'MEMORY.md'
    if working.exists() and working.read_text()!=document.get('memory',''):raise ValueError('Uncommitted memory edits must be reconciled')
    document['memory']=document.get('memory','')+'\n\n## Accepted lesson '+proposal_id+'\n\n'+proposal['text']+'\n\nSource job: '+proposal['job']+'; feedback: '+', '.join(proposal['feedback'])+'\n'
    document['version']='learn-'+identity(proposal)[:16]
    new=context.install(document)
    context.activate(new,active)
    # Active immutable snapshot is authoritative. Working copy updates only if
    # no other activation occurred; a crash here does not lose accepted memory.
    with context._lock():
        if context.active()['hash']==new:context._write(working,document['memory'].encode())
    return store.put('context_application',dict(proposal=proposal_id,previous=active,current=new,reversible=True))

if __name__=='__main__':
    import argparse
    from .core import Store
    p=argparse.ArgumentParser();p.add_argument('--state',required=True);p.add_argument('--config',required=True);p.add_argument('--proposal',required=True);a=p.parse_args()
    print(apply(Store(a.state,a.config),a.proposal))

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

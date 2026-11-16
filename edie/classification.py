"""Revisioned file-intake records and segment selection confirmation."""
import json
import time
from .workflow import identity

LABELS = ['a_roll','b_roll','hook','demonstration','reaction','establishing','needs_review','throw_away','blooper','star']
class Classifications:
    def __init__(self,store):
        self.store=store;self.db=store.db
        self.db.executescript('''CREATE TABLE IF NOT EXISTS classifications(
            job TEXT, source_id TEXT, version TEXT, sha256 TEXT, revision INTEGER, body TEXT,
            PRIMARY KEY(job,source_id,version,sha256));
            CREATE TABLE IF NOT EXISTS classification_events(id INTEGER PRIMARY KEY,job TEXT,source_id TEXT,body TEXT);''')

    def get(self,job,entry):
        row=self.db.execute('SELECT revision,body FROM classifications WHERE job=? AND source_id=? AND version=? AND sha256=?',
                            (job,entry['source_id'],entry['version'],entry['sha256'])).fetchone()
        if not row:return dict(revision=0,suggestion=None,override=None,effective=None)
        body=json.loads(row[1]);return dict(revision=row[0],**body,effective=body.get('override') or body.get('suggestion'))

    def save(self,job,entry,value,expected=None,human=False,actor='indexer'):
        if human and (not isinstance(expected,int) or isinstance(expected,bool) or expected<0):raise ValueError('Classification version required')
        if value is not None:
            if 'disposition' in value and value['disposition'] not in ('keep','exclude','unreviewed'):raise ValueError('Invalid file disposition')
            if not isinstance(value,dict) or not isinstance(value.get('labels'),list) or len(set(value['labels']))!=len(value['labels']) or any(x not in LABELS for x in value['labels']):raise ValueError('Invalid labels')
            if 'throw_away' in value['labels'] and 'star' in value['labels']:raise ValueError('Reject and star conflict')
            if not isinstance(value.get('reason'),str) or not value['reason'].strip() or len(value['reason'])>4000:raise ValueError('Reason required')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');current=self.get(job,entry)
            if human and current['revision']!=expected:raise ValueError('Stale classification')
            body={key:current[key] for key in ('suggestion','override')}
            body['override' if human else 'suggestion']=value
            self.db.execute('INSERT OR REPLACE INTO classifications VALUES (?,?,?,?,?,?)',(job,entry['source_id'],entry['version'],entry['sha256'],current['revision']+1,json.dumps(body)))
            self.db.execute('INSERT INTO classification_events(job,source_id,body) VALUES (?,?,?)',(job,entry['source_id'],json.dumps(dict(at=time.time(),actor=actor,version=entry['version'],sha256=entry['sha256'],human=human,value=value))))
        return self.get(job,entry)


def review_state(store,job,values=None,repo=None):
    from .editorial import indexes
    if values is None:values=indexes(store,job)
    repo=repo or Classifications(store)
    from .segments import Segments
    segments=Segments(store)
    from .tasks import Tasks
    Tasks(store.db)
    segment_mode=True
    rows=[];missing=[];excluded=[]
    for key,value in sorted(values.items()):
        entry=value['source'];record=repo.get(job,entry);effective=record['effective'];decision=file_decision(record)
        if decision=='unreviewed':missing.append(key)
        if decision=='exclude':excluded.append(key)
        parts=segments.get(job,entry)['items']
        if segment_mode and decision!='exclude' and not parts and key not in missing:missing.append(key)
        from .segments import selection
        if parts and all(selection(p)=='rejected' for p in parts) and key not in excluded:excluded.append(key)
        rows.append(dict(source_id=key,version=entry['version'],sha256=entry['sha256'],classification=decision,segments=parts))
    return dict(candidate=identity(rows),ready=bool(rows) and not missing,total=len(rows),unclassified=len(missing),excluded=excluded,included=len(rows)-len(excluded),segment_mode=segment_mode)


def file_decision(record):
    """Explicit intake only; migrations are operator operations, not runtime fallbacks."""
    value=record.get('override')
    if not value:return 'unreviewed'
    return value['disposition']

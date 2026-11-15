"""Durable task queue. Expired work needs explicit recovery, never blind replay."""
import json
import time
import uuid


class Tasks:
    def __init__(self, db):
        self.db = db
        db.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, job TEXT NOT NULL, key TEXT NOT NULL,
            payload TEXT NOT NULL, state TEXT NOT NULL, owner TEXT,
            expires REAL, result TEXT, UNIQUE(job,key))''')

    def submit(self, job, key, payload):
        if not key or len(key) > 200:
            raise ValueError('An idempotency key of 1–200 characters is required')
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO tasks(id,job,key,payload,state) VALUES (?,?,?,?,?)',
                            (uuid.uuid4().hex, job, key, encoded, 'queued'))
            row = self.db.execute('SELECT id,payload FROM tasks WHERE job=? AND key=?', (job, key)).fetchone()
            if row[1] != encoded:
                raise ValueError('Idempotency key already used with different input')
        return row[0]

    def get(self, identifier):
        cursor = self.db.execute('SELECT * FROM tasks WHERE id=?', (identifier,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError('Task not found')
        result = dict(zip((d[0] for d in cursor.description), row))
        result['payload'] = json.loads(result['payload'])
        result['result'] = json.loads(result['result']) if result['result'] else None
        return result

    def claim(self, owner, seconds=60):
        if not owner or seconds <= 0:
            raise ValueError('Invalid lease')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute("UPDATE tasks SET state='interrupted',owner=NULL WHERE state IN ('running','pause_requested','cancel_requested') AND expires < ?", (time.time(),))
            row = self.db.execute("SELECT id FROM tasks WHERE state='queued' ORDER BY rowid LIMIT 1").fetchone()
            if not row:
                return None
            self.db.execute("UPDATE tasks SET state='running',owner=?,expires=? WHERE id=?", (owner, time.time()+seconds, row[0]))
        return self.get(row[0])

    def finish(self, identifier, owner, result):
        with self.db:
            updated = self.db.execute("UPDATE tasks SET state='completed',result=?,owner=NULL WHERE id=? AND state='running' AND owner=? AND expires>=?", (json.dumps(result), identifier, owner, time.time()))
            if updated.rowcount != 1:
                raise ValueError('Lease expired or task no longer running')

    def heartbeat(self, identifier, owner, seconds=60):
        with self.db:
            changed = self.db.execute("UPDATE tasks SET expires=? WHERE id=? AND owner=? AND state IN ('running','pause_requested','cancel_requested') AND expires>=?", (time.time()+seconds, identifier, owner, time.time()))
            if changed.rowcount != 1:
                raise ValueError('Lease lost')
        return self.get(identifier)['state']

    def stopped(self, identifier, owner, state, result=None):
        if state not in ('paused', 'cancelled', 'failed'):
            raise ValueError('Invalid stop state')
        expected = {'paused': 'pause_requested', 'cancelled': 'cancel_requested', 'failed': 'running'}[state]
        with self.db:
            changed = self.db.execute("UPDATE tasks SET state=?,owner=NULL,expires=NULL,result=? WHERE id=? AND owner=? AND state=? AND expires>=?", (state, json.dumps(result), identifier, owner, expected, time.time()))
            if changed.rowcount != 1:
                raise ValueError('Lease lost or control state changed')

    def control(self, identifier, action):
        transitions = {
            'pause': {'queued': 'paused', 'running': 'pause_requested'},
            'resume': {'paused': 'queued'},
            'cancel': {'queued': 'cancelled', 'paused': 'cancelled', 'running': 'cancel_requested', 'pause_requested': 'cancel_requested'},
            'recover': {'interrupted': 'queued', 'failed': 'queued'},
        }
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            current = self.get(identifier)['state']
            target = transitions.get(action, {}).get(current)
            if target is None:
                raise ValueError('Task state does not permit this action')
            self.db.execute('UPDATE tasks SET state=? WHERE id=?', (target, identifier))
        return self.get(identifier)

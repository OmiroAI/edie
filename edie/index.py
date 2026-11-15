"""Private broker source catalogue. IDs survive renames; versions remain historical."""
import json
import re
from pathlib import PurePosixPath
from .core import digest, source


class Catalogue:
    def __init__(self, store):
        self.store = store
        store.db.execute('''CREATE TABLE IF NOT EXISTS sources (
            source_id TEXT, version TEXT, hash TEXT, path TEXT,
            PRIMARY KEY(source_id,version))''')

    def ingest(self, entries, media_root):
        if not isinstance(entries, list) or not entries:
            raise ValueError('Nonempty source list required')
        verified = []
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError('Source object required')
            if not all(isinstance(entry.get(k), str) and entry[k] for k in ('source_id', 'version', 'path', 'sha256')):
                raise ValueError('Source identity, version, path and hash required')
            if entry['source_id'] in seen:
                raise ValueError('Duplicate source ID')
            seen.add(entry['source_id'])
            path = PurePosixPath(entry['path'])
            if path.is_absolute() or '..' in path.parts or not re.fullmatch('[a-f0-9]{64}', entry['sha256']):
                raise ValueError('Invalid path or hash')
            local = source(media_root, entry['path'])
            if digest(local) != entry['sha256']:
                raise ValueError('Broker hash differs from local copy')
            verified.append(entry)
        # All-or-nothing manifest import, including conflicts with historical versions.
        with self.store.db:
            self.store.db.execute('BEGIN IMMEDIATE')
            for entry in verified:
                key = (entry['source_id'], entry['version'])
                previous = self.store.db.execute('SELECT hash FROM sources WHERE source_id=? AND version=?', key).fetchone()
                if previous and previous[0] != entry['sha256']:
                    raise ValueError('Source version reused with different content')
                self.store.db.execute('INSERT INTO sources VALUES (?,?,?,?) ON CONFLICT(source_id,version) DO UPDATE SET path=excluded.path', (*key, entry['sha256'], entry['path']))
        return self.list()

    def list(self):
        rows = self.store.db.execute('SELECT source_id,version,hash,path FROM sources ORDER BY source_id,version').fetchall()
        return [dict(zip(('source_id', 'version', 'sha256', 'path'), row)) for row in rows]

    def get(self, source_id, version):
        for entry in self.list():
            if entry['source_id'] == source_id and entry['version'] == version:
                return entry
        raise ValueError('Unknown source version')

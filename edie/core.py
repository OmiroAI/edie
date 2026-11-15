import hashlib
import math
import re
import json
import sqlite3
import subprocess
import uuid
from pathlib import Path


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / 'edie.sqlite')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT, body TEXT)')

    def put(self, kind, body):
        identifier = uuid.uuid4().hex
        with self.db:
            self.db.execute('INSERT INTO records VALUES (?,?,?)', (identifier, kind, json.dumps(body, allow_nan=False)))
        return identifier

    def get(self, identifier, kind):
        row = self.db.execute('SELECT body FROM records WHERE id=? AND kind=?', (identifier, kind)).fetchone()
        if not row:
            raise ValueError('Record not found')
        return json.loads(row[0])

    def project(self, name):
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError('Project name required; maximum 200 characters')
        return self.put('project', {'name': name})

    def job(self, project, brief):
        self.get(project, 'project')
        required = {'goal', 'audience', 'format', 'duration', 'language'}
        if not isinstance(brief, dict) or not required <= brief.keys():
            raise ValueError('Brief requires goal, audience, format, duration and language')
        if not all(isinstance(brief[k], str) and brief[k].strip() for k in required - {'duration'}):
            raise ValueError('Brief fields must be nonempty text')
        if isinstance(brief['duration'], bool) or not isinstance(brief['duration'], (int, float)) or not math.isfinite(brief['duration']) or brief['duration'] <= 0:
            raise ValueError('Duration must be positive seconds')
        return self.put('job', {'project': project, 'brief': brief})

    def revision(self, job, clips):
        self.get(job, 'job')
        if not isinstance(clips, list) or not clips:
            raise ValueError('Timeline must contain clips')
        for clip in clips:
            if (not isinstance(clip, dict) or not all(isinstance(clip.get(k), (int, float)) and not isinstance(clip[k], bool) and math.isfinite(clip[k]) for k in ('in', 'out'))
                    or not (0 <= clip['in'] < clip['out'])
                    or not isinstance(clip.get('path'), str)
                    or not isinstance(clip.get('sha256'), str)
                    or not re.fullmatch(r'[a-f0-9]{64}', clip['sha256'])):
                raise ValueError('Clips require valid bounds and source hash')
        return self.put('revision', {'job': job, 'clips': clips})

    def feedback(self, job, revision, text, timestamp):
        if self.get(revision, 'revision')['job'] != job:
            raise ValueError('Revision belongs to another job')
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Feedback text required')
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError('Negative timestamp')
        return self.put('feedback', dict(job=job, revision=revision, text=text, timestamp=timestamp))

    def approve(self, job, revision):
        if self.get(revision, 'revision')['job'] != job:
            raise ValueError('Revision belongs to another job')
        return self.put('approval', dict(job=job, revision=revision))


def source(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Source outside authorised mount or missing')
    return path


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)], check=True, capture_output=True, timeout=60)
    return json.loads(result.stdout)


def render(store, revision, media_root, attempt=None):
    timeline = store.get(revision, 'revision')
    # Immutable revisions get their own output; incomplete work is never accepted.
    attempt = attempt or uuid.uuid4().hex
    if not re.fullmatch(r'[a-f0-9]{32}', attempt):
        raise ValueError('Invalid attempt')
    destination = store.root / 'outputs' / revision / attempt
    destination.mkdir(parents=True, exist_ok=False)
    parts = []
    for index, clip in enumerate(timeline['clips']):
        path = source(media_root, clip['path'])
        if digest(path) != clip['sha256']:
            raise ValueError('Source version changed')
        metadata = probe(path)
        if clip['out'] > float(metadata['format']['duration']):
            raise ValueError('Clip exceeds source duration')
        if not any(s['codec_type'] == 'audio' for s in metadata['streams']):
            raise ValueError('Silent sources need an explicit audio policy; unsupported in this slice')
        part = destination / f'{index}.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-ss', str(clip['in']), '-i', str(path), '-t', str(clip['out']-clip['in']), '-map', '0:v:0', '-map', '0:a:0', '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1', '-r', '30', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2', str(part)], check=True, capture_output=True, timeout=3600)
        parts.append(part)
    listing = destination / 'concat.txt'
    listing.write_text(''.join(f"file '{p.name}'\n" for p in parts))
    temporary = destination / 'preview.pending.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-f', 'concat', '-safe', '1', '-i', str(listing), '-c', 'copy', '-movflags', '+faststart', str(temporary)], check=True, capture_output=True, timeout=3600)
    metadata = probe(temporary)
    expected = sum(c['out']-c['in'] for c in timeline['clips'])
    if abs(float(metadata['format']['duration'])-expected) > max(0.3, len(parts)*0.1):
        raise ValueError('Rendered duration mismatch')
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(temporary), '-f', 'null', '-'], check=True, capture_output=True, timeout=3600)
    output = destination / 'preview.mp4'
    temporary.replace(output)
    return str(output)

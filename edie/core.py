import os
import hashlib
import math
import re
import json
import sqlite3
import subprocess
import uuid
from pathlib import Path


class Store:
    def __init__(self, root, config_dir=None):
        from .context import Context
        directory = config_dir or os.getenv('EDIE_CONFIG_DIR')
        self.context = Context(directory) if directory else None
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / 'edie.sqlite')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT, body TEXT)')
        if self.db.execute("SELECT 1 FROM records WHERE kind='project' LIMIT 1").fetchone():
            self.db.close()
            raise ValueError('Legacy multi-project state: preserve it and select a fresh deployment state directory; automatic context merging is disabled')

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

    def job(self, brief):
        required = {'goal', 'audience', 'format', 'duration', 'language'}
        if not isinstance(brief, dict) or not required <= brief.keys():
            raise ValueError('Brief requires goal, audience, format, duration and language')
        if not all(isinstance(brief[k], str) and brief[k].strip() for k in required - {'duration'}):
            raise ValueError('Brief fields must be nonempty text')
        if isinstance(brief['duration'], bool) or not isinstance(brief['duration'], (int, float)) or not math.isfinite(brief['duration']) or brief['duration'] <= 0:
            raise ValueError('Duration must be positive seconds')
        if 'source_ids' in brief and (not isinstance(brief['source_ids'],list) or not 1<=len(brief['source_ids'])<=500 or not all(isinstance(s,str) and s for s in brief['source_ids'])):
            raise ValueError('Invalid source scope')
        context = self.context.active() if self.context else None
        return self.put('job', {'brief': brief, 'context': context})

    def job_context(self, job):
        record = self.get(job, 'job')
        reference = record.get('context')
        if not reference or not self.context:
            raise ValueError('Job has no configured context')
        return self.context.load(reference['hash'])

    def derivative(self, parent_job, brief):
        from .workflow import Workflow, identity
        state = Workflow(self).get(parent_job)
        if not state['revision'] or state['approvals'].get('main') != identity(state['revision']):
            raise ValueError('Approve the current main edit before derivatives')
        job = self.job(brief)
        record = self.get(job, 'job')
        record['parent_job'] = parent_job
        record['parent_revision'] = state['revision']
        record['accepted_master'] = state.get('accepted_master')
        with self.db:
            self.db.execute('UPDATE records SET body=? WHERE id=?', (json.dumps(record), job))
        return job

    def revision(self, job, clips):
        self.get(job, 'job')
        if not isinstance(clips, list) or not clips:
            raise ValueError('Timeline must contain clips')
        for clip in clips:
            if (not isinstance(clip, dict) or set(clip)-{'path','sha256','in','out'} or not all(isinstance(clip.get(k), (int, float)) and not isinstance(clip[k], bool) and math.isfinite(clip[k]) for k in ('in', 'out'))
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


def media_source(store, root, clip):
    relative=clip['path']
    if store is not None and clip.get('source_id') and clip.get('version'):
        from .index import Catalogue
        entry=Catalogue(store).get(clip['source_id'],clip['version'])
        if entry['sha256']!=clip['sha256']:raise ValueError('Source reference hash mismatch')
        relative=entry['path']
    return source(root,relative)


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
    from .storage import admit
    timeline = store.get(revision, 'revision')
    admit(store.root, int(sum(c['out']-c['in'] for c in timeline['clips'])*2_000_000))
    if 'otio' in timeline:
        import opentimelineio as otio
        from .timeline import compile_timeline, compile_overlays
        canonical = otio.adapters.read_from_string(timeline['otio'], 'otio_json')
        timeline['clips'] = compile_timeline(canonical)
        timeline['overlays'] = compile_overlays(canonical)
    # Immutable revisions get their own output; incomplete work is never accepted.
    attempt = attempt or uuid.uuid4().hex
    if not re.fullmatch(r'[a-f0-9]{32}', attempt):
        raise ValueError('Invalid attempt')
    destination = store.root / 'outputs' / revision / attempt
    destination.mkdir(parents=True, exist_ok=False)
    job_record = store.get(timeline['job'], 'job')
    if job_record.get('parent_job'):
        media_root = store.root/'derivative_media'
    profile = job_record['brief']['format']
    dimensions = {'16:9': (1280,720), '9:16': (720,1280), '1:1': (720,720)}
    if profile not in dimensions:
        raise ValueError('Unsupported output format')
    width, height = dimensions[profile]
    fit = f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1'
    parts = []
    for index, clip in enumerate(timeline['clips']):
        path = media_source(store, media_root, clip)
        if digest(path) != clip['sha256']:
            raise ValueError('Source version changed')
        if clip.get('proxy') and 'otio' in timeline:
            path = source(store.root, clip['proxy']['path'])
            if digest(path) != clip['proxy']['sha256']:raise ValueError('Editing proxy changed')
        metadata = probe(path)
        if clip['out'] > float(metadata['format']['duration']) + (1/60 if 'otio' in timeline else 0):
            raise ValueError('Clip exceeds source duration')
        silent = not any(s['codec_type'] == 'audio' for s in metadata['streams'])
        if silent and not clip.get('silent'):
            raise ValueError('Silent sources need an explicit audio policy')
        part = destination / f'{index}.mp4'
        command = ['ffmpeg', '-v', 'error', '-nostdin', '-y', '-ss', str(clip['in']), '-i', str(path)]
        if silent:
            command += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
        command += ['-t', str(clip['out']-clip['in']), '-map', '0:v:0', '-map', '1:a:0' if silent else '0:a:0', '-vf', fit, '-r', '30', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2', str(part)]
        subprocess.run(command, check=True, capture_output=True, timeout=3600)
        parts.append(part)
    listing = destination / 'concat.txt'
    listing.write_text(''.join(f"file '{p.name}'\n" for p in parts))
    temporary = destination / 'preview.pending.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-f', 'concat', '-safe', '1', '-i', str(listing), '-c', 'copy', '-movflags', '+faststart', str(temporary)], check=True, capture_output=True, timeout=3600)
    for number, overlay in enumerate(timeline.get('overlays', [])):
        path = media_source(store, media_root, overlay)
        if digest(path) != overlay['sha256']:
            raise ValueError('B-roll source changed')
        if overlay.get('proxy'):
            path = source(store.root, overlay['proxy']['path'])
            if digest(path) != overlay['proxy']['sha256']:raise ValueError('B-roll proxy changed')
        layered = destination / f'layer-{number}.mp4'
        length = overlay['out'] - overlay['in']
        filters = f"[1:v]{fit},setpts=PTS-STARTPTS+{overlay['at']}/TB[b];[0:v][b]overlay=eof_action=pass:enable='gte(t,{overlay['at']})*lt(t,{overlay['at']+length})'[v]"
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(temporary), '-ss', str(overlay['in']), '-t', str(length), '-i', str(path), '-filter_complex', filters, '-map', '[v]', '-map', '0:a', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'copy', str(layered)], check=True, capture_output=True, timeout=3600)
        temporary = layered
    if timeline.get('titles') or timeline.get('transitions'):
        filters = []
        for transition in timeline.get('transitions', []):
            at, half = transition['at'], transition['duration']/2
            filters.append(f"fade=t=out:st={at-half}:d={half}:enable='gte(t,{at-half})*lt(t,{at})'")
            filters.append(f"fade=t=in:st={at}:d={half}:enable='gte(t,{at})*lt(t,{at+half})'")
        for index, title in enumerate(timeline.get('titles', [])):
            title_file = destination / f'title-{index}.txt'
            title_file.write_text(title['text'])
            filters.append(f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:textfile='{title_file}':expansion=none:fontsize={width//28}:fontcolor=white:x=(w-text_w)/2:y=h*0.08:box=1:boxcolor=black@0.65:boxborderw=12:enable='gte(t,{title['start']})*lt(t,{title['end']})'")
        titled = destination / 'titled.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(temporary), '-vf', ','.join(filters), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'copy', str(titled)], check=True, capture_output=True, timeout=3600)
        temporary = titled
    metadata = probe(temporary)
    expected = sum(c['out']-c['in'] for c in timeline['clips'])
    if abs(float(metadata['format']['duration'])-expected) > max(0.3, len(parts)*0.1):
        raise ValueError('Rendered duration mismatch')
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(temporary), '-f', 'null', '-'], check=True, capture_output=True, timeout=3600)
    output = destination / 'preview.mp4'
    if timeline.get('cues'):
        from .timeline import srt
        subtitles = destination / 'subtitles.srt'
        subtitles.write_text(srt(timeline['cues'], expected))
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(temporary), '-i', str(subtitles), '-map', '0:v', '-map', '0:a', '-map', '1:0', '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'mov_text', '-movflags', '+faststart', str(output)], check=True, capture_output=True, timeout=600)
    else:
        temporary.replace(output)
    return str(output)

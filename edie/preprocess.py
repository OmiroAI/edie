"""Bounded local frame extraction with source-relative timestamps and private cache."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import uuid
from .core import Store, digest, probe, source
from .index import Catalogue

VERSION = 1


def prepare(store, project, source_id, version, media_root, chunk_seconds=30, overlap=2, fps=1, long_edge=640, max_frames=64):
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (chunk_seconds, overlap, fps)):
        raise ValueError('Finite sampling settings required')
    if not (1 <= chunk_seconds <= 60 and 0 <= overlap < chunk_seconds and 0 < fps <= 8):
        raise ValueError('Sampling settings out of bounds')
    if not isinstance(long_edge, int) or not 64 <= long_edge <= 1280 or not isinstance(max_frames, int) or not 1 <= max_frames <= 512:
        raise ValueError('Invalid image/frame bound')
    if math.ceil(chunk_seconds * fps) > max_frames:
        raise ValueError('Chunk exceeds frame budget')
    entry = Catalogue(store).get(project, source_id, version)
    local = source(media_root, entry['path'])
    if digest(local) != entry['sha256']:
        raise ValueError('Source changed')
    metadata = probe(local)
    stream = next((s for s in metadata['streams'] if s['codec_type'] == 'video'), None)
    if not stream:
        raise ValueError('Video stream required')
    duration = float(stream.get('duration', metadata['format']['duration']))
    if not math.isfinite(duration) or not 0 < duration <= 86400:
        raise ValueError('Unsupported duration')
    settings = dict(version=VERSION, chunk_seconds=chunk_seconds, overlap=overlap, fps=fps, long_edge=long_edge, max_frames=max_frames)
    key = hashlib.sha256(json.dumps({'hash': entry['sha256'], 'settings': settings}, sort_keys=True).encode()).hexdigest()
    root = store.root / 'analysis' / project / key
    root.mkdir(parents=True, exist_ok=True)
    chunks = []
    start = 0.0
    while start < duration:
        end = min(start + chunk_seconds, duration)
        number = len(chunks)
        record = root / f'{number:06d}.json'
        cached = None
        if record.exists():
            try:
                candidate = json.loads(record.read_text())
                if candidate['start'] == start and candidate['end'] == end and candidate['frames'] and all(source(root, f['path']).stat().st_size == f['bytes'] and digest(source(root, f['path'])) == f['sha256'] for f in candidate['frames']):
                    cached = candidate
            except (ValueError, KeyError, TypeError, OSError):
                pass  # Rebuild only the invalid chunk; preserve other completed chunks.
        if cached is None:
            attempt = root / uuid.uuid4().hex
            attempt.mkdir()
            # Select original decoded frames rather than fps-filter duplicates.
            # Reset first presentation timestamp to zero for source-relative time.
            select = f"gte(t,{start})*lt(t,{end})*if(isnan(prev_selected_t),1,gte(t-prev_selected_t,{1/fps}))"
            filters = f"setpts=PTS-STARTPTS,select='{select}',showinfo,scale='min({long_edge},iw)':'min({long_edge},ih)':force_original_aspect_ratio=decrease"
            result = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'info', '-i', str(local), '-map', '0:v:0', '-an', '-vf', filters, '-fps_mode', 'vfr', '-frames:v', str(max_frames), '-q:v', '3', str(attempt/'%04d.jpg')], capture_output=True, check=True, timeout=1800)
            timestamps = [float(t) for t in re.findall(r'\bn:\s*\d+\s+pts:\s*[-\d]+\s+pts_time:([-\d.e+]+)', result.stderr.decode(errors='replace'))]
            images = sorted(attempt.glob('*.jpg'))
            if not images or len(images) != len(timestamps) or any(not start <= t < end for t in timestamps):
                raise ValueError('Frame timestamp validation failed')
            cached = {'start': start, 'end': end, 'frames': [{'path': str(p.relative_to(root)), 'source_seconds': t, 'bytes': p.stat().st_size, 'sha256': digest(p)} for p, t in zip(images, timestamps)]}
            temporary = root / f'{number:06d}.{uuid.uuid4().hex}.tmp'
            temporary.write_text(json.dumps(cached, indent=2))
            temporary.replace(record)
        chunks.append(cached)
        if end == duration:
            break
        start += chunk_seconds - overlap
    return {'project': project, 'source_id': source_id, 'source_version': version, 'source_sha256': entry['sha256'], 'cache_root': str(root.relative_to(store.root)), 'timestamp_basis': 'seconds from first decoded video presentation timestamp', 'settings': settings, 'chunks': chunks}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', required=True)
    parser.add_argument('--media', required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--source-id', required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    store = Store(args.state)
    try:
        print(json.dumps(prepare(store, args.project, args.source_id, args.version, args.media)))
    finally:
        store.db.close()


if __name__ == '__main__':
    main()

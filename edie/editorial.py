"""Read models and bounded playback proxies for editorial review."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import uuid
from .core import Store, source, digest, probe
from .tasks import Tasks


def indexes(store, job):
    from .agent import Agent
    agent = Agent(store, None, None)
    agent.current_job = job
    return agent.indexes()


def footage(store, job):
    values = indexes(store, job)
    from .classification import Classifications,file_decision
    classifications=Classifications(store)
    from .segments import Segments
    segments=Segments(store)
    Tasks(store.db)
    rows = []
    progress={}
    for path in sorted((store.root/'index').glob('*/progress.json'),key=lambda p:p.stat().st_mtime):
        value=json.loads(path.read_text())
        if value.get('source_id'):progress[value['source_id']]=value
    proxy_tasks = [Tasks(store.db).get(row[0]) for row in store.db.execute('SELECT id FROM tasks WHERE job=? ORDER BY rowid DESC', (job,)).fetchall()]
    for key, value in values.items():
        entry = value['source']
        task = next((t for t in proxy_tasks if t['payload'].get('action') == 'review_proxy' and t['payload'].get('sha256') == entry['sha256']), None)
        rows.append(dict(source_id=key, path=entry['path'], version=entry['version'], sha256=entry['sha256'],
                         disposition=file_decision(classifications.get(job,entry)), duration=value['duration'], transcript=value['transcript'], visual=value['visual'], classification=classifications.get(job,entry),
                         segments=segments.get(job,entry), coverage=value.get('coverage'), visual_progress=progress.get(key), cut_candidates=value.get('cut_candidates',[]), timing_issues=len(value.get('transcript_issues', [])),
                         summary=' '.join(v['observations'] for v in value['visual'])[:800],
                         proxy_task=task['id'] if task else None, proxy_state=task['state'] if task else 'not_requested'))
    return rows


def request_proxy(store, job, source_id):
    entry = indexes(store, job)[source_id]['source']
    payload = dict(action='review_proxy', source_id=source_id, version=entry['version'], sha256=entry['sha256'])
    identifier = Tasks(store.db).submit(job, 'review-proxy-v1:'+entry['sha256'], payload)
    return Tasks(store.db).get(identifier)


def make_proxy(store, task, media):
    from .index import Catalogue
    from .storage import admit
    entry = Catalogue(store).get(task['payload']['source_id'], task['payload']['version'])
    original = source(media, entry['path'])
    if entry['sha256'] != task['payload']['sha256'] or digest(original) != entry['sha256']:
        raise ValueError('Source changed')
    metadata = probe(original)
    video = next(s for s in metadata['streams'] if s['codec_type'] == 'video')
    duration = float(metadata['format']['duration'])
    admit(store.root, int(duration * 200000))
    directory = store.root/'review-media'/entry['sha256']; directory.mkdir(parents=True, exist_ok=True)
    target = directory/(uuid.uuid4().hex+'.mp4')
    filters = ['setpts=PTS-STARTPTS', 'fps=24', 'scale=640:640:force_original_aspect_ratio=decrease:force_divisible_by=2']
    if video.get('color_transfer') in ('arib-std-b67', 'smpte2084'):
        filters += ['zscale=t=linear:npl=100', 'format=gbrpf32le', 'zscale=p=bt709', 'tonemap=tonemap=hable:desat=0', 'zscale=t=bt709:m=bt709:r=tv']
    filters += ['setsar=1', 'format=yuv420p']
    try:
        subprocess.run(['ffmpeg','-v','error','-nostdin','-threads','2','-i',str(original),'-map','0:v:0','-map','0:a:0?',
                        '-vf',','.join(filters),'-af','aresample=async=1:first_pts=0','-c:v','libx264','-threads','2','-preset','veryfast','-crf','29',
                        '-c:a','aac','-b:a','64k','-ac','2','-map_metadata','-1','-movflags','+faststart',str(target)],
                       check=True, capture_output=True, timeout=7200)
        actual = probe(target)
        if abs(float(actual['format']['duration'])-duration)>0.3: raise ValueError('Proxy duration mismatch')
        return dict(kind='source_preview', path=str(target.relative_to(store.root)), source_id=entry['source_id'],
                    sha256=digest(target), original_sha256=entry['sha256'], bytes=target.stat().st_size, duration=duration)
    except Exception:
        target.unlink(missing_ok=True)
        raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--state',required=True);p.add_argument('--media',required=True);p.add_argument('--task');p.add_argument('--once',action='store_true');a=p.parse_args()
    if a.task:
        store=Store(a.state)
        try: print(json.dumps(make_proxy(store,Tasks(store.db).get(a.task),a.media)))
        finally:store.db.close()
        return
    from .worker import run_once
    while True:
        worked=run_once(a.state,a.media,'review_proxy')
        if a.once:return
        if not worked:time.sleep(2)

if __name__=='__main__':main()

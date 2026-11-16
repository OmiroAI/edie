"""Derivatives use the approved preview or accepted human master, never old cuts."""
from pathlib import Path
import shutil
import uuid
from .core import digest,source
from .workflow import Workflow,identity
from .tasks import Tasks
from .index import Catalogue


def prepare(store,job):
    record=store.get(job,'job');parent=Workflow(store).get(record['parent_job'])
    if parent['revision']!=record['parent_revision'] or parent['approvals'].get('main')!=identity(parent['revision']):raise ValueError('Parent approval changed; reconcile derivative source')
    if parent.get('accepted_master'):
        reference=parent['accepted_master']
    else:
        task=Tasks(store.db).get(parent['pending_task'])
        if task['state']!='completed' or task['payload']['revision']!=parent['revision']:raise ValueError('Approved main preview unavailable')
        reference=task['result']
    original=source(store.root,reference['path'])
    if digest(original)!=reference['sha256']:raise ValueError('Approved master changed')
    root=store.root/'derivative_media';root.mkdir(exist_ok=True)
    target=root/(reference['sha256']+'.mp4')
    if not target.exists():
        from .storage import admit
        admit(store.root,original.stat().st_size)
        temporary=root/(uuid.uuid4().hex+'.pending')
        shutil.copyfile(original,temporary)
        if digest(temporary)!=reference['sha256']:raise ValueError('Master changed while copying')
        temporary.replace(target)
    elif digest(target)!=reference['sha256']:raise ValueError('Derivative media integrity failure')
    entry=dict(source_id='accepted:'+record['parent_job']+':'+parent['revision'],version=reference['sha256'],sha256=reference['sha256'],path=target.name)
    approved=store.get(parent['revision'],'revision')
    if 'cues' in approved:
        entry['approved_cues']=approved['cues']
    else:
        from .core import probe
        import subprocess
        streams=probe(target)['streams']
        if any(s['codec_type']=='subtitle' for s in streams):
            from .returns import parse_srt
            subtitle_file=root/(reference['sha256']+'.srt')
            if not subtitle_file.exists():
                subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(target),'-map','0:s:0',str(subtitle_file)],check=True,capture_output=True,timeout=120)
            entry['approved_cues']=parse_srt(subtitle_file.read_text())
    Catalogue(store).ingest([entry],root)
    return root,entry

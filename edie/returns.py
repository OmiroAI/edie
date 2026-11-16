"""Broker-ingested human masters stay immutable and replace rough cuts on approval."""
from pathlib import Path
import shutil
import uuid
from .core import digest,source,probe
from .export import validate_export


def import_master(store,job,base_revision,inbox,relative,sha256):
    if store.get(base_revision,'revision')['job']!=job:raise ValueError('Wrong base revision job')
    original=source(inbox,relative)
    if digest(original)!=sha256:raise ValueError('Returned master hash mismatch')
    duration=float(probe(original)['format']['duration'])
    report=validate_export(original,duration)
    from .storage import admit
    admit(store.root,original.stat().st_size)
    directory=store.root/'human_returns'/uuid.uuid4().hex;directory.mkdir(parents=True)
    master=directory/'master.mp4';shutil.copyfile(original,master)
    if digest(master)!=sha256:raise ValueError('Returned master changed during ingest')
    return store.put('revision',dict(job=job,parent=base_revision,author='human',master=dict(path=str(master.relative_to(store.root)),sha256=sha256,duration=duration),validation=report,editable_layers=False))


def parse_srt(text):
    import re
    cues=[]
    def seconds(stamp):
        h,m,s,ms=map(int,re.split('[:,.]',stamp));return h*3600+m*60+s+ms/1000
    for block in re.split(r'\n\s*\n',text.strip().replace('\r','')):
        lines=block.splitlines()
        if lines and lines[0].isdigit():lines=lines[1:]
        if len(lines)<2:raise ValueError('Malformed SRT cue')
        match=re.fullmatch(r'(\d{2,}:\d{2}:\d{2}[,.]\d{3}) --> (\d{2,}:\d{2}:\d{2}[,.]\d{3})',lines[0])
        if not match:raise ValueError('Malformed SRT timestamp')
        cues.append(dict(id=uuid.uuid4().hex,start=seconds(match[1]),end=seconds(match[2]),text='\n'.join(lines[1:]),needs_review=False,human_supplied=True))
    return cues


def import_timeline(store,job,base_revision,inbox,manifest,media):
    import json
    import opentimelineio as otio
    from urllib.parse import urlsplit,unquote
    from .timeline import compile_timeline,compile_overlays,commit
    base=store.get(base_revision,'revision')
    if base['job']!=job or 'otio' not in base:raise ValueError('Editable base revision required')
    incoming=source(inbox,manifest['timeline_path']);subtitles=source(inbox,manifest['srt_path'])
    if incoming.stat().st_size>10*1024*1024 or subtitles.stat().st_size>1024*1024:raise ValueError('Return package too large')
    if digest(incoming)!=manifest['timeline_sha256'] or digest(subtitles)!=manifest['srt_sha256']:raise ValueError('Return file hash mismatch')
    adapter={'xml':'fcp_xml','otio':'otio_json'}.get(incoming.suffix.lstrip('.').lower())
    if not adapter:raise ValueError('Unsupported interchange format')
    timeline=otio.adapters.read_from_file(str(incoming),adapter_name=adapter)
    videos=[t.deepcopy() for t in timeline.tracks if t.kind==otio.schema.TrackKind.Video]
    audio=[t.deepcopy() for t in timeline.tracks if t.kind==otio.schema.TrackKind.Audio]
    if not 1<=len(videos)<=2 or len(audio)!=1:raise ValueError('Unsupported returned track layout')
    timeline.tracks[:]=[videos[0],audio[0]]+videos[1:]
    mapping={}
    for clip in base['clips']+base.get('overlays',[]):
        mapping[clip['sha256']+Path(clip['path']).suffix.lower()]=clip
        mapping[clip['path']]=clip
        if clip.get('proxy'):mapping[clip['proxy']['sha256']+'.mp4']=clip
    for track in timeline.tracks:
        for item in track:
            if not isinstance(item,otio.schema.Clip):continue
            parsed=urlsplit(item.media_reference.target_url)
            if parsed.scheme not in ('','file'):raise ValueError('Remote media URLs prohibited')
            path=unquote(parsed.path)
            entry=mapping.get(path) or mapping.get(Path(path).name)
            if not entry:raise ValueError('Unmapped returned media; broker source mapping required')
            if digest(source(media,entry['path']))!=entry['sha256']:raise ValueError('Returned source version mismatch')
            item.metadata['edie']=dict(entry)
            item.media_reference.target_url='edie-proxy:'+entry['proxy']['path'] if entry.get('proxy') else entry['path']
    clips=compile_timeline(timeline);overlays=compile_overlays(timeline)
    cues=parse_srt(subtitles.read_text(encoding='utf-8-sig'))
    revision=commit(store,job,clips,media,cues,parent=base_revision,author='human',title=timeline.name or base.get('title','Human edit'),overlays=overlays)
    directory=store.root/'human_returns'/revision;directory.mkdir(parents=True)
    shutil.copyfile(incoming,directory/('received.'+incoming.suffix.lstrip('.')))
    shutil.copyfile(subtitles,directory/'received.srt')
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return revision

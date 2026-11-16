"""Offline review package from one immutable OTIO revision."""
import json
from pathlib import Path
import shutil
import subprocess
import uuid
import opentimelineio as otio
from .core import digest, probe, source, media_source
from .timeline import compile_timeline, compile_overlays, srt
from .analysis import atomic_json


def validate_export(path, expected, cues=()):
    from .timeline import validate_cues
    metadata=probe(path)
    video=next((s for s in metadata['streams'] if s['codec_type']=='video'),None)
    audio=next((s for s in metadata['streams'] if s['codec_type']=='audio'),None)
    if not video or not audio:raise ValueError('Export missing A/V stream')
    duration=float(metadata['format']['duration'])
    if abs(duration-expected)>0.3:raise ValueError('Export duration mismatch')
    skew=abs(float(video.get('duration',duration))-float(audio.get('duration',duration)))
    if skew>0.3:raise ValueError('Export A/V duration skew')
    validate_cues(cues,expected)
    subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(path),'-f','null','-'],check=True,capture_output=True,timeout=3600)
    # Detection is advisory: black frames and silence can be intentional.
    detect=subprocess.run(['ffmpeg','-hide_banner','-nostdin','-i',str(path),'-vf','blackdetect=d=0.5:pix_th=0.10,freezedetect=n=-60dB:d=3','-af','silencedetect=n=-50dB:d=3','-f','null','-'],capture_output=True,timeout=3600)
    findings=[line.strip() for line in detect.stderr.decode(errors='replace').splitlines() if any(x in line for x in ('black_start:','freeze_start:','silence_start:'))]
    return dict(duration=duration,av_duration_skew=skew,width=video['width'],height=video['height'],decode='passed',subtitle_bounds='passed',advisory_findings=findings,editorial_review='required',finishing_application_roundtrip='not_tested')


def package(store,revision,preview,media,language='en',allow_title_sidecar=False):
    import re
    if not re.fullmatch('[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*',language):raise ValueError('Invalid language code')
    record=store.get(revision,'revision')
    if (record.get('titles') or record.get('transitions')) and not allow_title_sidecar:raise ValueError('XML cannot preserve title/transition styling; explicitly accept effect sidecars before handoff')
    if 'otio' not in record:raise ValueError('OTIO revision required')
    timeline=otio.adapters.read_from_string(record['otio'],'otio_json')
    clips=compile_timeline(timeline)+compile_overlays(timeline)
    from .storage import admit
    unique={c['sha256']:c for c in clips}
    admit(store.root,sum(media_source(store,media,c).stat().st_size+(source(store.root,c['proxy']['path']).stat().st_size if c.get('proxy') else 0) for c in unique.values())+Path(preview).stat().st_size)
    report=validate_export(preview,timeline.duration().to_seconds(),record['cues'])
    root=store.root/'handoff'/revision/uuid.uuid4().hex
    root.mkdir(parents=True)
    linked=root/'media';linked.mkdir()
    originals=root/'originals';originals.mkdir()
    mapped={}
    for clip in clips:
        original=media_source(store,media,clip)
        if digest(original)!=clip['sha256']:raise ValueError('Source changed')
        editing=source(store.root,clip['proxy']['path']) if clip.get('proxy') else original
        editing_hash=clip['proxy']['sha256'] if clip.get('proxy') else clip['sha256']
        if digest(editing)!=editing_hash:raise ValueError('Editing media changed')
        name=editing_hash+editing.suffix.lower()
        if name not in mapped:
            # Independent copies: editor writes must never mutate source media.
            destination=linked/name
            shutil.copyfile(editing,destination)
            original_name=clip['sha256']+original.suffix.lower()
            shutil.copyfile(original,originals/original_name)
            mapped[name]=dict(path='media/'+name,sha256=editing_hash,original_path='originals/'+original_name,source_path=clip['path'],original_sha256=clip['sha256'],source_id=clip.get('source_id'),source_version=clip.get('version'),normalization=clip.get('proxy'))
    for track in timeline.tracks:
        for clip in track:
            if isinstance(clip,otio.schema.Clip):
                data=clip.metadata['edie']
                reference=data.get('proxy') or data
                suffix=Path(reference['path']).suffix.lower()
                clip.media_reference.target_url='media/'+reference['sha256']+suffix
    otio.adapters.write_to_file(timeline,str(root/'timeline.otio'))
    otio.adapters.write_to_file(timeline,str(root/'timeline.xml'),adapter_name='fcp_xml')
    returned=otio.adapters.read_from_file(str(root/'timeline.xml'),adapter_name='fcp_xml')
    if abs(returned.duration().to_seconds()-timeline.duration().to_seconds())>1/30:raise ValueError('XML duration roundtrip mismatch')
    before=sorted(timeline.tracks,key=lambda t:t.kind)
    after=sorted(returned.tracks,key=lambda t:t.kind)
    if len(before)!=len(after):raise ValueError('XML track count mismatch')
    for a,b in zip(before,after):
        if len(a)!=len(b):raise ValueError('XML clip count mismatch')
        for x,y in zip(a,b):
            if abs(x.duration().to_seconds()-y.duration().to_seconds())>1/30 or x.source_range!=y.source_range:raise ValueError('XML cut timing mismatch')
    report['xml_library_roundtrip']='passed'
    if record.get('transitions'):atomic_json(root/'transitions.json',record['transitions'])
    if record.get('titles'):
        report['title_compatibility']='Titles visible in preview; recreate from titles.json in finishing editor'
        atomic_json(root/'titles.json',record['titles'])
    tracks=record.get('subtitle_tracks',{language:record['cues']})
    for lang,cues in tracks.items():
        if not re.fullmatch('[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*',lang):raise ValueError('Invalid subtitle track language')
        (root/f'subtitles.{lang}.srt').write_text(srt(cues,timeline.duration().to_seconds()))
    atomic_json(root/'subtitle-cues.json',tracks)
    shutil.copyfile(preview,root/'preview.mp4')
    subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(preview),'-frames:v','1',str(root/'cover.jpg')],check=True,capture_output=True,timeout=60)
    (root/'README.txt').write_text('DRAFT FOR HUMAN REVIEW. Import timeline.xml into your finishing editor and relink the media/ directory if needed. Import subtitles separately. Preview is the reference. Linked editing media is normalized CFR/SDR; originals/ and the manifest retain the source mapping. Do not relink native VFR originals by frame number without conforming that mapping. XML library roundtrip has been tested; actual finishing-app compatibility remains unverified. No effects, grading or editable titles are promised. Review subtitle names and any partial utterances. This cover is a frame candidate, not a final designed thumbnail.\n')
    atomic_json(root/'posting.json',dict(status='draft_requires_review',title=record.get('title','Draft'),caption=record.get('title','Draft'),hashtags=[],publishing='external_operator_only'))
    atomic_json(root/'validation.json',report)
    manifest={'schema_version':1,'job':record['job'],'revision':revision,'status':'draft_review','source_mapping':list(mapped.values()),'files':[],'compatibility':report}
    for path in sorted(root.rglob('*')):
        if path.is_file():manifest['files'].append(dict(path=str(path.relative_to(root)),sha256=digest(path),bytes=path.stat().st_size))
    atomic_json(root/'manifest.json',manifest)
    return str(root)

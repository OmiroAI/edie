"""Canonical OTIO cut timeline and source-derived subtitle timings."""
import copy
from fractions import Fraction
import json
import math
import uuid
import opentimelineio as otio
from .core import source, digest, probe, media_source

RATE=30


def plain(value):
    if hasattr(value,'items'):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(str,int,float,bool,type(None))):return value
    return [plain(v) for v in value]


def frames(seconds):
    value=Fraction(str(seconds))*RATE
    return round(value)


def build(clips, media, title='Draft', overlays=(),store=None):
    timeline=otio.schema.Timeline(name=title)
    video=otio.schema.Track(name='Video',kind=otio.schema.TrackKind.Video)
    audio=otio.schema.Track(name='Dialogue',kind=otio.schema.TrackKind.Audio)
    for item in clips:
        path=media_source(store,media,item)
        if digest(path)!=item['sha256']:raise ValueError('Source changed')
        if item.get('proxy'):
            if store is None:raise ValueError('Proxy state required')
            path=source(store.root,item['proxy']['path'])
            if digest(path)!=item['proxy']['sha256']:raise ValueError('Proxy changed')
        meta=probe(path)
        start,end=frames(item['in']),frames(item['out'])
        duration=frames(float(meta['format']['duration']))
        if not 0<=start<end<=duration:raise ValueError('Invalid clip bounds')
        reference=otio.schema.ExternalReference(target_url=('edie-proxy:'+item['proxy']['path']) if item.get('proxy') else item['path'],available_range=otio.opentime.TimeRange(otio.opentime.RationalTime(0,RATE),otio.opentime.RationalTime(duration,RATE)))
        clip=otio.schema.Clip(name=item.get('name',path.stem),media_reference=reference,source_range=otio.opentime.TimeRange(otio.opentime.RationalTime(start,RATE),otio.opentime.RationalTime(end-start,RATE)),metadata={'edie':{**item,'clip_id':item.get('clip_id',uuid.uuid4().hex)}})
        video.append(clip)
        if any(s['codec_type']=='audio' for s in meta['streams']):audio.append(clip.deepcopy())
        else:audio.append(otio.schema.Gap(duration=otio.opentime.RationalTime(end-start,RATE)))
    timeline.tracks.extend([video,audio])
    if overlays:
        track=otio.schema.Track(name='B-roll',kind=otio.schema.TrackKind.Video)
        cursor=0
        for item in sorted(overlays,key=lambda x:x['at']):
            at=frames(item['at']);start=frames(item['in']);end=frames(item['out'])
            if at<cursor or at+end-start>frames(timeline.duration().to_seconds()):raise ValueError('B-roll overlaps or exceeds timeline')
            if at>cursor:track.append(otio.schema.Gap(duration=otio.opentime.RationalTime(at-cursor,RATE)))
            part=build([item],media,store=store).tracks[0][0].deepcopy()
            track.append(part);cursor=at+end-start
        timeline.tracks.append(track)
    return timeline


def compile_timeline(timeline):
    if len(timeline.tracks) not in (2,3) or timeline.tracks.effects:
        raise ValueError('Unsupported timeline structure')
    video,audio=timeline.tracks[0],timeline.tracks[1]
    if video.kind!=otio.schema.TrackKind.Video or audio.kind!=otio.schema.TrackKind.Audio or len(video)!=len(audio):raise ValueError('Unsupported track layout')
    if video.effects or audio.effects or video.source_range or audio.source_range:raise ValueError('Unsupported track effects or trims')
    compile_overlays(timeline)
    result=[]
    for v,a in zip(video,audio):
        if not isinstance(v,otio.schema.Clip) or v.effects or a.effects or not v.enabled or not a.enabled:raise ValueError('Unsupported clip/effect')
        if v.duration()!=a.duration():raise ValueError('Audio timing differs')
        if isinstance(a,otio.schema.Clip) and (v.source_range!=a.source_range or v.media_reference.target_url!=a.media_reference.target_url):raise ValueError('Independent audio edit unsupported')
        if not isinstance(a,(otio.schema.Clip,otio.schema.Gap)):raise ValueError('Unsupported audio item')
        data=plain(v.metadata['edie'])
        data.update(path=data['path'] if data.get('proxy') else v.media_reference.target_url,**{'in':v.source_range.start_time.to_seconds(),'out':v.source_range.end_time_exclusive().to_seconds(),'silent':isinstance(a,otio.schema.Gap)})
        result.append(data)
    return result


def cues_from_transcripts(clips, indexes):
    """Never shift a complete utterance onto a cut fragment. Flag partial cues."""
    cues=[];offset=0
    for clip_index,clip in enumerate(clips):
        index=indexes[clip['sha256']]
        for s in index['transcript']:
            begin=max(s['start'],clip['in']);end=min(s['end'],clip['out'])
            if begin>=end:continue
            partial=s['start']<clip['in']-0.05 or s['end']>clip['out']+0.05
            cues.append(dict(id=uuid.uuid4().hex,start=offset+begin-clip['in'],end=offset+end-clip['in'],text=s['text'].strip(),source_sha256=clip['sha256'],transcript_id=s['id'],clip_index=clip_index,source_start=begin,source_end=end,needs_review=partial,reason='Utterance crosses cut' if partial else None))
        offset+=clip['out']-clip['in']
    return cues


def validate_cues(cues,duration):
    last=0
    for c in cues:
        if not isinstance(c['text'],str) or not c['text'].strip() or '\n\n' in c['text']:raise ValueError('Invalid subtitle text')
        if not all(isinstance(c[k],(int,float)) and math.isfinite(c[k]) for k in ('start','end')) or not 0<=c['start']<c['end']<=duration+0.001 or c['start']<last-0.001:raise ValueError('Subtitle timing invalid/overlapping')
        last=c['end']


def srt(cues,duration):
    validate_cues(cues,duration)
    def stamp(value):
        ms=round(value*1000);seconds,ms=divmod(ms,1000);minutes,seconds=divmod(seconds,60);hours,minutes=divmod(minutes,60)
        return f'{hours:02}:{minutes:02}:{seconds:02},{ms:03}'
    return ''.join(f"{i}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}\n\n" for i,c in enumerate(cues,1))


def commit(store,job,clips,media,cues=None,parent=None,author='agent',title='Draft',overlays=(),titles=(),transitions=()):
    store.get(job,'job')
    if parent and store.get(parent,'revision')['job']!=job:raise ValueError('Wrong parent job')
    if author=='human' and any(abs(frames(c[k])/RATE-c[k])>1e-5 for c in list(clips)+list(overlays) for k in ('in','out')):raise ValueError('Returned edit timing is not representable at 30 fps; compatible timeline required')
    from .normalize import normalize
    clips=[{**c,'proxy':normalize(store,c,media)} for c in clips]
    overlays=[{**c,'proxy':normalize(store,c,media)} for c in overlays]
    timeline=build(clips,media,title,overlays,store)
    compiled=compile_timeline(timeline)
    cues=copy.deepcopy(cues or [])
    offsets=[];cursor=0
    for clip in compiled:
        offsets.append(cursor);cursor+=clip['out']-clip['in']
    for cue in cues:
        if 'clip_index' in cue:
            clip=compiled[cue['clip_index']]
            cue['start']=offsets[cue['clip_index']]+max(cue['source_start'],clip['in'])-clip['in']
            cue['end']=offsets[cue['clip_index']]+min(cue['source_end'],clip['out'])-clip['in']
    validate_cues(cues,timeline.duration().to_seconds())
    for graphic in titles:
        if set(graphic)!={'text','start','end'} or not isinstance(graphic['text'],str) or not 1<=len(graphic['text'])<=120 or '\n' in graphic['text']:raise ValueError('Invalid title')
        if not 0<=graphic['start']<graphic['end']<=timeline.duration().to_seconds():raise ValueError('Title outside timeline')
    cuts=[];cursor=0
    for clip in compiled[:-1]:
        cursor+=clip['out']-clip['in'];cuts.append(cursor)
    for transition in transitions:
        if set(transition)!={'kind','at','duration'} or transition['kind']!='dip_to_black':raise ValueError('Unsupported transition')
        if not 0<transition['duration']<=1 or not any(abs(transition['at']-cut)<1/60 for cut in cuts):raise ValueError('Transition must target a cut with duration <= 1 second')
    return store.put('revision',dict(job=job,clips=compiled,otio=otio.adapters.write_to_string(timeline,'otio_json'),cues=cues,parent=parent,author=author,title=title,overlays=compile_overlays(timeline),titles=list(titles),transitions=list(transitions)))


def compile_overlays(timeline):
    if len(timeline.tracks)<3:return []
    if len(timeline.tracks)>3:raise ValueError('Only one B-roll track supported')
    track=timeline.tracks[2]
    if track.kind!=otio.schema.TrackKind.Video or track.effects or track.source_range or not track.enabled:raise ValueError('Unsupported B-roll track')
    result=[];cursor=0
    for clip in track:
        if clip.effects or not clip.enabled:raise ValueError('Unsupported B-roll effect')
        if isinstance(clip,otio.schema.Clip):
            data=plain(clip.metadata['edie']);data.update(path=data['path'] if data.get('proxy') else clip.media_reference.target_url,at=cursor,**{'in':clip.source_range.start_time.to_seconds(),'out':clip.source_range.end_time_exclusive().to_seconds()})
            result.append(data)
        elif not isinstance(clip,otio.schema.Gap):raise ValueError('Unsupported B-roll item')
        cursor+=clip.duration().to_seconds()
    if cursor>timeline.tracks[0].duration().to_seconds()+0.001:raise ValueError('B-roll exceeds edit')
    return result

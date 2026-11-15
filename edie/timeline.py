"""Canonical OTIO cut timeline and source-derived subtitle timings."""
import copy
from fractions import Fraction
import json
import math
import uuid
import opentimelineio as otio
from .core import source, digest, probe

RATE=30

def frames(seconds):
    value=Fraction(str(seconds))*RATE
    return round(value)


def build(clips, media, title='Draft', overlays=()):
    timeline=otio.schema.Timeline(name=title)
    video=otio.schema.Track(name='Video',kind=otio.schema.TrackKind.Video)
    audio=otio.schema.Track(name='Dialogue',kind=otio.schema.TrackKind.Audio)
    for item in clips:
        path=source(media,item['path'])
        if digest(path)!=item['sha256']:raise ValueError('Source changed')
        meta=probe(path)
        start,end=frames(item['in']),frames(item['out'])
        duration=frames(float(meta['format']['duration']))
        if not 0<=start<end<=duration:raise ValueError('Invalid clip bounds')
        reference=otio.schema.ExternalReference(target_url=item['path'],available_range=otio.opentime.TimeRange(otio.opentime.RationalTime(0,RATE),otio.opentime.RationalTime(duration,RATE)))
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
            part=build([item],media).tracks[0][0].deepcopy()
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
        data=dict(v.metadata['edie'])
        data.update(path=v.media_reference.target_url,**{'in':v.source_range.start_time.to_seconds(),'out':v.source_range.end_time_exclusive().to_seconds(),'silent':isinstance(a,otio.schema.Gap)})
        result.append(data)
    return result


def cues_from_transcripts(clips, indexes):
    """Never shift a complete utterance onto a cut fragment. Flag partial cues."""
    cues=[];offset=0
    for clip in clips:
        index=indexes[clip['sha256']]
        for s in index['transcript']:
            begin=max(s['start'],clip['in']);end=min(s['end'],clip['out'])
            if begin>=end:continue
            partial=s['start']<clip['in']-0.05 or s['end']>clip['out']+0.05
            cues.append(dict(id=uuid.uuid4().hex,start=offset+begin-clip['in'],end=offset+end-clip['in'],text=s['text'].strip(),source_sha256=clip['sha256'],transcript_id=s['id'],needs_review=partial,reason='Utterance crosses cut' if partial else None))
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


def commit(store,job,clips,media,cues=None,parent=None,author='agent',title='Draft',overlays=()):
    store.get(job,'job')
    if parent and store.get(parent,'revision')['job']!=job:raise ValueError('Wrong parent job')
    timeline=build(clips,media,title,overlays)
    compiled=compile_timeline(timeline)
    cues=cues or []
    validate_cues(cues,timeline.duration().to_seconds())
    return store.put('revision',dict(job=job,clips=compiled,otio=otio.adapters.write_to_string(timeline,'otio_json'),cues=cues,parent=parent,author=author,title=title,overlays=compile_overlays(timeline)))


def compile_overlays(timeline):
    if len(timeline.tracks)<3:return []
    if len(timeline.tracks)>3:raise ValueError('Only one B-roll track supported')
    track=timeline.tracks[2]
    if track.kind!=otio.schema.TrackKind.Video or track.effects or track.source_range or not track.enabled:raise ValueError('Unsupported B-roll track')
    result=[];cursor=0
    for clip in track:
        if clip.effects or not clip.enabled:raise ValueError('Unsupported B-roll effect')
        if isinstance(clip,otio.schema.Clip):
            data=dict(clip.metadata['edie']);data.update(path=clip.media_reference.target_url,at=cursor,**{'in':clip.source_range.start_time.to_seconds(),'out':clip.source_range.end_time_exclusive().to_seconds()})
            result.append(data)
        elif not isinstance(clip,otio.schema.Gap):raise ValueError('Unsupported B-roll item')
        cursor+=clip.duration().to_seconds()
    if cursor>timeline.tracks[0].duration().to_seconds()+0.001:raise ValueError('B-roll exceeds edit')
    return result

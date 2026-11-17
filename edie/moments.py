"""Read-only editorial moments: one dialogue beat, multiple synchronized pictures."""
from .capture import Capture, finite
from .workflow import identity


def subtract(start,end,covered):
    cursor=start
    for a,b in sorted(covered):
        a=max(start,a);b=min(end,b)
        if b<=cursor or a>=end:continue
        if a>cursor+.001:yield cursor,a
        cursor=max(cursor,b)
    if cursor<end-.001:yield cursor,end


def project(capture,rows):
    sources={r['source_id']:r for r in rows};angles={};covered={};relations=[]
    for group in capture['groups']:
        if group['status'] not in ('confirmed','proposed'):continue
        valid=[]
        for m in group['members']:
            r=sources.get(m['source_id'])
            if not r or r.get('disposition')=='exclude' or not m.get('included',True) or not finite(m.get('offset')):continue
            if any(m.get(k)!=r.get(k) for k in ('version','sha256')):continue
            if group['status']!='confirmed' and m['source_id']!=group['anchor_source_id'] and m.get('alignment_review')!='automatic':continue
            valid.append(m)
        audio=next((m for m in group['members'] if m['source_id']==group['primary_audio_source_id']),None)
        if not audio:continue
        primary=[m for m in valid if m['camera_id']==audio['camera_id']]
        others=[m for m in valid if m['camera_id']!=audio['camera_id']]
        for a in primary:
            ar=sources[a['source_id']]
            for b in others:
                br=sources[b['source_id']];shift=a['offset']-b['offset']
                lo=max(0,-shift);hi=min(ar['duration'],br['duration']-shift)
                if hi<=lo:continue
                relations.append(dict(primary=a['source_id'],picture=b['source_id'],primary_start=lo,primary_end=hi,shift=shift,group_id=group['id']))
                # Suppress duplicate picture rows only where primary segment evidence exists.
                for part in ar['segments']['items']:
                    start=max(part['start'],lo);end=min(part['end'],hi)
                    if end<=start:continue
                    covered.setdefault(b['source_id'],[]).append((start+shift,end+shift))
                    for other in br['segments']['items']:
                        x=max(start,other['start']-shift);y=min(end,other['end']-shift)
                        if y<=x:continue
                        angles.setdefault((a['source_id'],part['id']),[]).append(dict(source_id=b['source_id'],segment_id=other['id'],path=br['path'],camera_id=b['camera_id'],start=x+shift,end=y+shift,dialogue_start=x,dialogue_end=y,selection=other['selection'],eligible=other['selection']!='rejected',sync_group_id=group['id'],sync_capture_revision=capture['revision'],sync_status=group['status']))
    result=[]
    for row in rows:
        for part in row['segments']['items']:
            ranges=list(subtract(part['start'],part['end'],covered.get(row['source_id'],[])))
            for start,end in ranges:
                fragment=start!=part['start'] or end!=part['end']
                attached=angles.get((row['source_id'],part['id']),[])
                result.append(dict(id=identity([row['source_id'],part['id'],start,end] if fragment else [row['source_id'],part['id']])[:24],source_id=row['source_id'],segment_id=part['id'],start=start,end=end,fragment=fragment,angles=attached,kind='multicam' if attached else 'standalone',score=part['score'],selection=part['selection']))
    return dict(schema_version=1,capture_revision=capture['revision'],items=result,relations=relations,raw_segment_count=sum(len(r['segments']['items']) for r in rows),policy='One dialogue segment owns the moment and its score. Aligned detail-camera audio is duplicate evidence; use its picture as muted coverage. Unaligned material remains separate.')


def read(store,job):
    from .editorial import footage
    return project(Capture(store).get(job),footage(store,job))


def validate_dialogue(store,job,clips):
    """Do not select the same synced dialogue again through a detail-camera mic."""
    model=read(store,job)
    for clip in clips:
        for rel in model['relations']:
            if clip['source_id']==rel['picture'] and clip['in']<rel['primary_end']+rel['shift']-.001 and clip['out']>rel['primary_start']+rel['shift']+.001:
                raise ValueError('Aligned picture coverage duplicates dialogue; use the primary moment and a muted overlay')

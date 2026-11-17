"""Audio-led script read model and validated synchronous picture coverage."""
from .capture import Capture,finite
from .workflow import identity


def script_layers(script):
    """A projection: existing script hashes and approvals are not rewritten."""
    if not script:return dict(schema_version=1,audio=[],picture=[],graphics=[])
    audio=[];picture=[];cursor=0
    for n,clip in enumerate(script.get('clips',[])):
        length=clip['out']-clip['in'];base=dict(beat=n+1,at=cursor,duration=length,source_id=clip.get('source_id'),path=clip['path'],start=clip['in'],end=clip['out'],purpose=clip.get('purpose',''))
        audio.append({**base,'role':'dialogue','audio':'source'})
        picture.append({**base,'role':'base_picture','track':1})
        cursor+=length
    for clip in script.get('overlays',[]):
        picture.append(dict(at=clip['at'],duration=clip['out']-clip['in'],source_id=clip.get('source_id'),path=clip['path'],start=clip['in'],end=clip['out'],purpose=clip.get('purpose',''),role=clip.get('picture_role','b_roll'),track=2,audio='muted',sync=clip.get('sync')))
    return dict(schema_version=1,duration=cursor,audio=audio,picture=picture,graphics=script.get('titles',[]),policy='Primary clips carry continuous dialogue. Picture coverage is muted; subtitles follow dialogue.')


def resolve_overlay(agent,job,item,clips):
    """Independent B-roll uses explicit source trims; camera switches use confirmed sync."""
    if 'sync_group_id' not in item:
        resolved=agent.resolve([{k:v for k,v in item.items() if k!='at'}])[0]
        return {**resolved,'at':item['at'],'picture_role':'b_roll','audio':'muted'}
    if set(item)!={'sync_group_id','sync_capture_revision','source_id','segment_id','at','duration','purpose'}:raise ValueError('Invalid alternate camera fields')
    config=Capture(agent.store).get(job)
    if item['sync_capture_revision']!=config['revision']:raise ValueError('Capture alignment changed')
    group=next((g for g in config['groups'] if g['id']==item['sync_group_id']),None)
    if group is None or group['status']!='confirmed':raise ValueError('Confirm camera synchronisation before using alternate angles')
    at=item['at'];length=item['duration']
    if not finite(at) or not finite(length) or at<0 or length<=0:raise ValueError('Invalid picture timing')
    cursor=0;base=None
    for clip in clips:
        stop=cursor+clip['out']-clip['in']
        if cursor<=at and at+length<=stop+.001:base=clip;break
        cursor=stop
    if base is None:raise ValueError('Camera switch must fit one dialogue beat')
    members={m['source_id']:m for m in group['members'] if m.get('included',True)}
    if base['source_id'] not in members or item['source_id'] not in members:raise ValueError('Both angles must belong to the confirmed session')
    a=members[base['source_id']];b=members[item['source_id']]
    values=agent.indexes()
    for m in (a,b):
        if m['source_id'] not in values or any(m[k]!=values[m['source_id']]['source'][k] for k in ('version','sha256')):raise ValueError('Synchronised source changed')
    begin=base['in']+(at-cursor)+a['offset']-b['offset']
    resolved=agent.resolve([dict(source_id=item['source_id'],segment_id=item['segment_id'],**{'in':begin,'out':begin+length},purpose=item['purpose'])])[0]
    return {**resolved,'at':at,'picture_role':'alternate_camera','audio':'muted','sync':dict(group_id=group['id'],capture_revision=config['revision'],group_hash=identity(group),audio_source_id=base['source_id'])}


def validate_sync(store,job,script):
    if script.get('clips'):
        from .moments import validate_dialogue
        validate_dialogue(store,job,script['clips'])
    config=None
    for item in script.get('overlays',[]):
        if not item.get('sync'):continue
        config=config or Capture(store).get(job);ref=item['sync']
        group=next((g for g in config['groups'] if g['id']==ref['group_id']),None)
        if not group or group['status']!='confirmed' or identity(group)!=ref['group_hash']:raise ValueError('Sync group changed; reconcile picture coverage')

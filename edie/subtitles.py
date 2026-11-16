"""Revisioned subtitle corrections/translations; original transcripts stay intact."""
import copy
import re
from .timeline import validate_cues


def revise(store,revision,language,edits,author='human'):
    if not re.fullmatch('[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*',language):raise ValueError('Invalid subtitle language')
    base=store.get(revision,'revision')
    if 'cues' not in base:raise ValueError('Editable subtitle cues required')
    if not isinstance(edits,list) or not edits:raise ValueError('Subtitle edits required')
    record=copy.deepcopy(base);default=store.get(base['job'],'job')['brief']['language']
    tracks=record.setdefault('subtitle_tracks',{default:copy.deepcopy(base['cues'])})
    cues=copy.deepcopy(tracks.get(language,base['cues']))
    by_id={c['id']:c for c in cues};seen=set()
    if language not in tracks and {e['id'] for e in edits}!=set(by_id):raise ValueError('A new language must cover every cue; partial translation is not publishable')
    for edit in edits:
        if set(edit)!={'id','text','reason'} or edit['id'] not in by_id or edit['id'] in seen:raise ValueError('Invalid or duplicate subtitle edit')
        if not isinstance(edit['text'],str) or not 0<len(edit['text'].strip())<=1000 or not isinstance(edit['reason'],str):raise ValueError('Subtitle text and reason required')
        cue=by_id[edit['id']];cue.setdefault('original_text',cue['text']);cue['text']=edit['text'];cue['correction_reason']=edit['reason'];cue['meaning_review']='required' if author=='agent' else 'human_supplied';seen.add(edit['id'])
    duration=sum(c['out']-c['in'] for c in base['clips']);validate_cues(cues,duration)
    tracks[language]=cues
    if language==default:record['cues']=cues
    record.update(parent=revision,author=author)
    return store.put('revision',record)

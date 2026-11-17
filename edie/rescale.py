"""Explicit operator migration of legacy five-point semantic scores to 100 points."""
import json
from .segments import Segments
from .classification import Classifications


def rescale(store, job):
    from .editorial import indexes
    repo=Segments(store);files=Classifications(store);count=0
    for index in indexes(store,job).values():
        entry=index['source'];old=repo.get(job,entry);items=old['items'];changed=False
        for item in items:
            if item.get('origin')=='human' or item.get('score_scale')==100:continue
            if item.get('profile')!=2:continue
            for key in ('score','story_fit'):
                value=item.get(key)
                if isinstance(value,int) and 0<value<=5:
                    item.setdefault('original_five_point_scores',{})[key]=value
                    item[key]=value*20;changed=True
            item['score_scale']=100
        if changed:
            with store.db:
                store.db.execute('BEGIN IMMEDIATE')
                current=repo.get(job,entry)
                if current['revision']!=old['revision']:raise ValueError('Segments changed during rescale')
                body=dict(items=items,human=old['human'])
                store.db.execute('UPDATE segments SET revision=?,body=? WHERE job=? AND source_key=?',(old['revision']+1,json.dumps(body),job,repo.key(entry)))
                store.db.execute('INSERT INTO segment_events(job,source_key,revision,body) VALUES (?,?,?,?)',(job,repo.key(entry),old['revision']+1,json.dumps(dict(actor='operator-score-rescale',**body))))
            count+=1
        record=files.get(job,entry);suggestion=record['suggestion']
        if suggestion and suggestion.get('intake_profile')==1:
            score=max((p['score'] for p in items if p.get('selection')!='rejected'),default=0)
            # Preserve disposition, reason, human override and duplicate priority.
            if suggestion.get('duplicate_of'):score=0
            if suggestion.get('score')!=score:
                files.save(job,entry,{**suggestion,'score':score},actor='operator-score-rescale')
    return count

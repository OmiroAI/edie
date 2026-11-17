"""Private capture/session records, conservative audio alignment and sync previews."""
import argparse
import copy
import json
import math
import subprocess
import time
import uuid
from pathlib import Path
from .core import Store,source,digest
from .scope import library_job
from .workflow import identity


def group_by_id(config,identifier):
    group=next((g for g in config['groups'] if g['id']==identifier),None)
    if group is None:raise ValueError('Unknown sync group')
    return group

def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


class Capture:
    def __init__(self,store):
        self.store=store;self.db=store.db
        self.db.execute('CREATE TABLE IF NOT EXISTS captures(job TEXT PRIMARY KEY,revision INTEGER,body TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS capture_events(id INTEGER PRIMARY KEY,job TEXT,revision INTEGER,actor TEXT,body TEXT)')

    def get(self,job):
        job=library_job(self.store,job)
        row=self.db.execute('SELECT revision,body FROM captures WHERE job=?',(job,)).fetchone()
        return dict(revision=row[0],**json.loads(row[1])) if row else dict(revision=0,schema_version=1,mode='audio_led',sources={},groups=[])

    def save(self,job,body,expected,actor):
        job=library_job(self.store,job)
        if type(expected)!=int:raise ValueError('Capture revision required')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');current=self.get(job)
            if current['revision']!=expected:raise ValueError('Capture changed; refresh')
            body={k:v for k,v in body.items() if k!='revision'}
            self.db.execute('INSERT OR REPLACE INTO captures VALUES (?,?,?)',(job,expected+1,json.dumps(body,allow_nan=False)))
            self.db.execute('INSERT INTO capture_events(job,revision,actor,body) VALUES (?,?,?,?)',(job,expected+1,actor,json.dumps(body,allow_nan=False)))
        return self.get(job)

    def configure(self,job,body):
        from .editorial import indexes
        values=indexes(self.store,job);old=self.get(job)
        if body['mode'] not in ('audio_led','multicam'):raise ValueError('Unknown capture mode')
        cameras=body['sources']
        if not isinstance(cameras,dict) or set(cameras)!=set(values):raise ValueError('Map each current source')
        for key,value in cameras.items():
            if set(value)!={'camera_id','role_hint'} or not isinstance(value['camera_id'],str) or not 1<=len(value['camera_id'])<=80 or value['role_hint'] not in ('dialogue','detail','unknown'):raise ValueError('Invalid camera metadata')
        # Camera identity is independent from moment labels and source Keep/Exclude.
        return self.save(job,{**old,'mode':body['mode'],'sources':cameras},body['expected_revision'],'operator-configure')

    def discover(self,job,body):
        from .editorial import indexes
        from .tasks import Tasks
        values=indexes(self.store,job);old=self.get(job)
        ids=body['source_ids'];anchor=body['anchor_source_id'];audio=body['primary_audio_source_id']
        if not isinstance(ids,list) or not 2<=len(ids)<=32 or len(set(ids))!=len(ids) or any(k not in values for k in ids) or anchor not in ids or audio not in ids:raise ValueError('Invalid session sources')
        if any(k not in old['sources'] for k in ids):raise ValueError('Assign camera identities first')
        group=dict(id=uuid.uuid4().hex,name=body.get('name','Camera session')[:120],anchor_source_id=anchor,primary_audio_source_id=audio,status='proposed',members=[{**values[k]['source'],'camera_id':old['sources'][k]['camera_id'],'offset':0.0 if k==anchor else None,'included':True} for k in ids])
        result=self.save(job,{**old,'mode':'multicam','groups':old['groups']+[group]},body['expected_revision'],'operator-discover')
        payload=dict(action='sync_index',group_id=group['id'],capture_revision=result['revision'])
        task=Tasks(self.db).submit(library_job(self.store,job),'sync:'+group['id'],payload)
        return dict(capture=result,task=task)

    def reject(self,job,body):
        old=self.get(job);groups=copy.deepcopy(old['groups'])
        group=group_by_id({'groups':groups},body['group_id']);group['status']='rejected'
        return self.save(job,{**old,'groups':groups},body['expected_revision'],'human-reject-sync')

    def confirm(self,job,body):
        from .editorial import indexes
        values=indexes(self.store,job);old=self.get(job);groups=copy.deepcopy(old['groups'])
        group=group_by_id({'groups':groups},body['group_id'])
        if group['status']=='confirmed':raise ValueError('Already confirmed; propose a new group to realign')
        offsets=body['offsets'];included=body['included']
        known={m['source_id'] for m in group['members']}
        if not isinstance(included,list) or len(set(included))!=len(included) or len(included)<2 or not set(included)<=known or set(offsets)!=set(included):raise ValueError('Select at least two aligned sources')
        if group['anchor_source_id'] not in included or offsets[group['anchor_source_id']]!=0:raise ValueError('Anchor must remain at zero')
        audio=body['primary_audio_source_id']
        if audio not in included:raise ValueError('Audio source must be included')
        for m in group['members']:
            key=m['source_id'];m['included']=key in included
            if not m['included']:continue
            if key not in values or any(m[k]!=values[key]['source'][k] for k in ('version','sha256')):raise ValueError('Capture source changed')
            if not finite(offsets[key]) or abs(offsets[key])>86400:raise ValueError('Invalid sync offset')
            if abs(m.get('drift_seconds') or 0)>.08:raise ValueError('Clock drift needs correction or exclusion before constant-offset sync')
            anchor_duration=values[group['anchor_source_id']].get('duration')
            member_duration=values[key].get('duration')
            if anchor_duration is not None and member_duration is not None and min(anchor_duration,offsets[key]+member_duration)-max(0,offsets[key])<1:raise ValueError('Included cameras need at least one second of shared coverage')
            m['offset']=offsets[key]
        group.update(status='confirmed',primary_audio_source_id=audio,confirmed_at=time.time())
        return self.save(job,{**old,'groups':groups},body['expected_revision'],'human-confirm-sync')


def proxy(store,job,entry):
    from .editorial import footage
    from .tasks import Tasks
    row=next(r for r in footage(store,job) if r['source_id']==entry['source_id'])
    if row['version']!=entry['version'] or row['sha256']!=entry['sha256']:raise ValueError('Sync source changed')
    if row['proxy_state']!='completed':raise ValueError('Prepare source review copies before synchronisation')
    task=Tasks(store.db).get(row['proxy_task']);result=task['result'];path=source(store.root,result['path'])
    if digest(path)!=result['sha256']:raise ValueError('Review copy changed')
    if result.get('duration',0)>7200:raise ValueError('Split recordings longer than two hours into scoped sync sessions')
    return path,result


def envelope(path):
    import numpy as np
    raw=subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(path),'-vn','-ac','1','-ar','8000','-f','f32le','pipe:1'],capture_output=True,timeout=180,check=True).stdout
    samples=np.frombuffer(raw,dtype='<f4');samples=samples[:len(samples)//80*80]
    if len(samples)<80000:raise ValueError('At least ten seconds of shared audio required')
    if not np.isfinite(samples).all():raise ValueError('Non-finite decoded audio')
    return np.log1p(np.sqrt(np.mean(samples.reshape(-1,80)**2,axis=1))*100)


def match_window(reference,query):
    import numpy as np
    n=len(query)
    if n<400 or n>len(reference) or np.std(query)<.015:raise ValueError('Insufficient distinctive audio')
    centered=query-query.mean();size=1<<(len(reference)+n-1).bit_length()
    cross=np.fft.irfft(np.fft.rfft(reference,size)*np.fft.rfft(centered[::-1],size),size)[n-1:len(reference)]
    sums=np.r_[0,np.cumsum(reference)];squares=np.r_[0,np.cumsum(reference**2)]
    variance=np.maximum((squares[n:]-squares[:-n])-(sums[n:]-sums[:-n])**2/n,1e-12)
    scores=cross/np.sqrt(variance*np.sum(centered**2));best=int(np.argmax(scores));peak=float(scores[best])
    other=scores.copy();other[max(0,best-200):best+201]=-1
    margin=peak-float(np.max(other))
    return best/100,peak,margin


def align(reference,member):
    # Three independent windows detect ambiguous matches and clock drift.
    length=min(2000,len(member)//3);starts=sorted(set([0,(len(member)-length)//2,len(member)-length]));matches=[]
    for at in starts:
        try:
            where,score,margin=match_window(reference,member[at:at+length])
            matches.append(dict(member_time=at/100,anchor_time=where,offset=where-at/100,correlation=round(score,4),margin=round(margin,4)))
        except ValueError:pass
    good=[m for m in matches if m['correlation']>=.65 and m['margin']>=.08]
    drift=(good[-1]['offset']-good[0]['offset']) if len(good)>1 else None
    stable=len(good)>=2 and max(m['offset'] for m in good)-min(m['offset'] for m in good)<=.08
    return dict(offset=round(sum(m['offset'] for m in good)/len(good),3) if stable else None,
                confidence='strong_candidate' if stable else 'uncertain',drift_seconds=drift,matches=matches,
                note='Shared-audio proposal; review before use.' if stable else 'Ambiguous audio, insufficient overlap or clock drift; manual alignment required.')


def synchronize(store,task):
    repo=Capture(store);config=repo.get(task['job'])
    if config['revision']!=task['payload']['capture_revision']:raise ValueError('Sync configuration changed')
    groups=copy.deepcopy(config['groups']);group=group_by_id({'groups':groups},task['payload']['group_id'])
    if group['status']!='proposed':raise ValueError('Only proposed groups can be analysed')
    anchor=next(m for m in group['members'] if m['source_id']==group['anchor_source_id'])
    reference=envelope(proxy(store,task['job'],anchor)[0])
    for member in group['members']:
        if member['source_id']==anchor['source_id']:continue
        path,_=proxy(store,task['job'],member)
        try:member.update(align(reference,envelope(path)))
        except (ValueError,subprocess.SubprocessError):member.update(offset=None,confidence='uncertain',drift_seconds=None,matches=[],note='No usable shared audio; manual alignment required.')
    group['analysed_at']=time.time()
    result=repo.save(task['job'],{**config,'groups':groups},config['revision'],'local-audio-sync')
    return dict(kind='sync_index',capture_revision=result['revision'],group_id=group['id'],matched=sum(m.get('offset') is not None for m in group['members'])-1)


def sync_preview(store,task):
    config=Capture(store).get(task['job']);p=task['payload']
    if config['revision']!=p['capture_revision']:raise ValueError('Sync preview stale')
    group=group_by_id(config,p['group_id'])
    anchor=next(m for m in group['members'] if m['source_id']==group['anchor_source_id']);member=next(m for m in group['members'] if m['source_id']==p['source_id'])
    offset=p.get('offset',member.get('offset'))
    if not finite(offset):raise ValueError('Provide a candidate offset')
    a,ar=proxy(store,task['job'],anchor);b,br=proxy(store,task['job'],member)
    begin=max(0,offset)+max(0,min(ar['duration'],offset+br['duration'])-max(0,offset))/2
    length=min(8,ar['duration']-begin,br['duration']-(begin-offset))
    if length<1:raise ValueError('No shared video range')
    from .storage import admit
    admit(store.root,4*1024*1024)
    folder=store.root/'sync-previews';folder.mkdir(exist_ok=True);target=folder/(uuid.uuid4().hex+'.mp4')
    vf='scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2,setsar=1'
    filters=f'[0:v]{vf},setpts=PTS-STARTPTS[a];[1:v]{vf},setpts=PTS-STARTPTS[b];[a][b]hstack[v];[0:a]aresample=48000,pan=mono|c0=c0,asetpts=PTS-STARTPTS[x];[1:a]aresample=48000,pan=mono|c0=c0,asetpts=PTS-STARTPTS[y];[x][y]join=inputs=2:channel_layout=stereo[audio]'
    try:
        subprocess.run(['ffmpeg','-v','error','-nostdin','-ss',str(begin),'-i',str(a),'-ss',str(begin-offset),'-i',str(b),'-t',str(length),'-filter_complex',filters,'-map','[v]','-map','[audio]','-r','30','-c:v','libx264','-threads','2','-c:a','aac','-movflags','+faststart',str(target)],capture_output=True,check=True,timeout=90)
    except Exception:target.unlink(missing_ok=True);raise
    return dict(kind='sync_preview',path=str(target.relative_to(store.root)),sha256=digest(target),duration=length,group_id=group['id'],capture_revision=config['revision'],anchor_time=begin,member_time=begin-offset,offset=offset,audio='Anchor in left channel; other camera in right channel')


def main():
    p=argparse.ArgumentParser();p.add_argument('--state',required=True);p.add_argument('--task');p.add_argument('--worker',action='store_true');a=p.parse_args()
    if a.task:
        from .tasks import Tasks
        s=Store(a.state);task=Tasks(s.db).get(a.task)
        try:print(json.dumps(synchronize(s,task) if task['payload']['action']=='sync_index' else sync_preview(s,task)))
        finally:s.db.close()
        return
    from .worker import run_once
    while True:
        worked=run_once(a.state,None,'sync_index') or run_once(a.state,None,'sync_preview')
        if not worked:time.sleep(2)

if __name__=='__main__':main()

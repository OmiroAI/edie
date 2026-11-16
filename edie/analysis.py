"""Restartable, source-versioned speech and visual indexing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid
from .context import canonical
from .core import Store, digest, probe, source
from .index import Catalogue
from .models import Route
from .preprocess import overview


def atomic_json(path, value):
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_bytes(canonical(value))
    temporary.replace(path)


def analyse(store, entry, media, routes, language=None):
    from .storage import admit
    admit(store.root, 32*1024*1024)
    local = source(media, entry['path'])
    if digest(local) != entry['sha256']:
        raise ValueError('Source content changed')
    settings = {'version': 3, 'sha256': entry['sha256'], 'routes': routes, 'language': language}
    key = hashlib.sha256(canonical(settings)).hexdigest()
    root = store.root/'index'/key
    root.mkdir(parents=True, exist_ok=True)
    prior_key=hashlib.sha256(canonical({**settings,'version':2})).hexdigest()
    prior_root=store.root/'index'/prior_key
    complete = root/'index.json'
    from .adaptive import upgrade
    speech_complete=root/'speech-index.json'
    if complete.exists() or speech_complete.exists():
        prior=json.loads((complete if complete.exists() else speech_complete).read_text())
        prior['source']=entry
        return upgrade(store,prior,media,routes['vision'])
    metadata = probe(local)
    duration = float(metadata['format']['duration'])
    transcripts, usage, timing_issues = [], [], []
    if any(s['codec_type']=='audio' for s in metadata['streams']):
        start = 0
        while start < duration:
            length = min(30, duration-start)
            record = root/f'speech-{start}.json'
            if not record.exists() and (prior_root/record.name).exists():
                atomic_json(record,json.loads((prior_root/record.name).read_text()))
            if record.exists():
                cached = json.loads(record.read_text())
            else:
                audio = root/f'audio-{start}.wav'
                subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(start),'-i',str(local),'-t',str(length),'-vn','-ac','1','-ar','16000',str(audio)],check=True,capture_output=True,timeout=600)
                result, measured = Route(routes['speech']).transcribe(audio, length, language)
                cached = {'offset': start, 'result': result, 'usage': measured}
                atomic_json(record,cached)
                audio.unlink()
            for i,s in enumerate(cached['result']['segments']):
                if not s.get('timing_valid', True):
                    timing_issues.append({'chunk_offset': start, 'segment': s, 'issue': 'Invalid model timestamps; manual alignment required'})
                    continue
                transcripts.append({**s,'id':f'{start}:{i}','start':s['start']+start,'end':s['end']+start})
            usage.append(cached['usage'])
            start += 30
    result = {'analysis_version':3,'schema_version':1,'source':entry,'duration':duration,'media':metadata,'transcript':transcripts,
              'visual':[],'usage':usage,'transcript_issues':timing_issues,'coverage':{'speech':'full audio in 30s chunks; invalid model timing explicitly flagged','vision':'pending adaptive pass'}}
    atomic_json(speech_complete,result)
    return upgrade(store,result,media,routes['vision'])


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--state',required=True);p.add_argument('--media',required=True)
    p.add_argument('--routes',required=True);p.add_argument('--manifest',required=True)
    p.add_argument('--language');args=p.parse_args()
    store=Store(args.state)
    os.environ["EDIE_USAGE_FILE"]=str(store.root/"usage.jsonl")
    entries=json.loads(Path(args.manifest).read_text())
    Catalogue(store).ingest(entries,args.media)
    routes=json.loads(Path(args.routes).read_text())
    for entry in entries:
        result=analyse(store,entry,args.media,routes,args.language)
        print(json.dumps({'source_id':entry['source_id'],'segments':len(result['transcript']),'visual_chunks':len(result['visual'])}),flush=True)

if __name__=='__main__':main()

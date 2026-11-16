"""CFR editing media with explicit original-source provenance and HDR conversion."""
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import uuid
from .core import source,digest,probe,media_source
from .context import canonical
from .analysis import atomic_json


def normalize(store,entry,media):
    original=media_source(store,media,entry)
    if digest(original)!=entry['sha256']:raise ValueError('Source changed before normalization')
    key=hashlib.sha256(canonical(dict(source_sha256=entry['sha256'],profile='editing-cfr30-sdr-v1'))).hexdigest()
    root=store.root/'proxies'/key;root.mkdir(parents=True,exist_ok=True)
    with (root/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        manifest=root/'source-map.json'
        if manifest.exists():
            result=json.loads(manifest.read_text())
            path=source(store.root,result['path'])
            if digest(path)!=result['sha256']:raise ValueError('Editing proxy corrupted')
            return result
        meta=probe(original);video=next(s for s in meta['streams'] if s['codec_type']=='video')
        duration=round(float(video.get('duration',meta['format']['duration']))*30)/30
        origin=float(video.get('start_time',meta['format'].get('start_time',0)))
        container_origin=float(meta['format'].get('start_time',0))
        if abs(origin-container_origin)>0.1:raise ValueError('Source stream-origin mapping needs explicit review')
        from .storage import admit
        admit(store.root,int(duration*4_000_000))
        path=root/(uuid.uuid4().hex+'.mp4')
        filters=['setpts=PTS-STARTPTS','fps=fps=30:start_time=0:round=near']
        hdr=video.get('color_transfer') in ('smpte2084','arib-std-b67')
        if hdr:filters+=['zscale=t=linear:npl=100','format=gbrpf32le','zscale=p=bt709','tonemap=tonemap=hable:desat=0','zscale=t=bt709:m=bt709:r=tv']
        filters+=['scale=trunc(iw/2)*2:trunc(ih/2)*2','setsar=1','format=yuv420p']
        command=['ffmpeg','-v','error','-nostdin','-i',str(original)]
        silent=not any(s['codec_type']=='audio' for s in meta['streams'])
        if silent:command+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
        command+=['-t',str(duration),'-map','0:v:0','-map','1:a:0' if silent else '0:a:0','-vf',','.join(filters),'-af','aresample=async=1:first_pts=0','-c:v','libx264','-preset','veryfast','-crf','18','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-map_metadata','-1','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-movflags','+faststart',str(path)]
        subprocess.run(command,check=True,capture_output=True,timeout=7200)
        actual=probe(path);stream=next(s for s in actual['streams'] if s['codec_type']=='video')
        if stream['r_frame_rate']!='30/1' or abs(float(actual['format']['duration'])-duration)>0.15:raise ValueError('Normalized timing validation failed')
        # Rotation has been applied by FFmpeg; metadata is cleared for finishing.
        if any(abs(d.get('rotation',0))>0 for d in stream.get('side_data_list',[])):raise ValueError('Rotation metadata remained on normalized media')
        result=dict(path=str(path.relative_to(store.root)),sha256=digest(path),duration=duration,rate=30,width=stream['width'],height=stream['height'],original_sha256=entry['sha256'],original_source_id=entry.get('source_id'),original_version=entry.get('version'),original_video_start=origin,original_nominal_rate=video.get('r_frame_rate'),original_average_rate=video.get('avg_frame_rate'),hdr_to_sdr=hdr,mapping='Normalized frame n samples source presentation time n/30 seconds from first video presentation; nearest-frame sampling, not original frame-number equivalence',profile='editing-cfr30-sdr-v1')
        atomic_json(manifest,result)
        return result

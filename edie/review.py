"""Local, sampled-frame review of the actual rendered artifact."""
from pathlib import Path
from .core import digest
from .models import Route
from .preprocess import overview


def review(store,path,route,brief):
    path=Path(path).resolve()
    relative=str(path.relative_to(store.root))
    frames=overview(store,dict(path=relative,sha256=digest(path)),store.root,count=8,long_edge=512)
    prompt=('Review these ordered frames from the actual edited preview. Goal: '+brief['goal']+'. '
            'Identify black/blank frames, wrong orientation, hidden subjects, composition problems, legibility issues and whether visual progression makes sense. '
            'Give timestamped findings and uncertainty. These are sparse frames, not continuous video or audio; do not claim speech timing, audio quality or complete coverage. '
            'Soft subtitles may not appear in extracted video frames. Do not score their readability as passed. Maximum 200 words.')
    answer,usage=Route(route).chat(prompt,frames)
    return dict(findings=answer,coverage={'artifact_sha256':digest(path),'frame_times':[f['seconds'] for f in frames],'audio':'not heard','subtitles':'not visually assessed','continuous_motion':'not assessed'},usage=usage)

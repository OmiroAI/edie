"""Conservative local resource admission; never deletes source media."""
import os
from pathlib import Path
import shutil


def admit(root, estimate_bytes=0):
    root=Path(root)
    minimum=int(os.getenv('EDIE_MIN_FREE_BYTES',str(2*1024**3)))
    maximum=int(os.getenv('EDIE_MAX_STATE_BYTES',str(100*1024**3)))
    if min(minimum,maximum,estimate_bytes)<0:raise ValueError('Invalid storage limits')
    used=sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink())
    free=shutil.disk_usage(root).free
    if used+estimate_bytes>maximum or free-estimate_bytes<minimum:raise ValueError('Storage limit reached; operator cleanup required')
    return dict(state_bytes=used,free_bytes=free,estimated_additional_bytes=estimate_bytes,maximum_state_bytes=maximum,minimum_free_bytes=minimum)

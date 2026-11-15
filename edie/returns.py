"""Broker-ingested human masters stay immutable and replace rough cuts on approval."""
from pathlib import Path
import shutil
import uuid
from .core import digest,source,probe
from .export import validate_export


def import_master(store,job,base_revision,inbox,relative,sha256):
    if store.get(base_revision,'revision')['job']!=job:raise ValueError('Wrong base revision job')
    original=source(inbox,relative)
    if digest(original)!=sha256:raise ValueError('Returned master hash mismatch')
    duration=float(probe(original)['format']['duration'])
    report=validate_export(original,duration)
    from .storage import admit
    admit(store.root,original.stat().st_size)
    directory=store.root/'human_returns'/uuid.uuid4().hex;directory.mkdir(parents=True)
    master=directory/'master.mp4';shutil.copyfile(original,master)
    if digest(master)!=sha256:raise ValueError('Returned master changed during ingest')
    return store.put('revision',dict(job=job,parent=base_revision,author='human',master=dict(path=str(master.relative_to(store.root)),sha256=sha256,duration=duration),validation=report,editable_layers=False))

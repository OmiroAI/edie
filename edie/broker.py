"""Validated organisation proposals only. The external broker applies changes."""
from pathlib import PurePosixPath
from .workflow import identity


def change_plan(catalogue,changes,scope,destination_root):
    root=PurePosixPath(destination_root)
    if root.is_absolute() or '..' in root.parts or not root.parts:raise ValueError('Relative destination scope required')
    current={e['source_id']:e for e in catalogue.list() if e['source_id'] in scope}
    destinations={e['path'].casefold():e['source_id'] for e in catalogue.list()}
    seen=set();result=[]
    for change in changes:
        if set(change)!={'source_id','version','sha256','destination'}:raise ValueError('Invalid organisation fields')
        source=current.get(change['source_id'])
        if not source or change['source_id'] in seen:raise ValueError('Unknown, duplicate or out-of-scope source')
        if any(source[k]!=change[k] for k in ('version','sha256')):raise ValueError('Stale source version')
        target=PurePosixPath(change['destination'])
        if target.is_absolute() or '..' in target.parts or not target.is_relative_to(root) or target==root:raise ValueError('Destination outside approved scope')
        key=str(target).casefold()
        if key in destinations and destinations[key]!=change['source_id']:raise ValueError('Naming conflict')
        destinations[key]=change['source_id'];seen.add(change['source_id'])
        result.append({**change,'current_path':source['path'],'operation':'rename'})
    plan=dict(schema_version=1,scope=sorted(scope),destination_root=str(root),changes=result,remote_action='broker_must_revalidate_and_apply',delete_originals=False)
    return {**plan,'plan_hash':identity(plan)}

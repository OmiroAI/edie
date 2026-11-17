"""Conservative automatic availability from existing, versioned editorial evidence.

This reuses the semantic model's work; scores are usefulness, not confidence.
No additional model calls, media uploads, approvals or source deletions occur.
"""
from .classification import Classifications, file_decision
from .segments import Segments
from .workflow import identity


def reconcile(store, job):
    from .editorial import indexes
    from .scope import library_job
    if library_job(store, job) != job:
        return
    import os
    threshold=int(os.environ.get('EDIE_INTAKE_REVIEW_THRESHOLD','70'))
    if not 0<=threshold<=100:raise ValueError('Intake review threshold must be 0–100')
    values = indexes(store, job)
    repo = Classifications(store)
    segments = Segments(store)
    decisions = {}
    for key, index in sorted(values.items()):
        entry = index['source']
        old = repo.get(job, entry)
        if old['override']:
            decisions[key] = old['override']
            continue
        parts = segments.get(job, entry)['items']
        ranked = [p for p in parts if p.get('profile')==2 and p.get('selection')!='rejected']
        score=max((p.get('score',0) for p in ranked),default=0)
        usable = [p for p in parts if p.get('profile') == 2 and
                  p.get('score', 0) >= threshold and
                  p.get('selection') != 'rejected']
        dense = isinstance(index.get('coverage'), dict) and bool(index['coverage'].get('profile'))
        pending = not dense or not parts
        disposition = 'keep' if dense and usable else 'unreviewed'
        reason = ('Edie found usable material: ' + usable[0]['title'] + '. ' + usable[0]['reason']) if disposition == 'keep' else (
            'Edie is waiting for dense indexing and semantic segments.' if pending else
            'Edie could not establish clearly usable material. Review before excluding; low scores alone do not justify rejection.')
        decisions[key] = dict(disposition=disposition, labels=[], reason=reason[:4000],
                              intake_profile=1, score=score, review_threshold=threshold, review_required=disposition!='keep', status='pending' if pending else 'decided' if disposition == 'keep' else 'uncertain',
                              evidence=identity([entry, index.get('coverage'), parts]))
    # Exclude only byte-identical copies with an explicitly kept representative.
    # Prefer human-kept sources; never override a human's own file decision.
    groups = {}
    for key, index in values.items():
        if index['source'].get('sha256'):
            groups.setdefault(index['source']['sha256'], []).append(key)
    for keys in groups.values():
        keep = [k for k in sorted(keys) if decisions[k]['disposition'] == 'keep']
        if not keep:
            continue
        human = [k for k in keep if repo.get(job, values[k]['source'])['override']]
        representative = (human or keep)[0]
        for key in keys:
            if key == representative or repo.get(job, values[key]['source'])['override']:
                continue
            decisions[key].update(disposition='exclude', status='uncertain' if threshold>0 else 'decided', score=0, review_required=threshold>0, duplicate_of=representative,
                                  reason='Exact SHA-256 duplicate of kept source: ' + values[representative]['source']['path'])
    for key, value in decisions.items():
        entry = values[key]['source']; old = repo.get(job, entry)
        if old['override'] or old['suggestion'] == value:
            continue
        repo.save(job, entry, value, actor='edie-intake-v1')

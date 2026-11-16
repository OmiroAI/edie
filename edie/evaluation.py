"""Evidence-based checks, separate from subjective editorial acceptance."""


def evaluate_script(script,indexes):
    findings=[];duration=0
    for position,clip in enumerate(script['clips']):
        source=indexes.get(clip['source_id'])
        if source is None or source['source']['sha256']!=clip['sha256']:
            findings.append(dict(severity='error',criterion='source_grounding',clip=position,detail='Source/version missing'));continue
        duration+=clip['out']-clip['in']
        spoken=[s for s in source['transcript'] if s['start']<clip['out'] and s['end']>clip['in']]
        crossing=[s['id'] for s in spoken if s['start']<clip['in']-0.05 or s['end']>clip['out']+0.05]
        if crossing:findings.append(dict(severity='review',criterion='speech_continuity',clip=position,detail='Cut intersects transcribed utterance',transcript_refs=crossing))
        sampled=[t for observation in source['visual'] for t in observation['sampled_times'] if clip['in']<=t<clip['out']]
        if not sampled:findings.append(dict(severity='review',criterion='visual_evidence',clip=position,detail='No overview frame in selected interval; targeted inspection required'))
        if source.get('transcript_issues'):findings.append(dict(severity='review',criterion='transcript_reliability',clip=position,detail='Source contains invalid model timing; inspect original audio'))
    return dict(duration=duration,findings=findings,subjective_criteria={key:'human_review_required' for key in ('hook_and_payoff','narrative_clarity','pacing','style','ending')},automatic_editorial_acceptance=False)

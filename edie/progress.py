"""Fact-based editorial progress shared by API and dashboard; no state mutations."""
from .scope import library_job
from .tasks import Tasks


def tasks_for(store,job):
    root=library_job(store,job);repo=Tasks(store.db)
    import json
    children={r[0]:json.loads(r[1]).get('output_name') for r in store.db.execute("SELECT id,body FROM records WHERE kind='job' AND json_extract(body,'$.output_of')=?",(root,)).fetchall()}
    ids=[job,root,*children] if job==root else [job,root]
    result=[]
    for identifier, in store.db.execute('SELECT id FROM tasks WHERE job IN ('+','.join('?' for _ in ids)+') ORDER BY rowid DESC',ids).fetchall():
        task=repo.get(identifier)
        if job!=root and task['job']!=job and task['payload']['action'] not in ('index','visual_index','segment_index','review_proxy','sync_index','sync_preview','sync_waveform'):continue
        result.append({**task,'shared':job!=root and task['job']==root,'output_name':children.get(task['job'])})
    return result


def summarize(state,rows,tasks,review):
    total=len(rows);unreviewed=sum(r.get('review_required',r.get('disposition')=='unreviewed') for r in rows)
    pending_intake=sum(r.get('intake_status')=='pending' for r in rows)
    sync_pending=review.get('sync_pending',0)
    human_review=max(0,unreviewed-pending_intake)
    human_decided=sum((r.get('classification',{}).get('override') or {}).get('disposition') in ('keep','exclude') for r in rows)
    suggested=max(0,total-unreviewed-human_decided)
    eligible=[r for r in rows if r.get('disposition')!='exclude'];prepared=sum(bool(r.get('segments',{}).get('items')) for r in eligible)
    dense=sum(bool(r.get('coverage',{}).get('profile')) for r in rows if isinstance(r.get('coverage'),dict))
    active=[t for t in tasks if t['state'] in ('running','queued','pause_requested','paused')]
    index_active=[t for t in active if t['payload']['action'] in ('index','visual_index')]
    segment_active=[t for t in active if t['payload']['action']=='segment_index']
    failures=[t for t in tasks if t['state'] in ('failed','interrupted') and (t['payload']['action']!='render' or t['payload'].get('revision')==state.get('revision') or t.get('output_name'))]
    running=sum(t['state']=='running' for t in active);queued=sum(t['state']=='queued' for t in active)
    agent_running=state.get('_agent_running',0)
    agent_requests=int(bool(state.get('requested_run')))
    paused=state.get('control')=='paused' or any(t['state']=='paused' for t in active)
    blocked=bool(failures) or state.get('stage') in ('blocked','failed','uncertain')
    confirmed=review.get('confirmed',False);script=state.get('script');approved=bool(state.get('approvals',{}).get('script'))
    rendered=any(t['state']=='completed' and t.get('result',{} ) and t['result'].get('kind')=='reference_preview' and t['payload'].get('revision')==state.get('revision') for t in tasks)
    steps=[]
    def step(key,label,status,detail):steps.append(dict(key=key,label=label,status=status,detail=detail))
    step('footage','Footage','working' if index_active else 'review' if unreviewed or sync_pending else 'ready' if total else 'pending',f'{human_decided}/{total} confirmed by you · {human_review} need review · {suggested} suggested · {pending_intake} analysing'+(f' · {sync_pending} sync review' if sync_pending else ''))
    segment_status='pending' if not total or index_active else 'working' if segment_active else 'pending' if prepared<len(eligible) else 'ready' if confirmed else 'review'
    step('segments','Segments',segment_status,f'{prepared}/{len(eligible)} sources prepared'+(' · waiting for indexing' if index_active else ' · selection confirmed' if confirmed else ' · review and confirm selection'))
    story_status='pending' if not confirmed else 'working' if agent_running and not approved else 'queued' if agent_requests and not approved else 'ready' if approved else 'review' if script and not state.get('needs_story_options') else 'pending'
    step('story','Stories',story_status,'Script approved' if approved else 'Choose a story and create an output' if story_status=='review' else 'Edie is planning stories' if story_status=='working' else 'Planning requested' if story_status=='queued' else 'Waiting for confirmed segments')
    final=bool(state.get('approvals',{}).get('final'))
    cut_status='ready' if final else 'review' if rendered or state.get('delivery') else 'working' if approved and any(t['payload']['action']=='render' and t['state']=='running' for t in active) else 'queued' if approved and (agent_requests or any(t['payload']['action']=='render' and t['state']=='queued' for t in active)) else 'pending'
    step('review','Cuts',cut_status,'Delivery approved' if final else 'Review export / delivery' if cut_status=='review' else 'Editing or rendering requested' if cut_status in ('working','queued') else 'Waiting for script approval')
    step('activity','Activity','attention' if blocked else 'working' if running or agent_running else 'queued' if queued or agent_requests else 'idle',f'{running} running · {queued} queued tasks · {agent_running} active agent calls · {agent_requests} agent requests · {len(failures)} failed')
    if human_review:action=dict(tab='footage',label='Review flagged files',detail=f'{human_review} files need your judgement. Review starts at the lowest rank.')
    elif pending_intake:action=dict(tab='footage',label='View Edie’s intake',detail=f'{pending_intake} files await indexing or semantic analysis.')
    elif sync_pending:action=dict(tab='footage',label='Review camera alignment',detail=f'{sync_pending} camera sessions need synchronisation review before story planning.')
    elif not confirmed:action=dict(tab='segments',label='Review segments',detail='Review prepared moments, then confirm selection in Footage.' if prepared else 'Segment preparation must finish before selection can be confirmed.')
    elif not approved:action=dict(tab='story',label='Review stories',detail='Choose a proposal, create an output and approve its script.' if script else 'Waiting for Edie to propose stories.')
    else:action=dict(tab='review',label='Review cut',detail='Watch the current export and give feedback.' if rendered else 'Your approved script is awaiting an edit.')
    if final:action=dict(tab='review',label='View approved output',detail='The approved delivery and its saved edit remain available.')
    if paused:action=dict(tab='activity',label='Review paused work',detail='Resume paused tasks in Activity or resume this workflow. Other tasks may still be running.')
    if blocked:action=dict(tab='activity',label='Resolve blocked work',detail=str(state.get('question') or ('A task failed or was interrupted. Inspect Activity before retrying.' if failures else 'Agent planning is blocked. Inspect workflow status before resuming.')))
    if state.get('control')=='cancelled':mode='cancelled';headline='Output cancelled'
    elif blocked:mode='attention';headline='Edie needs intervention'
    elif paused:mode='paused';headline='Some work is paused' if running else 'Work is paused'
    elif running or agent_running:mode='working';headline='Edie is planning stories' if agent_running and not approved else 'Edie is working'
    elif queued or state.get('requested_run'):mode='queued';headline='Work is queued for Edie'
    elif final:mode='ready';headline='Output approved'
    elif pending_intake and not human_review:mode='queued';headline='Waiting for intake analysis'
    else:mode='review';headline='Your review is needed'
    phase='complete' if final else 'footage' if unreviewed or sync_pending or not total else 'segments' if not confirmed else 'stories' if not approved else 'complete' if final else 'cuts'
    return dict(phase=phase,mode=mode,headline=headline,working=running>0 or agent_running>0,needs_intervention=blocked or paused,action=action,steps=steps,
                counts=dict(sources=total,dense=dense,unreviewed=unreviewed,pending_intake=pending_intake,human_review=human_review,sync_pending=sync_pending,human_decided=human_decided,suggested=suggested,segment_sources=prepared,segments=sum(len(r.get('segments',{}).get('items',[])) for r in rows),running=running,agent_running=agent_running,queued=queued,agent_requests=agent_requests,failed=len(failures)),raw_stage=state.get('stage'))


def progress(store,job,state=None):
    from .workflow import Workflow
    from .editorial import footage
    from .classification import review_state
    state=state or Workflow(store).get(job);review=review_state(store,job);review['confirmed']=state.get('footage_confirmation')==review['candidate']
    state={**state,'_agent_running':store.db.execute("SELECT COUNT(*) FROM invocations WHERE job=? AND state='running'",(job,)).fetchone()[0]}
    result=summarize(state,footage(store,job),tasks_for(store,job),review)
    result['outputs']=[]
    if library_job(store,job)==job:
        from .outputs import listing
        for child in listing(store,job):
            detail=progress(store,child['id'])
            result['outputs'].append(dict(id=child['id'],name=child['name'],mode=detail['mode'],headline=detail['headline'],phase=detail['phase'],steps=detail['steps'],agent_requests=detail['counts']['agent_requests'],agent_running=detail['counts']['agent_running']))
        children=result['outputs']
        result['counts']['agent_requests']+=sum(c['agent_requests'] for c in children)
        result['counts']['agent_running']+=sum(c['agent_running'] for c in children)
        counts=result['counts']
        result['steps'][4]['detail']=f"{counts['running']} running · {counts['queued']} queued tasks · {counts['agent_running']} active agent calls · {counts['agent_requests']} agent requests · {counts['failed']} failed"
        if counts['agent_requests'] and result['steps'][4]['status']=='idle':result['steps'][4]['status']='queued'
        if children and review['confirmed']:
            awaiting=[c for c in children if c['steps'][2]['status']!='ready']
            ready=sum(c['steps'][3]['status']=='ready' for c in children)
            working=[c for c in children if c['mode']=='working']
            queued_children=[c for c in children if c['mode']=='queued']
            attention=[c for c in children if c['mode'] in ('attention','paused')]
            result['steps'][2].update(status='review' if awaiting else 'ready',detail=f"{len(children)} outputs · {len(awaiting)} scripts await approval")
            result['steps'][3].update(status='working' if working else 'queued' if queued_children else 'ready' if ready==len(children) else 'review' if any(c['steps'][3]['status']=='review' for c in children) else 'pending',detail=f'{ready}/{len(children)} outputs approved for delivery')
            target=(attention or awaiting or [c for c in children if c['steps'][3]['status']!='ready'] or children)[0]
            result['phase']='stories' if awaiting else 'complete' if ready==len(children) else 'cuts'
            result['mode']='attention' if attention else 'working' if working else 'queued' if queued_children else 'ready' if ready==len(children) else 'review'
            result['working']=result['working'] or bool(working)
            result['needs_intervention']=bool(attention)
            result['headline']='An output needs intervention' if attention else 'Edie is working on your outputs' if working else 'Outputs queued for Edie' if queued_children else 'All outputs approved' if ready==len(children) else 'Your outputs need review'
            result['action']=dict(tab='activity' if attention else 'story' if awaiting else 'review',output_id=target['id'],label='Open '+target['name'],detail=f'{len(children)} independent outputs share this footage library.')
    attention=[o for o in result['outputs'] if o['mode'] in ('attention','paused')]
    if attention:
        target=attention[0];result.update(mode='attention',needs_intervention=True,headline='An output needs intervention',action=dict(tab='activity',output_id=target['id'],label='Open '+target['name'],detail=target['headline']))
        result['steps'][4]['status']='attention'
    if state.get('_agent_running') and state.get('control')=='active' and result['mode'] not in ('attention','paused'):
        result.update(mode='working',working=True,headline='Edie is planning stories' if not state.get('approvals',{}).get('script') else 'Edie is working')
        if not state.get('approvals',{}).get('script'):result['steps'][2].update(status='working',detail='Developing story proposals from source evidence')
    return result

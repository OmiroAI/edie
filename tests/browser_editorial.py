"""Optional real-browser acceptance using synthetic media, never real job approvals.
Run in a container with Playwright/Chromium, project dependencies and FFmpeg.
"""
import json
import tempfile
import threading
import subprocess
from pathlib import Path
from edie.api import Server,handler
from edie.core import Store,digest
from edie.index import Catalogue
from edie.workflow import Workflow
from edie.classification import Classifications
from edie.editorial import request_proxy
from edie.worker import run_once
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);media=root/'media';media.mkdir()
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=24','-t','4','-c:v','libx264',str(media/'demo.mp4')],check=True)
    store=Store(root/'state');entry=dict(source_id='source-1',version='1',sha256=digest(media/'demo.mp4'),path='demo.mp4');Catalogue(store).ingest([entry],media)
    folder=store.root/'index'/'source';folder.mkdir(parents=True);(folder/'index.json').write_text(json.dumps(dict(source=entry,duration=4,transcript=[dict(start=0,end=2,text='A surprising first impression.',timing_valid=True),dict(start=2,end=4,text='Here is the practical takeaway.',timing_valid=True)],visual=[dict(start=0,end=4,sampled_times=[1],observations='The presenter examines a compact camera on the table.')],coverage='Sparse overview')))
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=24','-t','1','-c:v','libx264',str(media/'short.mp4')],check=True)
    extra=dict(source_id='source-2',version='1',sha256=digest(media/'short.mp4'),path='short.mp4');Catalogue(store).ingest([entry,extra],media)
    folder=store.root/'index'/'extra';folder.mkdir(parents=True);(folder/'index.json').write_text(json.dumps(dict(source=extra,duration=1,transcript=[],visual=[])))
    for title in ['Unboxing a new perspective','Discoveries from the exhibition']:
        job=store.job(dict(goal=title,audience='Curious viewers',format='16:9',duration=4,language='en'));flow=Workflow(store);flow.start(job,footage_review_required=title!='Unboxing a new perspective')
        script=dict(title=title,angle='Does a dedicated camera earn a place next to your phone?',clips=[{**entry,'in':0,'out':2,'purpose':'An unexpected first impression'},{**entry,'in':2,'out':4,'purpose':'The practical takeaway'}],duration=4,missing_footage=[],review_notes=['Verify the model name before export.'])
        Classifications(store).save(job,entry,dict(labels=['a_roll','hook','star'],reason='Specific discovery and practical payoff.',score=90,confidence='medium',moments=[],origin='agent',star_rank=1))
        Classifications(store).save(job,extra,dict(labels=['b_roll'],reason='Short illustrative insert.',score=30,confidence='medium',moments=[],origin='agent'))
        from edie.segments import Segments
        Segments(store).save(job,dict(source=entry,duration=4),[dict(id='segment-one',start=0,end=4,title='A complete thought',labels=['a_roll'],score=90,reason='Specific discovery.',origin='agent')],0,False)
        flow.update(job,0,dict(script=script,stage='review_script'));request_proxy(store,job,entry['source_id']);run_once(store.root,media,'review_proxy')
    server=Server(('127.0.0.1',0),handler(store.root,'synthetic-browser-token-'*3));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    with sync_playwright() as p:
        browser=p.chromium.launch(args=['--no-sandbox']);page=browser.new_page(viewport={'width':1512,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
        page.goto(f'http://127.0.0.1:{server.server_address[1]}/dashboard');page.locator('#token').fill('synthetic-browser-token-'*3);page.get_by_role('button',name='Open workspace').click();page.get_by_role('heading',name='Source library').wait_for()
        assert page.locator('#jobs button').count()==2
        page.get_by_role('button',name='Play source',exact=True).click();page.locator('video').wait_for();page.wait_for_function('() => document.querySelector("video").readyState>=2')
        page.get_by_label('Search transcript').fill('takeaway');assert page.locator('.cue').count()==1
        page.get_by_role('button',name='File decision',exact=True).click();page.get_by_role('button',name='Keep',exact=True).click();page.get_by_label('File decision reason').fill('Available for editorial use.');page.get_by_role('button',name='Save file decision',exact=True).click();page.wait_for_function('() => document.querySelector(".source p").textContent.includes("Available for editorial")')
        page.get_by_label('Filter file decision').select_option('exclude');assert page.locator('.source').count()==0
        page.get_by_label('Filter file decision').select_option('keep');assert page.locator('.source').count()==1
        page.get_by_label('Filter file decision').select_option('all');page.get_by_label('Sort footage').select_option('longest');assert page.locator('.source strong').first.inner_text()=='demo.mp4';page.get_by_label('Sort footage').select_option('shortest');assert page.locator('.source strong').first.inner_text()=='short.mp4';page.get_by_label('Sort footage').select_option('name')
        page.get_by_role('button',name='Intake mode',exact=True).click();assert page.locator('#classification-editor').get_attribute('open') is not None;assert page.locator('input[type=checkbox]').count()==0
        page.get_by_role('button',name='Save & next →',exact=True).click();page.wait_for_function('() => document.querySelector(".classification-detail .section-head h3").textContent==="short.mp4"')
        page.get_by_role('button',name='Keep',exact=True).click();page.get_by_role('button',name='Save & next →',exact=True).click();page.get_by_role('button',name='Intake mode',exact=True).wait_for();page.locator('.source').filter(has_text='demo.mp4').click()
        page.screenshot(path='/output/footage.png',full_page=True)
        page.get_by_role('button',name='Segments',exact=True).click();page.get_by_role('heading',name='Editorial segments').wait_for()
        page.get_by_role('button',name='Play segment',exact=True).click();page.locator('video').wait_for()
        page.get_by_role('button',name='Segment Blooper',exact=True).click();page.get_by_role('button',name='Segment selection selected',exact=True).click();page.get_by_label('Segment editorial note').fill('Use as supporting detail.');page.get_by_role('button',name='Save & next segment').click();page.get_by_text('0:00–0:04 · Use as supporting detail.',exact=True).wait_for()
        page.get_by_text('Adjust boundaries',exact=True).click();page.get_by_label('Segment boundary seconds').fill('2');page.get_by_role('button',name='Split here',exact=True).click();page.wait_for_function('() => document.querySelectorAll(".sources .source").length===2')
        page.screenshot(path='/output/segments.png',full_page=True)
        page.get_by_role('button',name='Story & script',exact=True).click();assert page.locator('.beat').count()==2
        page.get_by_title('Move later',exact=True).first.click();page.get_by_role('button',name='Save new story order',exact=True).click();page.wait_for_function('() => document.querySelector(".beat h3").textContent==="The practical takeaway"')
        page.wait_for_function('() => document.querySelector(".proposal-select").options.length===2')
        page.get_by_label('Script proposals').select_option(index=0);page.wait_for_function('() => document.querySelector(".beat h3").textContent==="An unexpected first impression"')
        page.get_by_role('button',name='Play story sequence',exact=True).click();page.locator('video').wait_for();page.wait_for_function('() => document.querySelector("video").readyState>=2')
        page.screenshot(path='/output/story.png',full_page=True)
        page.locator('#intention').fill('Lead with the demonstration.');page.get_by_role('button',name='Send direction',exact=True).click();page.wait_for_function('() => document.querySelector("#send-status").textContent.includes("saved")');assert page.get_by_role('button',name='Approve script → create rough cut').is_disabled()
        page.locator('#intention').fill('Unsent job-specific note');page.locator('#jobs button').nth(1).click();page.wait_for_function('() => document.querySelector("#job-title").textContent==="Discoveries from the exhibition"');assert page.locator('#intention').input_value()==''
        page.locator('#jobs button').first.click();page.wait_for_function('() => document.querySelector("#job-title").textContent==="Unboxing a new perspective"');assert page.locator('#intention').input_value()=='Unsent job-specific note'
        page.set_viewport_size({'width':390,'height':844});page.get_by_role('button',name='Footage',exact=True).click();page.screenshot(path='/output/mobile.png',full_page=True);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.set_viewport_size({'width':1512,'height':1100});page.locator('#jobs button').nth(1).click();page.get_by_role('button',name='Confirm selection → suggest stories',exact=True).wait_for();page.get_by_role('button',name='Confirm selection → suggest stories',exact=True).click();page.wait_for_function('() => document.querySelector("#current-state").textContent.includes("planning")');page.get_by_role('button',name='Story & script',exact=True).click();page.get_by_role('heading',name='Edie is developing story options').wait_for()
        assert errors==[],errors
        browser.close();print('Browser acceptance passed: playback, search, classification overrides/filtering/duration sorting, proposals, reorder, approval invalidation, job isolation, mobile layout; no JavaScript errors.')
    server.shutdown();thread.join();server.server_close();store.db.close()

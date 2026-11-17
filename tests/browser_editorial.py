"""Optional real-browser acceptance using synthetic media, never real job approvals.
Run in a container with Playwright/Chromium, project dependencies and FFmpeg.
"""
import json
import tempfile
import threading
import subprocess
from pathlib import Path
from edie.api import Server,handler
from edie.core import Store,digest,probe
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
    folder=store.root/'index'/'source';folder.mkdir(parents=True);(folder/'index.json').write_text(json.dumps(dict(source=entry,duration=4,media=probe(media/'demo.mp4'),transcript=[dict(start=0,end=2,text='A surprising first impression.',timing_valid=True),dict(start=2,end=4,text='Here is the practical takeaway.',timing_valid=True)],visual=[dict(start=0,end=4,sampled_times=[1],observations='The presenter examines a compact camera on the table.')],coverage='Sparse overview')))
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=24','-t','1','-c:v','libx264',str(media/'short.mp4')],check=True)
    extra=dict(source_id='source-2',version='1',sha256=digest(media/'short.mp4'),path='short.mp4');Catalogue(store).ingest([entry,extra],media)
    folder=store.root/'index'/'extra';folder.mkdir(parents=True);(folder/'index.json').write_text(json.dumps(dict(source=extra,duration=1,transcript=[],visual=[])))
    for title in ['Unboxing a new perspective','Discoveries from the exhibition']:
        job=store.job(dict(goal=title,audience='Curious viewers',format='16:9',duration=4,language='en'));flow=Workflow(store);flow.start(job,footage_review_required=title!='Unboxing a new perspective')
        script=dict(title=title,angle='Does a dedicated camera earn a place next to your phone?',clips=[{**entry,'in':0,'out':2,'purpose':'An unexpected first impression'},{**entry,'in':2,'out':4,'purpose':'The practical takeaway'}],duration=4,missing_footage=[],review_notes=['Verify the model name before export.'])
        Classifications(store).save(job,entry,dict(disposition='keep',labels=[],reason='Specific discovery.',score=90,intake_profile=1,status='decided',review_required=False,review_threshold=70))
        Classifications(store).save(job,extra,dict(disposition='unreviewed',labels=[],reason='Short illustrative insert.',score=30,intake_profile=1,status='uncertain',review_required=True,review_threshold=70))
        from edie.segments import Segments
        Segments(store).save(job,dict(source=entry,duration=4),[dict(id='segment-one',start=0,end=4,title='A complete thought',labels=['a_roll'],selection='available',score=90,reason='Specific discovery.',origin='agent')],0,False)
        Classifications(store).save(job,extra,dict(disposition='keep',labels=[],reason='Available'),1,True)
        Segments(store).save(job,dict(source=extra,duration=1),[dict(id='extra-whole',start=0,end=1,title='Short insert',labels=['b_roll'],selection='available',score=30,reason='Illustration')],0,False)
        if title!='Unboxing a new perspective':Classifications(store).save(job,entry,dict(disposition='keep',labels=[],reason='Available'),1,True)
        flow.update(job,0,dict(script=script,stage='review_script'));request_proxy(store,job,entry['source_id']);run_once(store.root,media,'review_proxy')
    server=Server(('127.0.0.1',0),handler(store.root,'synthetic-browser-token-'*3));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    with sync_playwright() as p:
        browser=p.chromium.launch(args=['--no-sandbox']);page=browser.new_page(viewport={'width':1512,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
        page.goto(f'http://127.0.0.1:{server.server_address[1]}/dashboard');page.locator('#token').fill('synthetic-browser-token-'*3);page.get_by_role('button',name='Open workspace').click();page.get_by_role('heading',name='Source library').wait_for()
        assert page.locator('#jobs button').count()==2
        assert page.locator('.workflow-step').count()==5;assert 'Your review' in page.locator('#work-status').inner_text();assert '640 × 360' in page.locator('.file-properties').inner_text()
        page.wait_for_function('() => document.querySelector(".player-poster")?.naturalWidth>0')
        assert page.locator('video').count()==0
        poster=page.locator('.player-poster').bounding_box();play=page.locator('#player .source-play').bounding_box()
        assert abs((poster['x']+poster['width']/2)-(play['x']+play['width']/2))<2
        page.screenshot(path='/output/workspace-desktop.png',full_page=True)
        page.set_viewport_size({'width':1024,'height':900});page.screenshot(path='/output/workspace-tablet.png',full_page=True);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.set_viewport_size({'width':1512,'height':1100})
        assert page.locator('#player').get_by_role('button',name='Play source',exact=True).count()==1
        page.get_by_role('button',name='Play source',exact=True).click();page.locator('video').wait_for();page.wait_for_function('() => document.querySelector("video").readyState>=2')
        page.get_by_label('Search transcript').fill('takeaway');assert page.locator('.cue').count()==1
        page.get_by_role('button',name='File decision',exact=True).click();page.get_by_role('button',name='Keep',exact=True).click();page.get_by_label('File decision reason').fill('Available for editorial use.');page.get_by_role('button',name='Save file decision',exact=True).click();page.wait_for_function('() => document.querySelector(".source p").textContent.includes("Available for editorial")')
        page.get_by_label('Filter file decision').select_option('exclude');assert page.locator('.source').count()==0
        page.get_by_label('Filter file decision').select_option('keep');assert page.locator('.source').count()==2
        page.get_by_label('Filter file decision').select_option('all');page.get_by_label('Sort footage').select_option('longest');assert page.locator('.source strong').first.inner_text()=='demo.mp4';page.get_by_label('Sort footage').select_option('shortest');assert page.locator('.source strong').first.inner_text()=='short.mp4';page.get_by_label('Sort footage').select_option('name')
        # Return both decisions to the review queue; persistence is server-side.
        page.evaluate("""async()=>{for(const f of await api('/jobs/'+current.id+'/footage'))await api('/jobs/'+current.id+'/sources/'+f.source_id+'/disposition',{source_version:f.version,source_sha256:f.sha256,expected_revision:f.classification.revision,disposition:'unreviewed',reason:'Revisit decision'});await loadJob(false)}""")
        page.get_by_role('button',name='Review mode',exact=True).click()
        assert page.locator('.classification-detail .section-head h3').inner_text()=='short.mp4'
        page.get_by_role('button',name='Keep',exact=True).click()
        page.get_by_role('button',name='Save & next →',exact=True).click()
        page.get_by_role('button',name='Review mode',exact=True).wait_for()
        page.get_by_role('button',name='Review mode',exact=True).click()
        assert page.get_by_role('button',name='Exit review mode',exact=True).count()==0
        page.locator('.source').filter(has_text='demo.mp4').click()
        page.get_by_role('button',name='Confirm Edie’s keep suggestion',exact=True).click()
        page.wait_for_function('() => document.querySelector(".human-decision").textContent.startsWith("keep")')
        assert 'keep' in page.locator('.human-decision').inner_text()
        assert 'keep' in page.locator('.agent-suggestion').inner_text()
        page.screenshot(path='/output/footage.png',full_page=True)
        page.get_by_role('button',name='Segments',exact=True).click();page.get_by_role('heading',name='Editorial segments').wait_for()
        page.wait_for_function('() => document.querySelector(".player-poster")?.naturalWidth>0')
        page.get_by_role('button',name='Play segment',exact=True).click();page.locator('video').wait_for()
        page.get_by_role('button',name='Segment Blooper',exact=True).click();page.get_by_role('button',name='Segment selection selected',exact=True).click();page.get_by_label('Segment editorial note').fill('Use as supporting detail.');page.get_by_role('button',name='Save & next segment').click();page.get_by_role('heading',name='Short insert',exact=True).wait_for();page.locator('.source').filter(has_text='A complete thought').click();page.get_by_text('0:00–0:04 · Use as supporting detail.',exact=True).wait_for()
        page.get_by_text('Split or merge',exact=True).click();page.get_by_label('Segment boundary seconds').fill('2');page.get_by_role('button',name='Split here',exact=True).click();page.wait_for_function('() => document.querySelectorAll(".sources .source").length===3')
        handle=page.get_by_label('Segment start handle');box=handle.bounding_box();page.mouse.move(box['x']+8,box['y']+box['height']/2);page.mouse.down();page.mouse.move(box['x']+box['width']*.06,box['y']+box['height']/2,steps=6);page.mouse.up();assert float(handle.input_value())>0
        page.get_by_label('Segment start seconds').fill('0.25');page.get_by_label('Segment start seconds').press('Tab');page.get_by_label('Segment end seconds').fill('1.75');page.get_by_label('Segment end seconds').press('Tab')
        page.get_by_role('button',name='Preview range',exact=True).click();page.locator('video').wait_for()
        page.get_by_role('button',name='Load filmstrip',exact=True).click();page.wait_for_function('() => document.querySelectorAll(".filmstrip canvas").length===10')
        page.screenshot(path='/output/segment-range.png',full_page=True)
        page.get_by_role('button',name='Save segment range',exact=True).click();page.wait_for_function('() => document.querySelectorAll(".sources .source").length===4')
        assert page.get_by_label('Segment start seconds').input_value()=='0.250'
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
        page.set_viewport_size({'width':1512,'height':1100});page.locator('#jobs button').nth(1).click();page.get_by_role('button',name='Confirm selection → suggest stories',exact=True).wait_for();page.get_by_role('button',name='Confirm selection → suggest stories',exact=True).click();page.wait_for_function('() => state.stage==="planning"');page.get_by_role('button',name='Story & script',exact=True).click();page.get_by_role('heading',name='Edie is developing story options').wait_for()
        assert errors==[],errors
        browser.close();print('Browser acceptance passed: playback, search, classification overrides/filtering/duration sorting, proposals, reorder, approval invalidation, job isolation, mobile layout; no JavaScript errors.')
    server.shutdown();thread.join();server.server_close();store.db.close()

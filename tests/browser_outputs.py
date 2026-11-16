"""Synthetic browser check of independent output creation and workflow status."""
import sys,tempfile,threading
sys.path.insert(0,str(__import__('pathlib').Path(__file__).parent))
from test_outputs import OutputTest
from edie.api import Server,handler
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as d:
    store,job,entry,index,one,two=OutputTest().fixture(d)
    server=Server(('127.0.0.1',0),handler(store.root,'synthetic-output-token-'*3));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    with sync_playwright() as p:
        browser=p.chromium.launch(args=['--no-sandbox']);page=browser.new_page(viewport={'width':1512,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda x:x.accept())
        page.goto(f'http://127.0.0.1:{server.server_address[1]}/dashboard');page.locator('#token').fill('synthetic-output-token-'*3);page.get_by_role('button',name='Open workspace').click();page.get_by_role('button',name='Story & script',exact=True).click()
        page.get_by_label('New output name').fill('Discovery Alpha');page.get_by_role('button',name='Create independent output',exact=True).click();page.get_by_role('heading',name='Discovery Alpha',exact=True,level=1).wait_for()
        alpha=page.get_by_label('Output workspace').input_value();assert alpha!=job;assert page.locator('#jobs button').count()==1
        page.get_by_role('button',name='Approve script → create rough cut',exact=True).click();page.wait_for_function('() => document.querySelector("#work-status").textContent.includes("queued")')
        page.get_by_label('Output workspace').select_option(job);page.get_by_label('Script proposals').select_option(index=1);page.get_by_role('heading',name='Discovery two',exact=True).wait_for()
        page.get_by_label('New output name').fill('Discovery Beta');page.get_by_role('button',name='Create independent output',exact=True).click();page.get_by_role('heading',name='Discovery Beta',exact=True,level=1).wait_for()
        beta=page.get_by_label('Output workspace').input_value();assert beta not in [alpha,job];assert not page.get_by_role('button',name='Approve script → create rough cut',exact=True).is_disabled()
        page.get_by_label('Output workspace').select_option(job);page.wait_for_function('() => document.querySelectorAll(".output-card").length===2');page.screenshot(path='/output/multiple-outputs.png',full_page=True)
        page.get_by_label('Output workspace').select_option(alpha);page.get_by_role('heading',name='Discovery Alpha',exact=True,level=1).wait_for();assert page.get_by_role('button',name='Approve script → create rough cut',exact=True).is_disabled()
        assert errors==[],errors;browser.close();print('Output browser checks passed: two independent scripts, shared job navigation, separate approval and queued status.')
    server.shutdown();thread.join();server.server_close();store.db.close()

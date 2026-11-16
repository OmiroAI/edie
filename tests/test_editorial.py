import http.client
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import HTTPServer
from edie.api import handler
from edie.core import Store, digest
from edie.index import Catalogue
from edie.tasks import Tasks
from edie.workflow import Workflow, identity
from edie.editorial import footage, request_proxy
from edie.worker import run_once

class EditorialTest(unittest.TestCase):
    def test_scoped_proxy_and_range(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);media=root/'media';media.mkdir()
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=800x450:rate=24','-t','1','-c:v','libx264',str(media/'test.mp4')],check=True)
            store=Store(root/'state');job=store.job(dict(goal='Test',audience='Editors',format='16:9',duration=1,language='en',source_ids=['allowed']))
            entry=dict(source_id='allowed',version='v1',path='test.mp4',sha256=digest(media/'test.mp4'))
            Catalogue(store).ingest([entry],media)
            for name in ['allowed','other']:
                folder=store.root/'index'/name;folder.mkdir(parents=True)
                (folder/'index.json').write_text(json.dumps(dict(source={**entry,'source_id':name},duration=1,transcript=[dict(start=0,end=1,text='test')],visual=[])))
            self.assertEqual([f['source_id'] for f in footage(store,job)],['allowed'])
            with self.assertRaises(KeyError):request_proxy(store,job,'other')
            task=request_proxy(store,job,'allowed');self.assertEqual(request_proxy(store,job,'allowed')['id'],task['id'])
            self.assertTrue(run_once(store.root,media,'review_proxy'))
            result=Tasks(store.db).get(task['id']);self.assertEqual(result['state'],'completed')
            self.assertEqual(footage(store,job)[0]['proxy_state'],'completed')
            token='fixture-token-'*4;server=HTTPServer(('127.0.0.1',0),handler(store.root,token));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                url='/jobs/'+job+'/sources/allowed/classification'
                payload=dict(source_version='v1',source_sha256=entry['sha256'],expected_revision=0,labels=['b_roll','star'],reason='Useful illustrative footage.')
                for body,expected in [(payload,200),(payload,400),({**payload,'expected_revision':1,'source_version':'stale'},400),({**payload,'expected_revision':1,'reset':True},200)]:
                    conn=http.client.HTTPConnection(*server.server_address);conn.request('POST',url,body=json.dumps(body),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'});response=conn.getresponse();self.assertEqual(response.status,expected);response.read();conn.close()
                for byte_range,status,length in [('bytes=0-9',206,10),('bytes=-10',206,10),('bytes=999999999-',416,0),('bytes=oops',416,0)]:
                    conn=http.client.HTTPConnection(*server.server_address);conn.request('GET','/tasks/'+task['id']+'/artifact',headers={'Authorization':'Bearer '+token,'Range':byte_range});response=conn.getresponse();data=response.read();self.assertEqual(response.status,status);self.assertEqual(len(data),length);conn.close()
                conn=http.client.HTTPConnection(*server.server_address);conn.request('GET','/tasks/'+task['id']+'/artifact');response=conn.getresponse();self.assertEqual(response.status,401);response.read();conn.close()
            finally:server.shutdown();thread.join();server.server_close();store.db.close()

    def test_proposal_selection_reorder_and_revision_guard(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d);job=store.job(dict(goal='Test',audience='Editors',format='16:9',duration=4,language='en'));flow=Workflow(store);flow.start(job,footage_review_required=False)
            script=dict(title='First',clips=[{'in':0,'out':1},{'in':2,'out':3}])
            flow.update(job,0,dict(script=script,stage='review_script',approvals={'script':identity(script)}))
            flow.event(job,'reorder',1,'arrange_script',dict(candidate=identity(script),order=[1,0]))
            state=flow.get(job);self.assertEqual(state['script']['clips'],list(reversed(script['clips'])));self.assertEqual(state['approvals'],{});self.assertEqual(len(state['script_proposals']),2)
            flow.event(job,'select',2,'select_script',dict(candidate=identity(script)))
            self.assertEqual(flow.get(job)['script'],script)
            with self.assertRaises(ValueError):flow.event(job,'bad',3,'arrange_script',dict(candidate=identity(script),order=[0,0]))
            flow.update(job,3,dict(revision='accepted'))
            with self.assertRaises(ValueError):flow.event(job,'protected',4,'select_script',dict(candidate=identity(script)))
            store.db.close()

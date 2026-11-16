import json
import tempfile
import unittest
from pathlib import Path
from edie.core import Store
from edie.workflow import Workflow,identity
from edie.classification import Classifications,review_state
from edie.segments import Segments,propose
from edie.outputs import create,listing
from edie.progress import summarize,progress
from edie.editorial import properties

class OutputTest(unittest.TestCase):
    def fixture(self,d):
        store=Store(d);job=store.job(dict(goal='Two discoveries',audience='Viewers',format='16:9',duration=20,language='en'))
        entry=dict(source_id='source',version='1',sha256='a'*64,path='test.mp4');index=dict(source=entry,duration=20,transcript=[],visual=[])
        folder=Path(d)/'index'/'source';folder.mkdir(parents=True);(folder/'index.json').write_text(json.dumps(index))
        parts=propose(index);Segments(store).save(job,index,parts,0,False)
        Classifications(store).save(job,entry,dict(disposition='keep',labels=[],reason='Available'),0,True)
        flow=Workflow(store);flow.start(job);review=review_state(store,job)
        script=dict(title='Discovery one',angle='One angle',clips=[{**entry,'segment_id':parts[0]['id'],'segment_bounds':[0,20],'in':0,'out':10,'purpose':'Hook'}],duration=10,missing_footage=[],review_notes=[])
        second={**script,'title':'Discovery two','angle':'Second angle'}
        flow.update(job,0,dict(footage_confirmation=review['candidate'],script=script,script_proposals=[script,second],stage='review_script',needs_story_options=False))
        return store,job,entry,index,script,second

    def test_outputs_idempotent_and_independent_with_shared_selection(self):
        with tempfile.TemporaryDirectory() as d:
            store,job,entry,index,one,two=self.fixture(d)
            body=dict(request_id='one',name='Output one',script_candidate=identity(one))
            a=create(store,job,body)['id'];b=create(store,job,dict(request_id='two',name='Output two',script_candidate=identity(two)))['id']
            self.assertEqual(create(store,job,body)['id'],a)
            with self.assertRaises(ValueError):create(store,job,{**body,'name':'Changed'})
            flow=Workflow(store);self.assertEqual(len(listing(store,job)),2)
            flow.event(a,'approve-one',0,'approve',dict(scope='script',candidate=identity(one)))
            self.assertIn('script',flow.get(a)['approvals']);self.assertFalse(flow.get(b)['approvals']);self.assertFalse(flow.get(job)['approvals'])
            self.assertEqual(flow.get(b)['script']['title'],'Discovery two')
            status=progress(store,job)
            self.assertEqual(status['counts']['agent_requests'],1)
            self.assertEqual(status['steps'][3]['status'],'queued')
            self.assertEqual(status['steps'][4]['status'],'queued')
            self.assertIn('1 agent requests',status['steps'][4]['detail'])
            original=Segments(store).get(a,entry);Segments(store).edit(a,index,dict(expected_revision=original['revision'],segment_id=original['items'][0]['id'],action='label',labels=['blooper'],selection='selected',reason='Useful personality'))
            self.assertEqual(Segments(store).get(b,entry)['items'][0]['labels'],['blooper'])
            self.assertNotEqual(review_state(store,b)['candidate'],flow.get(b)['footage_confirmation'])
            with self.assertRaises(ValueError):flow.event(b,'stale-approval',0,'approve',dict(scope='script',candidate=identity(two)))
            with self.assertRaises(ValueError):create(store,job,dict(request_id='three',name='Third',script_candidate=identity(one)))
            self.assertEqual(len(listing(store,job)),2);store.db.close()

    def test_progress_uses_evidence_not_stale_stage(self):
        row=dict(disposition='unreviewed',coverage={},segments=dict(items=[]))
        task=dict(state='running',payload=dict(action='visual_index'),result=None)
        state=dict(stage='review_script',control='active',approvals={},script=None)
        result=summarize(state,[row],[task],dict(confirmed=False))
        self.assertEqual(result['phase'],'footage');self.assertEqual(result['mode'],'working');self.assertEqual(result['steps'][1]['status'],'pending')
        row.update(disposition='keep',segments=dict(items=[{}]))
        result=summarize(state,[row],[],dict(confirmed=False));self.assertEqual(result['phase'],'segments');self.assertEqual(result['mode'],'review')
        task['state']='failed';result=summarize(state,[row],[task],dict(confirmed=False));self.assertEqual(result['mode'],'attention')
        state['control']='paused';result=summarize(state,[row],[],dict(confirmed=False));self.assertEqual(result['mode'],'paused')

    def test_rotated_file_properties(self):
        p=properties(dict(media=dict(format=dict(size='12345'),streams=[dict(codec_type='video',width=3840,height=2160,avg_frame_rate='30000/1001',codec_name='hevc',color_transfer='arib-std-b67',side_data_list=[dict(rotation=-90)]),dict(codec_type='audio',codec_name='aac')])) )
        self.assertEqual(p['orientation'],'portrait');self.assertEqual(p['display_width'],2160);self.assertEqual(p['size_bytes'],12345);self.assertTrue(p['hdr']);self.assertAlmostEqual(p['fps'],29.97,places=2)

    def test_two_outputs_render_separate_artifacts(self):
        import subprocess
        from edie.core import digest,probe
        from edie.agent import Agent
        from edie.worker import run_once
        from edie.tasks import Tasks
        with tempfile.TemporaryDirectory() as d:
            store,job,entry,index,one,two=self.fixture(d)
            media=Path(d)/'media';media.mkdir();video=media/'test.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30','-t','2','-c:v','libx264',str(video)],check=True,capture_output=True)
            entry={**entry,'sha256':digest(video)}
            from edie.index import Catalogue
            Catalogue(store).ingest([entry],media)
            index=dict(source=entry,duration=2,transcript=[],visual=[],media=probe(video));(Path(d)/'index'/'source'/'index.json').write_text(json.dumps(index))
            parts=propose(index);Segments(store).save(job,index,parts,0,False);Classifications(store).save(job,entry,dict(disposition='keep',labels=[],reason='Available'),0,True)
            scripts=[]
            for i in range(2):scripts.append(dict(title='Story '+str(i),angle='Angle '+str(i),clips=[{**entry,'segment_id':parts[0]['id'],'segment_bounds':[0,2],'in':i,'out':i+1,'purpose':'Discovery'}],duration=1,missing_footage=[],review_notes=[]))
            flow=Workflow(store);flow.update(job,1,dict(script=scripts[0],script_proposals=scripts,footage_confirmation=review_state(store,job)['candidate']))
            task_ids=[];output_ids=[]
            for i,script in enumerate(scripts):
                output=create(store,job,dict(request_id=str(i),name='Output '+str(i),script_candidate=identity(script)))['id'];output_ids.append(output)
                flow.event(output,'approve-'+str(i),0,'approve',dict(scope='script',candidate=identity(script)))
                agent=Agent(store,media,None);agent.tool(output,'edit_timeline',{});task_ids.append(agent.tool(output,'render_preview',{})['task'])
            for _ in task_ids:self.assertTrue(run_once(d,media,'render'))
            results=[Tasks(store.db).get(t) for t in task_ids]
            self.assertTrue(all(t['state']=='completed' for t in results));self.assertNotEqual(results[0]['result']['path'],results[1]['result']['path'])
            self.assertNotEqual(flow.get(output_ids[0])['revision'],flow.get(output_ids[1])['revision']);self.assertIsNone(flow.get(job)['revision'])
            store.db.close()

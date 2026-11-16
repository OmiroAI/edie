import tempfile
import unittest
from edie.core import Store
from edie.segments import Segments,propose,allowed

class SegmentsTest(unittest.TestCase):
    def test_boundaries_edits_authority_and_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d);repo=Segments(store)
            index=dict(source=dict(source_id='s',version='1',sha256='a'*64),duration=30,transcript=[dict(start=0,end=9,text='A thought.'),dict(start=12,end=22,text='Another thought.')],cut_candidates=[dict(kind='scene_change',seconds=15)],visual=[])
            items=propose(index);self.assertEqual([s['end'] for s in items],[9,22,30])
            saved=repo.save('j',index,items,0,human=False)
            body=dict(expected_revision=1,segment_id=items[0]['id'],action='split',seconds=4)
            saved=repo.edit('j',index,body);self.assertEqual(len(saved['items']),4)
            with self.assertRaisesRegex(ValueError,'Stale'):repo.edit('j',index,body)
            with self.assertRaisesRegex(ValueError,'preserved'):repo.save('j',index,items,2,human=False)
            saved=repo.edit('j',index,dict(expected_revision=2,segment_id=saved['items'][0]['id'],action='label',labels=[],selection='rejected',reason='Accidental lead-in'))
            self.assertFalse(allowed(store,'j',index,0,2));self.assertFalse(allowed(store,'j',index,3,8));self.assertTrue(allowed(store,'j',index,4,9))
            saved=repo.edit('j',index,dict(expected_revision=3,segment_id=saved['items'][0]['id'],action='merge_next'))
            self.assertEqual(saved['items'][0]['labels'],['needs_review']);self.assertEqual(saved['items'][0]['end'],9)
            saved=repo.edit('j',index,dict(expected_revision=4,segment_id=saved['items'][0]['id'],action='range',start=0,end=10))
            self.assertEqual(saved['items'][1]['start'],10)
            changed={**index['source'],'version':'2'};self.assertEqual(repo.get('j',changed)['items'],[])
            for t in [float('nan'),True,40,-1]:
                with self.assertRaises(ValueError):repo.edit('j',index,dict(expected_revision=5,segment_id=saved['items'][0]['id'],action='split',seconds=t))
            self.assertEqual(store.db.execute('SELECT count(*) FROM segment_events').fetchone()[0],5)
            store.db.close()

    def test_review_gate_and_script_trim_rejection(self):
        import json
        from pathlib import Path
        from edie.classification import Classifications,review_state
        from edie.tasks import Tasks
        from edie.agent import Agent
        with tempfile.TemporaryDirectory() as d:
            store=Store(d);job=store.job(dict(goal='Story',audience='Viewers',format='16:9',duration=10,language='en'))
            index=dict(source=dict(source_id='s',version='1',sha256='a'*64,path='source.mp4'),duration=10,transcript=[],visual=[])
            folder=Path(d)/'index'/'s';folder.mkdir(parents=True);(folder/'index.json').write_text(json.dumps(index))
            Classifications(store).save(job,index['source'],dict(labels=[],disposition='keep',reason='Available',score=80),0,True)
            Tasks(store.db).submit(job,'segments',dict(action='segment_index'))
            self.assertFalse(review_state(store,job)['ready'])
            repo=Segments(store);items=propose(index);repo.save(job,index,items,0,False)
            before=review_state(store,job);self.assertTrue(before['ready'])
            saved=repo.edit(job,index,dict(expected_revision=1,segment_id=items[0]['id'],action='split',seconds=5))
            saved=repo.edit(job,index,dict(expected_revision=2,segment_id=saved['items'][0]['id'],action='label',labels=[],selection='rejected',reason='Mistake'))
            self.assertNotEqual(before['candidate'],review_state(store,job)['candidate'])
            agent=Agent(store,None,None);agent.current_job=job
            with self.assertRaisesRegex(ValueError,'rejected segment'):agent.resolve([dict(source_id='s',**{'in':3,'out':6})])
            self.assertEqual(agent.resolve([dict(source_id='s',segment_id=saved['items'][1]['id'],**{'in':5,'out':10})])[0]['in'],5)
            store.db.close()

    def test_semantic_planning_blooper_scores_cache_and_script_reference(self):
        from pathlib import Path
        from edie.segment_planner import plan
        from edie.segments import selection,reference
        class Model:
            calls=0
            def decide(self,prompt,schema):
                self.calls+=1
                self.assert_context='unboxing' in prompt and 'Keep banter' in prompt
                return {'segments':[dict(start=0,end=12,title='Reveal and funny interruption',labels=['blooper','reaction'],score=88,story_fit=61,reason='A real interruption with a reaction.',boundary_reason='Keep reveal and payoff together.')]},{'billing':'subscription','known_cost_micro_usd':0}
        with tempfile.TemporaryDirectory() as d:
            model=Model();index=dict(source=dict(source_id='s',version='1',sha256='b'*64),duration=12,transcript=[dict(start=0,end=6,text='Reveal.'),dict(start=7,end=12,text='Oops!')],visual=[])
            args=(index,dict(goal='unboxing'),{'style':'Keep banter'},model,Path(d)/'cache',Path(d)/'usage.jsonl')
            items=plan(*args);self.assertTrue(model.assert_context);self.assertEqual(selection(items[0]),'available');self.assertEqual(items[0]['story_fit'],61);plan(*args);self.assertEqual(model.calls,1)
            store=Store(Path(d)/'state');Segments(store).save('j',index,items,0,False)
            clip=dict(segment_id=items[0]['id'],**{'in':2,'out':9})
            self.assertEqual(reference(store,'j',index,clip,True)['segment_id'],items[0]['id'])
            with self.assertRaises(ValueError):reference(store,'j',index,{'in':0,'out':12},True)
            with self.assertRaises(ValueError):reference(store,'j',index,{**clip,'segment_bounds':[0,11]},True)
            store.db.close()

    def test_semantic_planner_rejects_mid_speech_cut(self):
        from pathlib import Path
        from edie.segment_planner import plan
        class Model:
            def decide(self,*args):return {'segments':[dict(start=a,end=b,title='Beat',labels=['a_roll'],score=50,story_fit=50,reason='Evidence',boundary_reason='Boundary') for a,b in [(0,5),(5,12)]]},{'known_cost_micro_usd':0}
        with tempfile.TemporaryDirectory() as d:
            index=dict(source=dict(source_id='s',version='1',sha256='b'*64),duration=12,transcript=[dict(start=0,end=12,text='One complete utterance.')],visual=[])
            with self.assertRaisesRegex(ValueError,'splits speech'):plan(index,{}, {},Model(),Path(d)/'cache',Path(d)/'usage.jsonl')

    def test_timeline_uses_source_ids_then_hash_index_and_rejects_stale_bounds(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        from edie.agent import Agent
        from edie.workflow import Workflow,identity
        with tempfile.TemporaryDirectory() as d:
            store=Store(d);job=store.job(dict(goal='Story',audience='Viewers',format='16:9',duration=10,language='en'))
            entry=dict(source_id='source-id-not-a-hash',version='1',sha256='c'*64,path='source.mp4')
            index=dict(source=entry,duration=10,transcript=[],visual=[])
            folder=Path(d)/'index'/'s';folder.mkdir(parents=True);(folder/'index.json').write_text(json.dumps(index))
            repo=Segments(store);items=propose(index);repo.save(job,index,items,0,False)
            clip={**entry,'in':0,'out':10,'segment_id':items[0]['id'],'segment_bounds':[0,10]}
            script=dict(title='Story',clips=[clip]);flow=Workflow(store);flow.start(job,footage_review_required=False)
            flow.update(job,0,dict(script=script,approvals={'script':identity(script)}))
            with patch('edie.agent.commit',return_value='test-revision') as commit:
                result=Agent(store,None,None).tool(job,'edit_timeline',{})
                self.assertEqual(result['revision'],'test-revision');commit.assert_called_once()
            with self.assertRaisesRegex(ValueError,'boundary changed'):
                from edie.segments import reference
                reference(store,job,index,{**clip,'segment_bounds':[0,9]},True)
            store.db.close()

    def test_range_edit_atomic_neighbours_and_edge_remainders(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d);repo=Segments(store)
            index=dict(source=dict(source_id='s',version='1',sha256='a'*64),duration=20,transcript=[],visual=[])
            saved=repo.save('j',index,propose(index),0,False);sid=saved['items'][0]['id']
            saved=repo.edit('j',index,dict(expected_revision=1,segment_id=sid,action='range',start=2,end=18))
            self.assertEqual([(s['start'],s['end']) for s in saved['items']],[(0,2),(2,18),(18,20)])
            self.assertEqual(saved['items'][1]['id'],sid)
            saved=repo.edit('j',index,dict(expected_revision=2,segment_id=sid,action='range',start=1,end=19))
            self.assertEqual([(s['start'],s['end']) for s in saved['items']],[(0,1),(1,19),(19,20)])
            for start,end in [(0,19),(1,20),(10,9),(float('nan'),19),(True,19)]:
                with self.assertRaises(ValueError):repo.edit('j',index,dict(expected_revision=3,segment_id=sid,action='range',start=start,end=end))
                self.assertEqual(repo.get('j',index['source'])['revision'],3)
            with self.assertRaises(ValueError):repo.edit('j',index,dict(expected_revision=2,segment_id=sid,action='range',start=2,end=18))
            store.db.close()

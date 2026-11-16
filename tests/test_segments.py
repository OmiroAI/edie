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
            saved=repo.edit('j',index,dict(expected_revision=2,segment_id=saved['items'][0]['id'],action='label',labels=['throw_away'],reason='Accidental lead-in'))
            self.assertFalse(allowed(store,'j',index,0,2));self.assertFalse(allowed(store,'j',index,3,8));self.assertTrue(allowed(store,'j',index,4,9))
            saved=repo.edit('j',index,dict(expected_revision=3,segment_id=saved['items'][0]['id'],action='merge_next'))
            self.assertEqual(saved['items'][0]['labels'],['needs_review']);self.assertEqual(saved['items'][0]['end'],9)
            saved=repo.edit('j',index,dict(expected_revision=4,segment_id=saved['items'][0]['id'],action='boundary',seconds=10))
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
            Classifications(store).save(job,index['source'],dict(labels=['a_roll'],reason='Useful',score=80))
            Tasks(store.db).submit(job,'segments',dict(action='segment_index'))
            self.assertFalse(review_state(store,job)['ready'])
            repo=Segments(store);items=propose(index);repo.save(job,index,items,0,False)
            before=review_state(store,job);self.assertTrue(before['ready'])
            saved=repo.edit(job,index,dict(expected_revision=1,segment_id=items[0]['id'],action='split',seconds=5))
            saved=repo.edit(job,index,dict(expected_revision=2,segment_id=saved['items'][0]['id'],action='label',labels=['throw_away'],reason='Mistake'))
            self.assertNotEqual(before['candidate'],review_state(store,job)['candidate'])
            agent=Agent(store,None,None);agent.current_job=job
            with self.assertRaisesRegex(ValueError,'rejected segment'):agent.resolve([dict(source_id='s',**{'in':3,'out':6})])
            self.assertEqual(agent.resolve([dict(source_id='s',**{'in':5,'out':10})])[0]['in'],5)
            store.db.close()

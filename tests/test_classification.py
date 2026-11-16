import json
from pathlib import Path
import tempfile
import unittest
from edie.core import Store
from edie.classification import Classifications,file_decision

class ClassificationTest(unittest.TestCase):
    def fixture(self,root):
        store=Store(root);job=store.job(dict(goal='A discovery',audience='Curious people',format='16:9',duration=30,language='en'))
        entries=[]
        for n in range(7):
            entry=dict(source_id=str(n),version='1',path=str(n)+'.mp4',sha256=str(n if n<6 else 0)*64);entries.append(entry)
            folder=Path(root)/'index'/str(n);folder.mkdir(parents=True)
            (folder/'index.json').write_text(json.dumps(dict(source=entry,duration=10,transcript=[dict(start=0,end=5,text='A specific discovery')],visual=[dict(sampled_times=[1],observations='A visible demonstration')],transcript_issues=[])))
        return store,job,entries

    def test_intake_decisions_require_explicit_review_and_reject_stale_writes(self):
        with tempfile.TemporaryDirectory() as d:
            store,job,entries=self.fixture(d);repo=Classifications(store);entry=entries[0]
            self.assertEqual(file_decision(repo.get(job,entry)),'unreviewed')
            repo.save(job,entry,dict(disposition='keep',labels=[],reason='Available'),0,True)
            self.assertEqual(file_decision(repo.get(job,entry)),'keep')
            with self.assertRaisesRegex(ValueError,'Stale'):repo.save(job,entry,dict(disposition='exclude',labels=[],reason='Exclude'),0,True)
            repo.save(job,entry,dict(disposition='exclude',labels=[],reason='Accidental'),1,True)
            self.assertEqual(file_decision(repo.get(job,entry)),'exclude')
            self.assertEqual(file_decision(repo.get(job,{**entry,'version':'2'})),'unreviewed')
            store.db.close()

    def test_invalid_labels_and_conflicting_star_reject(self):
        with tempfile.TemporaryDirectory() as d:
            store,job,entries=self.fixture(d);repo=Classifications(store)
            for labels in [['unknown'],['star','throw_away']]:
                with self.assertRaises(ValueError):repo.save(job,entries[0],dict(labels=labels,reason='test'),0,True)
            store.db.close()

    def test_human_selection_gate_and_reject_exclusion(self):
        from edie.workflow import Workflow
        from edie.classification import review_state
        from edie.agent import Agent
        with tempfile.TemporaryDirectory() as d:
            store,job,entries=self.fixture(d);flow=Workflow(store);flow.start(job);repo=Classifications(store)
            class NoCalls:
                def decide(self,*args):raise AssertionError('Model ran before human review')
            agent=Agent(store,Path(d),NoCalls())
            self.assertEqual(agent.run(job)['stage'],'review_footage')
            for n,entry in enumerate(entries):repo.save(job,entry,dict(labels=[],disposition='exclude' if n==0 else 'keep',reason='Reviewed selection.'),0,True)
            from edie.segments import Segments,propose
            from edie.editorial import indexes
            for index in indexes(store,job).values():Segments(store).save(job,index,propose(index),0,False)
            review=review_state(store,job);state=flow.get(job)
            flow.event(job,'confirm',state['version'],'confirm_footage',{'candidate':review['candidate']})
            current=flow.get(job);self.assertTrue(current['needs_story_options']);self.assertTrue(current['requested_run'])
            agent.current_job=job;agent.editorial_selection=True
            self.assertNotIn('0',agent.indexes());self.assertIn('1',agent.indexes())
            with self.assertRaises(KeyError):agent.resolve([{'source_id':'0','in':0,'out':1,'purpose':'Forbidden reject'}])
            rejected_script={'clips':[{'source_id':'0','in':0,'out':1}]}
            state=flow.get(job);flow.update(job,state['version'],dict(script=rejected_script,needs_story_options=False,script_changes_pending=False))
            from edie.workflow import identity
            with self.assertRaisesRegex(ValueError,'rejected'):
                flow.event(job,'reject-old-draft',state['version']+1,'approve',dict(scope='script',candidate=identity(rejected_script)))
            # Reclassification invalidates the exact reviewed selection, even without a workflow write.
            old=repo.get(job,entries[1]);repo.save(job,entries[1],dict(labels=[],disposition='exclude',reason='Excluded on review.'),old['revision'],True)
            self.assertNotEqual(review_state(store,job)['candidate'],current['footage_confirmation'])
            self.assertEqual(agent.run(job)['stage'],'review_footage')
            store.db.close()

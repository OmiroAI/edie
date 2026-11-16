import json
from pathlib import Path
import tempfile
import unittest
from edie.core import Store
from edie.classification import Classifications,classify

class ClassificationTest(unittest.TestCase):
    def fixture(self,root):
        store=Store(root);job=store.job(dict(goal='A discovery',audience='Curious people',format='16:9',duration=30,language='en'))
        entries=[]
        for n in range(7):
            entry=dict(source_id=str(n),version='1',path=str(n)+'.mp4',sha256=str(n if n<6 else 0)*64);entries.append(entry)
            folder=Path(root)/'index'/str(n);folder.mkdir(parents=True)
            (folder/'index.json').write_text(json.dumps(dict(source=entry,duration=10,transcript=[dict(start=0,end=5,text='A specific discovery')],visual=[dict(sampled_times=[1],observations='A visible demonstration')],transcript_issues=[])))
        return store,job,entries

    def test_ranking_cache_duplicates_and_human_authority(self):
        class Model:
            calls=0
            def decide(self,prompt,schema):
                self.calls+=1;data=json.loads(prompt.rsplit('\n',1)[-1])
                return {'clips':[dict(source_id=s['source_id'],labels=['a_roll','hook'],score=90-int(s['source_id']),confidence='medium',reason='A specific supported demonstration.',moments=[dict(start=0,end=5,reason='Opening discovery')]) for s in data['sources']]},{'known_cost_micro_usd':0,'billing':'subscription'}
        with tempfile.TemporaryDirectory() as d:
            store,job,entries=self.fixture(d);model=Model();result=classify(store,job,model);self.assertEqual(result['stars'],5)
            repo=Classifications(store);self.assertEqual(sum('star' in repo.get(job,e)['suggestion']['labels'] for e in entries),5)
            duplicate=repo.get(job,entries[-1]);self.assertIn('throw_away',duplicate['suggestion']['labels'])
            before=repo.get(job,entries[0]);repo.save(job,entries[0],dict(labels=['b_roll'],reason='Use as illustration.'),before['revision'],True,'editor')
            with self.assertRaises(ValueError):repo.save(job,entries[0],dict(labels=[],reason='Stale'),before['revision'],True)
            calls=model.calls;classify(store,job,model);self.assertEqual(model.calls,calls);self.assertEqual(repo.get(job,entries[0])['effective']['labels'],['b_roll'])
            changed={**entries[0],'version':'2'};self.assertIsNone(repo.get(job,changed)['effective'])
            # Removing the canonical exact duplicate must clear the derived reject flag.
            (Path(d)/'index'/'0'/'index.json').unlink();classify(store,job,model)
            self.assertNotIn('throw_away',repo.get(job,entries[-1])['suggestion']['labels'])
            current=repo.get(job,entries[0]);repo.save(job,entries[0],None,current['revision'],True);self.assertEqual(repo.get(job,entries[0])['effective']['origin'],'agent')
            self.assertIsNone(repo.get('other-job',entries[0])['effective']);store.db.close()

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
            for n,entry in enumerate(entries):repo.save(job,entry,dict(labels=['throw_away'] if n==0 else ['a_roll'],reason='Reviewed selection.'),0,True)
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
            old=repo.get(job,entries[1]);repo.save(job,entries[1],dict(labels=['b_roll'],reason='Corrected role.'),old['revision'],True)
            self.assertNotEqual(review_state(store,job)['candidate'],current['footage_confirmation'])
            self.assertEqual(agent.run(job)['stage'],'review_footage')
            store.db.close()

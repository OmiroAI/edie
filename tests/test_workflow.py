import json
from pathlib import Path
import tempfile
import unittest
from edie.core import Store
from edie.context import Context
from edie.workflow import Workflow,identity
from edie.agent import Agent

class WorkflowTest(unittest.TestCase):
    def test_approval_versions_dedup_and_control(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d);job=store.job(dict(goal='Test',audience='Test',format='16:9',duration=10,language='en'))
            w=Workflow(store);w.start(job)
            script={'clips':[]};w.update(job,0,dict(script=script,stage='review_script'))
            with self.assertRaises(ValueError):w.event(job,'bad',1,'approve',dict(scope='script',candidate='wrong'))
            payload=dict(scope='script',candidate=identity(script))
            first=w.event(job,'approval',1,'approve',payload)
            self.assertEqual(w.event(job,'approval',1,'approve',payload),first)
            with self.assertRaises(ValueError):w.event(job,'approval',1,'approve',dict(scope='main',candidate='wrong'))
            with self.assertRaises(ValueError):w.update(job,1,dict(stage='stale'))
            self.assertEqual(w.get(job)['stage'],'editing')
            w.event(job,'pause',2,'pause',{})
            self.assertEqual(w.get(job)['control'],'paused')
            self.assertEqual(w.reserve(job,'render',{'revision':'a'}),('reserved',None))
            with self.assertRaises(ValueError):w.reserve(job,'render',{'revision':'b'})
            store.db.close()

    def test_supplied_script_invalidates_approval_until_reconciled(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d);job=store.job(dict(goal='Test',audience='Test',format='16:9',duration=10,language='en'))
            flow=Workflow(store);flow.start(job)
            script={'title':'Original','clips':[]}
            flow.update(job,0,dict(script=script,stage='review_script'))
            flow.event(job,'approve-original',1,'approve',dict(scope='script',candidate=identity(script)))
            payload=dict(text='Use my new story',supplied_script='Start with the demonstration.')
            result=flow.event(job,'replacement',2,'instruction',payload)
            self.assertEqual(flow.event(job,'replacement',2,'instruction',payload),result)
            state=flow.get(job)
            self.assertEqual(state['approvals'],{})
            self.assertTrue(state['script_changes_pending'])
            self.assertTrue(state['requested_run'])
            self.assertEqual(state['supplied_script'],payload['supplied_script'])
            with self.assertRaisesRegex(ValueError,'reconciled script'):
                flow.event(job,'old-approval',3,'approve',dict(scope='script',candidate=identity(script)))
            self.assertEqual(flow.get(job)['version'],3)
            store.db.close()

    def test_agent_observes_then_proposes_and_parks_across_restart(self):
        class Decider:
            calls=0
            def decide(self,prompt,schema):
                self.calls+=1
                if self.calls==1:
                    tool='read_sources';args={'source_ids':['source']}
                else:
                    self.assertion='visible test' in prompt
                    tool='propose_script';args=dict(title='A grounded story',angle='A useful demo',clips=[dict(source_id='source',**{'in':0,'out':2},purpose='hook')],missing_footage=[],review_notes=[])
                return dict(summary='Evidence-based decision',plan=['Review source','Develop story'],action='invoke_tool',tool=tool,arguments=json.dumps(args),question=None),dict(known_cost_micro_usd=0)
        with tempfile.TemporaryDirectory() as d:
            config=Path(d)/'config';context=Context(config)
            h=context.install(dict(schema_version=1,strategy_id='test',version='1',rules=[dict(id='truth',kind='hard',rule='Do not invent')],soul='Curious',memory=''))
            context.activate(h,None)
            store=Store(Path(d)/'state',config);job=store.job(dict(goal='Test',audience='Test',format='16:9',duration=10,language='en'))
            path=store.root/'index'/'fixture';path.mkdir(parents=True)
            (path/'index.json').write_text(json.dumps(dict(source=dict(source_id='source',version='1',sha256='a'*64,path='test.mp4'),duration=3,transcript=[dict(id='s',start=0,end=2,text='visible test')],visual=[],usage=[],media={})))
            decider=Decider();agent=Agent(store,Path(d),decider)
            result=agent.run(job)
            self.assertEqual(result['stage'],'review_script');self.assertTrue(decider.assertion);self.assertEqual(decider.calls,2)
            store.db.close()
            reopened=Store(Path(d)/'state',config)
            self.assertEqual(Agent(reopened,Path(d),decider).run(job)['stage'],'review_script')
            self.assertEqual(decider.calls,2)
            reopened.db.close()

    def test_human_master_precedence_and_derivative_gate(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);brief=dict(goal='Test',audience='Test',format='16:9',duration=10,language='en');j=s.job(brief)
            w=Workflow(s);w.start(j)
            with self.assertRaises(ValueError):s.derivative(j,brief)
            script={'clips':[]};w.update(j,0,dict(script=script))
            w.event(j,'s',1,'approve',dict(scope='script',candidate=identity(script)))
            original=s.put('revision',dict(job=j,clips=[]))
            w.update(j,2,dict(revision=original,validation={'decode':'passed'}))
            human=s.put('revision',dict(job=j,parent=original,author='human',master={'sha256':'a'*64,'path':'master.mp4'},validation={'decode':'passed'}))
            w.event(j,'return',3,'human_return',dict(revision=human))
            with self.assertRaises(ValueError):w.event(j,'old',4,'approve',dict(scope='main',candidate=identity(original)))
            w.event(j,'main',4,'approve',dict(scope='main',candidate=identity(human)))
            self.assertEqual(w.get(j)['accepted_master']['sha256'],'a'*64)
            child=s.derivative(j,brief)
            self.assertEqual(s.get(child,'job')['parent_revision'],human)
            with self.assertRaises(ValueError):Agent(s,d,None).tool(j,'edit_timeline',{})
            s.db.close()

import tempfile
import unittest
from edie.core import Store
from edie.workflow import Workflow,canonical
from edie.agent import Agent
from edie.segments import Segments

class PlanningSnapshotTest(unittest.TestCase):
    def test_large_library_keeps_discovery_ids_without_full_reasons(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d);job=store.job(dict(goal='Discover stories',audience='People',format='16:9',duration=60,language='en'));Workflow(store).start(job)
            store.job_context=lambda j:{'style':'Private context'}
            indexes={}
            for n in range(62):
                entry=dict(source_id=str(n),version='1',sha256=str(n),path=str(n)+'.mp4')
                index=dict(source=entry,duration=60,transcript=[],visual=[]);indexes[str(n)]=index
                items=[dict(id=str(i),start=i*10,end=(i+1)*10,title='A supported story beat',labels=['a_roll'],selection='available',score=80,story_fit=60,reason='x'*4000) for i in range(6)]
                Segments(store).save(job,index,items,0,False)
            agent=Agent(store,None,None);agent.indexes=lambda:indexes
            snapshot=agent.snapshot(job)
            self.assertEqual(len(snapshot['sources']),62);self.assertLess(len(canonical(snapshot)),190*1024)
            self.assertEqual(len(snapshot['sources'][0]['segments'][0]['reason']),240)
            self.assertEqual(len(Segments(store).get(job,indexes['0']['source'])['items'][0]['reason']),4000)
            store.db.close()

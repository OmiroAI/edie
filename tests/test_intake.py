import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_classification
from edie.intake import reconcile
from edie.classification import Classifications,file_decision,needs_review
from edie.segments import Segments,propose
from edie.editorial import indexes

class IntakeTest(unittest.TestCase):
    def test_automatic_ranked_intake_and_human_authority(self):
        with tempfile.TemporaryDirectory() as d:
            store,job,entries=test_classification.ClassificationTest().fixture(d)
            for key,index in indexes(store,job).items():
                index['coverage']={'profile':{'baseline_fps':1}}
                (Path(d)/'index'/key/'index.json').write_text(json.dumps(index))
                parts=propose(index)
                for part in parts:part.update(profile=2,score=85 if key in ('0','6') else 30,story_fit=0,labels=['blooper'],reason='Useful reaction')
                Segments(store).save(job,index,parts,0,False)
            reconcile(store,job);repo=Classifications(store)
            first=repo.get(job,entries[0]);low=repo.get(job,entries[1]);duplicate=repo.get(job,entries[6])
            self.assertEqual(file_decision(first),'keep');self.assertFalse(needs_review(first))
            self.assertTrue(needs_review(low));self.assertEqual(low['suggestion']['score'],30)
            self.assertEqual(file_decision(duplicate),'exclude');self.assertEqual(duplicate['suggestion']['duplicate_of'],'0');self.assertTrue(needs_review(duplicate))
            reconcile(store,job);self.assertEqual(repo.get(job,entries[0])['revision'],first['revision'])
            repo.save(job,entries[0],dict(disposition='exclude',labels=[],reason='Human exclusion'),first['revision'],True)
            reconcile(store,job)
            self.assertEqual(file_decision(repo.get(job,entries[0])),'exclude')
            self.assertEqual(file_decision(repo.get(job,entries[6])),'keep')
            with patch.dict('os.environ',{'EDIE_INTAKE_REVIEW_THRESHOLD':'20'}):reconcile(store,job)
            self.assertEqual(file_decision(repo.get(job,entries[1])),'keep')
            store.db.close()

    def test_pending_and_uncertain_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            store,job,entries=test_classification.ClassificationTest().fixture(d)
            reconcile(store,job);repo=Classifications(store)
            self.assertEqual(repo.get(job,entries[0])['suggestion']['status'],'pending')
            index=indexes(store,job)['0'];index['coverage']={'profile':{'baseline_fps':1}}
            (Path(d)/'index'/'0'/'index.json').write_text(json.dumps(index))
            parts=propose(index)
            for p in parts:p.update(profile=2,score=99,labels=['needs_review'])
            Segments(store).save(job,index,parts,0,False);reconcile(store,job)
            self.assertTrue(needs_review(repo.get(job,entries[0])))
            self.assertEqual(repo.get(job,entries[0])['suggestion']['status'],'uncertain')
            store.db.close()

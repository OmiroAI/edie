import unittest
from edie.evaluation import evaluate_script
class EvaluationTest(unittest.TestCase):
    def test_missing_evidence_and_cut_speech_cannot_pass(self):
        clip=dict(source_id='a',sha256='hash',**{'in':1,'out':2})
        index={'source':{'sha256':'hash'},'transcript':[dict(id='speech',start=0,end=3,text='Keep this whole thought')],'visual':[]}
        report=evaluate_script({'clips':[clip]}, {'a':index})
        self.assertEqual({f['criterion'] for f in report['findings']},{'speech_continuity','visual_evidence'})
        self.assertFalse(report['automatic_editorial_acceptance'])
        self.assertEqual(evaluate_script({'clips':[clip]}, {})['findings'][0]['severity'],'error')

from pathlib import Path
import tempfile
import unittest
from edie.models import Route

class ModelTest(unittest.TestCase):
    def test_no_paid_fallback_or_unapproved_payloads(self):
        base=dict(base_url='http://127.0.0.1:1/v1',model='test',billing='local',allowed_payloads=['text'])
        with self.assertRaises(ValueError):Route({**base,'billing':'metered'})
        with self.assertRaises(ValueError):Route({**base,'fallback':'paid'})
        with self.assertRaises(ValueError):Route(base).request('/x',b'a','audio/wav',['audio'])
        with self.assertRaises(ValueError):Route({**base,'base_url':'http://user:secret@localhost/v1'})

    def test_bad_transcript_timing_is_preserved_and_flagged(self):
        class Fake(Route):
            def request(self,*args):return {'segments':[{'start':4,'end':2,'text':'Uncertain'},{'start':0,'end':1,'text':'Valid'}]},{}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'a.wav';path.write_bytes(b'fixture')
            result,_=Fake(dict(base_url='http://127.0.0.1/v1',model='test',billing='local',allowed_payloads=['audio'])).transcribe(path,5)
            self.assertFalse(result['segments'][0]['timing_valid']);self.assertTrue(result['segments'][1]['timing_valid'])
            self.assertEqual(result['segments'][0]['text'],'Uncertain')

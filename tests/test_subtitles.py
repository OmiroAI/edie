import tempfile
import unittest
from edie.core import Store
from edie.subtitles import revise

class SubtitleTest(unittest.TestCase):
    def test_corrections_are_new_revisions_and_translation_cannot_be_partial(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);j=s.job(dict(goal='Test',audience='Test',format='16:9',duration=2,language='en'))
            original=s.put('revision',dict(job=j,clips=[{'in':0,'out':2}],cues=[dict(id='a',start=0,end=1,text='It work'),dict(id='b',start=1,end=2,text='Great')]))
            edits=[dict(id='a',text='It works',reason='Grammar')]
            new=revise(s,original,'en',edits,author='agent')
            self.assertEqual(s.get(original,'revision')['cues'][0]['text'],'It work')
            self.assertEqual(s.get(new,'revision')['cues'][0]['original_text'],'It work')
            self.assertEqual(s.get(new,'revision')['cues'][0]['meaning_review'],'required')
            with self.assertRaises(ValueError):revise(s,new,'cs',edits)
            s.db.close()

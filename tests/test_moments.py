import copy
import unittest
from unittest.mock import patch
from edie.moments import project,validate_dialogue


class MomentsTest(unittest.TestCase):
    def fixture(self):
        def row(key,duration,parts):
            return dict(source_id=key,version='1',sha256=key*64,path=key+'.mov',duration=duration,disposition='keep',segments=dict(items=[dict(id=key+str(i),start=a,end=b,score=score,selection='available') for i,(a,b,score) in enumerate(parts)]))
        rows=[row('a',10,[(0,5,80),(5,10,60)]),row('b',20,[(0,20,99)])]
        members=[dict(source_id=r['source_id'],version='1',sha256=r['sha256'],camera_id=camera,offset=offset,included=True,alignment_review='automatic') for r,camera,offset in [(rows[0],'presenter',5),(rows[1],'product',0)]]
        capture=dict(revision=3,groups=[dict(id='session',status='proposed',anchor_source_id='b',primary_audio_source_id='a',members=members)])
        return capture,rows

    def test_one_score_and_unmatched_ranges_without_mutating_originals(self):
        capture,rows=self.fixture();before=copy.deepcopy(rows);result=project(capture,rows)
        primary=[m for m in result['items'] if m['source_id']=='a']
        self.assertEqual([m['score'] for m in primary],[80,60])
        self.assertEqual([(m['angles'][0]['start'],m['angles'][0]['end']) for m in primary],[(5,10),(10,15)])
        residual=[m for m in result['items'] if m['source_id']=='b']
        self.assertEqual([(m['start'],m['end']) for m in residual],[(0,5),(15,20)])
        self.assertTrue(all(m['fragment'] for m in residual));self.assertEqual(rows,before)
        with patch('edie.moments.read',return_value=result):
            with self.assertRaisesRegex(ValueError,'duplicates dialogue'):validate_dialogue(None,'j',[dict(source_id='b',**{'in':6,'out':8})])
            validate_dialogue(None,'j',[dict(source_id='a',**{'in':1,'out':3})])
            validate_dialogue(None,'j',[dict(source_id='b',**{'in':16,'out':18})])

    def test_uncertain_stale_or_excluded_sources_are_not_merged(self):
        for field,value in [('alignment_review','needs_review'),('version','stale'),('included',False)]:
            capture,rows=self.fixture();capture['groups'][0]['members'][0][field]=value
            result=project(capture,rows);self.assertEqual(len(result['items']),3);self.assertFalse(result['relations'])
        capture,rows=self.fixture();rows[0]['disposition']='exclude'
        self.assertFalse(project(capture,rows)['relations'])

    def test_rejected_angle_stays_unavailable_and_boundaries_reproject(self):
        capture,rows=self.fixture();rows[1]['segments']['items'][0]['selection']='rejected'
        result=project(capture,rows);self.assertFalse(result['items'][0]['angles'][0]['eligible'])
        rows[0]['segments']['items'][0]['end']=6;rows[0]['segments']['items'][1]['start']=6
        result=project(capture,rows);self.assertEqual(result['items'][0]['angles'][0]['end'],11)

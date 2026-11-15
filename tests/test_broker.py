import unittest
from edie.broker import change_plan

class BrokerTest(unittest.TestCase):
    def test_plan_checks_identity_scope_and_casefold_conflicts(self):
        class Catalogue:
            def list(self):return [dict(source_id='a',version='1',sha256='a'*64,path='clips/A.mp4'),dict(source_id='b',version='1',sha256='b'*64,path='clips/B.mp4')]
        change=dict(source_id='a',version='1',sha256='a'*64,destination='clips/new.mp4')
        plan=change_plan(Catalogue(),[change],['a'],'clips')
        self.assertFalse(plan['delete_originals'])
        for override in (dict(destination='../escape'),dict(destination='clips/b.mp4'),dict(version='2'),dict(source_id='b')):
            with self.assertRaises(ValueError):change_plan(Catalogue(),[{**change,**override}],['a'],'clips')

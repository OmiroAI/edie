import tempfile
import unittest
from pathlib import Path
from edie.context import Context
from edie.core import Store
from edie.workflow import Workflow
from edie.learning import propose

class LearningTest(unittest.TestCase):
    def test_unfinalised_output_cannot_teach_context(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);j=s.job(dict(goal='Test',audience='Test',format='16:9',duration=1,language='en'))
            Workflow(s).start(j)
            with self.assertRaises(ValueError):propose(s,j,['rejected'],'Change the house style')
            s.db.close()

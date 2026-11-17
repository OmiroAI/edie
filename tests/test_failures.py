import unittest
from jsonschema import ValidationError
from edie.failures import segment_failure

class FailureTest(unittest.TestCase):
    def test_safe_diagnostics(self):
        self.assertEqual(segment_failure(ValueError('Proposed boundary splits speech')),'segment_splits_speech')
        self.assertEqual(segment_failure(ValidationError('private response')),'segment_schema_invalid')
        self.assertEqual(segment_failure(TimeoutError('private endpoint')),'segment_timeout')
        self.assertEqual(segment_failure(ValueError('Subscription decision unavailable; no fallback attempted')),'subscription_unavailable')
        self.assertEqual(segment_failure(ValueError('private transcript or credentials')),'segment_index_failed')

from pathlib import Path
import tempfile
import unittest
from edie.context import Context
from edie.core import Store


class ContextTest(unittest.TestCase):
    def document(self):
        return {'schema_version': 1, 'strategy_id': 'fixture', 'version': '1',
                'rules': [{'id': 'honest', 'kind': 'constraint', 'rule': 'Use evidence'}]}

    def test_activation_pinning_rollback_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)/'config'
            context = Context(config)
            first = context.install(self.document())
            context.activate(first, None)
            store = Store(Path(directory)/'state', config)
            brief = dict(goal='Test', audience='Editor', format='16:9', duration=3, language='en')
            job = store.job(brief)
            second_doc = self.document()
            second_doc['version'] = '2'
            second = context.install(second_doc)
            with self.assertRaises(ValueError):
                context.activate(second, None)
            context.activate(second, first)
            self.assertEqual(store.job_context(job)['version'], '1')
            self.assertEqual(store.get(store.job(brief), 'job')['context']['hash'], second)
            store.db.close()
            reopened = Store(Path(directory)/'state', config)
            self.assertEqual(reopened.job_context(job)['version'], '1')
            context.activate(first, second)
            self.assertEqual(context.active()['hash'], first)
            reopened.db.close()
            self.assertEqual((config/'context/active.json').stat().st_mode & 0o777, 0o600)

    def test_tampered_or_missing_context_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            context = Context(directory)
            first = context.install(self.document())
            with self.assertRaises(ValueError):
                context.active()
            context.activate(first, None)
            (Path(directory)/'context/versions'/f'{first}.json').write_text('{}')
            with self.assertRaises(ValueError):
                context.active()
            with self.assertRaises(ValueError):
                context.load('../outside')

    def test_duplicate_rules_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            document = self.document()
            document['rules'] *= 2
            with self.assertRaises(ValueError):
                Context(directory).install(document)

    def test_markdown_snapshot_is_explicit_and_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            context = Context(directory)
            first = context.install(self.document())
            context.activate(first, None)
            root = Path(directory) / 'context'
            (root / 'SOUL.md').write_text('Curious and precise.')
            (root / 'MEMORY.md').write_text('No accepted lessons yet.')
            second = context.snapshot('2')
            self.assertEqual(context.active()['hash'], first)
            context.activate(second, first)
            (root / 'SOUL.md').write_text('Changed working copy')
            self.assertEqual(context.load(second)['soul'], 'Curious and precise.')
            (root / 'MEMORY.md').unlink()
            (root / 'MEMORY.md').symlink_to(root / 'SOUL.md')
            with self.assertRaises(ValueError):
                context.snapshot('3')

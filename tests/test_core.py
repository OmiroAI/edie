import tempfile
import unittest
from pathlib import Path
from edie.core import Store, source


class RecordsTest(unittest.TestCase):
    def test_revision_binding_and_restart(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            project = store.project('Example')
            brief = dict(goal='story', audience='public', format='16:9', duration=5, language='en')
            first, second = store.job(project, brief), store.job(project, brief)
            revision = store.revision(first, [dict(path='a.mp4', sha256='a'*64, **{'in': 0, 'out': 1})])
            with self.assertRaises(ValueError):
                store.approve(second, revision)
            store.approve(first, revision)
            store.db.close()
            self.assertEqual(Store(root).get(revision, 'revision')['job'], first)

    def test_mount_escape(self):
        with tempfile.TemporaryDirectory() as root:
            media = Path(root) / 'media'
            media.mkdir()
            private = Path(root) / 'private'
            private.write_text('fixture')
            (media / 'link').symlink_to(private)
            for path in ['../private', 'link', str(private)]:
                with self.assertRaises(ValueError):
                    source(media, path)

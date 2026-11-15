import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from edie.core import Store, digest, probe
from edie.tasks import Tasks
from edie.worker import run_once


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class RenderWorkerTest(unittest.TestCase):
    def test_real_render_and_no_duplicate_claim(self):
        with tempfile.TemporaryDirectory() as root:
            media = Path(root) / 'media'
            media.mkdir()
            clip = media / 'fixture.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-t', '2', '-c:v', 'libx264', '-c:a', 'aac', str(clip)], check=True)
            store = Store(Path(root) / 'state')
            job = store.job(dict(goal='test', audience='test', format='16:9', duration=1, language='en'))
            revision = store.revision(job, [{'path': clip.name, 'sha256': digest(clip), 'in': 0.25, 'out': 1.25}])
            tasks = Tasks(store.db)
            task = tasks.submit(job, 'one', {'action': 'render', 'revision': revision})
            self.assertTrue(run_once(store.root, media))
            result = tasks.get(task)
            self.assertEqual(result['state'], 'completed', result)
            output = store.root / result['result']['path']
            self.assertEqual(digest(output), result['result']['sha256'])
            self.assertAlmostEqual(float(probe(output)['format']['duration']), 1, delta=0.15)
            self.assertFalse(run_once(store.root, media))
            self.assertEqual(len(list((store.root/'outputs'/revision).iterdir())), 1)
            # Changed source bytes must fail, preserving the previously accepted artifact.
            clip.write_bytes(b'changed')
            second = tasks.submit(job, 'two', {'action': 'render', 'revision': revision})
            run_once(store.root, media)
            self.assertEqual(tasks.get(second)['state'], 'failed')
            self.assertTrue(output.exists())
            store.db.close()

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from edie.core import Store, digest
from edie.index import Catalogue
from edie.preprocess import prepare


class CatalogueTest(unittest.TestCase):
    def test_rename_and_conflicting_version(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(Path(root)/'state')
            project = store.project('Example')
            media = Path(root)/'media'
            media.mkdir()
            original = media/'original'
            original.write_bytes(b'fixture')
            entry = dict(source_id='stable', version='1', path='original', sha256=digest(original))
            index = Catalogue(store)
            index.ingest(project, [entry], media)
            original.rename(media/'renamed')
            entry['path'] = 'renamed'
            self.assertEqual(index.ingest(project, [entry], media)[0]['source_id'], 'stable')
            (media/'renamed').write_bytes(b'changed')
            entry['sha256'] = digest(media/'renamed')
            with self.assertRaises(ValueError):
                index.ingest(project, [entry], media)
            entry['version'] = '2'
            self.assertEqual(len(index.ingest(project, [entry], media)), 2)
            store.db.close()

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_frames_timestamps_cache_and_bounds(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(Path(root)/'state')
            project = store.project('Example')
            media = Path(root)/'media'
            media.mkdir()
            video = media/'clip.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-t','3','-c:v','libx264',str(video)],check=True)
            Catalogue(store).ingest(project,[dict(source_id='s',version='v',path=video.name,sha256=digest(video))],media)
            result = prepare(store,project,'s','v',media,chunk_seconds=2,overlap=0.5)
            self.assertEqual(len(result['chunks']),2)
            frames = result['chunks'][0]['frames']
            self.assertEqual([f['source_seconds'] for f in frames],[0,1])
            self.assertEqual(result,prepare(store,project,'s','v',media,chunk_seconds=2,overlap=0.5))
            self.assertEqual(len(list((store.root/result['cache_root']).glob('*.json'))),2)
            (store.root/result['cache_root']/frames[0]['path']).unlink()
            repaired = prepare(store,project,'s','v',media,chunk_seconds=2,overlap=0.5)
            self.assertEqual(repaired['chunks'][1], result['chunks'][1])
            self.assertNotEqual(repaired['chunks'][0]['frames'][0]['path'], frames[0]['path'])
            with self.assertRaises(ValueError):
                prepare(store,project,'s','v',media,fps=8,max_frames=2)
            store.db.close()

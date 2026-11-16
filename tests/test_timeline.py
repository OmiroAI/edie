import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import opentimelineio as otio
from edie.core import Store,digest,render
from edie.timeline import commit,compile_timeline,cues_from_transcripts
from edie.export import package

class TimelineTest(unittest.TestCase):
    def test_otio_render_subtitles_and_xml(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);media=root/'media';media.mkdir();clip=media/'test.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-f','lavfi','-i','sine=frequency=440','-t','3','-c:v','libx264','-c:a','aac',str(clip)],check=True)
            store=Store(root/'state');job=store.job(dict(goal='Test',audience='Test',format='16:9',duration=2,language='en'))
            clips=[dict(path=clip.name,sha256=digest(clip),**{'in':0.5,'out':1.5}),dict(path=clip.name,sha256=digest(clip),**{'in':2,'out':3})]
            cues=cues_from_transcripts(clips,{digest(clip):{'transcript':[dict(id='a',start=0.5,end=1.4,text='First'),dict(id='b',start=2,end=2.8,text='Second')]}})
            self.assertEqual(cues[1]['start'],1)
            rev=commit(store,job,clips,media,cues,overlays=[dict(path=clip.name,sha256=digest(clip),at=0.25,**{"in":1.5,"out":2})])
            preview=render(store,rev,media)
            folder=Path(package(store,rev,preview,media))
            result=json.loads((folder/'validation.json').read_text())
            self.assertEqual(result['xml_library_roundtrip'],'passed')
            self.assertIn('00:00:01,000',(folder/'subtitles.en.srt').read_text())
            from edie.returns import import_timeline
            received=import_timeline(store,job,rev,folder,dict(timeline_path='timeline.xml',timeline_sha256=digest(folder/'timeline.xml'),srt_path='subtitles.en.srt',srt_sha256=digest(folder/'subtitles.en.srt')),media)
            human=store.get(received,'revision')
            self.assertEqual(human['author'],'human')
            self.assertEqual(human['clips'][1]['in'],2)
            self.assertEqual(human['cues'][1]['text'],'Second')
            copied=next((folder/'media').iterdir())
            self.assertNotEqual(copied.stat().st_ino,clip.stat().st_ino)
            timeline=otio.adapters.read_from_string(store.get(rev,'revision')['otio'],'otio_json')
            timeline.tracks[0][0].effects.append(otio.schema.Effect(effect_name='Unknown'))
            with self.assertRaises(ValueError):compile_timeline(timeline)
            store.db.close()

    def test_graphics_transition_and_explicit_xml_loss(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);media=root/'media';media.mkdir();clip=media/'test.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-f','lavfi','-i','sine=frequency=440','-t','3','-c:v','libx264','-c:a','aac',str(clip)],check=True)
            s=Store(root/'state');j=s.job(dict(goal='Test',audience='Test',format='9:16',duration=2,language='en'))
            clips=[dict(path=clip.name,sha256=digest(clip),**{'in':0,'out':1}),dict(path=clip.name,sha256=digest(clip),**{'in':1,'out':2})]
            r=commit(s,j,clips,media,titles=[dict(text='A useful detail',start=0,end=.8)],transitions=[dict(kind='dip_to_black',at=1,duration=.2)])
            preview=render(s,r,media)
            with self.assertRaises(ValueError):package(s,r,preview,media)
            folder=Path(package(s,r,preview,media,allow_title_sidecar=True))
            self.assertTrue((folder/'titles.json').exists());self.assertTrue((folder/'transitions.json').exists())
            self.assertEqual(json.loads((folder/'validation.json').read_text())['height'],1280)
            s.db.close()

import tempfile
import json
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch
from edie.core import Store,digest,probe
from edie.adaptive import plan_focus,upgrade

class AdaptiveTest(unittest.TestCase):
    def test_transcript_guides_bounded_windows_and_cut_candidates(self):
        cues=[dict(id='a',start=1,end=3,text='Look at this screen'),dict(id='b',start=5,end=7,text='A finished sentence'),dict(id='bad',start=10,end=4,text='Show me',timing_valid=False)]
        windows,cuts,omitted=plan_focus(cues,[9],12)
        self.assertTrue(any(w['kind']=='transcript_focus' for w in windows))
        self.assertTrue(any(c['kind']=='speech_pause' and c['seconds']==3 for c in cuts))
        self.assertTrue(all(0<=w['start']<w['end']<=12 for w in windows))
        self.assertLessEqual(len(windows),3)

    def test_actual_frames_transcript_link_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);media=root/'media';media.mkdir();video=media/'fixture.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=24','-t','4','-c:v','libx264',str(video)],check=True)
            store=Store(root/'state');entry=dict(source_id='test',version='1',sha256=digest(video),path=video.name)
            index=dict(source=entry,duration=4,media=probe(video),transcript=[dict(id='cue',start=0,end=3,text='Look at this demonstration')],transcript_issues=[],visual=[],usage=[],coverage={'speech':'retained'})
            calls=[]
            class Fake:
                def __init__(self,config):pass
                def chat(self,prompt,frames):calls.append((prompt,frames));return 'Visible action at supplied times.',{'known_cost_micro_usd':0}
            with patch('edie.adaptive.Route',Fake):
                result=upgrade(store,index,media,{'model':'local','base_url':'http://localhost/v1'})
                self.assertEqual(result['analysis_version'],4);self.assertGreaterEqual(result['coverage']['baseline_frames'],4);self.assertLessEqual(result['coverage']['max_gap_seconds'],1.1)
                self.assertTrue(any('cue' in v['transcript_refs'] for v in result['visual']))
                self.assertTrue(any('demonstration' in p for p,_ in calls));count=len(calls)
                self.assertEqual(upgrade(store,index,media,{'model':'local','base_url':'http://localhost/v1'}),result);self.assertEqual(len(calls),count)
                self.assertEqual(result['transcript'],index['transcript'])
            from edie.index import Catalogue
            from edie.tasks import Tasks
            from edie.worker import run_once
            Catalogue(store).ingest([entry],media)
            job=store.job(dict(goal='Cached visual upgrade',audience='Editor',format='16:9',duration=4,language='en'))
            route_file=root/'routes.json';route_file.write_text(json.dumps({'vision':{'model':'local','base_url':'http://localhost/v1'}}))
            task=Tasks(store.db).submit(job,'visual-upgrade',dict(action='visual_index',sources=[{'source_id':'test','version':'1'}]))
            self.assertTrue(run_once(store.root,media,'visual_index',route_file))
            self.assertEqual(Tasks(store.db).get(task)['state'],'completed')

            store.db.close()

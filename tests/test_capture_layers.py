import copy
import tempfile
import unittest
import numpy as np
from unittest.mock import patch
from edie.capture import Capture,align
from edie.layers import resolve_overlay,script_layers
from edie.core import Store
from edie.workflow import Workflow

class CaptureTest(unittest.TestCase):
    def test_audio_offset_and_ambiguous_signal(self):
        rng=np.random.default_rng(4)
        raw=rng.normal(size=24000);reference=np.convolve(raw,np.ones(8)/8,mode='same')+2
        member=reference[3250:18250]*.8+.1
        result=align(reference,member)
        self.assertEqual(result['confidence'],'strong_candidate');self.assertAlmostEqual(result['offset'],32.5,places=2)
        self.assertIsNone(align(reference,np.ones(10000))['offset'])
        # Two chunks with substantially different offsets must not become approved sync.
        drifted=np.r_[reference[1000:6000],reference[6100:11100]]
        self.assertIsNone(align(reference,drifted)['offset'])

    def test_sync_gate_mapping_and_human_authority(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);job=s.job(dict(goal='Unboxing',audience='Viewers',format='16:9',duration=20,language='en'));Workflow(s).start(job)
            a=dict(source_id='a',version='1',sha256='a'*64,path='a.mp4');b=dict(source_id='b',version='1',sha256='b'*64,path='b.mp4')
            indexes={'a':dict(source=a,duration=30),'b':dict(source=b,duration=30)}
            repo=Capture(s);config=repo.save(job,dict(schema_version=1,mode='multicam',sources={},groups=[dict(id='g',name='Session',status='proposed',anchor_source_id='a',primary_audio_source_id='a',members=[{**a,'offset':0,'camera_id':'front','included':True},{**b,'offset':5,'camera_id':'detail','included':True}])]),0,'fixture')
            class Agent:
                store=s
                def indexes(self):return indexes
                def resolve(self,items):return [{**items[0],**indexes[items[0]['source_id']]['source']}]
            agent=Agent();clips=[{**a,'in':10,'out':20}];item=dict(sync_group_id='g',sync_capture_revision=1,source_id='b',segment_id='beat-b',at=1,duration=3,purpose='Show same action')
            with self.assertRaisesRegex(ValueError,'Confirm camera'):resolve_overlay(agent,job,item,clips)
            with patch('edie.editorial.indexes',return_value=indexes):
                with self.assertRaisesRegex(ValueError,'shared coverage'):
                    repo.confirm(job,dict(expected_revision=1,group_id='g',included=['a','b'],offsets={'a':0,'b':100},primary_audio_source_id='a'))
                repo.confirm(job,dict(expected_revision=1,group_id='g',included=['a','b'],offsets={'a':0,'b':5},primary_audio_source_id='a'))
            item['sync_capture_revision']=2;overlay=resolve_overlay(agent,job,item,clips)
            self.assertEqual(overlay['in'],6);self.assertEqual(overlay['out'],9);self.assertEqual(overlay['audio'],'muted')
            layers=script_layers(dict(clips=clips,overlays=[overlay]))
            self.assertEqual(layers['audio'][0]['source_id'],'a');self.assertEqual(layers['picture'][1]['source_id'],'b')
            self.assertEqual(layers['picture'][1]['role'],'alternate_camera')
            with self.assertRaisesRegex(ValueError,'one dialogue beat'):resolve_overlay(agent,job,{**item,'at':9},clips)
            with self.assertRaisesRegex(ValueError,'alignment changed'):resolve_overlay(agent,job,{**item,'sync_capture_revision':1},clips)
            self.assertFalse(Workflow(s).get(job)['approvals']);s.db.close()

    def test_automatic_alignment_accepts_evidence_and_keeps_uncertain_for_review(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);job=s.job(dict(goal='Review',audience='Viewers',format='16:9',duration=20,language='en'));Workflow(s).start(job)
            a=dict(source_id='a',version='1',sha256='a'*64,path='a.mp4');b=dict(source_id='b',version='1',sha256='b'*64,path='b.mp4')
            indexes={'a':dict(source=a,duration=100),'b':dict(source=b,duration=20)}
            repo=Capture(s);body=dict(mode='multicam',sources={},groups=[dict(id='g',status='proposed',anchor_source_id='a',primary_audio_source_id='b',members=[{**a,'offset':0,'included':True},{**b,'offset':10,'included':True,'confidence':'strong_candidate','matches':[]}])])
            repo.save(job,body,0,'fixture')
            with patch('edie.editorial.indexes',return_value=indexes):
                result=repo.accept_confident(job,dict(expected_revision=1,group_id='g'))
                self.assertEqual(result['groups'][0]['status'],'proposed')
                self.assertEqual(result['groups'][0]['members'][1]['alignment_review'],'needs_review')
                result['groups'][0]['members'][1]['matches']=[dict(offset=10,correlation=.9,margin=.2),dict(offset=10.01,correlation=.85,margin=.15)]
                result=repo.save(job,result,result['revision'],'fixture')
                result=repo.accept_confident(job,dict(expected_revision=result['revision'],group_id='g'))
                self.assertEqual(result['groups'][0]['status'],'confirmed')
                self.assertEqual(result['groups'][0]['approval_origin'],'automatic')
                self.assertEqual(result['groups'][0]['members'][1]['alignment_review'],'automatic')
                self.assertFalse(Workflow(s).get(job)['approvals'])
            s.db.close()

    def test_picture_coverage_keeps_dialogue_audio_in_real_render(self):
        import subprocess
        from pathlib import Path
        from edie.core import digest,render
        from edie.timeline import commit,cues_from_transcripts
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);media=root/'media';media.mkdir()
            for name,color,tone in [('a','red',440),('b','blue',880)]:
                subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color={color}:size=160x90:rate=30','-f','lavfi','-i',f'sine=frequency={tone}','-t','3','-c:v','libx264','-c:a','aac',str(media/(name+'.mp4'))],check=True,capture_output=True)
            s=Store(root/'state');job=s.job(dict(goal='Unboxing',audience='Viewers',format='16:9',duration=2,language='en'))
            clip=dict(source_id='a',path='a.mp4',sha256=digest(media/'a.mp4'),**{'in':0,'out':2})
            overlay=dict(source_id='b',path='b.mp4',sha256=digest(media/'b.mp4'),**{'in':.5,'out':1.5},at=.5,picture_role='b_roll',audio='muted')
            cues=cues_from_transcripts([clip],{clip['sha256']:dict(transcript=[dict(id='spoken',start=0,end=2,text='The dialogue continues.')])})
            revision=commit(s,job,[clip],media,cues,overlays=[overlay]);path=render(s,revision,media)
            audio=subprocess.run(['ffmpeg','-v','error','-ss','0.6','-i',str(path),'-t','0.6','-vn','-ac','1','-ar','8000','-f','f32le','pipe:1'],check=True,capture_output=True).stdout
            samples=np.frombuffer(audio,dtype='<f4');spectrum=abs(np.fft.rfft(samples));freq=np.fft.rfftfreq(len(samples),1/8000)
            self.assertLess(abs(freq[spectrum.argmax()]-440),4)
            pixels=subprocess.run(['ffmpeg','-v','error','-ss','1','-i',str(path),'-frames:v','1','-vf','scale=16:16','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],check=True,capture_output=True).stdout
            color=np.frombuffer(pixels,dtype=np.uint8).reshape(-1,3).mean(axis=0)
            self.assertGreater(color[2],color[0]+100)
            self.assertEqual(s.get(revision,'revision')['cues'][0]['text'],'The dialogue continues.')
            from edie.capture import sync_preview
            Capture(s).save(job,dict(mode='multicam',sources={},groups=[dict(id='g',anchor_source_id='a',members=[{'source_id':'a','offset':0},{'source_id':'b','offset':0}])]),0,'fixture')
            with patch('edie.capture.proxy',side_effect=lambda store,j,entry:(media/(entry['source_id']+'.mp4'),{'duration':3})):
                preview=sync_preview(s,dict(job=job,payload=dict(group_id='g',capture_revision=1,source_id='b')))
            self.assertTrue((s.root/preview['path']).is_file());self.assertEqual(preview['kind'],'sync_preview')
            from edie.capture import waveform
            entry=dict(source_id='a',version='1',sha256=digest(media/'a.mp4'))
            with patch('edie.editorial.indexes',return_value={'a':dict(source=entry)}),patch('edie.capture.proxy',return_value=(media/'a.mp4',{'duration':3})):
                wave=waveform(s,dict(job=job,payload=entry))
                self.assertEqual(wave['step'],.05);self.assertLessEqual(len(wave['peaks']),61)
                self.assertTrue(all(0<=v<=1 for v in wave['peaks']))
                with self.assertRaisesRegex(ValueError,'source changed'):
                    waveform(s,dict(job=job,payload={**entry,'version':'stale'}))

            s.db.close()

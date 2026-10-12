"""Frozen executable integration test. Uses its own runtime, Qt and FFmpeg only."""
import os, sys, json, time, subprocess, traceback, hashlib
from pathlib import Path
from .runtime import resource_root, data_dir
from .engine import tool, probe
from .model import Project, Caption, Audio

def run_selftest(report_path,require_frozen=False):
    report_path=report_path.resolve();report_path.parent.mkdir(parents=True,exist_ok=True)
    root=report_path.parent/'selftest-media';root.mkdir(exist_ok=True)
    report={'status':'running','frozen':bool(getattr(sys,'frozen',False)),'platform':sys.platform,'python_executable':sys.executable,'resource_root':str(resource_root()),'checks':{},'limitation':'PATH를 제한한 러너 테스트는 Python이 미설치된 실제 Windows 클린 PC 테스트와 다릅니다.'}
    window=None;app=None
    def check(name,ok):
        report['checks'][name]=bool(ok)
        if not ok:raise AssertionError(name)
    try:
        if require_frozen:check('frozen_runtime',report['frozen'])
        for name in ['ffmpeg','ffprobe']:
            p=Path(tool(name)).resolve();report[name]=str(p)
            if require_frozen:check(name+'_bundled',p.is_relative_to(resource_root()))
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen');os.environ.setdefault('QT_MEDIA_BACKEND','ffmpeg')
        from .ui import create_app, Window
        from PySide6 import QtCore
        check('qt_available',True)
        if require_frozen:check('qt_bundled',Path(QtCore.__file__).resolve().is_relative_to(resource_root()))
        app=create_app();window=Window(startup_recovery=False);window.autosave.stop();window.recovery=root/'recovery.sss'
        errors=[];window.error=lambda message:errors.append(str(message))
        def wait_jobs():
            deadline=time.monotonic()+120
            while window.jobs and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
            app.processEvents()
            if errors:raise RuntimeError('\n'.join(errors))
            if window.jobs:window.cancel();raise TimeoutError('worker timeout')
        def ff(*args):
            subprocess.run([tool('ffmpeg'),'-hide_banner','-v','error','-nostdin','-y',*map(str,args)],check=True,timeout=90,creationflags=0x08000000 if os.name=='nt' else 0)
        src=root/'한국어 원본.mp4';bgm=root/'음악.wav'
        ff('-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=4','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=4','-c:v','libx264','-threads','2','-c:a','aac','-shortest',src)
        ff('-f','lavfi','-i','sine=frequency=880:sample_rate=48000:duration=3',bgm)
        original=hashlib.sha256(src.read_bytes()).hexdigest()
        window.load_source(str(src));wait_jobs();check('video_import',window.info['video']['width']==320)
        window.inedit.setText('0.5');window.outedit.setText('2.5');window.import_range();check('in_out_import',window.project.duration==2)
        window.select('clips',0);window.timeline.position=.5;window.split();check('split',len(window.project.clips)==2)
        window.select('clips',0);window.delete();check('delete',abs(window.project.duration-1.5)<.001)
        window.undo_action();window.reorder(0,1);check('reorder',window.project.clips[0].start==1)
        window.project.clips[0].layout='split';window.project.clips[1].layout='blur'
        window.project.clips[0].volume=0.;window.project.clips[1].volume=0.
        window.mutate(lambda:window.project.captions.append(Caption('한글 자막\nPortable 테스트',.2,1.4,font='Noto Sans KR',animation='fade')))
        window.mutate(lambda:window.project.audio.append(Audio(str(bgm),.1,0,1.7,.3,.1,.2)))
        window.project.save(root/'project.sss');before=window.project.data();window.open_project(str(root/'project.sss'));check('project_roundtrip',window.project.data()==before)
        rendered=[];out=root/'export.mp4'
        window.render_job(out,1080,30,'medium','libx264',lambda path:rendered.append(path));wait_jobs()
        check('export_created',bool(rendered) and out.is_file());meta=probe(out);report['output']=meta
        check('export_1080_h264',meta['video']['width']==1080 and meta['video']['height']==1920 and meta['video']['codec_name']=='h264')
        check('audio_present',meta['audio']);check('duration',abs(meta['duration']-2)<.08)
        ff('-i',out,'-f','null','-');check('decode_complete',True)
        pcm=subprocess.check_output([tool('ffmpeg'),'-v','error','-i',str(out),'-vn','-ac','1','-f','f32le','-'],timeout=30,creationflags=0x08000000 if os.name=='nt' else 0)
        import array
        values=array.array('f');values.frombytes(pcm);check('audio_signal',max(map(abs,values),default=0)>.01);check('bgm_mix_signal',max(map(abs,values),default=0)>.01)
        # Frozen builds also verify captions alter output pixels, not merely the model.
        plain=root/'without-caption.mp4';saved=window.project.captions;window.project.captions=[]
        window.render_job(plain,1080,30,'medium','libx264',lambda _:None);wait_jobs();window.project.captions=saved
        def frame(path):return subprocess.check_output([tool('ffmpeg'),'-v','error','-ss','0.8','-i',str(path),'-frames:v','1','-vf','scale=270:480','-f','rawvideo','-pix_fmt','rgb24','-'],timeout=30,creationflags=0x08000000 if os.name=='nt' else 0)
        a,b=frame(out),frame(plain);check('caption_burn_in',sum(abs(x-y)>30 for x,y in zip(a,b))>150)
        window.preview();wait_jobs();check('preview_rendered',window.preview_key is not None)
        frames=[];window.preview_video.videoSink().videoFrameChanged.connect(lambda f:frames.append(f.isValid()));window.preview_player.play()
        deadline=time.monotonic()+12
        while not frames and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        check('qt_preview_decode',any(frames));window.preview_player.stop()
        check('source_unchanged',hashlib.sha256(src.read_bytes()).hexdigest()==original)
        report['status']='passed'
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc()
    finally:
        if window:
            if any(j.isRunning() for j in window.jobs):
                window.cancel()
                for j in list(window.jobs):j.wait(15000)
            window.close()
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['status']=='passed' else 1

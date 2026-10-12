import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from studio.ui import Window, create_app
from studio.model import Clip, Caption, Audio
from studio.engine import tool

def test_ui_edit_undo_reorder(tmp_path):
    app=create_app()
    w=Window(startup_recovery=False);w.autosave.stop()
    w.mutate(lambda:w.project.clips.extend([Clip('a.mp4',0,3,'A'),Clip('b.mp4',2,4,'B')]))
    w.select('clips',0);w.timeline.position=1;w.split();assert len(w.project.clips)==3
    w.undo_action();assert len(w.project.clips)==2
    w.redo_action();assert len(w.project.clips)==3
    w.select('clips',1);w.delete();assert len(w.project.clips)==2
    w.reorder(0,1);assert w.project.clips[0].name=='B'
    w.project.save(tmp_path/'ui.sss');assert (tmp_path/'ui.sss').exists()
    w.grab().save(str(tmp_path/'ui.png'))
    w.recovery=tmp_path/'recovery.sss';w.close()

def test_ui_async_import_and_export(tmp_path):
    import subprocess, time
    app=create_app();w=Window(startup_recovery=False);w.autosave.stop();w.recovery=tmp_path/'recovery.sss'
    src=tmp_path/'sample.mp4'
    subprocess.run([tool('ffmpeg'),'-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=2','-c:v','libx264',str(src)],check=True)
    def finish():
        limit=time.monotonic()+30
        while w.jobs and time.monotonic()<limit:app.processEvents();time.sleep(.01)
        app.processEvents();assert not w.jobs
    w.load_source(str(src));finish();assert w.info['duration']==2
    w.inedit.setText('0.25');w.outedit.setText('1.25');w.import_range();assert w.project.duration==1
    w.select('clips',0);w.canvas_move(.1,0);assert w.project.clips[0].x==.4
    w.project.captions.append(Caption('한글 자막',0,1,font='Noto Sans KR'))
    dest=tmp_path/'ui-output.mp4';result=[]
    w.render_job(dest,360,30,'small','libx264',lambda p:result.append(p));finish();assert dest.exists();assert result
    w.preview();finish();assert w.preview_key is not None
    w.show();app.processEvents();w.grab().save(str(tmp_path/'dark-editor.png'))
    # Verify Qt's media backend actually decodes the rendered output, not just its existence.
    frames=[];w.preview_video.videoSink().videoFrameChanged.connect(lambda f:frames.append(f.isValid()))
    w.preview_player.play();limit=time.monotonic()+5
    while not frames and time.monotonic()<limit:app.processEvents();time.sleep(.01)
    assert any(frames)
    w.preview_player.stop();w.close()

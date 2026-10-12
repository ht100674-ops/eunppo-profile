import os, subprocess, json, hashlib, threading, time
from pathlib import Path
import pytest
from studio.model import Project, Clip, Caption, Audio
from studio.engine import Renderer, probe, write_ass, Cancelled, tool

def ff(*args): subprocess.run([tool('ffmpeg'),'-hide_banner','-loglevel','error','-y',*map(str,args)],check=True)
@pytest.fixture(scope='module')
def media(tmp_path_factory):
    root=tmp_path_factory.mktemp('media'); video=root/'원본 영상.mp4'; bgm=root/'음악.wav'; silent=root/'silent.mkv'
    ff('-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=6','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=6','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',video)
    ff('-f','lavfi','-i','sine=frequency=880:sample_rate=48000:duration=4',bgm)
    ff('-f','lavfi','-i','color=blue:size=320x180:rate=30:duration=2','-c:v','libx264',silent)
    return video,bgm,silent

def test_probe_model_save_split(media,tmp_path):
    video,_,_=media;info=probe(video);assert abs(info['duration']-6)<.1;assert info['audio']
    p=Project(clips=[Clip(str(video),1,5)])
    assert p.split(0,1.5);assert [(x.start,x.end) for x in p.clips]==[(1,2.5),(2.5,5)]
    p.clips.pop(1);p.save(tmp_path/'project.sss');q=Project.load(tmp_path/'project.sss');assert q.data()==p.data()

def test_non_destructive_and_composite(media,tmp_path):
    video,bgm,silent=media; before=hashlib.sha256(video.read_bytes()).hexdigest()
    p=Project(clips=[Clip(str(video),1,2.5,volume=0,layout='split'),Clip(str(silent),0,1,layout='blur')],captions=[Caption('한글 자막\nStreamShort',.2,1.2,font='Noto Sans KR',animation='fade')],audio=[Audio(str(bgm),.3,0,1.8,.4,.1,.2)])
    p.save(tmp_path/'edit.sss');p=Project.load(tmp_path/'edit.sss');out=tmp_path/'result.mp4';progress=[]
    Renderer().render(p,out,720,30,progress=progress.append)
    d=probe(out);v=d['video'];assert (v['width'],v['height'])==(720,1280);assert v['codec_name']=='h264';assert d['audio'];assert abs(d['duration']-2.5)<.08;assert progress[-1]==1
    assert hashlib.sha256(video.read_bytes()).hexdigest()==before
    ff('-i',out,'-f','null','-')
    # Reordering, source crop and audio are all represented in the export.
    raw=subprocess.check_output([tool('ffmpeg'),'-v','error','-ss','2','-i',str(out),'-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','-'])
    assert raw[2]>raw[0]+80  # second clip is blue
    pcm=subprocess.check_output([tool('ffmpeg'),'-v','error','-i',str(out),'-vn','-ac','1','-f','f32le','-'])
    import array
    samples=array.array('f');samples.frombytes(pcm)
    assert max(abs(x) for x in samples)> .01

@pytest.mark.parametrize('layout',['crop','fit','blur','split'])
def test_layouts(media,tmp_path,layout):
    video,_,_=media;p=Project(clips=[Clip(str(video),.2,.7,layout=layout)])
    Renderer().render(p,tmp_path/(layout+'.mp4'),360,30)
    assert probe(tmp_path/(layout+'.mp4'))['video']['height']==640

def test_caption_burn_in(media,tmp_path):
    video,_,_=media;p=Project(clips=[Clip(str(video),0,1)])
    a=tmp_path/'without.mp4';b=tmp_path/'with.mp4';Renderer().render(p,a,360)
    p.captions=[Caption('테스트 한글',0,1,font='Noto Sans KR',size=100,y=.5)]
    Renderer().render(p,b,360)
    def pixels(path):return subprocess.check_output([tool('ffmpeg'),'-v','error','-ss','0.5','-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
    x,y=pixels(a),pixels(b);assert sum(abs(i-j)>30 for i,j in zip(x,y))>300

def test_guard_and_cancel(media,tmp_path):
    video,_,_=media;p=Project(clips=[Clip(str(video),0,1)])
    with pytest.raises(ValueError):Renderer().render(p,video,360)
    r=Renderer();r.cancel()
    with pytest.raises(Cancelled):r.render(p,tmp_path/'cancel.mp4',360)
    assert not (tmp_path/'cancel.mp4').exists()

def test_long_source_model(media):
    video,_,_=media
    # A 15-hour source only stores a path and selected absolute seconds.
    p=Project(clips=[Clip(str(video),53900,53930)])
    assert p.duration==30;assert len(json.dumps(p.data()))<2000

def test_1080_60fps(media,tmp_path):
    video,_,_=media;p=Project(clips=[Clip(str(video),0,.5)])
    Renderer().render(p,tmp_path/'1080.mp4',1080,60)
    v=probe(tmp_path/'1080.mp4')['video'];assert (v['width'],v['height'])==(1080,1920);assert v['avg_frame_rate']=='60/1'

def test_real_ten_hour_seek(tmp_path):
    src=tmp_path/'ten-hours.mkv'
    ff('-f','lavfi','-i','color=green:size=16x16:rate=1:duration=36005','-c:v','libx264','-preset','ultrafast','-g','10',src)
    info=probe(src);assert info['duration']>=36000
    p=Project(clips=[Clip(str(src),35999,36001)])
    Renderer().render(p,tmp_path/'late.mp4',360,30)
    assert abs(probe(tmp_path/'late.mp4')['duration']-2)<.1
    assert src.stat().st_size<20_000_000

def test_cancel_running_preserves_destination(media,tmp_path):
    video,_,_=media;p=Project(clips=[Clip(str(video),0,6)])
    dest=tmp_path/'preserved.mp4';dest.write_bytes(b'previous output')
    r=Renderer();errors=[]
    def work():
        try:r.render(p,dest,1080,60)
        except Exception as e:errors.append(e)
    t=threading.Thread(target=work);t.start()
    for _ in range(200):
        if r.process is not None:break
        time.sleep(.01)
    r.cancel();t.join(15);assert not t.is_alive();assert isinstance(errors[0],Cancelled);assert dest.read_bytes()==b'previous output'
    assert not list(tmp_path.glob('streamshort-*'))

def test_bounded_cache(media,tmp_path):
    from studio.cache import waveform, thumbnail
    video,bgm,_=media
    assert Path(thumbnail(str(video),1,tmp_path)).is_file()
    wave=waveform(str(bgm),0,100000,tmp_path)
    assert wave['duration']==60 and 1<=len(wave['peaks'])<=201

@pytest.mark.parametrize('animation',['pop','slide','scale'])
def test_caption_animation(media,tmp_path,animation):
    video,_,_=media;p=Project(clips=[Clip(str(video),0,.6)],captions=[Caption('안녕',0,.6,font='Noto Sans KR',animation=animation,box=True)])
    Renderer().render(p,tmp_path/(animation+'.mp4'),360)
    assert probe(tmp_path/(animation+'.mp4'))['duration']>.5

def test_audio_cut_and_caption_timing(tmp_path):
    import array, math
    src=tmp_path/'sync-source.mp4'
    ff('-f','lavfi','-i','color=black:size=320x180:rate=30:duration=3','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=3','-af',"volume=enable='lt(t,1.5)':volume=0",'-c:v','libx264','-c:a','aac',src)
    # The tone begins 1.5s into source, hence 0.5s into the extracted clip.
    p=Project(clips=[Clip(str(src),1,2.5)],captions=[Caption('동기화',.5,1,font='Noto Sans KR',size=100,y=.5)])
    out=tmp_path/'sync.mp4';Renderer().render(p,out,360)
    pcm=subprocess.check_output([tool('ffmpeg'),'-v','error','-i',str(out),'-vn','-ac','1','-ar','48000','-f','f32le','-'])
    samples=array.array('f');samples.frombytes(pcm)
    first=next(i for i,x in enumerate(samples) if abs(x)>.02)/48000
    assert abs(first-.5)<.06
    def brightness(t):
        pixels=subprocess.check_output([tool('ffmpeg'),'-v','error','-ss',str(t),'-i',str(out),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
        return sum(x>100 for x in pixels)
    assert brightness(.3)<100;assert brightness(.7)>500;assert brightness(1.2)<100

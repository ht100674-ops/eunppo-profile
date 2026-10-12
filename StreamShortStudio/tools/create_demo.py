"""Generate reproducible sample assets and project without bundled copyrighted media."""
import sys, subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studio.engine import tool
from studio.model import Project, Clip, Caption, Audio
root=Path(__file__).resolve().parents[1]/'demo';root.mkdir(exist_ok=True)
def ff(*args):subprocess.run([tool('ffmpeg'),'-v','error','-y',*map(str,args)],check=True)
video=root/'source.mp4';bgm=root/'bgm.wav'
ff('-f','lavfi','-i','testsrc2=size=640x360:rate=30:duration=6','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=6','-c:v','libx264','-c:a','aac','-shortest',video)
ff('-f','lavfi','-i','sine=frequency=880:sample_rate=48000:duration=4',bgm)
p=Project(name='테스트 쇼츠',clips=[Clip(str(video),1,2.5,'게임 영역',layout='split',volume=.5),Clip(str(video),3,5,'블러 배경',layout='blur',volume=.5)],captions=[Caption('한글 자막 테스트\nStreamShort Studio',.2,1.3,animation='fade'),Caption('컷 · 배치 · BGM 반영',1.6,3.3,animation='pop')],audio=[Audio(str(bgm),0,0,3.5,.25,.2,.4)])
p.save(root/'demo.sss');print(root/'demo.sss')

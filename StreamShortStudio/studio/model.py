from dataclasses import dataclass, field, asdict
from pathlib import Path
import json, uuid, math, os, re

def uid(): return uuid.uuid4().hex[:12]
@dataclass
class Clip:
    path: str
    start: float
    end: float
    name: str = '클립'
    id: str = field(default_factory=uid)
    volume: float = 1.0
    layout: str = 'crop'
    zoom: float = 1.0
    x: float = .5
    y: float = .5
    background: str = '#121521'
    top: list = field(default_factory=lambda:[0.,0.,1.,.65])
    bottom: list = field(default_factory=lambda:[.7,.55,.3,.45])
    @property
    def duration(self): return self.end-self.start
@dataclass
class Caption:
    text: str
    start: float
    end: float
    id: str = field(default_factory=uid)
    font: str = 'Noto Sans KR'
    size: int = 64
    color: str = '#FFFFFF'
    outline: int = 3
    shadow: int = 2
    box: bool = False
    x: float = .5
    y: float = .78
    animation: str = 'none'
@dataclass
class Audio:
    path: str
    start: float = 0.
    source_start: float = 0.
    duration: float = 10.
    volume: float = .25
    fade_in: float = .2
    fade_out: float = .5
    id: str = field(default_factory=uid)
@dataclass
class Project:
    version: int = 1
    name: str = '새 쇼츠'
    clips: list = field(default_factory=list)
    captions: list = field(default_factory=list)
    audio: list = field(default_factory=list)
    ranges: list = field(default_factory=list)
    @property
    def duration(self): return sum(c.duration for c in self.clips)
    def data(self): return asdict(self)
    @classmethod
    def from_data(cls,d):
        if d.get('version')!=1: raise ValueError('지원하지 않는 프로젝트 버전')
        p=cls(name=d.get('name','새 쇼츠'),ranges=d.get('ranges',[]))
        p.clips=[Clip(**x) for x in d.get('clips',[])]
        p.captions=[Caption(**x) for x in d.get('captions',[])]
        p.audio=[Audio(**x) for x in d.get('audio',[])]
        return p
    def save(self,path):
        target=Path(path); tmp=target.with_suffix(target.suffix+'.tmp')
        tmp.write_text(json.dumps(self.data(),ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(tmp,target)
    @classmethod
    def load(cls,path): return cls.from_data(json.loads(Path(path).read_text(encoding='utf-8')))
    def validate(self):
        if not self.clips: raise ValueError('영상 클립을 추가하세요')
        for c in self.clips:
            if not Path(c.path).is_file(): raise ValueError('원본 미디어를 재연결하세요: '+c.path)
            if not all(math.isfinite(v) for v in [c.start,c.end,c.zoom,c.x,c.y,c.volume]): raise ValueError('잘못된 수치')
            if c.start<0 or c.duration<=0 or not 1<=c.zoom<=4 or not 0<=c.x<=1 or not 0<=c.y<=1: raise ValueError('클립 범위를 확인하세요')
            if not 0<=c.volume<=2 or not re.fullmatch(r'#[0-9A-Fa-f]{6}',c.background): raise ValueError('잘못된 음량 / 배경색')
            if c.layout not in ['crop','fit','blur','split']: raise ValueError('잘못된 배치')
            for roi in [c.top,c.bottom]:
                x,y,w,h=roi
                if min(x,y)<0 or min(w,h)<=0 or x+w>1.001 or y+h>1.001: raise ValueError('크롭 영역이 원본을 벗어납니다')
        for a in self.audio:
            if not all(math.isfinite(v) for v in [a.start,a.source_start,a.duration,a.volume,a.fade_in,a.fade_out]) or not 0<=a.volume<=2: raise ValueError('잘못된 오디오 수치')
            if not Path(a.path).is_file() or a.duration<=0 or min(a.start,a.source_start,a.fade_in,a.fade_out)<0: raise ValueError('오디오 범위를 확인하세요')
        for c in self.captions:
            if not all(math.isfinite(v) for v in [c.start,c.end,c.size,c.x,c.y,c.outline,c.shadow]): raise ValueError('잘못된 자막 수치')
            if c.end<=c.start or c.start<0: raise ValueError('자막 시간을 확인하세요')
            if not 8<=c.size<=300 or not 0<=c.x<=1 or not 0<=c.y<=1 or not 0<=c.outline<=20 or not 0<=c.shadow<=20: raise ValueError('자막 스타일 범위를 확인하세요')
            if not re.fullmatch(r'#[0-9A-Fa-f]{6}',c.color) or c.animation not in ['none','fade','pop','slide','scale']: raise ValueError('자막 색상 / 애니메이션을 확인하세요')
    def split(self,index,t):
        c=self.clips[index]
        if not .001<t<c.duration-.001: return False
        d=asdict(c); d['start']=c.start+t; d['id']=uid()
        c.end=c.start+t; self.clips.insert(index+1,Clip(**d)); return True

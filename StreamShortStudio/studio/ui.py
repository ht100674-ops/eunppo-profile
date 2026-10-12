import copy, json, os, tempfile, hashlib, time, sys
from pathlib import Path
from dataclasses import asdict
from PySide6.QtCore import Qt, QUrl, QTimer, QThread, Signal, QRectF, QStandardPaths
from PySide6.QtGui import QColor, QPainter, QPen, QShortcut, QKeySequence, QFont, QPixmap, QFontDatabase
from PySide6.QtWidgets import *
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from .model import Project, Clip, Caption, Audio, uid
from .engine import Renderer, probe, Cancelled
from .cache import thumbnail, waveform
from .runtime import data_dir, resource_root

def tc(t):
    t=max(0,t); h=int(t)//3600; m=int(t)%3600//60; s=t%60
    return f'{h:02}:{m:02}:{s:06.3f}'
def seconds(s):
    v=s.strip().split(':'); result=0.
    for x in v: result=result*60+float(x)
    return result

class Task(QThread):
    done=Signal(object); failed=Signal(str); progress=Signal(float)
    def __init__(self,fn): super().__init__(); self.fn=fn
    def run(self):
        try: self.done.emit(self.fn(self.progress.emit))
        except Cancelled: self.failed.emit('작업이 취소되었습니다.')
        except Exception as e: self.failed.emit(str(e))

class Guide(QWidget):
    def __init__(self,parent):
        super().__init__(parent);self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);self.enabled=False;self.margins=[.08,.2,.15]
    def paintEvent(self,e):
        if not self.enabled:return
        q=QPainter(self);h=self.height();w=min(self.width(),h*9/16);x=(self.width()-w)/2
        q.setPen(QPen(QColor('#ffcf7d'),1,Qt.PenStyle.DashLine));top,bottom,right=self.margins
        q.drawRect(QRectF(x+w*.05,h*top,w*(.95-right),h*(1-top-bottom)))
        q.setPen(QColor('#ffcf7d'));q.drawText(int(x+8),18,'사용자 안전 영역 · 참고 가이드')

class CanvasVideo(QVideoWidget):
    moved=Signal(float,float)
    def __init__(self):
        super().__init__();self.origin=None;self.guide=Guide(self)
    def resizeEvent(self,e):super().resizeEvent(e);self.guide.setGeometry(self.rect());self.guide.raise_()
    def mousePressEvent(self,e):self.origin=e.position()
    def mouseReleaseEvent(self,e):
        if self.origin is not None:
            d=e.position()-self.origin;self.moved.emit(d.x()/max(1,self.width()),d.y()/max(1,self.height()));self.origin=None

class WaveView(QWidget):
    def __init__(self):super().__init__();self.peaks=[];self.setFixedHeight(65)
    def paintEvent(self,e):
        q=QPainter(self);q.fillRect(self.rect(),QColor('#111722'));q.setPen(QColor('#65dcc8'))
        for i,v in enumerate(self.peaks):
            x=int(i*self.width()/max(1,len(self.peaks)));height=max(1,int(v*28));q.drawLine(x,32-height,x,32+height)

class Timeline(QWidget):
    seek=Signal(float); selected=Signal(str,int); changed=Signal(str,int,float); reorder=Signal(int,int); zoomed=Signal(float)
    def __init__(self,parent):
        super().__init__(); self.host=parent; self.scale=75.; self.position=0.; self.drag=None; self.setMinimumHeight(205); self.setMouseTracking(True)
    def rects(self):
        p=self.host.project; out=[]; t=0
        for i,c in enumerate(p.clips):
            out.append(('clips',i,QRectF(110+t*self.scale,40,c.duration*self.scale,46),c.name));t+=c.duration
        for i,a in enumerate(p.audio): out.append(('audio',i,QRectF(110+a.start*self.scale,98,a.duration*self.scale,36),Path(a.path).name))
        for i,c in enumerate(p.captions): out.append(('captions',i,QRectF(110+c.start*self.scale,145,(c.end-c.start)*self.scale,36),c.text))
        return out
    def refresh(self): self.setMinimumWidth(int(130+max(15,self.host.project.duration)*self.scale)); self.update()
    def paintEvent(self,e):
        q=QPainter(self); q.fillRect(self.rect(),QColor('#10131c')); q.setPen(QColor('#8290a7'))
        for y,label in [(65,'영상 · 원음'),(120,'BGM / 효과음'),(167,'수동 자막')]: q.drawText(10,y,label)
        step=max(1,int(60/self.scale))
        for t in range(0,int(self.host.project.duration)+2,step):
            x=int(110+t*self.scale); q.drawText(x,25,f'{t}s'); q.setPen(QColor('#252b38')); q.drawLine(x,32,x,190);q.setPen(QColor('#8290a7'))
        for kind,i,r,label in self.rects():
            q.setBrush(QColor({'clips':'#254665','audio':'#23564c','captions':'#61447a'}[kind])); q.setPen(QPen(QColor('#56d5c0' if self.host.selection==(kind,i) else '#384252'),2 if self.host.selection==(kind,i) else 1));q.drawRoundedRect(r.adjusted(1,1,-1,-1),5,5)
            q.setPen(QColor('#eef4ff')); q.save();q.setClipRect(r.adjusted(7,0,-5,0));q.drawText(r.adjusted(8,0,0,0),Qt.AlignmentFlag.AlignVCenter,label.replace('\n',' '));q.restore()
        x=int(110+self.position*self.scale); q.setPen(QPen(QColor('#fbc775'),2));q.drawLine(x,32,x,193)
    def mousePressEvent(self,e):
        for kind,i,r,_ in reversed(self.rects()):
            if r.contains(e.position()):
                self.selected.emit(kind,i); self.drag=(kind,i,e.position().x(),abs(e.position().x()-r.right())<10); return
        self.seek.emit(max(0,(e.position().x()-110)/self.scale))
    def mouseReleaseEvent(self,e):
        if not self.drag:return
        kind,i,x,edge=self.drag; self.drag=None; delta=(e.position().x()-x)/self.scale
        if abs(delta)<.08:return
        if kind=='clips' and not edge:
            dest=i
            for k,j,r,_ in self.rects():
                if k=='clips' and r.contains(e.position()):dest=j
            self.reorder.emit(i,dest)
        else:self.changed.emit(kind,i,delta if not edge else 100000+delta)
    def wheelEvent(self,e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.scale=max(10,min(300,self.scale*(1.15 if e.angleDelta().y()>0 else 1/1.15)));self.refresh()
        else:super().wheelEvent(e)

class Form(QDialog):
    def __init__(self,title,fields,parent):
        super().__init__(parent);self.setWindowTitle(title);self.widgets={};layout=QFormLayout(self)
        for key,label,value,options in fields:
            if options:
                w=QComboBox();w.addItems(options);w.setCurrentText(str(value))
            elif isinstance(value,bool):w=QCheckBox();w.setChecked(value)
            elif key=='text':w=QPlainTextEdit(str(value));w.setMaximumHeight(100)
            elif key=='font':w=QFontComboBox();w.setCurrentFont(QFont(str(value)))
            else:w=QLineEdit(str(value))
            self.widgets[key]=w;layout.addRow(label,w)
        b=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);b.accepted.connect(self.accept);b.rejected.connect(self.reject);layout.addRow(b)
    def values(self):
        d={}
        for k,w in self.widgets.items():
            d[k]=w.isChecked() if isinstance(w,QCheckBox) else w.toPlainText() if isinstance(w,QPlainTextEdit) else w.currentFont().family() if isinstance(w,QFontComboBox) else w.currentText() if isinstance(w,QComboBox) else w.text()
        return d

class Window(QMainWindow):
    def __init__(self,startup_recovery=True):
        super().__init__(); self.setWindowTitle('StreamShort Studio · 0.1');self.resize(1280,840);self.setMinimumSize(980,680);self.setAcceptDrops(True)
        self.project=Project();self.path=None;self.selection=('clips',-1);self.undo=[];self.redo=[];self.jobs=[];self.renderer=None;self.source=None;self.info=None;self.inpoint=0.;self.outpoint=15.;self.preview_key=None
        base=data_dir(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation));self.base=base;self.cache=base/'cache';self.cache.mkdir(exist_ok=True)
        self.recovery=base/'recovery.sss'; self.recent=base/'recent.json'
        root=QWidget();self.setCentralWidget(root);layout=QVBoxLayout(root);layout.setContentsMargins(16,12,16,12)
        bar=QHBoxLayout();title=QLabel('STREAMSHORT  /  STUDIO');title.setStyleSheet('font-size:18px;font-weight:700;color:#65dcc8');bar.addWidget(title);bar.addStretch()
        for label,fn in [('새 프로젝트',self.new),('열기',self.open_project),('저장',self.save),('다른 이름',lambda:self.save(True)),('MP4 내보내기',self.export)]:bar.addWidget(self.button(label,fn))
        layout.addLayout(bar); self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.build_browser();self.build_editor()
        foot=QHBoxLayout();self.status=QLabel('로컬 전용 · 원본 비파괴 편집');foot.addWidget(self.status,1);self.progress=QProgressBar();self.progress.setFixedWidth(210);foot.addWidget(self.progress);self.cancel_button=self.button('작업 취소',self.cancel);self.cancel_button.setEnabled(False);foot.addWidget(self.cancel_button);layout.addLayout(foot)
        self.autosave=QTimer(self);self.autosave.timeout.connect(self.auto_save);self.autosave.start(30000)
        for key,fn in [('Space',self.play),('S',self.split),('Delete',self.delete),('Ctrl+Z',self.undo_action),('Ctrl+Shift+Z',self.redo_action),('Ctrl+S',self.save),('Left',lambda:self.frame(-1)),('Right',lambda:self.frame(1))]:
            sc=QShortcut(QKeySequence(key),self);sc.activated.connect(lambda f=fn:self.shortcut(f))
        self.refresh()
        if startup_recovery:QTimer.singleShot(100,self.offer_recovery)
    def button(self,text,fn):
        b=QPushButton(text);b.clicked.connect(lambda _=False:fn());return b
    def shortcut(self,fn):
        if isinstance(QApplication.focusWidget(),(QLineEdit,QPlainTextEdit,QTextEdit,QAbstractSpinBox)):return
        fn()
    def error(self,msg):QMessageBox.warning(self,'StreamShort Studio',str(msg))
    def job(self,fn,done):
        if any(j.isRunning() for j in self.jobs):self.error('현재 작업이 끝난 뒤 다시 시도하세요.');return False
        j=Task(fn);self.jobs.append(j);self.cancel_button.setEnabled(self.renderer is not None);j.progress.connect(lambda p:self.progress.setValue(round(p*100)))
        def success(result):self.cancel_button.setEnabled(False);self.renderer=None;done(result)
        def failure(msg):self.cancel_button.setEnabled(False);self.renderer=None;self.error(msg)
        j.done.connect(success);j.failed.connect(failure);j.finished.connect(lambda:self.jobs.remove(j));j.start();return True
    def player(self,parent):
        video=CanvasVideo();video.setMinimumSize(260,200);player=QMediaPlayer(self);audio=QAudioOutput(self);player.setAudioOutput(audio);player.setVideoOutput(video);audio.setVolume(.8)
        player.errorOccurred.connect(lambda err,msg:self.status.setText('재생 오류: '+msg+' · 선택 구간 프록시 사용 가능'))
        return video,player,audio
    def build_browser(self):
        page=QWidget();self.tabs.addTab(page,'01  방송 녹화본 탐색');l=QHBoxLayout(page);left=QVBoxLayout();l.addLayout(left,1);right=QVBoxLayout();l.addLayout(right)
        row=QHBoxLayout();row.addWidget(self.button('녹화본 불러오기',self.load_source));row.addWidget(self.button('선택 구간 프록시',self.source_proxy));self.source_meta=QLabel('MP4 · MOV · MKV / 드래그하여 불러오기');row.addWidget(self.source_meta,1);left.addLayout(row)
        self.source_video,self.source_player,self.source_audio=self.player(page);left.addWidget(self.source_video,1)
        self.source_slider=QSlider(Qt.Orientation.Horizontal);self.source_slider.setRange(0,1000000);self.source_slider.sliderMoved.connect(self.seek_source_slider);left.addWidget(self.source_slider)
        row=QHBoxLayout();self.source_time=QLabel('00:00:00.000');row.addWidget(self.source_time)
        for label,fn in [('−10초',lambda:self.source_player.setPosition(max(0,self.source_player.position()-10000))),('재생 / 정지',lambda:self.toggle(self.source_player)),('+10초',lambda:self.source_player.setPosition(self.source_player.position()+10000))]:row.addWidget(self.button(label,fn))
        self.jump=QLineEdit('00:00:00');self.jump.setMaximumWidth(110);row.addWidget(self.jump);row.addWidget(self.button('시간 이동',self.jump_source));left.addLayout(row)
        self.source_player.positionChanged.connect(self.source_position)
        box=QGroupBox('장면 선택');rl=QVBoxLayout(box);right.addWidget(box)
        self.inedit=QLineEdit('00:00:00.000');self.outedit=QLineEdit('00:00:15.000');self.range_name=QLineEdit('재미있는 장면')
        rl.addWidget(QLabel('시작 IN'));rl.addWidget(self.inedit);rl.addWidget(self.button('현재 위치 → IN',lambda:self.inedit.setText(tc(self.source_seconds()))));rl.addWidget(QLabel('종료 OUT'));rl.addWidget(self.outedit);rl.addWidget(self.button('현재 위치 → OUT',lambda:self.outedit.setText(tc(self.source_seconds()))));rl.addWidget(self.range_name)
        self.loop=QCheckBox('IN / OUT 반복 재생');rl.addWidget(self.loop);rl.addWidget(self.button('구간 목록에 저장',self.add_range));rl.addWidget(self.button('편집 스튜디오로 추가',self.import_range))
        self.range_list=QListWidget();right.addWidget(self.range_list,1);self.range_list.itemClicked.connect(self.select_range);right.addWidget(self.button('선택 구간 삭제',self.remove_range));right.setSpacing(8)
        self.source_offset=0.
    def build_editor(self):
        page=QWidget();self.tabs.addTab(page,'02  쇼츠 편집 스튜디오');layout=QVBoxLayout(page);panels=QSplitter();layout.addWidget(panels,1)
        lib=QWidget();ll=QVBoxLayout(lib);ll.addWidget(QLabel('미디어 / 트랙'))
        self.thumb=QLabel('필요한 클립만 썸네일 생성');self.thumb.setMinimumHeight(75);self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter);ll.addWidget(self.thumb);self.wave=WaveView();ll.addWidget(self.wave)
        self.clip_list=QListWidget();self.clip_list.setMinimumHeight(100);self.clip_list.currentRowChanged.connect(lambda i:self.select('clips',i));ll.addWidget(self.clip_list,1)
        for label,fn in [('선택 썸네일 / 파형 생성',self.analyze_selected),('영상 추가',self.add_video),('BGM / 효과음 추가',self.add_audio),('수동 자막 추가',self.add_caption),('선택 항목 속성',self.edit_selected),('선택 항목 삭제',self.delete),('원본 재연결',self.relink),('최근 프로젝트',self.show_recent),('캐시 비우기',self.clear_cache)]:ll.addWidget(self.button(label,fn))
        lib_scroll=QScrollArea();lib_scroll.setWidgetResizable(True);lib_scroll.setWidget(lib);lib_scroll.setMinimumWidth(205);panels.addWidget(lib_scroll)
        center=QWidget();cl=QVBoxLayout(center);self.preview_video,self.preview_player,self.preview_audio=self.player(page);cl.addWidget(self.preview_video,1);self.preview_video.moved.connect(self.canvas_move)
        self.preview_notice=QLabel('편집 후 “미리보기 갱신” · 실제 렌더 엔진 사용');cl.addWidget(self.preview_notice)
        row=QHBoxLayout();row.addWidget(self.button('재생 / 정지',lambda:self.toggle(self.preview_player)));row.addWidget(self.button('미리보기 갱신',self.preview));self.preview_quality=QComboBox();self.preview_quality.addItems(['360p','720p']);row.addWidget(self.preview_quality);cl.addLayout(row)
        guide_row=QHBoxLayout();self.guide_check=QCheckBox('안전 영역');self.guide_check.toggled.connect(self.guide_toggle);guide_row.addWidget(self.guide_check);guide_row.addWidget(self.button('가이드 조절',self.guide_settings));cl.addLayout(guide_row)
        self.edit_time=QLabel('00:00:00.000 / 00:00:00.000');cl.addWidget(self.edit_time);self.preview_player.positionChanged.connect(self.preview_position);panels.addWidget(center)
        props=QWidget();pl=QVBoxLayout(props);pl.addWidget(QLabel('선택 항목 / 편집'))
        self.selected_label=QLabel('클립을 선택하세요');self.selected_label.setWordWrap(True);self.selected_label.setMinimumHeight(110);pl.addWidget(self.selected_label)
        for label,fn in [('크롭 · 배치 · 음량',self.edit_selected),('분할  S',self.split),('복제',self.duplicate),('앞으로 이동',lambda:self.move(-1)),('뒤로 이동',lambda:self.move(1)),('실행 취소',self.undo_action),('다시 실행',self.redo_action),('배치 / 자막 저장',self.save_preset),('배치 / 자막 적용',self.load_preset),('단축키 안내',self.help)]:pl.addWidget(self.button(label,fn))
        pl.addStretch();pl.addWidget(QLabel('길이 가이드 15 · 30 · 60 · 180초\n가이드 위치는 플랫폼별 확인 필요'));props_scroll=QScrollArea();props_scroll.setWidgetResizable(True);props_scroll.setWidget(props);props_scroll.setMinimumWidth(230);panels.addWidget(props_scroll);panels.setSizes([220,700,240])
        tools=QHBoxLayout();tools.addWidget(QLabel('타임라인 · 드래그: 순서 / 시작 이동 · 우측 끝: 길이'));tools.addStretch();tools.addWidget(self.button('−',lambda:self.zoom(.8)));tools.addWidget(self.button('+',lambda:self.zoom(1.25)));layout.addLayout(tools)
        self.timeline=Timeline(self);self.timeline.seek.connect(self.seek_edit);self.timeline.selected.connect(self.select);self.timeline.changed.connect(self.timeline_change);self.timeline.reorder.connect(self.reorder)
        scroll=QScrollArea();scroll.setWidget(self.timeline);scroll.setWidgetResizable(True);scroll.setFixedHeight(230);layout.addWidget(scroll)
    def snapshot(self):return self.project.data()
    def mutate(self,fn):
        self.undo.append(self.snapshot());self.undo=self.undo[-50:];self.redo.clear()
        try:fn()
        except Exception as e:self.project=Project.from_data(self.undo.pop());self.error(e)
        self.preview_key=None;self.preview_player.pause();self.preview_notice.setText('편집 변경됨 · 미리보기 갱신 필요');self.refresh()
    def undo_action(self):
        if self.undo:self.redo.append(self.snapshot());self.project=Project.from_data(self.undo.pop());self.preview_key=None;self.refresh()
    def redo_action(self):
        if self.redo:self.undo.append(self.snapshot());self.project=Project.from_data(self.redo.pop());self.preview_key=None;self.refresh()
    def refresh(self):
        self.clip_list.blockSignals(True);self.clip_list.clear()
        for c in self.project.clips:self.clip_list.addItem(f'{c.name}  ·  {c.duration:.2f}s')
        if self.selection[0]=='clips':self.clip_list.setCurrentRow(self.selection[1])
        self.clip_list.blockSignals(False);self.range_list.clear()
        for r in self.project.ranges:self.range_list.addItem(f"{r['name']} · {tc(r['start'])} — {tc(r['end'])}")
        self.timeline.refresh();self.edit_time.setText(f'{tc(self.timeline.position)} / {tc(self.project.duration)}');self.setWindowTitle(f'{self.project.name} — StreamShort Studio')
        kind,i=self.selection;items=getattr(self.project,kind)
        if 0<=i<len(items):
            obj=items[i]
            if kind=='clips':details=f'{obj.name}\n{tc(obj.start)} — {tc(obj.end)}\n배치 {obj.layout} · 확대 {obj.zoom:.2f}\n원음 {obj.volume:.0%}'
            elif kind=='audio':details=f'{Path(obj.path).name}\n시작 {obj.start:.2f}s · 길이 {obj.duration:.2f}s\n음량 {obj.volume:.0%}'
            else:details=f'{obj.text}\n{obj.start:.2f}s — {obj.end:.2f}s\n{obj.font} · {obj.size}px'
            self.selected_label.setText(details)
        else:self.selected_label.setText('항목을 선택하세요')
    def select(self,kind,i):self.selection=(kind,i);self.refresh()
    def selected(self):
        kind,i=self.selection;items=getattr(self.project,kind)
        return items[i] if 0<=i<len(items) else None
    def load_source(self,path=None,selected_range=None):
        if not path:path=QFileDialog.getOpenFileName(self,'녹화본 선택','','영상 (*.mp4 *.mkv *.mov *.avi *.webm);;모든 파일 (*)')[0]
        if not path:return
        path=str(Path(path).resolve());self.status.setText('미디어 분석 중…')
        def done(info):
            if not info['video']:self.error('영상 스트림이 없습니다');return
            self.source=path;self.info=info;self.source_offset=0.;v=info['video'];self.source_player.setSource(QUrl.fromLocalFile(path));self.source_meta.setText(f"{tc(info['duration'])} · {v['width']}×{v['height']} · {v.get('avg_frame_rate')} fps · {v.get('codec_name')}");self.status.setText('원본 탐색 준비 완료');self.outedit.setText(tc(min(15,info['duration'])))
            if selected_range:self.inedit.setText(tc(selected_range['start']));self.outedit.setText(tc(selected_range['end']))
        self.job(lambda _:probe(path),done)
    def source_seconds(self):return self.source_offset+self.source_player.position()/1000
    def source_position(self,pos):
        t=self.source_offset+pos/1000;self.source_time.setText(tc(t))
        if self.info and not self.source_slider.isSliderDown():self.source_slider.setValue(round(t/max(1,self.info['duration'])*1000000))
        if self.loop.isChecked():
            try:
                start,end=seconds(self.inedit.text()),seconds(self.outedit.text())
                if end>start and t>=end:self.source_player.setPosition(round(max(0,start-self.source_offset)*1000))
            except ValueError:pass
    def seek_source_slider(self,n):
        if self.info:self.source_player.setPosition(round(max(0,n/1000000*self.info['duration']-self.source_offset)*1000))
    def jump_source(self):
        try:self.source_player.setPosition(round(max(0,seconds(self.jump.text())-self.source_offset)*1000))
        except ValueError:self.error('HH:MM:SS 또는 초 단위로 입력하세요')
    def get_range(self):
        if not self.source:raise ValueError('녹화본을 불러오세요')
        a,b=seconds(self.inedit.text()),seconds(self.outedit.text())
        if a<0 or b<=a or b>self.info['duration']+.01:raise ValueError('IN / OUT 범위가 올바르지 않습니다')
        if b-a>180:raise ValueError('한 장면은 180초 이하로 선택하세요')
        return {'path':self.source,'start':a,'end':b,'name':self.range_name.text() or '장면'}
    def add_range(self):
        try:r=self.get_range();self.mutate(lambda:self.project.ranges.append(r))
        except Exception as e:self.error(e)
    def import_range(self):
        try:r=self.get_range();self.mutate(lambda:self.project.clips.append(Clip(**r)));self.tabs.setCurrentIndex(1)
        except Exception as e:self.error(e)
    def select_range(self,item):
        r=self.project.ranges[self.range_list.row(item)];self.range_name.setText(r['name']);self.inedit.setText(tc(r['start']));self.outedit.setText(tc(r['end']))
        if r['path']!=self.source:self.load_source(r['path'],r)
    def remove_range(self):
        i=self.range_list.currentRow()
        if i>=0:self.mutate(lambda:self.project.ranges.pop(i))
    def source_proxy(self):
        try:r=self.get_range()
        except Exception as e:self.error(e);return
        self.renderer=Renderer();engine=self.renderer;dest=self.cache/(uid()+'.mp4')
        def done(path):self.source_offset=r['start'];self.source_player.setSource(QUrl.fromLocalFile(str(dest)));self.source_player.play();self.status.setText('선택 구간 프록시 재생 · 원본 복귀는 녹화본 다시 불러오기')
        def fn(progress):
            engine.run(['-ss',str(r['start']),'-i',r['path'],'-t',str(r['end']-r['start']),'-vf','scale=960:-2','-c:v','libx264','-preset','veryfast','-crf','25','-c:a','aac',str(dest)],r['end']-r['start'],progress);return str(dest)
        self.job(fn,done)
    def add_video(self):
        path=QFileDialog.getOpenFileName(self,'짧은 영상 추가','','영상 (*.mp4 *.mkv *.mov *.webm);;모든 파일 (*)')[0]
        if not path:return
        def done(info):
            if not info['video']:self.error('영상이 없습니다');return
            if info['duration']>180:self.tabs.setCurrentIndex(0);self.load_source(path);return
            self.mutate(lambda:self.project.clips.append(Clip(str(Path(path).resolve()),0,info['duration'],Path(path).stem)))
        self.job(lambda _:probe(path),done)
    def add_audio(self):
        path=QFileDialog.getOpenFileName(self,'BGM / 효과음','','오디오 (*.mp3 *.wav *.m4a *.flac *.ogg);;모든 파일 (*)')[0]
        if path:self.job(lambda _:probe(path),lambda info:self.mutate(lambda:self.project.audio.append(Audio(str(Path(path).resolve()),self.timeline.position,0,min(info['duration'],max(1,self.project.duration-self.timeline.position))))))
    def add_caption(self):
        c=Caption('자막을 입력하세요',self.timeline.position,min(self.timeline.position+2,max(2,self.project.duration)))
        if c.end<=c.start:c.end=c.start+2
        self.mutate(lambda:self.project.captions.append(c));self.select('captions',len(self.project.captions)-1);self.edit_selected()
    def edit_selected(self):
        obj=self.selected()
        if not obj:return
        d=asdict(obj);kind,i=self.selection; fields=[]
        labels={'name':'이름','start':'시작 (초)','end':'종료 (초)','volume':'음량 (0~2)','layout':'배치 crop / fit / blur / split','zoom':'확대 (1~4)','x':'가로 위치 (0~1)','y':'세로 위치 (0~1)','background':'배경 #RRGGBB','top':'상단 크롭 x,y,w,h (0~1)','bottom':'하단 크롭 x,y,w,h (0~1)','text':'자막 내용','font':'폰트','size':'크기 (1080 기준)','color':'글자 #RRGGBB','outline':'외곽선','shadow':'그림자','box':'배경 박스','animation':'애니메이션','source_start':'오디오 원본 시작 (초)','duration':'길이 (초)','fade_in':'페이드 인 (초)','fade_out':'페이드 아웃 (초)'}
        for k,v in d.items():
            if k in ['id','path']:continue
            fields.append((k,labels.get(k,k),','.join(str(x) for x in v) if isinstance(v,list) else v,['crop','fit','blur','split'] if k=='layout' else ['none','fade','pop','slide','scale'] if k=='animation' else None))
        dialog=Form('선택 항목 속성',fields,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        try:
            vals=dialog.values()
            for k,v in vals.items():
                old=d[k];d[k]=[float(x) for x in v.split(',')] if isinstance(old,list) else bool(v) if isinstance(old,bool) else int(v) if isinstance(old,int) else float(v) if isinstance(old,float) else v
            if any(not QColor(d[k]).isValid() or len(d[k])!=7 for k in ['color','background'] if k in d):raise ValueError('색상은 #RRGGBB 형식입니다')
            new=type(obj)(**d)
            trial=Project.from_data(self.snapshot());getattr(trial,kind)[i]=new;trial.validate()
            self.mutate(lambda:getattr(self.project,kind).__setitem__(i,new))
        except Exception as e:self.error(e)
    def split(self):
        if self.selection[0]!='clips':return
        i=self.selection[1]
        if not 0<=i<len(self.project.clips):return
        local=self.timeline.position-sum(c.duration for c in self.project.clips[:i]);self.mutate(lambda:self.project.split(i,local))
    def delete(self):
        kind,i=self.selection
        if self.selected():self.mutate(lambda:getattr(self.project,kind).pop(i));self.selection=(kind,-1);self.refresh()
    def duplicate(self):
        kind,i=self.selection;o=self.selected()
        if o:
            d=asdict(o);d['id']=uid();self.mutate(lambda:getattr(self.project,kind).insert(i+1,type(o)(**d)))
    def reorder(self,i,j):
        if i!=j:self.mutate(lambda:self.project.clips.insert(j,self.project.clips.pop(i)));self.select('clips',j)
    def move(self,delta):
        k,i=self.selection
        if k=='clips' and 0<=i+delta<len(self.project.clips):self.reorder(i,i+delta)
    def timeline_change(self,kind,i,delta):
        edge=delta>50000;delta=delta-100000 if edge else delta;obj=getattr(self.project,kind)[i]
        def change():
            if kind=='clips':obj.end=max(obj.start+.05,obj.end+delta)
            elif edge:
                if kind=='captions':obj.end=max(obj.start+.05,obj.end+delta)
                else:obj.duration=max(.05,obj.duration+delta)
            else:
                start=max(0,obj.start+delta); snap=round(start*30)/30
                if kind=='captions':obj.end+=snap-obj.start
                obj.start=snap
        self.mutate(change)
    def zoom(self,factor):self.timeline.scale=max(10,min(300,self.timeline.scale*factor));self.timeline.refresh()
    def seek_edit(self,t):self.timeline.position=min(t,self.project.duration);self.preview_player.setPosition(round(self.timeline.position*1000));self.refresh()
    def preview_position(self,pos):self.timeline.position=pos/1000;self.timeline.update();self.edit_time.setText(f'{tc(pos/1000)} / {tc(self.project.duration)}')
    def frame(self,direction):
        if self.tabs.currentIndex()==0:self.source_player.pause();self.source_player.setPosition(max(0,self.source_player.position()+round(direction*1000/30)))
        else:self.preview_player.pause();self.seek_edit(max(0,self.timeline.position+direction/30))
    def toggle(self,player):
        if player is self.preview_player and self.preview_key is None:self.status.setText('편집이 변경되었습니다. 미리보기를 갱신하세요.');return
        player.pause() if player.playbackState()==QMediaPlayer.PlaybackState.PlayingState else player.play()
    def play(self):self.toggle(self.source_player if self.tabs.currentIndex()==0 else self.preview_player)
    def render_job(self,dest,width,fps,quality,encoder,done):
        try:self.project.validate()
        except Exception as e:self.error(e);return
        if any(j.isRunning() for j in self.jobs):self.error('현재 작업 완료 후 시도하세요');return
        frozen=Project.from_data(self.snapshot());self.renderer=Renderer();engine=self.renderer;self.status.setText('선택 구간 렌더링 중…')
        self.job(lambda cb:engine.render(frozen,dest,width,fps,quality,encoder,cb),done)
    def preview(self):
        key=hashlib.sha256(json.dumps(self.snapshot(),sort_keys=True).encode()).hexdigest();dest=self.cache/(key+'-'+self.preview_quality.currentText()+'.mp4')
        def done(path):self.preview_player.setSource(QUrl.fromLocalFile(str(path)));self.preview_key=key;self.preview_notice.setText('렌더된 편집 미리보기 · 자막 / 배치 / 오디오 반영');self.status.setText('미리보기 준비 완료')
        if dest.exists():done(dest)
        else:self.render_job(dest,int(self.preview_quality.currentText()[:-1]),30,'small','libx264',done)
    def export(self):
        if not self.project.clips:self.error('클립을 추가하세요');return
        dialog=Form('MP4 출력', [('width','해상도','1080',['1080','720']),('fps','FPS','30',['30','60']),('quality','품질','medium',['high','medium','small']),('encoder','인코더 (실패 시 CPU 대체)','libx264',['libx264','h264_nvenc','h264_qsv','h264_amf'])],self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        opts=dialog.values(); mb=self.project.duration*({'high':10,'medium':6,'small':3}[opts['quality']]+.192)/8
        dest=QFileDialog.getSaveFileName(self,f'MP4 출력 · 대략 {mb:.1f} MB (가변 비트레이트 추정)',self.project.name+'.mp4','MP4 (*.mp4)')[0]
        if dest:self.render_job(dest,int(opts['width']),int(opts['fps']),opts['quality'],opts['encoder'],lambda path:(self.status.setText('MP4 출력 완료: '+path),QMessageBox.information(self,'출력 완료',path)))
    def cancel(self):
        if self.renderer:self.renderer.cancel()
    def auto_save(self):
        try:
            if self.project.clips or self.project.ranges:self.project.save(self.recovery)
        except OSError as e:self.status.setText('자동 저장 실패: '+str(e))
    def remember(self,path):
        try:old=json.loads(self.recent.read_text(encoding='utf-8')) if self.recent.exists() else []
        except Exception:old=[]
        self.recent.write_text(json.dumps([str(path)]+[x for x in old if x!=str(path)][:9],ensure_ascii=False),encoding='utf-8')
    def save(self,save_as=False):
        path=self.path
        if save_as or not path:path=QFileDialog.getSaveFileName(self,'프로젝트 저장',self.project.name+'.sss','StreamShort (*.sss)')[0]
        if not path:return
        try:self.project.save(path);self.path=path;self.remember(path);self.status.setText('프로젝트 저장 완료')
        except Exception as e:self.error(e)
    def open_project(self,path=None):
        if not path:path=QFileDialog.getOpenFileName(self,'프로젝트 열기','','StreamShort (*.sss)')[0]
        if not path:return
        try:self.project=Project.load(path);self.path=path;self.undo.clear();self.redo.clear();self.selection=('clips',-1);self.preview_key=None;self.preview_player.setSource(QUrl());self.refresh();self.remember(path);self.tabs.setCurrentIndex(1)
        except Exception as e:self.error(e)
    def new(self):
        if self.project.clips and QMessageBox.question(self,'새 프로젝트','현재 편집을 닫을까요? 저장되지 않은 변경은 사라집니다.')!=QMessageBox.StandardButton.Yes:return
        self.project=Project();self.path=None;self.undo.clear();self.redo.clear();self.preview_player.setSource(QUrl());self.selection=('clips',-1);self.refresh()
    def offer_recovery(self):
        if self.recovery.exists() and QMessageBox.question(self,'프로젝트 복구','자동 저장된 편집을 복구할까요?')==QMessageBox.StandardButton.Yes:self.open_project(str(self.recovery));self.path=None
    def relink(self):
        obj=self.selected()
        if not obj or not hasattr(obj,'path'):return
        path=QFileDialog.getOpenFileName(self,'원본 재연결')[0]
        if path:
            old=obj.path
            def apply():
                for o in self.project.clips+self.project.audio:
                    if o.path==old:o.path=str(Path(path).resolve())
                for r in self.project.ranges:
                    if r['path']==old:r['path']=str(Path(path).resolve())
            self.mutate(apply)
    def show_recent(self):
        try:items=json.loads(self.recent.read_text(encoding='utf-8'))
        except Exception:items=[]
        if not items:self.error('최근 프로젝트가 없습니다');return
        path,ok=QInputDialog.getItem(self,'최근 프로젝트','열기',items,0,False)
        if ok:self.open_project(path)
    def clear_cache(self):
        if any(j.isRunning() for j in self.jobs):self.error('작업 중에는 캐시를 지울 수 없습니다');return
        self.preview_player.setSource(QUrl());self.preview_key=None
        removed=0
        for p in self.cache.iterdir():
            try:p.unlink();removed+=1
            except OSError:pass
        self.status.setText(f'캐시 {removed}개 삭제')
    def analyze_selected(self):
        obj=self.selected()
        if not isinstance(obj,(Clip,Audio)):return
        path=obj.path;start=obj.start if isinstance(obj,Clip) else obj.source_start;duration=obj.duration
        def task(progress):
            info=probe(path);thumb=thumbnail(path,start,self.cache) if info['video'] else None
            waves=waveform(path,start,duration,self.cache) if info['audio'] else {'peaks':[],'duration':0}
            return thumb,waves
        def done(result):
            thumb,waves=result
            if thumb:self.thumb.setPixmap(QPixmap(thumb).scaled(210,100,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            self.wave.peaks=waves['peaks'];self.wave.update();self.status.setText(f"선택 구간 파형 {waves['duration']:.1f}초 · 최대 60초만 분석")
        self.job(task,done)
    def canvas_move(self,dx,dy):
        obj=self.selected()
        if not isinstance(obj,Clip) or obj.layout!='crop':return
        def apply():obj.x=max(0,min(1,obj.x-dx));obj.y=max(0,min(1,obj.y-dy))
        self.mutate(apply);self.status.setText('드래그 구도 변경됨 · 미리보기 갱신으로 확인')
    def guide_toggle(self,enabled):self.preview_video.guide.enabled=enabled;self.preview_video.guide.update()
    def guide_settings(self):
        old=self.preview_video.guide.margins
        d=Form('사용자 안전 영역',[(str(i),label,value,None) for i,(label,value) in enumerate(zip(['상단 여백 (0~0.4)','하단 여백 (0~0.4)','오른쪽 여백 (0~0.4)'],old))],self)
        if d.exec()==QDialog.DialogCode.Accepted:
            try:self.preview_video.guide.margins=[max(0,min(.4,float(v))) for v in d.values().values()];self.preview_video.guide.update()
            except ValueError:self.error('숫자를 입력하세요')
    def preset_keys(self,obj):
        if isinstance(obj,Clip):return ['layout','zoom','x','y','background','top','bottom']
        if isinstance(obj,Caption):return ['font','size','color','outline','shadow','box','x','y','animation']
        return []
    def save_preset(self):
        obj=self.selected();keys=self.preset_keys(obj)
        if not keys:return
        path=QFileDialog.getSaveFileName(self,'배치 / 자막 스타일 저장','preset.json','JSON (*.json)')[0]
        if path:
            try:Path(path).write_text(json.dumps({'type':type(obj).__name__,'style':{k:asdict(obj)[k] for k in keys}},ensure_ascii=False),encoding='utf-8')
            except Exception as e:self.error(e)
    def load_preset(self):
        obj=self.selected();keys=self.preset_keys(obj)
        if not keys:return
        path=QFileDialog.getOpenFileName(self,'배치 / 자막 스타일 적용','','JSON (*.json)')[0]
        if path:
            try:
                d=json.loads(Path(path).read_text(encoding='utf-8'))
                if d['type']!=type(obj).__name__:raise ValueError('선택 항목과 프리셋 종류가 다릅니다')
                style=d['style']
                def apply():
                    for k in keys:
                        if k in style:setattr(obj,k,style[k])
                    self.project.validate()
                self.mutate(apply)
            except Exception as e:self.error(e)
    def help(self):QMessageBox.information(self,'단축키','Space 재생 / 정지\nS 선택 클립 분할\nDelete 삭제\nCtrl+Z 실행 취소\nCtrl+Shift+Z 다시 실행\nCtrl+S 저장\n← → 30fps 프레임 이동\nCtrl+휠 타임라인 확대\n\n자막 / 오디오 시작은 타임라인 드래그로 이동합니다.\n영상 순서는 드래그 또는 이동 버튼으로 바꿉니다.\n분할 / 삭제 후 자막과 BGM 시간은 자동으로 당겨지지 않습니다.')
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls():e.acceptProposedAction()
    def dropEvent(self,e):
        urls=e.mimeData().urls()
        if urls:
            path=urls[0].toLocalFile()
            if path.lower().endswith('.sss'):self.open_project(path)
            else:self.load_source(path);self.tabs.setCurrentIndex(0)
    def closeEvent(self,e):
        if any(j.isRunning() for j in self.jobs):self.error('작업을 취소하고 종료될 때까지 기다려 주세요');e.ignore();return
        self.auto_save();self.autosave.stop();self.source_player.stop();self.preview_player.stop();self.source_player.setSource(QUrl());self.preview_player.setSource(QUrl());e.accept()

def create_app():
    app=QApplication.instance() or QApplication([]);app.setOrganizationName('StreamShort');app.setApplicationName('StreamShortStudio');app.setFont(QFont('Noto Sans KR',10))
    font_path=resource_root()/'fonts'/'NotoSansKR.ttf'
    if font_path.exists():QFontDatabase.addApplicationFont(str(font_path))
    app.setStyleSheet('''QWidget{background:#171b26;color:#e3e9f4;} QMainWindow,QDialog{background:#171b26;} QPushButton{background:#272f40;border:1px solid #384257;border-radius:6px;padding:8px 10px;min-height:16px;} QPushButton:hover{background:#33455b;border-color:#65dcc8;} QPushButton:disabled{color:#596575;} QLineEdit,QPlainTextEdit,QListWidget,QComboBox{background:#101520;border:1px solid #344052;border-radius:5px;padding:6px;} QListWidget::item{padding:8px;} QListWidget::item:selected{background:#285369;} QTabBar::tab{padding:12px 22px;background:#202738;} QTabBar::tab:selected{color:#65dcc8;border-bottom:2px solid #65dcc8;} QGroupBox{border:1px solid #344052;border-radius:8px;margin-top:12px;padding-top:14px;} QProgressBar{border:1px solid #344052;border-radius:4px;text-align:center;} QProgressBar::chunk{background:#36bfa9;} QSlider::groove:horizontal{height:5px;background:#323b50;} QSlider::handle:horizontal{background:#65dcc8;width:12px;margin:-5px 0;border-radius:5px;}''')
    return app

def run():
    app=create_app();w=Window();w.show();return app.exec()

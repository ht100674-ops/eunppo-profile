import subprocess, shutil, os, sys, json, tempfile, threading, time
from pathlib import Path
from .runtime import resource_root

class Cancelled(Exception): pass

def tool(name):
    root=resource_root()
    local=root/'bin'/(name+'.exe' if os.name=='nt' else name)
    found=str(local) if local.exists() else None
    if not found and not getattr(sys,'frozen',False):found=shutil.which(name)
    if not found: raise RuntimeError(f'{name} 배포 파일이 없습니다. ZIP 전체를 다시 압축 해제하세요.' if getattr(sys,'frozen',False) else f'{name} 실행파일이 없습니다. bin 폴더 또는 PATH에 설치하세요.')
    return found

def probe(path):
    r=subprocess.run([tool('ffprobe'),'-v','error','-show_format','-show_streams','-of','json',str(path)],stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45,creationflags=0x08000000 if os.name=='nt' else 0)
    if r.returncode: raise RuntimeError(r.stderr[-3000:])
    d=json.loads(r.stdout); v=next((s for s in d['streams'] if s['codec_type']=='video'),None)
    return {'duration':float(d['format'].get('duration',0)), 'video':v,'audio':any(s['codec_type']=='audio' for s in d['streams'])}

def ass_time(t):
    n=max(0,round(t*100)); h,n=divmod(n,360000); m,n=divmod(n,6000); s,n=divmod(n,100)
    return f'{h}:{m:02}:{s:02}.{n:02}'
def ass_color(c): return '&H00'+c[5:7]+c[3:5]+c[1:3]
def write_ass(project,path,w,h):
    rows=['[Script Info]', 'ScriptType: v4.00+',f'PlayResX: {w}',f'PlayResY: {h}','WrapStyle: 0','[V4+ Styles]','Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding','[Events]','Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    styles=[]; events=[]
    for i,c in enumerate(project.captions):
        font=c.font.replace(',','').replace('\n','')
        styles.append(f'Style: S{i},{font},{c.size*w/1080},{ass_color(c.color)},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,{3 if c.box else 1},{c.outline*w/1080},{c.shadow*w/1080},5,20,20,20,1')
        x,y=round(c.x*w),round(c.y*h); tags=f'\\pos({x},{y})'
        if c.animation=='fade': tags+='\\fad(150,150)'
        if c.animation in ['pop','scale']: tags+='\\fscx60\\fscy60\\t(0,150,\\fscx100\\fscy100)'
        if c.animation=='slide': tags=f'\\move({x},{y+round(h*.08)},{x},{y},0,180)'
        txt=c.text.replace('\\','').replace('{','').replace('}','').replace('\r','').replace('\n',r'\N')
        events.append(f'Dialogue: 0,{ass_time(c.start)},{ass_time(c.end)},S{i},,0,0,0,,{{{tags}}}{txt}')
    k=rows.index('[Events]'); rows[k:k]=styles
    Path(path).write_text('\n'.join(rows+events),encoding='utf-8')

class Renderer:
    def __init__(self): self.cancelled=threading.Event(); self.process=None
    def cancel(self):
        self.cancelled.set()
        if self.process and self.process.poll() is None:
            try: self.process.terminate()
            except OSError: pass
    def run(self,args,duration,callback):
        if self.cancelled.is_set(): raise Cancelled()
        with tempfile.TemporaryFile(mode='w+b') as err:
            self.process=subprocess.Popen([tool('ffmpeg'),'-hide_banner','-nostdin','-y','-threads','2','-filter_complex_threads','1','-filter_threads','1',*args,'-progress','pipe:1','-nostats'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=err,creationflags=0x08000000 if os.name=='nt' else 0)
            try:
                for raw in self.process.stdout:
                    line=raw.decode(errors='replace').strip()
                    if line.startswith('out_time_us='):
                        try: callback(min(.99,float(line.split('=')[1])/1e6/max(duration,.001)))
                        except ValueError: pass
                    if self.cancelled.is_set(): self.process.terminate()
                code=self.process.wait(timeout=10)
            finally:
                if self.process.poll() is None: self.process.kill(); self.process.wait()
                self.process.stdout.close()
            if self.cancelled.is_set(): raise Cancelled()
            if code:
                err.seek(0,2); size=err.tell(); err.seek(max(0,size-6000))
                raise RuntimeError(err.read().decode(errors='replace'))
    def render(self,p,output,width=1080,fps=30,quality='medium',encoder='libx264',progress=lambda x:None):
        p.validate(); h=width*16//9; output=Path(output).resolve()
        sources={Path(c.path).resolve() for c in p.clips}|{Path(a.path).resolve() for a in p.audio}
        if output in sources: raise ValueError('원본 경로에 출력할 수 없습니다')
        if output.suffix.lower()!='.mp4': raise ValueError('MP4 확장자를 사용하세요')
        if fps not in [30,60] or width not in [360,720,1080]: raise ValueError('지원하지 않는 출력 설정')
        output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='streamshort-',dir=output.parent) as tmp:
            root=Path(tmp); segments=[]; total=p.duration
            for i,c in enumerate(p.clips):
                info=probe(c.path)
                if c.end>info['duration']+.1: raise ValueError('클립 OUT이 원본 길이를 초과합니다')
                args=['-ss',str(c.start),'-i',c.path]
                if not info['audio']: args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
                if c.layout=='crop':
                    vf=f'scale={int(width*c.zoom)//2*2}:{int(h*c.zoom)//2*2}:force_original_aspect_ratio=increase,crop={width}:{h}:(iw-ow)*{c.x}:(ih-oh)*{c.y}'
                    graph=f'[0:v]{vf},setsar=1,fps={fps},setpts=PTS-STARTPTS[v]'
                elif c.layout=='fit':
                    graph=f'[0:v]scale={width}:{h}:force_original_aspect_ratio=decrease,pad={width}:{h}:(ow-iw)/2:(oh-ih)/2:color={c.background},setsar=1,fps={fps},setpts=PTS-STARTPTS[v]'
                elif c.layout=='blur':
                    graph=f'[0:v]split=2[b][f];[b]scale={width}:{h}:force_original_aspect_ratio=increase,crop={width}:{h},boxblur=20:2[bg];[f]scale={width}:{h}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={fps},setpts=PTS-STARTPTS[v]'
                else:
                    graph='[0:v]split=2[t][b];'
                    for label,roi in [('t',c.top),('b',c.bottom)]:
                        x,y,rw,rh=roi
                        graph+=f'[{label}]crop=trunc(iw*{rw}/2)*2:trunc(ih*{rh}/2)*2:trunc(iw*{x}/2)*2:trunc(ih*{y}/2)*2,scale={width}:{h//2}:force_original_aspect_ratio=increase,crop={width}:{h//2}[{label}o];'
                    graph+=f'[to][bo]vstack=inputs=2,setsar=1,fps={fps},setpts=PTS-STARTPTS[v]'
                ai='0:a' if info['audio'] else '1:a'
                graph+=f';[{ai}]aresample=48000,asetpts=PTS-STARTPTS,volume={c.volume},apad,atrim=duration={c.duration}[a]'
                seg=root/f'{i}.mp4'; segments.append(seg)
                done=sum(x.duration for x in p.clips[:i])
                self.run(args+['-filter_complex',graph,'-map','[v]','-map','[a]','-t',str(c.duration),'-c:v','libx264','-threads','2','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k',str(seg)],c.duration,lambda r:progress(.65*(done+r*c.duration)/total))
            listing=root/'concat.txt'; listing.write_text('\n'.join(f"file '{x.name}'" for x in segments),encoding='utf-8')
            joined=root/'joined.mp4'
            self.run(['-f','concat','-safe','0','-i',str(listing),'-c','copy',str(joined)],total,lambda r:progress(.65+.03*r))
            args=['-i',str(joined)]; graph=''
            for i,a in enumerate(p.audio):
                args+=['-ss',str(a.source_start),'-t',str(a.duration),'-i',a.path]
                dur=min(a.duration,max(0,total-a.start)); fade=min(a.fade_out,dur)
                graph+=f'[{i+1}:a]aresample=48000,asetpts=PTS-STARTPTS,volume={a.volume},afade=t=in:d={min(a.fade_in,dur)},afade=t=out:st={max(0,dur-fade)}:d={fade},adelay={round(a.start*1000)}:all=1[a{i}];'
            if p.audio:
                graph+='[0:a]'+''.join(f'[a{i}]' for i in range(len(p.audio)))+f'amix=inputs={len(p.audio)+1}:duration=first:normalize=0,alimiter=limit=.95:latency=1[aout]'
            final=root/'final.mp4'; ass=root/'captions.ass'; write_ass(p,ass,width,h)
            # No global cwd mutation: run receives absolute video paths and subtitles are copied next to output.
            ass_filter=str(ass).replace('\\','/').replace(':',r'\:').replace("'",r"'\''")
            font_root=resource_root()/'fonts'
            font_filter=str(font_root).replace('\\','/').replace(':',r'\:').replace("'",r"'\''")
            vf=f"subtitles=filename='{ass_filter}':fontsdir='{font_filter}'" if p.captions else 'null'
            if graph: args+=['-filter_complex',graph,'-map','0:v','-map','[aout]']
            else: args+=['-map','0:v','-map','0:a']
            args+=['-vf',vf,'-t',str(total),'-c:v',encoder]
            if encoder=='libx264': args+=['-preset','veryfast','-crf',{'high':'18','medium':'22','small':'27'}[quality]]
            else: args+=['-b:v',{'high':'10M','medium':'6M','small':'3M'}[quality]]
            args+=['-threads','2','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(final)]
            try: self.run(args,total,lambda r:progress(.68+.32*r))
            except RuntimeError:
                if encoder=='libx264': raise
                j=args.index('-c:v'); args[j+1]='libx264'; b=args.index('-b:v'); args[b:b+2]=['-preset','veryfast','-crf','22']
                self.run(args,total,lambda r:progress(.68+.32*r))
            if self.cancelled.is_set(): raise Cancelled()
            os.replace(final,output); progress(1.)
        return str(output)

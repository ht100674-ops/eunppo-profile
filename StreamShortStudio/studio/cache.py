"""Bounded on-demand cache jobs. Never process an entire broadcast."""
import hashlib, json, subprocess, struct, os
from pathlib import Path
from .engine import tool

def key(path,start,end):
    p=Path(path);return hashlib.sha256(f'{p.resolve()}:{p.stat().st_mtime_ns}:{p.stat().st_size}:{start}:{end}'.encode()).hexdigest()

def thumbnail(path,start,cache):
    target=Path(cache)/(key(path,start,start)+'.jpg')
    if not target.exists():
        r=subprocess.run([tool('ffmpeg'),'-v','error','-nostdin','-y','-ss',str(start),'-i',path,'-frames:v','1','-vf','scale=240:-2','-threads','1',str(target)],stdin=subprocess.DEVNULL,capture_output=True,timeout=30,creationflags=0x08000000 if os.name=='nt' else 0)
        if r.returncode:target.unlink(missing_ok=True);raise RuntimeError(r.stderr.decode(errors='replace')[-2000:])
    return str(target)

def waveform(path,start,duration,cache):
    # At most 60 seconds, 8 kHz mono = 0.96 MB. No broadcast-sized PCM buffer.
    duration=min(60,duration);target=Path(cache)/(key(path,start,start+duration)+'.wave.json')
    if target.exists():return json.loads(target.read_text())
    r=subprocess.run([tool('ffmpeg'),'-v','error','-nostdin','-ss',str(start),'-t',str(duration),'-i',path,'-vn','-ac','1','-ar','8000','-f','s16le','-'],stdin=subprocess.DEVNULL,capture_output=True,timeout=45,creationflags=0x08000000 if os.name=='nt' else 0)
    if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace')[-2000:])
    values=struct.unpack('<'+'h'*(len(r.stdout)//2),r.stdout)
    stride=max(1,len(values)//200);peaks=[max((abs(v) for v in values[i:i+stride]),default=0)/32768 for i in range(0,len(values),stride)][:201]
    result={'duration':duration,'peaks':peaks};target.write_text(json.dumps(result));return result

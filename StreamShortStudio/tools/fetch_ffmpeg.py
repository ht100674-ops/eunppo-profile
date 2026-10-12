"""Build-time only HTTPS download with pinned checksum. The shipped app never downloads."""
import hashlib, json, os, shutil, tempfile, urllib.request, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def extract_checked(archive,destination):
    dest=Path(destination).resolve()
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            target=(dest/info.filename.replace('\\','/')).resolve()
            if not target.is_relative_to(dest):raise ValueError('Unsafe archive path')
            if (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Symlink archive entry')
        z.extractall(dest)

def download(url,target):
    req=urllib.request.Request(url,headers={'User-Agent':'StreamShortStudio-build/0.2'})
    with urllib.request.urlopen(req,timeout=180) as response,open(target,'wb') as f:shutil.copyfileobj(response,f)

def fetch():
    lock=json.loads((ROOT/'tools'/'ffmpeg-lock.json').read_text());cache=ROOT/'vendor-downloads';cache.mkdir(exist_ok=True)
    archive=cache/lock['asset']
    def digest(p):
        h=hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        return h.hexdigest()
    if not archive.exists():
        tmp=archive.with_suffix('.download')
        try:download(lock['url'],tmp);os.replace(tmp,archive)
        finally:tmp.unlink(missing_ok=True)
    if digest(archive)!=lock['sha256']:archive.unlink();raise RuntimeError('FFmpeg checksum mismatch; download rejected')
    with tempfile.TemporaryDirectory(prefix='ffmpeg-vendor-') as temp:
        extract_checked(archive,temp);files=list(Path(temp).rglob('ffmpeg.exe'))
        if len(files)!=1:raise RuntimeError('Expected one ffmpeg.exe')
        vendor=files[0].parent.parent
        (ROOT/'bin').mkdir(exist_ok=True)
        for name in ['ffmpeg.exe','ffprobe.exe']:
            source=vendor/'bin'/name
            if not source.is_file():raise RuntimeError('Missing '+name)
            shutil.copy2(source,ROOT/'bin'/name)
        notices=ROOT/'licenses'/'ffmpeg-provider';notices.mkdir(parents=True,exist_ok=True)
        for p in vendor.iterdir():
            if p.name=='bin':continue
            if p.is_dir():shutil.copytree(p,notices/p.name,dirs_exist_ok=True)
            else:shutil.copy2(p,notices/p.name)
        (notices/'ORIGIN.json').write_text(json.dumps(lock,indent=2),encoding='utf-8')
    print('FFmpeg/FFprobe fetched and checksum verified.')
if __name__=='__main__':fetch()

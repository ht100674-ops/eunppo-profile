"""Runtime paths work from arbitrary cwd, without system Python or FFmpeg."""
import os, sys, tempfile
from pathlib import Path

def resource_root():
    return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1])).resolve()

def executable_dir():
    return Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else resource_root()

def data_dir(fallback=None):
    base=executable_dir()
    if (base/'portable.ini').exists():
        dest=base/'Data'
        try:
            dest.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryFile(dir=dest):pass
            return dest
        except OSError:pass
    if fallback is None:
        fallback=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local'/'share')))/'StreamShort'/'StreamShortStudio'
    dest=Path(fallback);dest.mkdir(parents=True,exist_ok=True);return dest

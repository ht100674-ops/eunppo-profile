"""Validate required bundle files, collect notices, and zip a self-contained Windows app."""
import hashlib, json, platform, shutil, sys, zipfile
from pathlib import Path
from importlib.metadata import distribution
ROOT=Path(__file__).resolve().parents[1]

def validate_bundle(folder):
    folder=Path(folder);internal=folder/'_internal'
    required=[folder/'StreamShortStudio.exe',internal/'bin'/'ffmpeg.exe',internal/'bin'/'ffprobe.exe',internal/'fonts'/'NotoSansKR.ttf',internal/'PySide6'/'QtMultimedia.pyd',internal/'PySide6'/'QtMultimediaWidgets.pyd',internal/'PySide6'/'Qt6Multimedia.dll',internal/'PySide6'/'Qt6MultimediaWidgets.dll',internal/'PySide6'/'plugins'/'platforms'/'qwindows.dll',internal/'PySide6'/'plugins'/'multimedia'/'ffmpegmediaplugin.dll']
    missing=[str(p.relative_to(folder)) for p in required if not p.is_file()]
    if not list(internal.glob('python3*.dll')):missing.append('_internal/python3*.dll')
    for pattern in ['vcruntime140.dll','msvcp140.dll','avcodec-*.dll','avformat-*.dll','avutil-*.dll','swresample-*.dll','swscale-*.dll']:
        if not list(internal.rglob(pattern)):missing.append('Qt FFmpeg runtime: '+pattern)
    if missing:raise RuntimeError('Incomplete portable bundle:\n'+'\n'.join(missing))
    return required

def package():
    if sys.platform!='win32':raise RuntimeError('Windows build only')
    folder=ROOT/'dist'/'StreamShortStudio';validate_bundle(folder)
    for name in ['portable.ini','PORTABLE_README.txt','USER_GUIDE.md','THIRD_PARTY.md','LICENSE','Validate-Clean-Windows.cmd','Validate-Clean-Windows.ps1']:
        shutil.copy2(ROOT/name,folder/name)
    lic=folder/'licenses';shutil.copytree(ROOT/'licenses',lic,dirs_exist_ok=True)
    shutil.copytree(ROOT/'fonts',lic/'fonts',dirs_exist_ok=True)
    for package_name in ['PySide6','PySide6-Essentials','PySide6-Addons','shiboken6','pyinstaller']:
        d=distribution(package_name)
        for f in d.files or []:
            if any(x in str(f).lower() for x in ['license','copying','notice']):
                target=lic/package_name/str(f);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(d.locate_file(f),target)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if not python_license.exists():raise RuntimeError('Python license notice not found')
    shutil.copy2(python_license,lic/'PYTHON-LICENSE.txt')
    build_info={'python':sys.version,'platform':platform.platform(),'pyside6':distribution('PySide6').version,'pyinstaller':distribution('pyinstaller').version,'ffmpeg':json.loads((ROOT/'tools'/'ffmpeg-lock.json').read_text()),'frozen_self_test':'pending','clean_windows_test':'not_run'}
    (folder/'BUILD_INFO.json').write_text(json.dumps(build_info,ensure_ascii=False,indent=2),encoding='utf-8')
    print(folder)

if __name__=='__main__':package()

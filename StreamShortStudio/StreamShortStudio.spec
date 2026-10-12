# Native Windows x64 build; Python/Qt/FFmpeg are all included in the onedir bundle.
from pathlib import Path
import sys
from PyInstaller.utils.hooks import copy_metadata
root=Path(SPECPATH)
if sys.platform!='win32':raise SystemExit('Windows builds must run on Windows. Use .github/workflows/windows-portable.yml')
required=[root/'bin'/'ffmpeg.exe',root/'bin'/'ffprobe.exe']
for path in required:
    if not path.is_file():raise SystemExit(f'Missing bundled dependency: {path}')
metadata=[]
for name in ['PySide6','PySide6-Essentials','PySide6-Addons','shiboken6']:
    metadata+=copy_metadata(name)
a=Analysis([str(root/'main.py')],pathex=[str(root)],binaries=[(str(x),'bin') for x in required],datas=[(str(root/'fonts'),'fonts'),(str(root/'licenses'),'licenses'),(str(root/'THIRD_PARTY.md'),'.'),*metadata],hiddenimports=['studio.selftest','PySide6.QtMultimedia','PySide6.QtMultimediaWidgets'],hookspath=[],hooksconfig={},excludes=['PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtQml','PySide6.QtQuick','PySide6.Qt3DCore','tkinter','numpy'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='StreamShortStudio',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,uac_admin=False,contents_directory='_internal')
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='StreamShortStudio')

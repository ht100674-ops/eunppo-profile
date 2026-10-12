import importlib.util, json, sys, zipfile
from pathlib import Path
import pytest
from studio.runtime import resource_root, data_dir
from studio.engine import tool

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_frozen_no_path_fallback(tmp_path,monkeypatch):
    monkeypatch.setattr(sys,'frozen',True,raising=False);monkeypatch.setattr(sys,'_MEIPASS',str(tmp_path),raising=False)
    # A system FFmpeg exists on the host, but a frozen package must reject a missing bundled executable.
    with pytest.raises(RuntimeError,match='ZIP'):tool('ffmpeg')
    (tmp_path/'bin').mkdir();name='ffmpeg.exe' if sys.platform=='win32' else 'ffmpeg';(tmp_path/'bin'/name).write_bytes(b'test')
    assert Path(tool('ffmpeg')).is_relative_to(resource_root())

def test_portable_data_and_readonly_fallback(tmp_path,monkeypatch):
    import studio.runtime as runtime
    monkeypatch.setattr(runtime,'executable_dir',lambda:tmp_path);(tmp_path/'portable.ini').touch()
    assert data_dir(tmp_path/'fallback')==tmp_path/'Data'
    monkeypatch.setattr(runtime.tempfile,'TemporaryFile',lambda **kwargs:(_ for _ in ()).throw(PermissionError()))
    assert data_dir(tmp_path/'fallback')==tmp_path/'fallback'

def test_archive_traversal_rejected(tmp_path):
    fetch=module('fetch_ffmpeg');bad=tmp_path/'bad.zip'
    with zipfile.ZipFile(bad,'w') as z:z.writestr('../escaped.txt','bad')
    with pytest.raises(ValueError):fetch.extract_checked(bad,tmp_path/'output')
    assert not (tmp_path/'escaped.txt').exists()

def test_bundle_inventory_rejects_missing_dlls(tmp_path):
    package=module('package_portable')
    with pytest.raises(RuntimeError,match='Incomplete'):package.validate_bundle(tmp_path)

def test_failed_frozen_test_blocks_release_zip(tmp_path,monkeypatch):
    final=module('finalize_portable');monkeypatch.setattr(final,'ROOT',tmp_path);report=tmp_path/'report.json'
    report.write_text(json.dumps({'status':'failed','frozen':True,'platform':'win32'}))
    with pytest.raises(RuntimeError):final.finalize(report)
    assert not (tmp_path/'artifacts').exists()

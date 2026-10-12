"""A failing frozen integration test must never produce a 'passed' release ZIP."""
import json, hashlib, zipfile, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def finalize(report_path):
    report_path=Path(report_path);report=json.loads(report_path.read_text(encoding='utf-8-sig'))
    if report.get('status')!='passed' or not report.get('frozen') or report.get('platform')!='win32':raise RuntimeError('Frozen Windows self-test did not pass')
    required=['frozen_runtime','ffmpeg_bundled','ffprobe_bundled','qt_bundled','video_import','in_out_import','split','delete','reorder','project_roundtrip','export_created','export_1080_h264','audio_present','audio_signal','bgm_mix_signal','caption_burn_in','qt_preview_decode','source_unchanged']
    if not all(report.get('checks',{}).get(k) for k in required):raise RuntimeError('Self-test checks incomplete')
    folder=ROOT/'dist'/'StreamShortStudio';shutil.copy2(report_path,folder/'self-test.json')
    info_path=folder/'BUILD_INFO.json';info=json.loads(info_path.read_text());info['frozen_self_test']='passed_path_isolated_windows_runner';info_path.write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'BUILD_STATUS.txt').write_text('Windows x64 EXE build: completed\nFrozen app with isolated PATH: integration test passed\nExternal Python/pip/FFmpeg executable lookup: disabled\nClean Windows PC without Python: NOT TESTED\nWindows 10/11 physical devices and GPU: NOT TESTED\nSee self-test.json and BUILD_INFO.json for recorded evidence.\n',encoding='utf-8')
    files=[]
    for p in sorted(folder.rglob('*')):
        if p.is_file() and 'Data' not in p.relative_to(folder).parts:
            h=hashlib.sha256(p.read_bytes()).hexdigest();files.append({'path':str(p.relative_to(folder)).replace('\\','/'),'sha256':h,'bytes':p.stat().st_size})
    (folder/'FILES.json').write_text(json.dumps(files,indent=2),encoding='utf-8')
    artifacts=ROOT/'artifacts';artifacts.mkdir(exist_ok=True);target=artifacts/'StreamShortStudio-Windows-x64-Portable.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file() and 'Data' not in p.relative_to(folder).parts:z.write(p,Path('StreamShortStudio')/p.relative_to(folder))
    (target.with_suffix('.zip.sha256')).write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+target.name+'\n',encoding='utf-8')
    print(target)
if __name__=='__main__':
    import sys
    finalize(sys.argv[1])

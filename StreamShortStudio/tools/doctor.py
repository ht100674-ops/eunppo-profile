import sys, subprocess, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studio.engine import tool

def check():
    report={}
    for name in ['ffmpeg','ffprobe']:
        path=tool(name);r=subprocess.run([path,'-version'],capture_output=True,text=True,encoding='utf-8',errors='replace',check=True)
        if '--enable-nonfree' in r.stdout:raise RuntimeError('재배포 불가 nonfree FFmpeg 빌드를 사용할 수 없습니다')
        report[name]={'path':path,'version':r.stdout.splitlines()[0],'configuration':r.stdout}
    codecs=subprocess.check_output([tool('ffmpeg'),'-hide_banner','-encoders'],stderr=subprocess.DEVNULL).decode(errors='replace')
    filters=subprocess.check_output([tool('ffmpeg'),'-hide_banner','-filters'],stderr=subprocess.DEVNULL).decode(errors='replace')
    for x in ['libx264','aac']:
        if x not in codecs:raise RuntimeError('필수 인코더 없음: '+x)
    for x in ['subtitles','amix','crop','scale','boxblur']:
        if x not in filters:raise RuntimeError('필수 필터 없음: '+x)
    report['hardware_encoders_listed']=[x for x in ['h264_nvenc','h264_qsv','h264_amf'] if x in codecs]
    report['note']='목록은 드라이버/실제 GPU 동작을 보장하지 않습니다. 출력 시 CPU fallback을 사용합니다.'
    return report
if __name__=='__main__':
    try:print(json.dumps(check(),ensure_ascii=False,indent=2))
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)

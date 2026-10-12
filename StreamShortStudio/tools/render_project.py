import argparse, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studio.engine import Renderer
from studio.model import Project
p=argparse.ArgumentParser(description='StreamShort JSON 프로젝트를 GUI 없이 실제 MP4로 출력')
p.add_argument('project');p.add_argument('output');p.add_argument('--width',type=int,choices=[720,1080],default=1080);p.add_argument('--fps',type=int,choices=[30,60],default=30)
a=p.parse_args();Renderer().render(Project.load(a.project),a.output,a.width,a.fps,progress=lambda v:print(f'\r{v:.0%}',end='',flush=True));print()

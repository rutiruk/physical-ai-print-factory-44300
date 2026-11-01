"""All actual source frames in order, encoded at exactly 2x with no cuts."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]


def continuous_plan(frame_count):
    if frame_count<=0:raise ValueError('Source must contain frames')
    duration=frame_count/40
    if duration>180:raise ValueError('Continuous 2x video exceeds 180 seconds; no frames may be omitted')
    return dict(continuous=True,frame_count=frame_count,source_frame_count=frame_count,
                source_fps=20,fps=40,playback_speed=2,duration_seconds=duration,
                cuts=[],keep=[[0.,frame_count/20]],source_sim_first_frame_s=.05,
                sim_frame_step_s=.05,source_sim_last_frame_s=frame_count/20,
                dropped_frames=0,interpolated_frames=0,closing_summary_seconds=0)


def compose(folder,output):
    import av
    import numpy as np
    from PIL import ImageDraw
    sys.path.insert(0,str(ROOT/'src'))
    from print_factory.video import VideoWriter,font
    result_path=folder/'result.json';raw=folder/'factory_raw.mp4'
    result=json.loads(result_path.read_text(encoding='utf8'))
    if not result.get('success') or result.get('status')!='complete':
        raise RuntimeError('A continuous submission requires a completed successful run')
    expected=round(result['simulation_seconds']*20)
    if abs(expected/20-result['simulation_seconds'])>1e-6:
        raise ValueError('Run must finish on a capture boundary')
    plan=continuous_plan(expected)
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_name(output.stem+'.encoding.mp4')
    writer=VideoWriter(temporary,40);count=0;last=None
    try:
        with av.open(str(raw)) as source:
            if abs(float(source.streams.video[0].average_rate)-20)>.001:
                raise ValueError('Expected 20 fps source')
            for frame in source.decode(video=0):
                if abs(float(frame.time)-count/20)>1e-6:
                    raise ValueError('Source timestamps are not continuous')
                canvas=frame.to_image();draw=ImageDraw.Draw(canvas)
                draw.rectangle((0,866,1439,899),fill='#0d1722')
                draw.text((24,873),'2倍速 / カットなし / SIM時刻は連続',font=font(17,True),fill='#ffd278')
                draw.text((690,875),'印刷・折り・製本の内部は状態遷移モデル',font=font(15),fill='#a6b9cc')
                draw.rectangle((1090,50,1410,77),fill='#0d1722')
                draw.text((1098,53),'再生 2倍速 / 全画面同期',font=font(16),fill='#a6b9cc')
                if result.get('scenario')=='single':
                    draw.rectangle((330,20,1060,58),fill='#0d1722')
                    draw.text((333,25),'1ジョブの印刷 → Jeffが判断 → 2台のAMRが搬送',font=font(20),fill='#7ce5c8')
                writer.append_data(np.asarray(canvas));last=canvas;count+=1
        if count!=expected:
            raise ValueError(f'Source frame count {count} differs from SIM clock {expected}')
    finally:writer.close()
    temporary.replace(output)
    last.save(folder/'completed_jeff.png')
    plan.update(source=str(raw),output=str(output),
                source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
                description='Every source frame retained in original order. No cuts, interpolation, synthetic completion, or static closing card.')
    (folder/'video_edit.json').write_text(json.dumps(plan,indent=2),encoding='utf8')
    return plan


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,default=ROOT/'output/jeff_factory/jeff_single')
    parser.add_argument('--output',type=Path,default=ROOT/'output/PrintFactory_Jeff_demo_44300.mp4')
    args=parser.parse_args()
    print(json.dumps(compose(args.folder,args.output),indent=2))

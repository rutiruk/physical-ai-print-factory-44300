"""Uncut, real-time evidence of the last loaded NoMaD trip in the completed run."""
from pathlib import Path
import json
import sys
import av
import numpy as np
from PIL import ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from print_factory.video import VideoWriter,font


def main():
    folder=ROOT/'output/jeff_factory/jeff'
    result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
    if not result.get('success') or result.get('status')!='complete':
        raise RuntimeError('Only a successfully completed run may be exported')
    start=None;trips=[]
    for event in result['events']:
        if event['event']=='PHYSICAL_PUSH' and event['amr']==1:
            if event['loading']:start=event['time_s']
            elif start is not None:trips.append((start,event['time_s']));start=None
    start,end=trips[-1]
    path=ROOT/'output/AMR_motion_check_44300.mp4'
    writer=VideoWriter(path,20);count=0;first=last=None
    try:
        with av.open(str(folder/'factory_raw.mp4')) as source:
            source.seek(int(max(0,start-.05)*1_000_000))
            for frame in source.decode(video=0):
                sim_time=float(frame.time)+.05
                if sim_time<start:continue
                if sim_time>end:break
                canvas=frame.to_image();draw=ImageDraw.Draw(canvas)
                draw.rectangle((0,866,1439,899),fill='#0d1722')
                draw.text((24,873),'AMR2動作確認 / 等速・連続映像（カットなし）',font=font(17,True),fill='#ffd278')
                draw.text((820,875),'元の物理描画 / 位置・フレーム補間なし',font=font(16),fill='#a6b9cc')
                writer.append_data(np.asarray(canvas));count+=1
                if first is None:first=sim_time
                last=sim_time
    finally:writer.close()
    if not count or abs((last-first)*20-(count-1))>1e-5:
        raise RuntimeError('Motion check must contain consecutive source frames')
    manifest=dict(source=str(folder/'factory_raw.mp4'),output=str(path),
                  start_sim_s=first,end_sim_s=last,frames=count,fps=20,duration_s=count/20,
                  playback_speed=1,cuts=0,interpolated_frames=0,robot='AMR2 / NoMaD',
                  purpose='Continuous loaded trip; additional motion check, separate from the 1-3 minute submission edit.')
    (folder/'motion_clip.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()

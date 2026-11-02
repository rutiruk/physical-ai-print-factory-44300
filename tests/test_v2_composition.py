"""Synthetic camera frames verify ordered, timestamped offline HUD composition."""
import json
from pathlib import Path
import subprocess
import sys
import av
import numpy as np
from print_factory.video import VideoWriter


def test_parallel_composition_preserves_camera_order_and_uniform_timing(tmp_path):
    colors=[(40,80,120),(150,65,35)]
    writer=VideoWriter(tmp_path/'overview.mp4',40)
    for color in colors:writer.append_data(np.full((66,110,3),color,np.uint8))
    writer.close()
    (tmp_path/'frames.jsonl').write_text(''.join(json.dumps({'now':(i+1)*.05,'robots':[]})+'\n' for i in range(2)),encoding='utf8')
    (tmp_path/'result.json').write_text(json.dumps({'success':False,'status':'synthetic_test'}),encoding='utf8')
    script=Path(__file__).resolve().parents[1]/'scripts/compose_v2_video.py'
    subprocess.run([sys.executable,str(script),str(tmp_path),'--workers','2'],check=True,timeout=120,capture_output=True)
    with av.open(str(tmp_path/'demo.mp4')) as video:
        frames=list(video.decode(video=0))
        assert len(frames)==2
        assert [float(f.pts*f.time_base) for f in frames]==[0.,.025]
        for frame,color in zip(frames,colors):
            assert np.max(abs(frame.to_ndarray(format='rgb24')[400,500].astype(int)-color))<8
    assert json.loads((tmp_path/'result.json').read_text())['video_composition']=='complete'

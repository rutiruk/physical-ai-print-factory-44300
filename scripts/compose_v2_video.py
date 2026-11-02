"""Compose all recorded V2 frames and their original telemetry, in order."""
import argparse,json,sys
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import av
import numpy as np
from print_factory.v2_dashboard import render_v2_dashboard
from print_factory.video import VideoWriter
from print_factory.run_artifacts import write_result


def render(payload):
    rgb,data=payload
    return np.asarray(render_v2_dashboard(rgb,None,data))


def compose(folder,workers=4):
    folder=Path(folder);count=0;pending=deque()
    writer=VideoWriter(folder/'demo.mp4',40)
    try:
        with ProcessPoolExecutor(max_workers=workers) as pool, av.open(str(folder/'overview.mp4')) as camera, (folder/'frames.jsonl').open(encoding='utf8') as states:
            for index,frame in enumerate(camera.decode(video=0)):
                line=states.readline()
                if not line:raise RuntimeError('Camera has more frames than telemetry')
                data=json.loads(line)
                if abs(data['now']-(index+1)*.05)>1e-6:raise RuntimeError('Non-contiguous capture time')
                if abs(float(frame.pts*frame.time_base)-index/40)>1e-6:raise RuntimeError('Non-contiguous camera time')
                pending.append(pool.submit(render,(frame.to_ndarray(format='rgb24'),data)))
                if len(pending)>=workers*2:
                    writer.append_data(pending.popleft().result());count+=1
            if states.readline():raise RuntimeError('Telemetry has more frames than camera')
            while pending:writer.append_data(pending.popleft().result());count+=1
    finally:writer.close()
    result=json.loads((folder/'result.json').read_text(encoding='utf8'))
    result.update(video_composition='complete',video_frames=count)
    write_result(folder/'result.json',result)
    print(json.dumps(dict(frames=count,duration_seconds=count/40,video=str(folder/'demo.mp4')),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');p.add_argument('--workers',type=int,default=4)
    args=p.parse_args()
    if args.workers<1:p.error('workers must be positive')
    compose(args.folder,args.workers)

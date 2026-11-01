"""Actual learned waypoint -> PD -> Genesis -> RGB loop. No goal-vector steering."""
import argparse,json,math,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import numpy as np
from PIL import Image
from print_factory.print_scene import build_print_workshop
from print_factory.scene import numpy
from print_factory.json_worker import JsonWorker


def camera_pose(camera,xy,yaw):
    direction=np.array([math.cos(yaw),math.sin(yaw)])
    # Camera above front bumper, not behind its own deck.
    p=np.asarray(xy)+direction*.28
    camera.set_pose(pos=(*p,.67),lookat=(*(p+direction*2),.60),up=(0,0,1))


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',default='vint');p.add_argument('--steps',type=int,default=50)
    args=p.parse_args();out=ROOT/'output/jeff_factory/nav_loop';out.mkdir(parents=True,exist_ok=True)
    result={'model':args.model,'success':False,'steps':[]};(out/f'{args.model}.json').write_text(json.dumps(result))
    worker=JsonWorker('.venv-nav','navigation_worker.py',f'output/jeff_factory/nav_{args.model}_worker.log')
    try:
        f=build_print_workshop(navigation=True)
        amr=f.amrs[0];q=np.array([-.6,-1.1,0,0.]);amr.set_dofs_position(q);amr.control_dofs_position(q)
        # Desired forward-facing goal observation, sampled from the simulator map.
        goal=np.array([-1.,-1.1]);goal_yaw=0.
        camera_pose(f.navigation_cameras[2],goal,goal_yaw)
        for _ in range(30):f.scene.step()
        Image.fromarray(f.navigation_cameras[2].render()[0]).save(out/'goal.png')
        history=[]
        for tick in range(args.steps):
            q=numpy(amr.get_dofs_position());pos=numpy(amr.get_link('amr').get_pos())[:2]
            camera_pose(f.navigation_cameras[0],pos,q[2]);path=out/f'{args.model}_{tick:03}.png'
            Image.fromarray(f.navigation_cameras[0].render()[0]).save(path);history.append(str(path))
            response=worker.request(dict(model=args.model,observation_paths=history[-7:],goal_path=str(out/'goal.png'),max_v=.4,frame_rate=4,seed=tick))
            wp=np.array(response['waypoints'][2]);norm=np.linalg.norm(wp)
            # Learned waypoint dictates heading; only speed/turn limits are conventional.
            heading=math.atan2(wp[1],wp[0]);speed=min(.4,norm/.25)*max(0,math.cos(heading))
            yaw_rate=float(np.clip(heading*2,-1.,1.))
            target=numpy(amr.get_dofs_position()).copy()
            for _ in range(25):
                actual=numpy(amr.get_dofs_position())
                target[:2]+=[math.cos(actual[2])*speed*.01,math.sin(actual[2])*speed*.01]
                target[2]+=yaw_rate*.01;amr.control_dofs_position(target);f.scene.step()
            distance=float(np.linalg.norm(pos-goal))
            result['steps'].append(dict(tick=tick,position=pos.tolist(),goal_distance=distance,waypoint=wp.tolist(),latency_ms=response['latency_ms']))
            print(result['steps'][-1],flush=True)
            if distance<.18:result['success']=True;break
        result['model_metadata']=worker.ready
    finally:
        worker.close();(out/f'{args.model}.json').write_text(json.dumps(result,indent=2))


if __name__=='__main__':main()

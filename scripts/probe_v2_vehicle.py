"""Standalone wheel-contact physics evidence; no base-state writes."""
import sys, json, math, os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.environ.setdefault('CUDA_VISIBLE_DEVICES','0')
import numpy as np
import genesis as gs
from print_factory.v2_vehicle import build_drive_amr

def main():
    gs.init(backend=gs.cuda,logging_level='warning',seed=42)
    scene=gs.Scene(sim_options=gs.options.SimOptions(dt=.01,substeps=4),
                   rigid_options=gs.options.RigidOptions(enable_self_collision=False),show_viewer=False)
    scene.add_entity(gs.morphs.Plane(), material=gs.materials.Rigid(friction=.65))
    robot=build_drive_amr(scene)
    pile=scene.add_entity(gs.morphs.Box(pos=(0,0,.43),size=(.42,.297,.05)),
                          material=gs.materials.Rigid(rho=1.44/(.42*.297*.05),friction=.9),
                          surface=gs.surfaces.Default(color=(.95,.94,.85)))
    camera=scene.add_camera(res=(800,600),pos=(2.7,-3.3,2),lookat=(.4,0,.2),fov=42,GUI=False)
    print('Building drive probe...',flush=True)
    scene.build()
    print('Built; simulating settle/straight/turn/lift...',flush=True)
    robot.configure()
    samples=[]
    def advance(n,v=0,w=0):
        for i in range(n):
            robot.set_twist(v,w,.01)
            scene.step()
            if i%25==0:
                samples.append(robot.state())
    advance(150)
    settled=robot.state()
    pile_start=np.asarray(pile.get_pos().cpu())
    advance(260,.25,0)
    straight=robot.state()
    advance(100)
    turn_start=robot.state()
    advance(260,0,.65)
    turning=robot.state()
    advance(100)
    robot.set_lift(1.)
    advance(150)
    raised=robot.state()
    pile_end=np.asarray(pile.get_pos().cpu())
    rgb,*_=camera.render(rgb=True)
    from PIL import Image
    out=ROOT/'output/v2';out.mkdir(exist_ok=True,parents=True)
    Image.fromarray(rgb).save(out/'drive_probe.png')
    distance=math.hypot(straight['x']-settled['x'],straight['y']-settled['y'])
    yaw_change=math.atan2(math.sin(turning['yaw']-turn_start['yaw']),math.cos(turning['yaw']-turn_start['yaw']))
    result=dict(settled=settled,straight=straight,turn_start=turn_start,turning=turning,raised=raised,
                distance=distance,yaw_change=yaw_change,pile_start=pile_start.tolist(),pile_end=pile_end.tolist(),
                max_torque=max(abs(t) for s in samples for t in s['wheel_torque']),
                max_lift_force=max(abs(s['lift_force']) for s in samples),samples=samples,
                note='1.44kg payload rests freely by contact; no fixed attachment. No base pose or velocity commands after spawning.')
    (out/'drive_probe.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='samples'},indent=2))
    assert distance>.35
    assert abs(yaw_change)>.35
    assert abs(raised['lift_position']-.06)<.01
    assert result['max_torque']<=6.001
    assert result['max_lift_force']<=250.001
    assert abs(pile_end[2]-(raised['z']+.285+.02+.06+.025))<.04
if __name__=='__main__':main()


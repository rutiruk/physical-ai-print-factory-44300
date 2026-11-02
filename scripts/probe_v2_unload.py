"""Replay end-on AMR unloading. Original baseline: --lift 0 --tool-z .4.
Corrected calibration: --lift .005 (automatic measured-height tool target).

All entity placement happens at construction. Runtime uses wheel/lift and gantry
motor commands exclusively. JSON includes actual support heights and contacts.
"""
import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import numpy as np
from print_factory.v2_vehicle import build_drive_amr
from print_factory.v2_machines import build_gantry, build_machine
from print_factory.v2_transfer import transfer_height_targets,transfer_push_targets


def arr(value):
    return value.detach().cpu().numpy() if hasattr(value, 'detach') else np.asarray(value)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--case',choices=['A','B'],default='B')
    p.add_argument('--lift',type=float,default=.005)
    p.add_argument('--feed',action='store_true')
    p.add_argument('--tool-z',type=float,default=None)
    p.add_argument('--robot-x',type=float)
    p.add_argument('--robot-y',type=float)
    p.add_argument('--robot-yaw',type=float)
    p.add_argument('--paper-position',nargs=3,type=float)
    p.add_argument('--paper-quat',nargs=4,type=float)
    p.add_argument('--paper-yaw-deg',type=float)
    p.add_argument('--direction',choices=['north','south'])
    p.add_argument('--output',default='output/v2/unload_probe')
    args=p.parse_args()
    import genesis as gs
    gs.init(backend=gs.cuda,logging_level='warning',seed=42)
    sign=1 if (args.direction or ('north' if args.case=='A' else 'south'))=='north' else -1
    x=2.8 if sign>0 else -2.8
    robot_x=x if args.robot_x is None else args.robot_x
    y=sign*.54107 if args.robot_y is None else args.robot_y
    robot_yaw=sign*1.55125 if args.robot_yaw is None else args.robot_yaw
    thickness=.01 if args.case=='A' else .02
    width=.45 if args.case=='A' else .225
    scene=gs.Scene(sim_options=gs.options.SimOptions(dt=.01,substeps=4),rigid_options=gs.options.RigidOptions(enable_self_collision=False),show_viewer=False)
    scene.add_entity(gs.morphs.Plane(),material=gs.materials.Rigid(friction=.65))
    amr=build_drive_amr(scene,(robot_x,y),robot_yaw)
    gantry=build_gantry(scene)
    machine=build_machine(scene,'folder' if sign>0 else 'trim',(x,sign*1.25))
    bridge=scene.add_entity(gs.morphs.Box(pos=(x,sign*.94,.375),size=(.62,.09,.04),fixed=True),material=gs.materials.Rigid(friction=.65))
    paper_position=tuple(args.paper_position) if args.paper_position is not None else (robot_x,y,.403+thickness/2)
    angle=math.radians(args.paper_yaw_deg or 0)
    paper_quaternion=tuple(args.paper_quat) if args.paper_quat is not None else (math.cos(angle/2),0.,0.,math.sin(angle/2))
    paper=scene.add_entity(gs.morphs.Box(pos=paper_position,quat=paper_quaternion,size=(width,.32,thickness)),material=gs.materials.Rigid(rho=1.44/(width*.32*thickness),friction=.65))
    camera=scene.add_camera(res=(900,600),pos=(x+2,sign*(-2.3),1.7),lookat=(x,sign*.9,.4),GUI=False)
    scene.build();amr.configure();gantry.configure();machine.configure()
    sample=[];maximum_force=0.
    def contacts(other):
        c=paper.get_contacts(with_entity=other)
        return {k:arr(c[k]).tolist() for k in ('geom_a','geom_b','position','force_a')}
    def tick(n=1):
        nonlocal maximum_force
        for _ in range(n):
            amr.set_twist(0,0,.01,emergency=True)
            gantry.step(.01);machine.step(.01);scene.step()
            maximum_force=max(maximum_force,abs(gantry.state()['force'][1]))
    def move(tx,ty,tz,speed=None,limit=1800):
        if speed is not None:
            gantry.trajectory.limits=replace(gantry.trajectory.limits,speed=(.6,speed,.25,1.2))
        gantry.set_target(tx,ty,tz)
        good=0;stalled=0
        for i in range(limit):
            tick()
            state=gantry.state()
            good=good+1 if max(abs(v) for v in state['tracking_error'][:3])<.008 else 0
            stalled=stalled+1 if abs(state['force'][1])>120 and abs(state['velocity'][1])<.003 else 0
            if i%25==0:
                sample.append(dict(paper=arr(paper.get_pos()).tolist(),gantry=state['pose'],force_y=state['force'][1]))
            if good>=12:return True
            if stalled>=80:return False
        return False
    tick(100)
    before_lift=amr.state()
    amr.set_lift(args.lift);tick(150)
    decktop=float(arr(amr.entity.get_link('deck').get_pos())[2]+.02)
    height_targets=transfer_height_targets(decktop, thickness)
    tool_z=height_targets['command_z'] if args.tool_z is None else args.tool_z
    initial=arr(paper.get_pos()).tolist()
    initial_quat=arr(paper.get_quat()).tolist()
    push_targets=transfer_push_targets(initial,initial_quat,(width/2,.16,thickness/2),sign*1.25,sign)
    behind=push_targets['behind_y']
    move(initial[0],behind,1.)
    lowered=move(initial[0],behind,tool_z)
    engagement_error=abs(gantry.state()['pose'][2]-height_targets['actual_center'])
    engaged=engagement_error<.0015
    if args.feed:machine.request('feed',guard_closed=True,pile_present=True)
    pushed=move(initial[0],push_targets['target_blade_y'],tool_z,.12) if engaged else False
    push_state=gantry.state()
    paper_quat=arr(paper.get_quat()).tolist()
    machine.request('stop')
    at_push=arr(paper.get_pos()).tolist()
    contact_at_push=dict(bridge=contacts(bridge),machine=contacts(machine.entity),amr=contacts(amr.entity),gantry=contacts(gantry.entity))
    move(initial[0],push_state['pose'][1],1.)
    tick(60)
    final=arr(paper.get_pos()).tolist()
    receiver_contacts=contacts(machine.entity)
    supported=bool(receiver_contacts['geom_a']) and abs(final[1]-sign*1.25)<.09 and abs(final[2]-(.395+thickness/2))<.02
    report=dict(case=args.case,sign=sign,lift_target=args.lift,deck_top=decktop,bridge_top=.395,
                ascending_step=.395-decktop,height_targets=height_targets,tool_command=tool_z,before_lift=before_lift,amr=amr.state(),initial=initial,
                after_push=at_push,initial_quat=initial_quat,push_targets=push_targets,engaged=engaged,engagement_error=engagement_error,paper_quat=paper_quat,feed=args.feed,final=final,lowered=lowered,push_reached=pushed,supported=supported,
                maximum_y_force=maximum_force,push_state=push_state,contacts_at_push=contact_at_push,
                receiver_contacts=receiver_contacts,samples=sample)
    output=Path(args.output)/f'{args.case}_{"north" if sign>0 else "south"}_lift{args.lift:.3f}_feed{int(args.feed)}_z{tool_z:.4f}'
    output.mkdir(parents=True,exist_ok=True)
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    from PIL import Image
    rgb,*_=camera.render(rgb=True);Image.fromarray(rgb).save(output/'overview.png')
    print(json.dumps({k:v for k,v in report.items() if k not in ('samples','contacts_at_push','receiver_contacts')},indent=2))
    gs.destroy()
    if args.lift>0 and not (supported and pushed and engaged):raise RuntimeError('corrected unload failed; inspect report')


if __name__=='__main__':main()


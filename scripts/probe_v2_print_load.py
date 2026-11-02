"""Physical A raw→printing-feed→press-to-AMR contact loading prelude.

Use only after reserving GPU0. Ink appearance is a process-state approximation;
the same rigid pile contacts printing rollers and is pushed onto the real AMR.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import math
import numpy as np
from print_factory.v2_vehicle import build_drive_amr
from print_factory.v2_machines import build_gantry
from print_factory.v2_transfer import transfer_height_targets
from print_factory.v2_printing import build_printing_press,PrintJob


def arr(value):
    return value.detach().cpu().numpy() if hasattr(value,'detach') else np.asarray(value)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default='output/v2/print_load_probe');args=p.parse_args()
    import genesis as gs
    gs.init(backend=gs.cuda,logging_level='warning',seed=42)
    scene=gs.Scene(sim_options=gs.options.SimOptions(dt=.01,substeps=4),rigid_options=gs.options.RigidOptions(enable_self_collision=False),show_viewer=False)
    scene.add_entity(gs.morphs.Plane(),material=gs.materials.Rigid(friction=.65))
    amr=build_drive_amr(scene,(-2.8,.55),-math.pi/2)
    gantry=build_gantry(scene)
    press=build_printing_press(scene,(-2.8,1.25))
    bridge=scene.add_entity(gs.morphs.Box(pos=(-2.8,.94,.375),size=(.62,.09,.04),fixed=True),material=gs.materials.Rigid(friction=.65))
    paper=scene.add_entity(gs.morphs.Box(pos=(-2.8,1.25,.4),size=(.45,.32,.01)),material=gs.materials.Rigid(rho=1000,friction=.65))
    camera=scene.add_camera(res=(900,600),pos=(-.8,-1.4,1.8),lookat=(-2.8,.95,.4),GUI=False)
    scene.build();amr.configure();gantry.configure();press.configure()
    job=PrintJob('A');now=0.;samples=[];max_force=0.
    def contacts(entity):
        values=paper.get_contacts(with_entity=entity)
        return {k:arr(values[k]).tolist() for k in ('geom_a','geom_b','position','force_a')}
    def tick(n=1):
        nonlocal now,max_force
        for _ in range(n):
            amr.set_twist(0,0,.01,emergency=True)
            gantry.step(.01);press.step(.01);scene.step();now+=.01
            max_force=max(max_force,abs(gantry.state()['force'][1]))
    def move(x,y,z,speed=.45):
        gantry.trajectory.limits=replace(gantry.trajectory.limits,speed=(.6,speed,.25,1.2))
        gantry.set_target(x,y,z);good=0;stall=0
        for step in range(1800):
            tick();state=gantry.state()
            good=good+1 if max(abs(v) for v in state['tracking_error'][:3])<.008 else 0
            stall=stall+1 if abs(state['force'][1])>120 and abs(state['velocity'][1])<.003 else 0
            if step%25==0:samples.append(dict(t=now,paper=arr(paper.get_pos()).tolist(),gantry=state['pose'],force=state['force']))
            if good>=12:return True
            if stall>=80:return False
        return False
    tick(100)
    raw=arr(paper.get_pos()).tolist();angle0=press.state()['dof_position'][0]
    press.request('feed',guard_closed=True,pile_present=bool(contacts(press.entity)['geom_a']))
    press.cycle.roller_velocity=.4
    tick(150);press.request('stop');tick(30)
    roller_delta=press.state()['dof_position'][0]-angle0
    print_contact=contacts(press.entity)
    job.record_operation('press',paper_supported=bool(print_contact['geom_a']),roller_delta=roller_delta)
    printed=arr(paper.get_pos()).tolist()
    from PIL import Image
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    rgb,*_=camera.render(rgb=True);Image.fromarray(rgb).save(output/'printed_on_press.png')
    decktop=float(arr(amr.entity.get_link('deck').get_pos())[2]+.02)
    target=transfer_height_targets(.395,.01,receiver_top=decktop)
    behind=printed[1]+.185
    positioned=move(printed[0],behind,1.)
    lowered=move(printed[0],behind,target['command_z'])
    pushed=move(printed[0],.55+.172,target['command_z'],.12)
    push_state=gantry.state();at_push=arr(paper.get_pos()).tolist();paper_quat=arr(paper.get_quat()).tolist()
    push_contacts=dict(press=contacts(press.entity),bridge=contacts(bridge),amr=contacts(amr.entity),gantry=contacts(gantry.entity))
    move(printed[0],push_state['pose'][1],1.);tick(80)
    final=arr(paper.get_pos()).tolist();amr_contact=contacts(amr.entity)
    actualdeck=float(arr(amr.entity.get_link('deck').get_pos())[2]+.02)
    supported=bool(amr_contact['geom_a']) and abs(final[1]-amr.pose()['y'])<.08 and abs(final[0]-amr.pose()['x'])<.08 and abs(final[2]-(actualdeck+.005))<.015
    report=dict(job=job.state(),raw=raw,printed=printed,roller_delta=roller_delta,print_contact=print_contact,
                deck_top=decktop,height_targets=target,positioned=positioned,lowered=lowered,push_reached=pushed,
                after_push=at_push,paper_quat=paper_quat,push_state=push_state,push_contacts=push_contacts,
                final=final,supported=supported,amr=amr.state(),maximum_y_force=max_force,simulation_seconds=now,samples=samples)
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    rgb,*_=camera.render(rgb=True);Image.fromarray(rgb).save(output/'loaded_amr.png')
    print(json.dumps({k:v for k,v in report.items() if k not in ('samples','push_contacts','print_contact')},indent=2))
    gs.destroy()
    if not (positioned and lowered and pushed and supported):raise RuntimeError('printing contact load failed; inspect report.json')


if __name__=='__main__':main()

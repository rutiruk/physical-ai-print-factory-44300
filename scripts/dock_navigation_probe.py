"""Loaded NoMaD docking regression using production Demo controllers.

The sole pile placement is the declared initial condition. Learned travel uses
public NoMaD; only final docking uses the production conventional servo.
--legacy calls the former non-docking capture (0.3m), then rotates afterward.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import time
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from jeff_factory_demo import Demo
from print_factory.dispatch import Factory
from print_factory.print_scene import build_print_workshop
from print_factory.scene import numpy
from print_factory.json_worker import JsonWorker
from print_factory.printing import supported_pile
from print_factory.navigation_motion import MotionLimiter


def probe(legacy=False,max_seconds=60.,unload=False,case="centered"):
    start_xy=(1.677,.490) if case=="recorded" else (2.,-.65)
    out=ROOT/'output/jeff_factory/dock_probe'/(case+('_legacy' if legacy else '_fixed'))
    out.mkdir(parents=True,exist_ok=True)
    result={'success':False,'legacy':legacy,'initial_condition':{'amr':1,'position':list(start_xy),'yaw':math.pi/2,'cargo':'folded 100-sheet pile on AMR deck'},'positions':[],'inferences':[]}
    (out/'result.json').write_text(json.dumps(result))
    d=Demo.__new__(Demo)
    d.out=out;d.factory=Factory([]);d.nav=None
    d.navigation=[dict(model='ViNT',phase='idle'),dict(model='NoMaD',phase='idle')]
    d.nav_count=0;d.nav_active=None;d.goal_cache={};d.movements=[];d.loader_owner=None
    d.motion=[MotionLimiter(),MotionLimiter()];d.motion_samples=[]
    try:
        d.nav=JsonWorker('.venv-nav','navigation_worker.py',str(out.relative_to(ROOT)/'navigation_worker.log'),args=('--models','nomad'))
        d.f=build_print_workshop(navigation=True)
        # Initial placement only: an already loaded folded lot, not an in-episode transfer.
        for i,q in enumerate((np.array([-1.2,-1.9,0.,0.]),np.array([start_xy[0]+2,start_xy[1],math.pi/2,0.]))):
            d.f.amrs[i].set_dofs_position(q);d.f.amrs[i].control_dofs_position(q)
        pile=d.f.folded[0]
        pile.set_pos((*start_xy,.406));pile.set_quat((math.cos(math.pi/4),0.,0.,math.sin(math.pi/4)));pile.set_dofs_velocity(np.zeros(6))
        for _ in range(100):d.f.scene.step()
        d.commands=[numpy(a.get_dofs_position()).copy() for a in d.f.amrs]
        d.loader_command=numpy(d.f.loader.get_dofs_position()).copy()
        Image.fromarray(d.f.overview.render()[0]).save(out/'initial.png')
        result['initial_contact']=len(numpy(pile.get_contacts(with_entity=d.f.amrs[1])['link_a']))>0
        if not result['initial_contact']:raise RuntimeError('Loaded initial pile is not supported on AMR')

        def action():
            if legacy:
                yield from d.navigate(1,(2.,.55))
                yield from d.precise(1,yaw=0.)
            else:
                yield from d.navigate(1,(2.,.55),dock_yaw=0.)
            dock_pos=numpy(d.f.amrs[1].get_link('amr').get_pos())
            dock_contact=len(numpy(pile.get_contacts(with_entity=d.f.amrs[1])['link_a']))>0
            result['loaded_dock_supported']=supported_pile(numpy(pile.get_pos()),numpy(pile.get_quat()),[2.,.55],.395,.02,dock_contact)
            result['loaded_dock_position']=dock_pos.tolist()
            if not result['loaded_dock_supported']:raise RuntimeError('Loaded pile lost support during final docking')
            if unload:
                d.f.gather_bridge.control_dofs_position(np.array([1.5*9.81/50000]))
                for _ in range(40):yield
                yield from d.precise(1,lift=.0015)
                yield from d.push(1,pile,2.,False,.395,.02,d.f.supports['gather'])
        gen=action();done=False
        for tick in range(int(max_seconds/.01)):
            d.factory.now=tick*.01
            try:next(gen)
            except StopIteration:done=True;break
            d.update_navigation();d.f.scene.step()
            if tick%10==0:
                q=numpy(d.f.amrs[1].get_dofs_position());pos=numpy(d.f.amrs[1].get_link('amr').get_pos())
                result['positions'].append(dict(time_s=round(tick*.01,3),position=pos.tolist(),yaw=float(q[2]),pile_position=numpy(pile.get_pos()).tolist(),active=bool(d.navigation[1].get('active'))))
            if tick%100==0:
                print('dock',legacy,tick*.01,result['positions'][-1],flush=True)
        if not done:raise RuntimeError('Dock regression simulation time limit')
        for _ in range(50):d.f.scene.step()
        pos=numpy(d.f.amrs[1].get_link('amr').get_pos());q=numpy(d.f.amrs[1].get_dofs_position())
        contact_entity=d.f.supports['gather'] if unload else d.f.amrs[1]
        contact=len(numpy(pile.get_contacts(with_entity=contact_entity)['link_a']))>0
        pile_valid=supported_pile(numpy(pile.get_pos()),numpy(pile.get_quat()),[2.,1.25 if unload else .55],.395,.02,contact)
        result.update(final_position=pos.tolist(),final_yaw=float(q[2]),goal_distance=float(np.linalg.norm(pos[:2]-[2.,.55])),pile_position=numpy(pile.get_pos()).tolist(),pile_quaternion=numpy(pile.get_quat()).tolist(),pile_contact=contact,pile_supported=pile_valid,unloaded=unload)
        result['success']=bool(result['goal_distance']<.065 and abs(math.atan2(math.sin(q[2]),math.cos(q[2])))<math.radians(10) and pile_valid)
        if not result['success']:raise RuntimeError('Dock endpoint or loaded pile support assertion failed')
    except Exception as exc:
        result['error']=f'{type(exc).__name__}: {exc}'
    finally:
        result['inferences']=d.movements;result['events']=d.factory.events
        if hasattr(d,'f'):
            result['last_amr_position']=numpy(d.f.amrs[1].get_link('amr').get_pos()).tolist()
            Image.fromarray(d.f.overview.render()[0]).save(out/'endpoint.png')
            Image.fromarray(d.f.overhead.render()[0]).save(out/'endpoint_overhead.png')
        if d.nav:
            result['model_metadata']=d.nav.ready;d.nav.close()
        (out/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('positions','inferences','events')},indent=2),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=['centered','recorded'],default='centered');parser.add_argument('--legacy',action='store_true');parser.add_argument('--unload',action='store_true');parser.add_argument('--max-seconds',type=float,default=60.)
    args=parser.parse_args();result=probe(args.legacy,args.max_seconds,args.unload,args.case)
    raise SystemExit(0 if result['success'] else 1)

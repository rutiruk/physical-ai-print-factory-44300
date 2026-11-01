"""Irregular print jobs -> Jeff decisions -> ViNT/NoMaD motion -> Genesis RGB.

No foundation-model failure is replaced with a conventional navigation policy.
The side pusher and precision docking are conventional industrial mechanisms.
"""
import argparse,json,math,sys,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import numpy as np
from PIL import Image
from print_factory.dispatch import Factory,Job,StaleDecision
from print_factory.printing import FormLot,supported_pile
from print_factory.print_scene import build_print_workshop
from print_factory.scene import numpy
from print_factory.json_worker import JsonWorker
from print_factory.factory_dashboard import render_dashboard
from print_factory.video import VideoWriter
from print_factory.run_artifacts import write_result
from print_factory.navigation_guard import recovery_reason
from print_factory.navigation_motion import MotionLimiter, local_goal_plan
from nav_factory_probe import camera_pose

GATHER_X={'A':1.6,'B':2.,'C':2.4}
PARKS=((-2.,-1.65),(2.,-1.65))


class Demo:
    def __init__(self,args):
        self.args=args;self.out=ROOT/'output/jeff_factory'/args.policy;self.out.mkdir(parents=True,exist_ok=True)
        self.result=dict(success=False,status='initializing',policy=args.policy)
        write_result(self.out/'result.json',self.result)
        self.jeff=None;self.nav=None;self.writer=None
        self.factory=Factory([Job('A',0,600,pages=8,description='Regular 8-page brochure'),
                              Job('B',8.5,350,pages=4,description='Urgent 4-page leaflet'),
                              Job('C',23.7,750,pages=4,description='Additional folded 4-page leaflet')])
        self.slots={}
        # Four interchangeable 100-sheet stock piles. Job identity is assigned at print start.
        specs=[FormLot('SRA3',1,1,100,4) for _ in range(4)]
        self.nav=JsonWorker('.venv-nav','navigation_worker.py',str(self.out.relative_to(ROOT)/'navigation_worker.log'))
        if args.policy=='jeff':self.jeff=JsonWorker('.venv-jeff','jeff_worker.py',str(self.out.relative_to(ROOT)/'jeff_worker.log'),
                                                 args=('--checkpoint',str(ROOT/'models/jeff-2b-v1.2')))
        self.f=build_print_workshop(navigation=True,lot_specs=specs)
        for i,amr in enumerate(self.f.amrs):
            q=np.array([PARKS[i][0]+2,PARKS[i][1],0.,0.])
            amr.set_dofs_position(q);amr.control_dofs_position(q)
        self.writer=VideoWriter(self.out/'factory_raw.mp4',20)
        self.ticks=0;self.decision=None;self.request_version=None;self.request_candidates=None
        self.next_decision=0.;self.decision_count=0;self.nav_count=0;self.nav_active=None
        self.robot_generators=[None,None];self.navigation=[dict(model='ViNT',phase='idle'),dict(model='NoMaD',phase='idle')]
        self.commands=[numpy(a.get_dofs_position()).copy() for a in self.f.amrs]
        self.motion=[MotionLimiter(),MotionLimiter()]
        self.motion_samples=[]
        self.loader_command=numpy(self.f.loader.get_dofs_position()).copy();self.loader_owner=None
        self.movement_owner=None
        self.source_slots=[0,1,2,3];self.gather_slots={jid:[] for jid in ('A','B','C')}
        self.gather_x=GATHER_X;self.processed_events=0
        self.decisions=[];self.movements=[];self.cooldown=[0.,0.];self.goal_cache={};self.fault_applied=False;self.recovered=False

    def log(self,kind,**kw):self.factory.log(kind,**kw)

    def eligible(self):
        candidates=[]
        locations=[(j.id,form,loc) for j in self.factory.jobs.values() for form,loc in j.locations.items()]
        folder_busy=any(loc in ('folder_in','processing:folder','folder') for _,_,loc in locations)
        source_occupied=lambda source:any(t and t['source']==source and not t.get('picked_up') for t in self.factory.amrs)
        folder_busy=folder_busy or source_occupied('folder')
        folder_reserved=any(t and t['destination']=='folder' for t in self.factory.amrs)
        for c in self.factory.candidates():
            parts=c['id'].split(':');kind=parts[0]
            if kind=='print':
                if not self.source_slots or source_occupied('press') or any(loc in ('press','processing:press') for _,_,loc in locations):continue
                j=self.factory.jobs[parts[1]];form=int(parts[2])
                # One output cassette at the folder: release inner signatures first to avoid deadlock.
                if form!=max(i for i,loc in j.locations.items() if loc=='stock'):continue
            if kind=='fold' and any(loc=='folder' for _,_,loc in locations):continue
            if kind=='carry':
                i=c['amr'];slot=self.slots[(c['job'],c['form'])]
                if self.factory.now<self.cooldown[i] or self.robot_generators[i] is not None:continue
                if c['source']=='press' and (not self.source_slots or slot!=self.source_slots[-1] or folder_busy or folder_reserved):continue
                # High-level route choice belongs to Jeff; geometric safety may only veto.
                for route in ('direct','south'):
                    cc=dict(c);cc['id']+='@'+route;cc['route']=route
                    cc['description']+=f'; route {route} (direct lane y=0.55; south lane y=-0.65)'
                    candidates.append(cc)
            else:candidates.append(c)
        for i,nav in enumerate(self.navigation):
            if nav.get('needs_recovery'):
                candidates.insert(0,dict(id=f'recover:{i}',amr=i,
                    description=f'Restart AMR{i+1} {nav["model"]} visual navigation from its safely stopped current pose toward {nav["goal"]}. Reorient in place and refresh RGB history, then let the learned model generate motion again. This advances the assigned delivery; waiting does not fix its deviation.'))
        return candidates

    def save_rgb(self,camera,name):
        path=self.out/name;Image.fromarray(camera.render()[0]).save(path);return str(path)

    def dispatch(self):
        now=self.factory.now
        if self.jeff:
            response=self.jeff.poll()
            if response is not None:
                response.update(time_s=now,generation=self.request_version,candidates=self.request_candidates,
                                observation=self.request_state,image_path=self.request_image,corridor_image_path=self.request_corridor)
                self.decisions.append(response);self.decision=response
                valid={c['id']:c for c in self.eligible()}
                if self.request_version!=self.factory.version:
                    self.log('STALE_DECISION_REJECTED',choice=response['choice']);self.next_decision=now
                elif response['choice'] not in valid:raise RuntimeError('Jeff selected an unavailable action')
                else:self.apply(valid[response['choice']]);self.next_decision=now+(.75 if response['choice']=='wait' else .05)
        if (self.jeff and self.jeff.busy) or now<self.next_decision:return
        candidates=self.eligible()
        if len(candidates)==1 and candidates[0]['id']=='wait':return
        self.request_candidates=candidates;self.request_version=self.factory.version
        image=self.save_rgb(self.f.overhead,f'decision_{self.decision_count:04}.png');self.decision_count+=1
        state=self.factory.observation()
        state.update(plant='Sheetfed duplex UV printing, folded signatures, saddle stitching. Source feeder LIFO constraint already filtered.',
                     routes='Judge visible red-crate obstructions from the ceiling image. Direct lane y=0.55. South lane y=-0.65. Ports x press=-2, folder=0, gather=2.',
                     objective='Choose a useful eligible action, prioritize urgent jobs without starving production. Decisions run repeatedly. Avoid wait when useful work is safe.',
                     robots=[dict(position=np.round(numpy(a.get_link('amr').get_pos())[:2],2).tolist(),model=('ViNT','NoMaD')[i]) for i,a in enumerate(self.f.amrs)])
        state['navigation_recovery']=[dict(amr=i,goal=n.get('goal'),reason=n.get('recovery_reason'),attempt=n.get('attempt',0))
                                      for i,n in enumerate(self.navigation) if n.get('needs_recovery')]
        if self.jeff:
            corridor=self.save_rgb(self.f.corridor_camera,f'corridor_{self.decision_count:04}.png')
            self.request_state=state;self.request_image=image;self.request_corridor=corridor
            self.jeff.submit(dict(image_path=image,corridor_image_path=corridor,state=state,candidates=candidates,plan_text_only=True))
        else:
            # Explicit reference controller, never a fallback for Jeff errors.
            actions=[c for c in candidates if c['id']!='wait' and c.get('route')!='direct']
            def priority(c):
                if c['id'].startswith('recover:'):return (-1,-1,c['amr'])
                p=c['id'].split(':');jid=p[1];return (self.factory.jobs[jid].due,{'finish':0,'carry':1,'fold':2,'print':3}[p[0]],c.get('amr',0))
            choice=min(actions,key=priority)
            self.decision=dict(choice=choice['id'],latency_ms=0.,time_s=now)
            self.decisions.append(dict(self.decision,candidates=candidates));self.apply(choice);self.next_decision=now+.05

    def apply(self,c):
        raw=c['id'].split('@')[0]
        if raw.startswith('recover:'):
            i=c['amr'];self.navigation[i]['resume_requested']=True
            self.factory.version+=1;self.log('NAV_RECOVERY_CHOSEN',amr=i,policy=self.args.policy)
            return
        if raw.startswith('print:'):
            parts=raw.split(':');self.slots[(parts[1],int(parts[2]))]=self.source_slots[-1]
        self.factory.select(raw,self.factory.version)
        if raw.startswith('carry:'):
            i=c['amr'];self.factory.amrs[i]['route']=c['route']
            self.robot_generators[i]=self.transport(i,c)

    def servo(self,entity,start,target,duration):
        count=max(1,int(duration/.01));start=np.asarray(start);target=np.asarray(target)
        for tick in range(count):
            alpha=(tick+1)/count;s=alpha*alpha*(3-2*alpha)
            entity.control_dofs_position(start+(target-start)*s);yield
        for _ in range(20):yield

    def precise(self,i,xy=None,yaw=None,lift=None):
        start=self.commands[i].copy();target=start.copy()
        if xy is not None:target[:2]=np.asarray(xy)-[-2,0]
        if yaw is not None:target[2]=yaw
        if lift is not None:target[3]=lift
        duration=max(np.linalg.norm(target[:2]-start[:2])/.25,abs(target[2]-start[2])/.5,abs(target[3]-start[3])/.06,.2)
        yield from self.servo(self.f.amrs[i],start,target,duration);self.commands[i]=target.copy()

    def loader(self,target,speed=.5):
        target=np.asarray(target,float);duration=max(np.linalg.norm(target[:3]-self.loader_command[:3])/speed,.2)
        yield from self.servo(self.f.loader,self.loader_command.copy(),target,duration);self.loader_command=target.copy()

    def clear_loader(self):
        target=self.loader_command.copy();target[2]=.8;yield from self.loader(target)

    def push(self,i,entity,x,loading,bottom,height,support):
        while self.loader_owner not in (None,i):yield
        self.loader_owner=i
        try:
            yield from self.clear_loader();yield from self.loader([x,1.425 if loading else .375,.8,0])
            yield from self.loader([x,1.425 if loading else .375,bottom+.007,0])
            before=numpy(entity.get_pos()).tolist()
            yield from self.loader([x,.725 if loading else 1.075,bottom+.007,0],.25)
            yield from self.clear_loader()
            for _ in range(25):yield
            after=numpy(entity.get_pos());contact=len(numpy(entity.get_contacts(with_entity=support)['link_a']))>0
            valid=supported_pile(after,numpy(entity.get_quat()),[x,.55 if loading else 1.25],bottom,height,contact)
            self.log('PHYSICAL_PUSH',amr=i,loading=loading,before=before,after=after.tolist(),supported=valid)
            if not valid:raise RuntimeError(f'Contact transfer failed: AMR{i+1}, {after}, loading={loading}')
        finally:self.loader_owner=None

    def navigate(self,i,goal,dock_yaw=None,_through=False,_continuing=False):
        pos=numpy(self.f.amrs[i].get_link('amr').get_pos())[:2];delta=np.asarray(goal)-pos
        capture=.4 if dock_yaw is not None else .3
        # Public visual-navigation deployment uses a dense topological image map.
        # Keep each image goal within a local segment; route choice remains Jeff's.
        if np.linalg.norm(delta)>1.35:
            for part,(local_goal,through) in enumerate(local_goal_plan(pos,goal)):
                yield from self.navigate(i,local_goal,dock_yaw=None if through or _through else dock_yaw,
                                         _through=through or _through,_continuing=_continuing or part>0)
            return
        if np.linalg.norm(delta)<capture:
            if dock_yaw is not None:yield from self.precise(i,yaw=dock_yaw)
            yield from self.precise(i,xy=goal)
            return
        yaw=math.atan2(delta[1],delta[0]);current=self.commands[i][2]
        yaw=current+math.atan2(math.sin(yaw-current),math.cos(yaw-current))
        # Initial heading, final fiducial docking and speed limits are conventional.
        if not _continuing:
            self.motion[i].reset()
            yield from self.precise(i,yaw=yaw)
        key=(*goal,round(yaw,3));camera=self.f.navigation_cameras[2]
        if key not in self.goal_cache:
            camera_pose(camera,goal,yaw);self.goal_cache[key]=self.save_rgb(camera,f'goal_{len(self.goal_cache):03}.png')
        nav=self.navigation[i]
        prior_speed=nav.get('speed',0.) if _continuing else 0.
        prior_yaw=nav.get('yaw_rate',0.) if _continuing else 0.
        nav.update(goal=list(goal),goal_path=self.goal_cache[key],history=[],active=True,started=self.factory.now,
                                         speed=prior_speed,yaw_rate=prior_yaw,next_infer=self.factory.now,phase='moving',leg_id=self.nav_count,
                                         segment_start=pos.tolist(),capture=capture,attempt=0,needs_recovery=False,resume_requested=False,
                                         best_distance=float(np.linalg.norm(delta)),last_progress_time=self.factory.now)
        self.log('LEARNED_NAV_START',amr=i,goal=list(goal),position=pos.tolist(),model=nav['model'])
        while np.linalg.norm(numpy(self.f.amrs[i].get_link('amr').get_pos())[:2]-goal)>capture:
            if nav.get('needs_recovery'):
                while not nav.get('resume_requested'):yield
                if nav['attempt']>=4:raise RuntimeError('Navigation recovery limit exceeded; no conventional trajectory fallback')
                nav.update(resume_requested=False,needs_recovery=False,phase='recovering',attempt=nav['attempt']+1)
                self.motion[i].reset()
                pos=numpy(self.f.amrs[i].get_link('amr').get_pos())[:2];delta=np.asarray(goal)-pos
                self.commands[i]=numpy(self.f.amrs[i].get_dofs_position()).copy()
                current=self.commands[i][2];yaw=math.atan2(delta[1],delta[0]);yaw=current+math.atan2(math.sin(yaw-current),math.cos(yaw-current))
                yield from self.precise(i,yaw=yaw)
                camera_pose(camera,goal,yaw);path=self.save_rgb(camera,f'goal_recovery_{self.nav_count:05}.png')
                nav.update(goal_path=path,history=[],active=True,needs_recovery=False,phase='moving',speed=0.,yaw_rate=0.,
                           segment_start=pos.tolist(),leg_id=self.nav_count,next_infer=self.factory.now,started=self.factory.now,
                           best_distance=float(np.linalg.norm(delta)),last_progress_time=self.factory.now)
                self.log('LEARNED_NAV_RETRY',amr=i,goal=list(goal),model=nav['model'],attempt=nav['attempt'])
            if self.factory.now-nav['started']>45:raise RuntimeError(f'Learned {nav["model"]} navigation did not reach {goal}')
            yield
        if not _through:
            nav.update(speed=0.,yaw_rate=0.,phase='braking')
            while self.motion[i].speed>1e-4 or abs(self.motion[i].yaw_rate)>1e-4:
                yield
            if nav.get('needs_recovery'):
                raise RuntimeError('Safety monitor stopped terminal braking; run not accepted')
            self.motion[i].reset()
        nav.update(active=False)
        self.log('LEARNED_NAV_END',amr=i,goal=list(goal),position=numpy(self.f.amrs[i].get_link('amr').get_pos())[:2].tolist(),model=nav['model'])
        if _through:
            self.log('NAV_LOCAL_GOAL_THROUGH',amr=i,goal=list(goal),speed=self.motion[i].speed)
            return
        self.commands[i]=numpy(self.f.amrs[i].get_dofs_position()).copy()
        if dock_yaw is not None:yield from self.precise(i,yaw=dock_yaw)
        yield from self.precise(i,xy=goal)

    def transport(self,i,c):
        # Single shared aisle is an exclusive hardware resource, like the loader.
        while self.movement_owner not in (None,i):
            self.navigation[i]['phase']='waiting';yield
        self.movement_owner=i
        source=c['source'];dest=c['destination'];slot=self.slots[(c['job'],c['form'])]
        sx=self.f.ports[source][0];dx=self.gather_x[c['job']] if dest=='gather' else self.f.ports[dest][0];nav=self.navigation[i]
        nav.update(phase='approach',cargo=f'{c["job"]} F{c["form"]}')
        yield from self.navigate(i,(sx,-.65));yield from self.navigate(i,(sx,.55),dock_yaw=0.)
        source_height=.03 if source=='press' else 0.;height=.01 if source=='press' else .02
        entity=self.f.flat[slot] if source=='press' else self.f.folded[slot]
        yield from self.precise(i,lift=source_height)
        nav['phase']='loading';yield from self.push(i,entity,sx,True,.395+source_height,height,self.f.amrs[i])
        self.factory.amrs[i]['picked_up']=True
        if source=='press':
            assert self.source_slots.pop()==slot
            removed=4-len(self.source_slots)
            bias=(2+1.44*len(self.source_slots))*9.81/50000
            self.f.stock_lift.control_dofs_position(np.array([removed*.01+.0015+bias]))
        yield from self.precise(i,lift=0.)
        nav['phase']='deliver'
        if c['route']=='south':
            yield from self.navigate(i,(sx,-.65));yield from self.navigate(i,(dx,-.65));yield from self.navigate(i,(dx,.55),dock_yaw=0.)
        else:
            if min(sx,dx)<-1<max(sx,dx):raise RuntimeError('Jeff chose direct route intersecting visible red crate; safety veto, no reroute')
            yield from self.navigate(i,(dx,.55),dock_yaw=0.)
        yield from self.precise(i,yaw=0.)
        cassette=self.gather_slots[c['job']]
        destination_height=len(cassette)*.02 if dest=='gather' else 0.
        if dest=='gather':
            self.f.gather_bridge.control_dofs_position(np.array([destination_height+1.5*9.81/50000]))
            for _ in range(40):yield
        yield from self.precise(i,lift=destination_height+.0015)
        support=self.f.folded[cassette[-1]] if dest=='gather' and cassette else self.f.supports[dest]
        nav['phase']='unload';yield from self.push(i,entity,dx,False,.395+destination_height,height,support)
        if dest=='gather':cassette.append(slot)
        self.factory.complete_transport(i,True);yield from self.precise(i,lift=0.)
        nav.update(phase='return',cargo=None)
        yield from self.navigate(i,(dx,-.65))
        park=PARKS[i]
        yield from self.navigate(i,(park[0],-.65));yield from self.navigate(i,park)
        nav.update(phase='idle',cargo=None);self.cooldown[i]=self.factory.now+2.;self.movement_owner=None

    def update_navigation(self):
        response=self.nav.poll()
        if response is not None:
            i=self.nav_active;nav=self.navigation[i]
            if nav.get('active') and nav.get('phase')!='braking' and response.get('id')==nav.get('leg_id'):
                wp=np.asarray(response['waypoints'][2]);heading=math.atan2(wp[1],wp[0])
                nav.update(speed=min(.4,np.linalg.norm(wp)/.25)*max(0.,math.cos(heading)),
                           yaw_rate=float(np.clip(heading*2,-.8,.8)),latency_ms=response['latency_ms'],distance=response['distance'])
                self.movements.append(dict(time_s=self.factory.now,amr=i,position=numpy(self.f.amrs[i].get_link('amr').get_pos()).tolist(),goal=nav['goal'],
                                           observation_paths=self.nav_request['observation_paths'],goal_path=self.nav_request['goal_path'],
                                           commanded_speed=nav['speed'],commanded_yaw_rate=nav['yaw_rate'],**response))
        if not self.nav.busy:
            ready=[i for i,n in enumerate(self.navigation) if n.get('active') and n.get('phase')!='braking' and self.factory.now>=n['next_infer']]
            if ready:
                i=min(ready,key=lambda i:self.navigation[i]['next_infer']);nav=self.navigation[i]
                q=numpy(self.f.amrs[i].get_dofs_position());pos=numpy(self.f.amrs[i].get_link('amr').get_pos())[:2]
                camera_pose(self.f.navigation_cameras[i],pos,q[2]);path=self.save_rgb(self.f.navigation_cameras[i],f'nav_{self.nav_count:05}.png');self.nav_count+=1
                nav['history'].append(path);nav['next_infer']=self.factory.now+.25
                self.nav_request=dict(model=nav['model'].lower(),observation_paths=nav['history'][-7:],goal_path=nav['goal_path'],max_v=.4,frame_rate=4,seed=self.nav_count,id=nav['leg_id'])
                self.nav.submit(self.nav_request)
                self.nav_active=i
        positions=[numpy(a.get_link('amr').get_pos())[:2] for a in self.f.amrs]
        for i,nav in enumerate(self.navigation):
            if not nav.get('active'):continue
            distance=float(np.linalg.norm(positions[i]-nav['goal']))
            if distance<nav['best_distance']-.02:nav.update(best_distance=distance,last_progress_time=self.factory.now)
            reason=recovery_reason(nav['segment_start'],nav['goal'],positions[i],nav['capture'])
            if reason is None and distance>nav['capture'] and self.factory.now-nav['last_progress_time']>2.5:reason='no_progress'
            if reason:
                nav.update(active=False,needs_recovery=True,recovery_reason=reason,phase='blocked',speed=0.,yaw_rate=0.)
                self.motion[i].reset()
                self.commands[i]=numpy(self.f.amrs[i].get_dofs_position()).copy();self.f.amrs[i].control_dofs_position(self.commands[i])
                self.factory.version+=1;self.log('NAV_RECOVERY_REQUIRED',amr=i,reason=reason,position=positions[i].tolist(),goal=nav['goal'])
                continue
            speed,yaw_rate=self.motion[i].step(nav['speed'],nav['yaw_rate'],.01)
            safety_stop=False
            if np.linalg.norm(positions[0]-positions[1])<.75:
                safety_stop=True
                self.motion[i].reset()
                speed=0.;yaw_rate=0.;self.commands[i]=numpy(self.f.amrs[i].get_dofs_position()).copy()
            if not (-3.9<positions[i][0]<3.9 and -2.5<positions[i][1]<.85):
                raise RuntimeError('Learned navigation crossed permitted floor boundary')
            actual=numpy(self.f.amrs[i].get_dofs_position());self.commands[i][:2]+=[math.cos(actual[2])*speed*.01,math.sin(actual[2])*speed*.01]
            self.commands[i][2]+=yaw_rate*.01;self.f.amrs[i].control_dofs_position(self.commands[i])
            self.motion_samples.append(dict(time_s=round(self.factory.now,2),amr=i,leg_id=nav['leg_id'],
                                            phase=nav['phase'],speed=speed,yaw_rate=yaw_rate,
                                            safety_stop=safety_stop,
                                            position=positions[i].tolist(),target_speed=nav['speed'],target_yaw_rate=nav['yaw_rate']))

    def process_changes(self):
        for event in self.factory.events[self.processed_events:]:
            if event['event']=='PROCESS_COMPLETE' and event['machine']=='folder':
                slot=self.slots[(event['job'],event['form'])];old=self.f.flat[slot];pos=numpy(old.get_pos()).copy()
                old.set_pos((40+slot,0,-2));old.set_dofs_velocity(np.zeros(6))
                self.f.folded[slot].set_pos((pos[0],pos[1],.405));self.f.folded[slot].set_dofs_velocity(np.zeros(6))
                self.log('PROCESS_LOCAL_GEOMETRY_CHANGE',job=event['job'],form=event['form'])
            if event['event']=='PROCESS_COMPLETE' and event['machine']=='finishing':
                for slot in self.gather_slots[event['job']]:self.f.folded[slot].set_pos((45+slot,0,-2))
                self.gather_slots[event['job']]=[]
                # Every unload commands its own bridge height. Finishing must not
                # retract the shared bridge during another job's contact transfer.
                self.log('PACKED_OUTPUT',job=event['job'])
        self.processed_events=len(self.factory.events)

    def run(self):
        start=time.perf_counter()
        try:
            for _ in range(100):self.f.scene.step()
            self.f.stock_lift.control_dofs_position(np.array([.0015+(2+5.76)*9.81/50000]))
            while self.ticks*.01<self.args.max_seconds:
                self.factory.advance(self.ticks*.01);self.process_changes()
                if self.factory.now>=12 and not self.fault_applied and 'folder' not in self.factory.machines:
                    self.factory.set_fault('folder',True);self.fault_applied=True;self.recover_at=self.factory.now+7.
                if self.fault_applied and not self.recovered and self.factory.now>=self.recover_at:
                    self.factory.set_fault('folder',False);self.recovered=True
                self.dispatch()
                for i,gen in enumerate(self.robot_generators):
                    if gen is not None:
                        try:next(gen)
                        except StopIteration:self.robot_generators[i]=None
                self.update_navigation();self.f.scene.step();self.ticks+=1
                if self.ticks%5==0:
                    state=self.factory.observation();state['time_s']=self.ticks*.01
                    state['policy']=self.args.policy
                    frame=render_dashboard(self.f.overview.render()[0],self.f.overhead.render()[0],state,self.decision,self.factory.events,self.navigation)
                    self.writer.append_data(np.asarray(frame))
                    if self.ticks%100==0:frame.save(self.out/'latest.png')
                if self.ticks%100==0:
                    print(f't={self.factory.now:.1f} jobs={len(self.factory.jobs)} decisions={len(self.decisions)} nav={len(self.movements)}',flush=True)
                    self.persist('running')
                if not self.factory.pending and all(j.completed is not None for j in self.factory.jobs.values()):
                    self.result['success']=True;break
            self.persist('complete' if self.result['success'] else 'time_limit')
        except BaseException as exc:
            self.result['error']=f'{type(exc).__name__}: {exc}';self.persist('failed');raise
        finally:
            self.result['wall_seconds']=time.perf_counter()-start
            if self.writer:self.writer.close()
            if self.nav:self.nav.close()
            if self.jeff:self.jeff.close()
            write_result(self.out/'motion_samples.json',self.motion_samples)
            self.persist(self.result['status'])

    def persist(self,status):
        self.result.update(status=status,simulation_seconds=self.ticks*.01,events=self.factory.events,
                           immutable_observation_snapshot=True,
                           decisions=self.decisions,navigation=self.movements,state=self.factory.observation(),
                           models=dict(navigation=self.nav.ready,jeff=self.jeff.ready if self.jeff else None),
                           motion_control=dict(acceleration_limit_m_s2=.6,angular_acceleration_limit_rad_s2=.9,
                                               filter_time_constant_s=.12,through_internal_collinear_goals=True),
                           conventional_components=['initial heading','last 0.40m dock alignment (0.30m corridor nodes)','actuator acceleration limits and command filtering','side-pusher','exclusive shared aisle','speed/contact interlocks','machine/PLC process states'])
        write_result(self.out/'result.json',self.result)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--policy',choices=['jeff','rules'],default='jeff');p.add_argument('--max-seconds',type=float,default=1200)
    Demo(p.parse_args()).run()

"""Concurrent RGB ViNT/NoMaD driving with explicit conventional dock/heading servos.

Learned motion derives steering solely from waypoint[2] anchored at the RGB
observation heading. World goals are used only for initial alignment, observation
capture, progress/safety checks and the declared final precision region.
"""
import math
import json
from pathlib import Path
import numpy as np
from PIL import Image


def wrap_angle(value):
    return math.atan2(math.sin(value),math.cos(value))


def dense_goals(start,goal):
    start=tuple(map(float,start));goal=tuple(map(float,goal))
    # Reserve the .16m through capture margin so the following RGB goal is
    # still within .8m of the actual robot when a continuous handoff occurs.
    count=max(1,math.ceil(math.dist(start,goal)/.64))
    return [(float(start[0]+(goal[0]-start[0])*i/count),float(start[1]+(goal[1]-start[1])*i/count)) for i in range(1,count+1)]


def heading_command(error):
    if abs(error)<.04:return 0.
    return math.copysign(min(.8,max(.60,abs(error)*2.)),error)


def model_command(waypoint,observation_yaw,current_yaw):
    x,y=map(float,waypoint[:2])
    if not all(math.isfinite(a) for a in (x,y,observation_yaw,current_yaw)):
        raise ValueError('Nonfinite model waypoint/heading')
    if math.hypot(x,y)<1e-5:raise ValueError('Model waypoint has zero magnitude')
    relative=math.atan2(y,x)
    target=wrap_angle(float(observation_yaw)+relative)
    error=wrap_angle(target-current_yaw)
    # Heading is a world target anchored at observation capture, never at a
    # continually changing current heading, and never at the map goal vector.
    v=min(.20,math.hypot(x,y)/.25)*max(0.,math.cos(error))
    if abs(error)>.55:v=0.
    w=heading_command(error)
    return float(v),float(w),float(target)


def precision_command(pose,goal,final_yaw,max_distance=.7):
    dx,dy=float(goal[0])-pose['x'],float(goal[1])-pose['y']
    distance=math.hypot(dx,dy)
    if distance>max_distance+1e-6:
        raise ValueError(f'Conventional precision region exceeded: {distance:.3f}m')
    if distance<.018:
        return 0.,heading_command(wrap_angle(final_yaw-pose['yaw']))
    bearing=math.atan2(dy,dx)
    error=wrap_angle(bearing-pose['yaw'])
    if abs(error)>.18:return 0.,heading_command(error)
    return min(.13,max(.025,distance*.9)),heading_command(error)


def dock_axis_errors(pose,goal,final_yaw):
    dx,dy=float(goal[0])-pose['x'],float(goal[1])-pose['y']
    c,s=math.cos(final_yaw),math.sin(final_yaw)
    return float(c*dx+s*dy),float(-s*dx+c*dy),wrap_angle(final_yaw-pose['yaw'])


def dock_reached(pose,goal,final_yaw):
    longitudinal,lateral,yaw_error=dock_axis_errors(pose,goal,final_yaw)
    return abs(longitudinal)<.018 and abs(lateral)<.025 and abs(yaw_error)<.055


def constrained_dock_command(pose,goal,final_yaw,max_distance=.7):
    """Low-angle forward/reverse station approach; never chase lateral bearing."""
    longitudinal,lateral,yaw_error=dock_axis_errors(pose,goal,final_yaw)
    distance=math.hypot(longitudinal,lateral)
    if distance>max_distance+1e-6:raise ValueError('Conventional dock region exceeded')
    if dock_reached(pose,goal,final_yaw):return 0.,0.
    near=distance<=.18
    correction_limit=.04 if near else .12
    direction=1. if longitudinal>=0 else -1.
    correction=math.atan2(lateral,max(abs(longitudinal),.15))*direction
    correction=max(-correction_limit,min(correction_limit,correction))
    # Unlike free-space heading alignment, station docking has no minimum
    # pivot command. The constrained approach accepts a finite lateral band.
    desired=wrap_angle(final_yaw+correction-pose['yaw'])
    w=max(-3*correction_limit,min(3*correction_limit,3*desired))
    if abs(longitudinal)<.018:
        if abs(lateral)>=.025:
            raise ValueError('Dock lateral residual requires a new approach from outside the receiver')
        return 0.,max(-.12,min(.12,3*yaw_error)) if abs(yaw_error)>.055 else 0.
    if abs(yaw_error)>(.08 if near else .16):return 0.,float(w)
    speed=min(.13,max(.018,abs(longitudinal)*.9))
    return float(direction*speed),float(w)


def _xy(pose):return (float(pose['x']),float(pose['y']))


class LearnedNavigator:
    def __init__(self,robots,front_cameras,goal_camera,worker,outdir,now,event):
        self.robots=robots;self.front_cameras=front_cameras;self.goal_camera=goal_camera
        self.worker=worker;self.now=now;self.event=event
        self.outdir=Path(outdir);self.outdir.mkdir(parents=True,exist_ok=True)
        self.states=[dict(model=model,phase='idle',goal=None,waypoints=[],latency_ms=0.,input_time_s=None,
                          input_image=None,needs_recovery=False,active=False,mode='idle',history=[],attempt=0,
                          resume_requested=False,speed=0.,yaw_rate=0.,next_infer=0.,token=0) for model in ('ViNT','NoMaD')]
        self.inferences=[];self.samples=[];self._pending=None;self._sequence=0;self._rr=0

    def _emit(self,kind,i,**kwargs):
        self.event(kind,amr=int(i),**kwargs)

    def _stop(self,i,phase='idle'):
        self.states[i].update(mode='idle',phase=phase,active=False,speed=0.,yaw_rate=0.)

    def _trip(self,i,reason):
        s=self.states[i]
        if s['needs_recovery']:return
        s.update(needs_recovery=True,resume_requested=False,phase='needs_recovery',speed=0.,yaw_rate=0.,recovery_reason=str(reason))
        self._emit('NAV_NEEDS_RECOVERY',i,reason=str(reason),model=s['model'],goal=s['goal'])

    def resume(self,i):
        """Only a Jeff-authorized parent recovery calls this entry point."""
        if self.states[i]['needs_recovery']:
            self.states[i]['resume_requested']=True

    def request_recovery(self,i,reason):
        """A safety observer can request a pause, never select a replacement path."""
        self._trip(i,reason)

    def orient(self,i,yaw):
        s=self.states[i];previous_mode=s['mode']
        s.update(mode='orient',phase='heading_servo_conventional',active=True,target_yaw=float(yaw),speed=0.,yaw_rate=0.)
        started=float(self.now());good=0
        try:
            while good<8:
                p=self.robots[i].pose();error=wrap_angle(float(yaw)-p['yaw'])
                good=good+1 if abs(error)<.05 else 0
                if self.now()-started>45:raise RuntimeError(f'AMR{i+1} heading servo timed out')
                yield
        finally:
            self._stop(i,'heading_ready')
        self._emit('CONVENTIONAL_HEADING_END',i,yaw=float(yaw),actual_yaw=float(self.robots[i].pose()['yaw']))

    def _precision(self,i,goal,yaw,max_distance,phase,constrained=False):
        p=self.robots[i].pose()
        if math.dist(_xy(p),goal)>max_distance+1e-6:
            raise ValueError('Precision controller refuses a route outside its declared region')
        s=self.states[i]
        s.update(mode='precision',phase=phase,active=True,goal=list(map(float,goal)),target_yaw=float(yaw),precision_radius=float(max_distance),constrained_dock=bool(constrained))
        self._emit('CONVENTIONAL_PRECISION_START',i,goal=s['goal'],radius_m=float(max_distance))
        started=float(self.now());good=0
        try:
            while good<12:
                p=self.robots[i].pose();distance=math.dist(_xy(p),goal)
                reached=dock_reached(p,goal,yaw) if constrained else distance<.022 and abs(wrap_angle(yaw-p['yaw']))<.055
                good=good+1 if reached else 0
                if self.now()-started>60:raise RuntimeError(f'AMR{i+1} precision approach timed out')
                yield
        finally:self._stop(i,'precision_ready')
        # Hold the actual rolling base by zero wheel setpoint for a brief settle.
        for _ in range(20):yield
        self._emit('CONVENTIONAL_PRECISION_END',i,goal=list(map(float,goal)),position=list(_xy(self.robots[i].pose())))

    def dock(self,i,goal,yaw):
        """Conventional finite-clearance approach, limited to <=.7m from start."""
        yield from self._precision(i,tuple(map(float,goal)),float(yaw),.7,'docking_conventional',constrained=True)

    def travel(self,i,goal,terminal_capture=.16):
        terminal_capture=float(terminal_capture)
        if not math.isfinite(terminal_capture) or not .04<=terminal_capture<=.16:
            raise ValueError('terminal_capture must be finite and within .04.. .16m')
        final=tuple(map(float,goal));start=_xy(self.robots[i].pose())
        goals=dense_goals(start,final)
        for part,local in enumerate(goals):
            yield from self._leg(i,local,through=part<len(goals)-1,continuing=part>0,terminal_capture=terminal_capture)

    def _leg(self,i,goal,through=False,continuing=False,terminal_capture=.16):
        capture=.16 if through else float(terminal_capture)
        s=self.states[i];attempt=0
        while True:
            p=self.robots[i].pose();position=_xy(p);distance=math.dist(position,goal)
            yaw=math.atan2(goal[1]-p['y'],goal[0]-p['x']) if distance>.018 else p['yaw']
            if distance<=capture:
                if through:return
                yield from self._precision(i,goal,yaw,.18,'final_18cm_conventional')
                return
            if not continuing or attempt>0:
                yield from self.orient(i,yaw)
            # The shared goal camera is only used synchronously for one capture.
            goal_path=self._capture(self.goal_camera,goal,yaw,'goal',i)
            if not continuing or attempt>0:
                s.update(history=[],waypoints=[],observation_yaw=None,target_heading=None,last_response_time=None)
            s.update(mode='learned',active=True,phase='learned_driving' if continuing and s.get('last_response_time') is not None else 'awaiting_model',goal=list(goal),goal_path=goal_path,
                     next_infer=float(self.now()),through=bool(through),
                     started=float(self.now()),last_progress_time=float(self.now()),best_distance=float(distance),
                     segment_start=list(_xy(self.robots[i].pose())),needs_recovery=False,resume_requested=False,
                     token=s['token']+1,attempt=attempt)
            self._emit('LEARNED_NAV_START' if attempt==0 else 'LEARNED_NAV_RETRY',i,model=s['model'],goal=list(goal),attempt=attempt)
            while True:
                p=self.robots[i].pose();remaining=math.dist(_xy(p),goal)
                if remaining<=capture and not s['needs_recovery']:
                    if through:
                        self._emit('NAV_LOCAL_GOAL_THROUGH',i,goal=list(goal),speed=float(s['speed']),yaw_rate=float(s['yaw_rate']))
                        return
                    self._stop(i,'capture_braking')
                    for _ in range(25):yield
                    self._emit('LEARNED_NAV_END',i,model=s['model'],goal=list(goal),position=list(_xy(self.robots[i].pose())))
                    p=self.robots[i].pose()
                    if math.dist(_xy(p),goal)>.18:
                        self._trip(i,'capture_coast_exceeded_precision_region')
                    else:
                        yield from self._precision(i,goal,yaw,.18,'final_18cm_conventional')
                        return
                if s['needs_recovery']:
                    while not s['resume_requested']:yield
                    if attempt>=4:
                        raise RuntimeError(f'{s["model"]}: four learned retries exhausted; no trajectory fallback')
                    attempt+=1;s.update(resume_requested=False,needs_recovery=False,token=s['token']+1)
                    self._stop(i,'recovery_reorient')
                    break
                yield

    def _capture(self,camera,xy,yaw,prefix,i):
        direction=np.array([math.cos(yaw),math.sin(yaw)])
        front=np.asarray(xy,dtype=float)+direction*.30
        camera.set_pose(pos=(float(front[0]),float(front[1]),.67),
                        lookat=(float(front[0]+direction[0]*2),float(front[1]+direction[1]*2),.60),up=(0,0,1))
        rgb=camera.render(rgb=True)[0]
        path=self.outdir/f'{prefix}_amr{i+1}_{self._sequence:06d}.png';self._sequence+=1
        Image.fromarray(np.asarray(rgb,dtype=np.uint8)).save(path)
        return str(path.resolve())

    def _receive(self,now):
        if self._pending is None:return
        i,request,metadata=self._pending
        try:response=self.worker.poll()
        except Exception as exc:
            self._pending=None;self._trip(i,f'model_error: {exc}');return
        if response is None:return
        self._pending=None;s=self.states[i]
        record=dict(amr=int(i),received_time_s=float(now),request=request,observation=metadata,response=response,
                    accepted=bool(s['mode']=='learned' and request['id']==s['token'] and not s['needs_recovery']))
        self.inferences.append(record)
        (self.outdir/'navigation_inferences.json').write_text(json.dumps(self.inferences,indent=2,allow_nan=False),encoding='utf-8')
        if not record['accepted']:return
        try:
            waypoint=response['waypoints'][2]
            v,w,target=model_command(waypoint,metadata['yaw'],self.robots[i].pose()['yaw'])
            s.update(waypoints=response['waypoints'],latency_ms=float(response['latency_ms']),
                     target_heading=target,observation_yaw=float(metadata['yaw']),policy_waypoint=list(map(float,waypoint)),
                     last_response_time=float(now),phase='learned_driving',speed=v,yaw_rate=w,
                     input_time_s=float(metadata['time_s']),input_image=request['observation_paths'][-1],
                     distance=float(response.get('distance',0.)))
        except Exception as exc:self._trip(i,f'invalid_model_response: {exc}')

    def step(self,dt,now,safety):
        now=float(now);dt=float(dt)
        self._receive(now)
        for i,s in enumerate(self.states):
            p=self.robots[i].pose();v=w=0.;reason=safety.get(i)
            if reason:
                if s['mode']=='learned':
                    s['last_progress_time']=now;s['started']+=dt
            elif s['needs_recovery']:pass
            elif s['mode']=='orient':
                w=heading_command(wrap_angle(s['target_yaw']-p['yaw']))
            elif s['mode']=='precision':
                controller=constrained_dock_command if s.get('constrained_dock') else precision_command
                v,w=controller(p,s['goal'],s['target_yaw'],s['precision_radius']+.04)
            elif s['mode']=='learned':
                remaining=math.dist(_xy(p),s['goal'])
                if remaining<s['best_distance']-.025:
                    s.update(best_distance=remaining,last_progress_time=now)
                a=s['segment_start'];b=s['goal'];length=math.dist(a,b)
                cross=abs((b[0]-a[0])*(p['y']-a[1])-(b[1]-a[1])*(p['x']-a[0]))/max(length,1e-6)
                if cross>.30:self._trip(i,'cross_track_deviation')
                elif remaining>length+.20:self._trip(i,'moving_away_from_goal')
                elif now-s['last_progress_time']>14:self._trip(i,'no_progress')
                elif now-s['started']>60:self._trip(i,'learned_leg_timeout')
                elif s['last_response_time'] is not None and now-s['last_response_time']<2.:
                    v,w,_=model_command(s['policy_waypoint'],s['observation_yaw'],p['yaw'])
                    # Distance can reduce speed for capture, but cannot redirect
                    # the learned heading. No world-vector trajectory fallback.
                    if not s.get('through'):v=min(v,max(.025,remaining*.8))
            emergency=bool(reason or s['needs_recovery'] or s['mode']=='idle')
            if emergency:v=w=0.
            self.robots[i].set_twist(float(v),float(w),dt,emergency=emergency)
            s.update(speed=float(v),yaw_rate=float(w),safety_stop=str(reason) if reason else None)
        if not self.worker.busy and self._pending is None:
            for offset in range(2):
                i=(self._rr+offset)%2;s=self.states[i]
                if s['mode']!='learned' or s['needs_recovery'] or safety.get(i) or now<s['next_infer']:continue
                p=self.robots[i].pose();path=self._capture(self.front_cameras[i],_xy(p),p['yaw'],'input',i)
                s['history']=(s['history']+[path])[-7:]
                request=dict(model=s['model'].lower(),observation_paths=list(s['history']),goal_path=s['goal_path'],
                             max_v=.20,frame_rate=4.,seed=int(self._sequence),id=int(s['token']))
                metadata=dict(time_s=now,x=float(p['x']),y=float(p['y']),yaw=float(p['yaw']))
                try:self.worker.submit(request)
                except Exception as exc:self._trip(i,f'model_submit_error: {exc}');break
                self._pending=(i,request,metadata);s['next_infer']=now+.25;self._rr=(i+1)%2
                break




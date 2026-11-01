"""Conventional actuator limits; all navigation targets still come from the policy."""
import math
from dataclasses import dataclass


@dataclass
class MotionLimiter:
    speed: float = 0.
    yaw_rate: float = 0.

    def reset(self):
        self.speed = self.yaw_rate = 0.

    def step(self, speed, yaw_rate, dt):
        if dt <= 0:
            raise ValueError('dt must be positive')
        # First-order command filtering plus hard acceleration bounds. Neither
        # this filter nor the limiter receives a map, position, or goal vector.
        alpha = 1-math.exp(-dt/.12)
        def advance(actual, target, acceleration):
            change = (target-actual)*alpha
            return actual+max(-acceleration*dt, min(acceleration*dt, change))
        self.speed = advance(self.speed, max(0., min(.4, speed)), .6)
        self.yaw_rate = advance(self.yaw_rate, max(-.8, min(.8, yaw_rate)), .9)
        return self.speed, self.yaw_rate


def local_goal_plan(start, goal):
    """Dense image goals on one straight segment; corners remain real stops."""
    start,goal=tuple(map(float,start)),tuple(map(float,goal))
    count = max(1, math.ceil(math.dist(start, goal)/1.2))
    return [((start[0]+(goal[0]-start[0])*part/count,
              start[1]+(goal[1]-start[1])*part/count), part < count)
            for part in range(1, count+1)]


def motion_summary(samples, events):
    """Audit applied commands, separately from raw policy-output jitter."""
    previous = {}
    linear, angular = [], []
    for row in samples:
        prior = previous.get(row['amr'])
        previous[row['amr']] = row
        if prior is None:
            continue
        if row.get('safety_stop'):
            continue  # Immediate safety veto is intentionally outside comfort limits.
        dt = row['time_s']-prior['time_s']
        if not .009 < dt < .011:
            continue  # A docking, rotation, or safety stop separates these samples.
        linear.append(abs(row['speed']-prior['speed'])/dt)
        angular.append(abs(row['yaw_rate']-prior['yaw_rate'])/dt)
    through = [e for e in events if e['event']=='NAV_LOCAL_GOAL_THROUGH']
    return dict(samples=len(samples), adjacent_physics_ticks=len(linear),
                safety_stop_samples=sum(bool(row.get('safety_stop')) for row in samples),
                max_linear_acceleration_m_s2=max(linear,default=0.),
                max_angular_acceleration_rad_s2=max(angular,default=0.),
                linear_limit_violations=sum(a>.600001 for a in linear),
                angular_limit_violations=sum(a>.900001 for a in angular),
                internal_nodes_without_stop=len(through),
                internal_nodes_with_nonzero_command=sum(e['speed']>.01 for e in through),
                scope='Applied learned-navigation commands, not a bound on rigid-body acceleration or emergency stops.')


def handoff_speeds(samples,events):
    """Secant body speed from actual positions within +/-0.1s of each handoff."""
    previous={};velocities=[]
    for row in samples:
        prior=previous.get(row['amr']);previous[row['amr']]=row
        if prior is None:continue
        dt=row['time_s']-prior['time_s']
        if .009<dt<.011:
            speed=math.dist(row['position'],prior['position'])/dt
            if not math.isfinite(speed):raise ValueError('Nonfinite actual position speed')
            velocities.append((row['amr'],row['time_s'],speed))
    result=[]
    for event in events:
        if event['event']!='NAV_LOCAL_GOAL_THROUGH':continue
        speeds=[v for i,t,v in velocities if i==event['amr'] and abs(t-event['time_s'])<=.1]
        result.append(dict(amr=event['amr'],time_s=event['time_s'],
                           minimum_measured_speed=min(speeds) if speeds else None))
    return result

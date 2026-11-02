import math
import pytest


def test_constrained_dock_rejects_unreachable_lateral_residual_instead_of_zero_command():
    from print_factory.v2_navigation import constrained_dock_command
    with pytest.raises(ValueError,match='lateral'):
        constrained_dock_command(dict(x=0.,y=.03,yaw=0.),(0.,0.),0.)
from print_factory.v2_navigation import dense_goals, wrap_angle, model_command, heading_command, precision_command


def test_dense_goals_are_native_float_and_at_most_point_eight_meters():
    goals=dense_goals((0,0),(2,0))
    assert goals[-1]==(2.,0.)
    assert len(goals)==4
    assert max(math.dist(a,b) for a,b in zip([(0,0)]+goals,goals))<=.8


def test_learned_steering_uses_saved_observation_heading_and_waypoint():
    v,w,target=model_command([.4,.2],math.pi/2,math.pi/2)
    assert target==pytest.approx(math.pi/2+math.atan2(.2,.4))
    assert v>0 and w>0
    _,corrected,_=model_command([.4,.2],math.pi/2,target)
    assert corrected==pytest.approx(0.)


def test_heading_servo_has_useful_minimum_torque_command_outside_deadband():
    assert heading_command(.09)>=.55
    assert heading_command(-.09)<=-.55
    assert heading_command(.02)==0
    assert heading_command(3)<=.8
    assert wrap_angle(3*math.pi)==pytest.approx(math.pi)


def test_precision_dock_refuses_long_route_and_respects_final_heading():
    with pytest.raises(ValueError):
        precision_command(dict(x=0,y=0,yaw=0),(1,0),0)
    v,w=precision_command(dict(x=0,y=0,yaw=0),(.5,0),0)
    assert 0<v<=.13 and w==0
    v,w=precision_command(dict(x=0,y=0,yaw=math.pi/2),(.5,0),0)
    assert v==0 and w<0


def test_dock_lateral_residual_never_requests_pivot_and_overshoot_reverses():
    from print_factory.v2_navigation import constrained_dock_command, dock_reached
    p=dict(x=-.01,y=-.021,yaw=0.)
    v,w=constrained_dock_command(p,(0,0),0.)
    assert v==0 and abs(w)<.2
    assert dock_reached(p,(0,0),0.)
    v,w=constrained_dock_command(dict(x=.04,y=.02,yaw=.015),(0,0),0.)
    assert v<0 and abs(w)<.2
    # Far approach target is bounded at .12rad, near station at .04rad.
    _,far=constrained_dock_command(dict(x=-.4,y=-.05,yaw=0.),(0,0),0.)
    _,near=constrained_dock_command(dict(x=-.05,y=-.05,yaw=0.),(0,0),0.)
    assert abs(far)<=.36 and abs(near)<=.12


def test_actual_travel_generator_continues_internal_node_without_brake_or_reorient(tmp_path):
    from types import SimpleNamespace
    from print_factory.v2_navigation import LearnedNavigator
    class Robot:
        def __init__(self):self.p=dict(x=0.,y=0.,yaw=0.)
        def pose(self):return self.p.copy()
    robot=Robot();events=[]
    nav=LearnedNavigator([robot,Robot()],[None,None],None,SimpleNamespace(busy=True),tmp_path,
                         lambda:0.,lambda kind,**kw:events.append(kind))
    nav._capture=lambda *args:'actual-goal-image.png'
    travel=nav.travel(0,(1.28,0))
    for _ in range(12):
        next(travel)
        if nav.states[0]['mode']=='learned':break
    s=nav.states[0]
    assert s['goal']==[.64,0.]
    s.update(speed=.18,yaw_rate=.07,history=['prior-observation.png'],waypoints=[[.1,0]]*3,
             observation_yaw=0.,target_heading=.03,last_response_time=0.,policy_waypoint=[.2,.006])
    robot.p['x']=.54
    heading_events=events.count('CONVENTIONAL_HEADING_END')
    next(travel)
    assert s['goal']==[1.28,0.]
    assert s['mode']=='learned' and s['active']
    assert s['speed']==.18 and s['yaw_rate']==.07
    assert s['history']==['prior-observation.png'] and s['target_heading']==.03
    assert s['last_response_time']==0.
    assert events.count('CONVENTIONAL_HEADING_END')==heading_events
    assert 'CONVENTIONAL_PRECISION_START' not in events
    assert 'NAV_LOCAL_GOAL_THROUGH' in events
    # The final goal still begins a real braking phase.
    robot.p['x']=1.18
    next(travel)
    assert s['mode']=='idle' and s['phase']=='capture_braking'
    travel.close()



def test_travel_terminal_capture_eight_cm_keeps_learning_at_twelve_cm(tmp_path):
    from types import SimpleNamespace
    from print_factory.v2_navigation import LearnedNavigator
    class Robot:
        def __init__(self):self.p=dict(x=0.,y=0.,yaw=0.)
        def pose(self):return self.p.copy()
    robot=Robot()
    nav=LearnedNavigator([robot,Robot()],[None,None],None,SimpleNamespace(busy=True),tmp_path,lambda:0.,lambda *a,**k:None)
    nav._capture=lambda *args:'goal.png'
    travel=nav.travel(0,(.12,0),terminal_capture=.08)
    for _ in range(12):
        next(travel)
        if nav.states[0]['mode']=='learned':break
    assert nav.states[0]['mode']=='learned'
    robot.p['x']=.05
    next(travel)
    assert nav.states[0]['phase']=='capture_braking'
    travel.close()
    for capture in (.03,.17,float('nan')):
        with pytest.raises(ValueError):
            next(nav.travel(0,(1,0),terminal_capture=capture))

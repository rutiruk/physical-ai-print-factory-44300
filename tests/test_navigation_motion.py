import math


def test_learned_turn_changes_are_acceleration_limited_at_physics_rate():
    from print_factory.navigation_motion import MotionLimiter
    motion = MotionLimiter()
    previous = (0., 0.)
    for tick in range(160):
        target = (.4, .8 if tick < 80 else -.8)
        actual = motion.step(*target, dt=.01)
        assert abs(actual[0]-previous[0]) <= .6*.01+1e-10
        assert abs(actual[1]-previous[1]) <= .9*.01+1e-10
        assert 0 <= actual[0] <= .4
        previous = actual
    assert actual[1] < 0


def test_braking_reaches_rest_and_safety_reset_is_immediate():
    from print_factory.navigation_motion import MotionLimiter
    motion = MotionLimiter()
    for _ in range(150): motion.step(.4, .8, .01)
    distance = 0.
    for _ in range(180):
        speed, yaw = motion.step(0., 0., .01)
        distance += speed*.01
    assert speed < 1e-4 and abs(yaw) < 1e-4
    assert distance < .21  # Fits inside the 0.30 m local-goal capture radius.
    motion.step(.4, .8, .1)
    motion.reset()
    assert motion.speed == 0 and motion.yaw_rate == 0


def test_dense_image_goals_mark_only_collinear_internal_nodes_as_through():
    from print_factory.navigation_motion import local_goal_plan
    goals = local_goal_plan((0., 0.), (3.5, 0.))
    assert len(goals) == 3
    assert [through for _, through in goals] == [True, True, False]
    assert goals[-1][0] == (3.5, 0.)
    previous = (0., 0.)
    for xy, _ in goals:
        assert math.dist(previous, xy) <= 1.2
        previous = xy


def test_motion_audit_rejects_the_original_instant_turn_change():
    from print_factory.navigation_motion import motion_summary
    samples = [dict(time_s=0.,amr=1,speed=.4,yaw_rate=.1),
               dict(time_s=.01,amr=1,speed=.4,yaw_rate=-.3)]
    assert motion_summary(samples, [])['angular_limit_violations'] == 1


def test_motion_audit_separates_explicit_safety_stops_from_normal_braking():
    from print_factory.navigation_motion import motion_summary
    samples=[dict(time_s=0.,amr=0,speed=.4,yaw_rate=.5),
             dict(time_s=.01,amr=0,speed=0.,yaw_rate=0.,safety_stop=True),
             dict(time_s=.02,amr=0,speed=.006,yaw_rate=.009)]
    summary=motion_summary(samples,[])
    assert summary['linear_limit_violations']==0
    assert summary['angular_limit_violations']==0
    assert summary['safety_stop_samples']==1


def test_handoff_evidence_uses_actual_positions_instead_of_commanded_speed():
    from print_factory.navigation_motion import handoff_speeds
    samples=[dict(time_s=0.,amr=1,speed=.4,position=[1.,0.]),
             dict(time_s=.01,amr=1,speed=.4,position=[1.,0.])]
    events=[dict(event='NAV_LOCAL_GOAL_THROUGH',amr=1,time_s=.01)]
    assert handoff_speeds(samples,events)[0]['minimum_measured_speed']==0.


def test_local_goals_from_genesis_float32_can_be_recorded_as_json():
    import json
    import numpy as np
    from print_factory.navigation_motion import local_goal_plan
    goals=local_goal_plan(np.array([-2.,-.65],dtype=np.float32),np.array([2.,-.65],dtype=np.float32))
    assert json.loads(json.dumps(goals))[-1][0] == [2.,float(np.float32(-.65))]


def test_nested_local_segments_preserve_a_continuous_handoff(monkeypatch):
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    import numpy as np
    scripts=Path(__file__).parents[1]/'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec=importlib.util.spec_from_file_location('motion_demo_test',scripts/'jeff_factory_demo.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'numpy',lambda value:np.array(value))
    amr=SimpleNamespace(get_link=lambda name:SimpleNamespace(get_pos=lambda:[-2.,-.65,.22]))
    calls=[]
    def child(i,goal,**kwargs):
        calls.append(kwargs)
        yield from ()
    demo=SimpleNamespace(f=SimpleNamespace(amrs=[amr]),navigate=child)
    list(module.Demo.navigate(demo,0,(2.,-.65),_through=True,_continuing=True))
    assert all(c['_through'] and c['_continuing'] for c in calls)

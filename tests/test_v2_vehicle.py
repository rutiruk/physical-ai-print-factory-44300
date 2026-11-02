import math
import pytest
from print_factory.v2_vehicle import DriveLimits, twist_to_wheels, limited_twist


def test_forward_and_turn_have_physical_differential_wheel_rates():
    left, right = twist_to_wheels(.2, 0)
    assert left == pytest.approx(.2/.09)
    assert right == left
    left, right = twist_to_wheels(0, .8)
    assert right == pytest.approx(-left)
    assert right == pytest.approx(.8*.49/(2*.09))


def test_command_limits_and_acceleration_are_enforced():
    limits = DriveLimits()
    assert limited_twist(10, 10, (0, 0), .01) == pytest.approx((.005, .009))
    v, w = limited_twist(10, 10, (.35, .8), .01)
    assert (v,w) == pytest.approx((.35,.8))
    assert limits.motor_torque == 6.0
    assert limits.lift_force == 250
    assert limits.lift_travel == .06


def test_invalid_commands_rejected_instead_of_poisoning_simulation():
    with pytest.raises(ValueError):
        limited_twist(math.nan, 0, (0, 0), .01)
    with pytest.raises(ValueError):
        limited_twist(0, 0, (0, 0), 0)


def test_robot_color_keeps_black_wheels_and_green_heading_marker():
    from print_factory.v2_vehicle import _colored_amr_xml
    root = _colored_amr_xml((1., .2, .1))
    assert root.find(".//geom[@name='chassis']").get('rgba') == '1.0 0.2 0.1 1'
    assert root.find(".//body[@name='wheel_fl']/geom").get('rgba') == '.035 .04 .05 1'
    assert root.find(".//geom[@name='front_marker']").get('rgba') == '.1 .9 .55 1'


def test_pose_sample_is_consistent_within_tick_and_refreshes_after_physics():
    import numpy as np
    from print_factory.v2_vehicle import DriveAMR
    class Entity:
        def __init__(self):self.x=0.;self.reads=0
        def get_pos(self):self.reads+=1;return np.array([self.x,0.,.1])
        def get_quat(self):return np.array([1.,0.,0.,0.])
    r=DriveAMR.__new__(DriveAMR);r.entity=Entity();r._pose_cache=None
    r.refresh_pose()
    assert r.pose()['x']==0.
    p=r.pose();p['x']=99
    r.entity.x=1.
    assert r.pose()['x']==0. and r.entity.reads==1
    r.refresh_pose()
    assert r.pose()['x']==1. and r.entity.reads==2

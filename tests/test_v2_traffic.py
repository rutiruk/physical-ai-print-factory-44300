import pytest


def test_single_aisle_geometry_cannot_fit_two_robots_and_bays_clear_exits():
    from print_factory.v2_traffic import AISLE_WIDTH,ROBOT_WIDTH,BAYS
    assert ROBOT_WIDTH < AISLE_WIDTH < 2*ROBOT_WIDTH
    assert all(abs(y)>1. for x,y in BAYS.values())


def test_jeff_has_both_priority_orders_and_no_priority_before_decision():
    from print_factory.v2_traffic import TrafficCoordinator
    c=TrafficCoordinator()
    poses=[dict(x=-2.4,y=0.),dict(x=2.4,y=0.)]
    assert not c.can_cross(0,poses) and not c.can_cross(1,poses)
    assert {row['id'] for row in c.candidates(poses)} >= {'priority_0','priority_1','hold'}
    c.select('priority_0')
    assert not c.can_cross(0,poses)  # Partner must physically clear first.
    poses[1]['y']=-1.45;poses[1]['x']=1.95
    assert c.can_cross(0,poses) and not c.can_cross(1,poses)


def test_waiting_robot_needs_a_second_jeff_release_after_first_robot_exits():
    from print_factory.v2_traffic import TrafficCoordinator
    c=TrafficCoordinator();c.select('priority_1')
    poses=[dict(x=-1.95,y=-1.45),dict(x=-1.95,y=0.)]
    c.mark_crossed(1)
    assert not c.can_cross(0,poses)
    assert 'release_0' in {row['id'] for row in c.candidates(poses)}
    c.select('release_0')
    assert not c.can_cross(0,poses)  # Exit turn still occupied by first robot.
    poses[1]=dict(x=-2.8,y=-.55)
    assert c.can_cross(0,poses)
    with pytest.raises(ValueError):c.select('release_1')


def test_stop_envelope_depends_on_actual_velocity_and_physical_braking():
    from print_factory.v2_traffic import stopping_envelope
    assert stopping_envelope(.3) > stopping_envelope(.1)
    assert stopping_envelope(.3) >= .3*.3+.3**2/(2*.5)


def test_pair_brake_stops_head_on_but_allows_safe_parallel_bay_exit():
    from print_factory.v2_traffic import pair_envelope
    p0=dict(x=-.45,y=0.,yaw=0.,velocity=[.2,0,0],angular_velocity=[0,0,0])
    p1=dict(x=.45,y=0.,yaw=3.14159,velocity=[-.2,0,0],angular_velocity=[0,0,0])
    assert pair_envelope(p0,p1)['stop']
    p0.update(x=-2.8,y=-.55,yaw=-1.570796,velocity=[0,0,0])
    p1.update(x=-1.95,y=-.9,yaw=1.570796,velocity=[0,.2,0])
    result=pair_envelope(p0,p1)
    assert not result['stop'] and result['clearance']>.25

from print_factory.navigation_guard import recovery_reason


def test_normal_model_motion_and_arrival_are_not_overridden():
    assert recovery_reason((0,0),(1,0),(.5,.08),.3) is None
    assert recovery_reason((0,0),(1,0),(.8,.05),.3) is None


def test_lateral_drift_requests_ai_recovery_before_leaving_safe_floor():
    assert recovery_reason((2,-.65),(2,.55),(1.73,-.2),.4)=='cross_track_deviation'
    assert recovery_reason((0,0),(1,0),(-.2,0),.3)=='moving_away_from_goal'


def test_safety_monitor_produces_no_replacement_motion():
    result=recovery_reason((0,0),(1,0),(.5,.3),.3)
    assert isinstance(result,str) # A reason for Jeff, never a hand-written waypoint.


def test_retry_from_margin_can_move_inward_but_cannot_continue_outward():
    assert recovery_reason((1,.76),(1,0),(1,.75),.3) is None
    assert recovery_reason((1,.76),(1,0),(1,.80),.3)=='floor_margin'

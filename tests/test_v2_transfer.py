import pytest
from print_factory.v2_transfer import transfer_height_targets


def test_transfer_calibration_clears_raised_deck_and_overlaps_thin_paper():
    targets = transfer_height_targets(.3983, .01)
    assert targets['actual_center'] == pytest.approx(.4043)
    assert targets['command_z'] == pytest.approx(.4086)
    assert targets['actual_center'] - .003 > .3983 + .001
    assert targets['actual_center'] - .003 < .395 + .01


def test_transfer_calibration_rejects_unbridgeable_height_or_bad_values():
    for deck, thickness in [(float('nan'), .01), (.41, .01), (.398, 0)]:
        with pytest.raises(ValueError):
            transfer_height_targets(deck, thickness)


def test_world_paper_extent_accounts_for_actual_yaw_and_quaternion_sign():
    import math
    from print_factory.v2_transfer import paper_world_half_extents
    half=(.225,.16,.005)
    q=(-.045952175, -3.70e-8, 1.21e-6, .998943686)
    extent=paper_world_half_extents(q,half)
    yaw=math.radians(185.2675)
    assert extent[1]==pytest.approx(.225*abs(math.sin(yaw))+.16*abs(math.cos(yaw)),abs=1e-5)
    assert extent[1]>.179
    assert extent==pytest.approx(paper_world_half_extents(tuple(-v for v in q),half))
    assert paper_world_half_extents((math.sqrt(.5),0,0,math.sqrt(.5)),half)==pytest.approx((.16,.225,.005))


def test_push_targets_clear_rotated_stock_and_use_projected_receiver_edge():
    from print_factory.v2_transfer import transfer_push_targets
    target=transfer_push_targets((2.792631626,.533451498,.403287739),(-.045952175,-3.7e-8,1.21e-6,.998943686),(.225,.16,.005),1.25,1)
    assert target['extent_y']>.179
    assert target['behind_y']<.330
    assert target['target_blade_y']<1.060
    assert .533451498-target['behind_y']==pytest.approx(target['extent_y']+.025)
    south=transfer_push_targets((0,-.55,.41),(1,0,0,0),(.1125,.16,.01),-1.25,-1)
    assert south['behind_y']==pytest.approx(-.365)
    assert south['target_blade_y']==pytest.approx(-1.078)


def test_paper_extent_rejects_invalid_geometry_measurements():
    from print_factory.v2_transfer import paper_world_half_extents,transfer_push_targets
    for q,half in [((0,0,0,0),(.2,.1,.01)),((1,0,0,float('nan')),(.2,.1,.01)),((1,0,0,0),(.2,-.1,.01))]:
        with pytest.raises(ValueError):paper_world_half_extents(q,half)
    with pytest.raises(ValueError):transfer_push_targets((0,0,.4),(1,0,0,0),(.2,.1,.01),1.25,0)

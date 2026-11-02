import math
import xml.etree.ElementTree as ET
import numpy as np
import pytest

from print_factory.v2_machines import GantryLimits, GantryTrajectory, MachineCycle, ASSETS


def test_gantry_rejects_unreachable_or_nonfinite_targets():
    path = GantryTrajectory()
    for target in [(3.41, 0, .5, 0), (0, -1.61, .5, 0), (0, 0, .39, 0), (0, 0, float('nan'), 0)]:
        with pytest.raises(ValueError):
            path.set_target(*target)
    assert path.command == pytest.approx([-3, 0, 1, 0])


def test_gantry_command_slew_and_mechanical_z_conversion():
    path = GantryTrajectory()
    path.set_target(3, 1, .4, math.pi / 2)
    q = path.advance(.1)
    assert path.command == pytest.approx([-2.94, .045, .975, .12])
    assert q == pytest.approx([-2.94, .045, -.775, .12])
    for _ in range(1000):
        path.advance(.1)
    assert path.command == pytest.approx([3, 1, .4, math.pi / 2])
    with pytest.raises(ValueError):
        path.advance(0)


def test_clamp_cannot_close_without_guard_and_pile():
    cycle = MachineCycle('trim')
    with pytest.raises(ValueError, match='guard'):
        cycle.request('clamp', guard_closed=False, pile_present=True)
    with pytest.raises(ValueError, match='pile'):
        cycle.request('clamp', guard_closed=True, pile_present=False)
    cycle.request('clamp', guard_closed=True, pile_present=True)
    assert cycle.clamp_target == pytest.approx(-.065)
    cycle.request('release')
    assert cycle.clamp_target == 0


def test_roller_overload_latches_and_requires_reset():
    cycle = MachineCycle('folder')
    cycle.request('feed', guard_closed=True, pile_present=True)
    assert cycle.roller_velocity == pytest.approx(-4)
    cycle.observe_load(9)
    assert cycle.fault == 'roller_overload'
    assert cycle.roller_velocity == 0
    with pytest.raises(ValueError, match='fault'):
        cycle.request('feed', guard_closed=True, pile_present=True)
    cycle.request('reset')
    assert cycle.fault is None


def test_gantry_has_nested_mechanical_chain_and_anchored_posts():
    root = ET.parse(ASSETS / 'gantry.xml').getroot()
    world = root.find('worldbody')
    assert len(world.findall("body[@name='portal']/geom")) >= 6
    bridge = world.find("body[@name='portal']/body[@name='bridge']")
    assert bridge.find("joint[@name='x']").get('range') == '-3.4 3.4'
    trolley = bridge.find("body[@name='trolley']")
    slide = trolley.find("body[@name='z_slide']")
    assert slide.find("joint[@name='z']").get('range') == '-1.35 -.65'
    assert slide.find("body[@name='tool']/geom[@name='pusher']").get('size') == '.18 .012 .003'


def test_feed_rolls_top_contact_toward_machine_positive_y():
    cycle = MachineCycle('press')
    cycle.request('feed', guard_closed=True, pile_present=True)
    # omega cross r at top of an X-axis roller: velocity_y = -omega_x * radius.
    assert -cycle.roller_velocity * .04 > 0



def test_telescoping_mast_overlaps_guide_at_bottom_of_travel():
    root = ET.parse(ASSETS / 'gantry.xml').getroot()
    trolley = root.find("worldbody/body/body/body")
    guide = trolley.find("geom[@name='z_guide_l']")
    mast = trolley.find("body/geom[@name='telescoping_mast']")
    guide_bottom = 1.75 + float(guide.get('pos').split()[2]) - float(guide.get('size').split()[2])
    mast_top_at_lowest = .4 + float(mast.get('pos').split()[2]) + float(mast.get('size').split()[2])
    mast_top_at_highest = 1.1 + float(mast.get('pos').split()[2]) + float(mast.get('size').split()[2])
    assert mast_top_at_lowest > guide_bottom + .05
    assert mast_top_at_highest <= 1.8 - .055 + 1e-8


def test_machine_roller_support_surface_is_flush_with_deck():
    root = ET.parse(ASSETS / 'machine.xml').getroot()
    frame = root.find('worldbody/body')
    for name in ('roller_a', 'roller_b'):
        roller = frame.find(f"body[@name='{name}']")
        center = float(roller.get('pos').split()[2])
        radius = float(roller.find('geom').get('size').split()[0])
        assert center + radius == pytest.approx(.395)
    assert len([g for g in frame.findall('geom') if g.get('name', '').startswith('table_')]) == 3


def test_bridge_explicit_inertia_matches_beam_and_runner_geometry_in_body_axes():
    bridge = ET.parse(ASSETS / 'gantry.xml').getroot().find("worldbody/body/body[@name='bridge']")
    geoms = bridge.findall('geom')
    masses = np.array([float(g.get('mass')) for g in geoms])
    centers = np.array([np.fromstring(g.get('pos', '0 0 0'), sep=' ') for g in geoms])
    mass = masses.sum()
    com = (masses[:, None] * centers).sum(axis=0) / mass
    inertia = np.zeros((3, 3))
    for geom, geom_mass, center in zip(geoms, masses, centers):
        half = np.fromstring(geom.get('size'), sep=' ')
        # Solid cuboid inertia using half extents, plus parallel-axis translation.
        local = np.diag(geom_mass / 3 * (np.sum(half**2) - half**2))
        offset = center - com
        inertia += local + geom_mass * (np.dot(offset, offset) * np.eye(3) - np.outer(offset, offset))
    authored = bridge.find('inertial')
    assert authored is not None, 'author body-axis inertia to avoid principal-axis warning ambiguity'
    assert float(authored.get('mass')) == pytest.approx(mass)
    assert mass == pytest.approx(9.)
    assert np.fromstring(authored.get('pos'), sep=' ') == pytest.approx(com, abs=1e-11)
    assert np.fromstring(authored.get('quat'), sep=' ') == pytest.approx([1, 0, 0, 0])
    assert np.diag(np.fromstring(authored.get('diaginertia'), sep=' ')) == pytest.approx(inertia, abs=1e-9)


def test_trim_faces_corridor_and_other_machines_face_negative_y():
    from print_factory.v2_machines import machine_yaw
    assert machine_yaw('trim') == pytest.approx(math.pi)
    assert machine_yaw('folder') == 0
    assert machine_yaw('press') == 0
    assert machine_yaw('trim', 0) == 0
    with pytest.raises(ValueError):
        machine_yaw('trim', float('nan'))


def test_south_receiver_clamp_rotates_behind_paper_target():
    from print_factory.v2_machines import machine_yaw
    frame = ET.parse(ASSETS / 'machine.xml').getroot().find('worldbody/body')
    clamp = frame.find("body[@name='clamp']")
    local = np.fromstring(clamp.get('pos'), sep=' ')
    yaw = machine_yaw('trim')
    world_y = -1.25 + math.sin(yaw) * local[0] + math.cos(yaw) * local[1]
    # South-bound paper target -1.25 is approached from larger Y. Clamp must
    # lie beyond that target, leaving the Z mast's path to -1.078 unobstructed.
    assert world_y == pytest.approx(-1.42)
    assert world_y + .055 < -1.25


def test_tabletop_strips_are_single_continuous_profiles_with_two_sided_chamfers():
    root = ET.parse(ASSETS / 'machine.xml').getroot()
    profiles = {m.get('name'): m for m in root.findall('asset/mesh')}
    frame = root.find('worldbody/body')
    bounds = {'front': (-.30, -.16), 'middle': (-.08, -.03), 'back': (.05, .30)}
    assert len(profiles) == 3
    assert not [g for g in frame.findall('geom') if g.get('name', '').startswith('entry_bevel_')]
    for name, (lo, hi) in bounds.items():
        geom = frame.find(f"geom[@name='table_{name}']")
        assert geom.get('type') == 'mesh'
        vertices = np.fromstring(profiles[geom.get('mesh')].get('vertex'), sep=' ').reshape(-1, 3)
        assert vertices[:, 1].min() == pytest.approx(lo)
        assert vertices[:, 1].max() == pytest.approx(hi)
        for edge in (lo, hi):
            assert vertices[np.isclose(vertices[:, 1], edge), 2].max() == pytest.approx(.392)
        for flat_edge in (lo+.01, hi-.01):
            assert vertices[np.isclose(vertices[:, 1], flat_edge), 2].max() == pytest.approx(.395)
        assert vertices[:, 2].max() == pytest.approx(.395)

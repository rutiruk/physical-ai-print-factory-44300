"""Synchronization and visible-content contracts for the video compositor."""
import numpy as np
from print_factory.factory_dashboard import dashboard_content, render_dashboard


def state(now=12.):
    return {'time_s': now, 'jobs': [], 'amrs': [None, None], 'machines': {}, 'faults': []}


def test_arrival_toast_never_precedes_event_and_expires_after_five_seconds():
    events = [{'time_s': 12., 'event': 'JOB_ARRIVAL', 'job': 'B', 'pages': 16, 'copies': 100}]
    assert dashboard_content(state(11.99), None, events, [])['arrivals'] == []
    assert dashboard_content(state(12.), None, events, [])['arrivals'][0]['job'] == 'B'
    assert dashboard_content(state(16.99), None, events, [])['arrivals'][0]['job'] == 'B'
    assert dashboard_content(state(17.), None, events, [])['arrivals'] == []


def test_future_events_are_hidden_from_timeline():
    events = [{'time_s': 8., 'event': 'PROCESS_START', 'job': 'A', 'machine': 'press'},
              {'time_s': 13., 'event': 'JOB_ARRIVAL', 'job': 'B'}]
    content = dashboard_content(state(), None, events, [])
    assert len(content['timeline']) == 1
    assert 'A' in content['timeline'][0]


def test_both_robot_labels_and_actual_cargo_remain_visible_when_one_is_idle():
    snapshot = state()
    snapshot['amrs'][0] = {'job': 'A', 'form': 2, 'source': 'press', 'destination': 'folder'}
    content = dashboard_content(snapshot, None, [], [{'model': 'vint', 'phase': 'carrying'}])
    assert 'AMR1' in content['robots'][0]['title'] and 'ViNT' in content['robots'][0]['title']
    assert 'A' in content['robots'][0]['cargo'] and 'F2' in content['robots'][0]['cargo']
    assert 'AMR2' in content['robots'][1]['title'] and 'NoMaD' in content['robots'][1]['title']
    assert content['robots'][1]['phase'] == '待機'


def test_progress_counts_gathered_forms_without_claiming_completion():
    snapshot = state()
    snapshot['jobs'] = [{'id': 'A', 'pages': 16, 'copies': 100, 'due': 100,
                         'locations': {1: 'gather', 2: 'folder', 3: 'press', 4: 'stock'},
                         'received': [1], 'completed': None}]
    row = dashboard_content(snapshot, None, [], [])['jobs'][0]
    assert row['gathered'] == 1 and row['forms'] == 4
    assert not row['done']


def test_renderer_preserves_rgb_inputs_and_returns_full_size_image():
    rgb = np.full((120, 200, 3), [35, 70, 110], dtype=np.uint8)
    original = rgb.copy()
    image = render_dashboard(rgb, rgb, state(), None, [], [])
    assert image.mode == 'RGB' and image.size == (1440, 900)
    assert np.array_equal(rgb, original)
    assert image.getpixel((100, 350)) == (35, 70, 110)

"""Editing must preserve observed actions, especially complete physical pushes."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('compose_jeff_video', Path(__file__).parents[1] / 'scripts/compose_jeff_video.py')
video = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video)


def test_merge_clamps_and_unites_overlapping_windows():
    assert video.merge_intervals([(-2, 3), (2, 5), (9, 12)], 10) == [(0., 5.), (9., 10.)]


def test_all_push_motion_survives_navigation_compression():
    events = [{'time_s': 0, 'event': 'JOB_ARRIVAL'},
              {'time_s': 8.5, 'event': 'JOB_ARRIVAL'},
              {'time_s': 23.7, 'event': 'JOB_ARRIVAL'},
              {'time_s': 40, 'event': 'PHYSICAL_PUSH_START', 'amr': 0},
              {'time_s': 48, 'event': 'PHYSICAL_PUSH', 'amr': 0},
              {'time_s': 60, 'event': 'LEARNED_NAV_START', 'amr': 1, 'model': 'NoMaD'},
              {'time_s': 450, 'event': 'LEARNED_NAV_END', 'amr': 1, 'model': 'NoMaD'}]
    plan = video.select_intervals(events, [], 500, max_seconds=40)
    assert any(a <= 40 and b >= 48 for a, b in plan['keep'])
    for instant in (0, 8.5, 23.7, 60, 450):
        assert any(a <= instant <= b for a, b in plan['keep'])
    assert sum(b-a for a,b in plan['keep']) / 2 <= 40
    assert plan['cuts']


def test_older_log_preserves_five_seconds_before_push_completion():
    plan = video.select_intervals([{'time_s': 20, 'event': 'PHYSICAL_PUSH', 'amr': 0}], [], 30)
    assert any(a <= 15 and b >= 20.5 for a,b in plan['keep'])
    assert plan['pushes'][0]['start_inferred'] is True


def test_closing_summary_counts_actual_completion_and_reserves_three_seconds():
    result = {'simulation_seconds': 91.23, 'state': {'jobs': [
        {'id': 'A', 'copies': 100, 'completed': 60.1},
        {'id': 'B', 'copies': 100, 'completed': 80.2},
        {'id': 'C', 'copies': 100, 'completed': 91.22}]}}
    summary = video.closing_summary(result)
    assert summary['completed_jobs'] == 3 and summary['copies'] == 300
    assert summary['simulation_seconds'] == 91.23
    assert summary['completion_times'] == [('A', 60.1), ('B', 80.2), ('C', 91.22)]
    plan = video.select_intervals([], [], 500, max_seconds=175-3)
    assert plan['predicted_seconds']+3 <= 175


def test_closing_summary_does_not_count_unfinished_job_as_completed():
    result = {'simulation_seconds': 10, 'state': {'jobs': [
        {'id': 'A', 'copies': 100, 'completed': 9},
        {'id': 'B', 'copies': 100, 'completed': None}]}}
    summary = video.closing_summary(result)
    assert summary['completed_jobs'] == 1 and summary['copies'] == 100


def test_many_local_image_goals_shorten_endpoint_previews_before_dropping_evidence():
    events=[]
    for i in range(100):
        events += [dict(time_s=i*7,event='LEARNED_NAV_START',amr=0),
                   dict(time_s=i*7+5,event='LEARNED_NAV_END',amr=0)]
    plan=video.select_intervals(events,[],700,max_seconds=120)
    assert plan['predicted_seconds'] <= 120
    for event in events:
        assert any(a <= event['time_s'] <= b for a,b in plan['keep'])

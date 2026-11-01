import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('check_jeff_artifacts', Path(__file__).parents[1]/'scripts/check_jeff_artifacts.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_summary_rejects_missing_physical_transfers():
    result = {'status': 'complete', 'success': True,
              'state': {'jobs': [{'completed': 5, 'copies': 100} for _ in range(3)]},
              'events': [{'event': 'PHYSICAL_PUSH', 'supported': True} for _ in range(15)]}
    summary = audit.check_summary(result)
    assert any('16 PHYSICAL_PUSH' in error for error in summary['errors'])


def test_annotation_preserves_decisions_and_marks_mutable_observation():
    result = {'decisions': [{'observation': {'time_s': 3}, 'choice': 'wait', 'probabilities': {'wait': 1}}]}
    assert audit.annotate_legacy_observations(result)
    decision = result['decisions'][0]
    assert 'observation' not in decision
    assert decision['live_state_metadata'] == {'time_s': 3}
    assert decision['choice'] == 'wait' and decision['probabilities'] == {'wait': 1}
    assert 'not an immutable input capture' in result['observation_history_note']
    assert not audit.annotate_legacy_observations(result)

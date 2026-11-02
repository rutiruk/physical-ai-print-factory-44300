"""A real observed equal-score response must not become input-order priority."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from print_factory.v2_traffic import TrafficCoordinator


def experiment(version=0):
    path=Path(__file__).resolve().parents[1]/'scripts/mechanical_factory_v2.py'
    spec=importlib.util.spec_from_file_location('v2_runtime_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    e=module.Experiment.__new__(module.Experiment)
    e.now=2.;e.version=version;e.next_jeff=0.;e.ambiguous_decisions=0
    e.events=[];e.decisions=[];e.traffic=TrafficCoordinator()
    e.choices=lambda:[{'id':'priority_0'},{'id':'priority_1'},{'id':'hold'}]
    e.pending=dict(time_s=1.,image_path='actual.png',state={},candidates=e.choices(),version=0)
    response=dict(choice='priority_0',probabilities={'priority_0':.46029175,'priority_1':.46029175,'hold':.07941649})
    e.jeff_worker=SimpleNamespace(poll=lambda:response,busy=True)
    return e


def test_equal_score_response_never_grants_first_candidate():
    e=experiment();e.dispatch()
    assert e.traffic.winner is None
    assert not e.decisions[0]['accepted']
    assert e.jeff_view['choice']=='ambiguous'
    assert e.ambiguous_decisions==1


def test_stale_equal_score_response_does_not_consume_ambiguity_budget():
    e=experiment(version=1);e.dispatch()
    assert e.traffic.winner is None and e.ambiguous_decisions==0
    assert e.events[-1]['event']=='STALE_JEFF'


def test_jeff_start_print_authorizes_process_without_implicitly_granting_traffic():
    e=experiment();e.print_authorized=False
    e.choices=lambda:[{'id':'start_print_A'},{'id':'hold'}]
    e.jeff_worker.poll=lambda:dict(choice='start_print_A',probabilities={'start_print_A':.9,'hold':.1})
    e.dispatch()
    assert e.print_authorized and e.traffic.winner is None
    assert e.events[-1]['event']=='JEFF_START_PRINT'


def test_paper_losing_support_during_folder_feed_cannot_advance_job():
    import numpy as np
    import pytest
    from print_factory.v2_printing import PrintJob
    e=experiment();e.jobs=[PrintJob('A',stage='printed')];e.job_ui=['in_transit']
    calls=[]
    def contacts(**kw):
        calls.append(1)
        value=np.array([0] if len(calls)==1 else [],dtype=int)
        return {'link_a':SimpleNamespace(detach=lambda:SimpleNamespace(cpu=lambda:SimpleNamespace(numpy=lambda:value)))}
    machine=SimpleNamespace(entity=object(),cycle=SimpleNamespace(roller_velocity=0.),
                            state=lambda:{'dof_position':[0.,0.,0.]},request=lambda *a,**kw:None)
    e.f=SimpleNamespace(papers=[SimpleNamespace(get_contacts=contacts)],machines={'folder':machine},
                        gantry=SimpleNamespace(state=lambda:{'pose':[0.,0.,1.]}))
    gen=e.machine_cycle(0)
    with pytest.raises(RuntimeError,match='support'):
        for _ in range(400):next(gen)
    assert e.jobs[0].stage=='printed' and e.jobs[0].history==[]

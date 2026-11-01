import pytest
from print_factory.dispatch import Factory, Job, StaleDecision


def test_irregular_arrivals_and_multiple_legal_choices():
    f=Factory([Job('A',0,90,pages=8),Job('B',2.7,40,pages=4)])
    f.advance(0)
    assert {c['id'] for c in f.candidates()} >= {'print:A:1','print:A:2'}
    assert 'B' not in f.jobs
    f.advance(2.7)
    assert 'print:B:1' in {c['id'] for c in f.candidates()}
    assert len([e for e in f.events if e['event']=='JOB_ARRIVAL'])==2


def test_stale_choice_cannot_start_a_job():
    f=Factory([Job('A',0,90),Job('B',1,40)])
    f.advance(0);version=f.version
    f.advance(1)
    with pytest.raises(StaleDecision):f.select('print:A:1',version)
    assert not f.machines


def test_resource_reservation_and_no_processing_before_transport():
    f=Factory([Job('A',0,90,pages=4)])
    f.advance(0);f.select('print:A:1',f.version)
    assert not any(c['id'].startswith('print:') for c in f.candidates())
    f.advance(10)
    ids={c['id'] for c in f.candidates()}
    assert 'carry:A:1:press:folder:0' in ids
    assert 'fold:A:1' not in ids
    f.select('carry:A:1:press:folder:0',f.version)
    assert f.amrs[0] is not None
    assert not any(c['id'].startswith('carry:A:1') for c in f.candidates())
    with pytest.raises(ValueError):f.complete_transport(0,physically_supported=False)
    assert f.amrs[0] is not None
    f.complete_transport(0,physically_supported=True)
    assert 'fold:A:1' in {c['id'] for c in f.candidates()}


def test_manufacturing_mass_and_finishing_from_actual_process_gates():
    f=Factory([Job('A',0,90,pages=8)])
    f.advance(0)
    for form in [2,1]:
        f.select(f'print:A:{form}',f.version);f.advance(f.now+10)
        f.select(f'carry:A:{form}:press:folder:0',f.version)
        f.complete_transport(0,True)
        f.select(f'fold:A:{form}',f.version);f.advance(f.now+10)
        f.select(f'carry:A:{form}:folder:gather:1',f.version)
        f.complete_transport(1,True)
    f.select('finish:A',f.version);f.advance(f.now+20)
    assert f.jobs['A'].book.packed
    b=f.jobs['A'].book
    assert b.product_mass_kg+b.trim_waste_kg==pytest.approx(b.input_mass_kg)


def test_folder_fault_and_inner_first_gate():
    f=Factory([Job('A',0,90,pages=8)])
    f.advance(0);f.select('print:A:1',f.version);f.advance(10)
    f.select('carry:A:1:press:folder:0',f.version);f.complete_transport(0,True)
    f.set_fault('folder',True)
    assert 'fold:A:1' not in {c['id'] for c in f.candidates()}
    f.set_fault('folder',False);f.select('fold:A:1',f.version);f.advance(20)
    assert not any(c['id'].startswith('carry:A:1:folder:gather:') for c in f.candidates())


def test_inflight_observation_does_not_change_when_world_advances():
    f=Factory([Job('A',0,90,pages=4)]);f.advance(0)
    snapshot=f.observation()
    f.select('print:A:1',f.version)
    assert snapshot['jobs'][0]['locations'][1]=='stock'
    f.advance(10);f.select('carry:A:1:press:folder:0',f.version)
    carried=f.observation();f.amrs[0]['picked_up']=True
    assert 'picked_up' not in carried['amrs'][0]

import xml.etree.ElementTree as ET
import pytest
from print_factory.v2_printing import PrintJob, printing_press_xml


def test_printing_job_requires_stock_contact_and_measured_roller_motion():
    job=PrintJob('A')
    for supported,delta in [(False, .6),(True, .01)]:
        with pytest.raises(ValueError):
            job.record_operation('press',paper_supported=supported,roller_delta=delta)
    assert job.stage=='raw'
    job.record_operation('press',paper_supported=True,roller_delta=-.55)
    assert job.stage=='printed'
    assert job.ink_coverage==1.
    assert 'approximation' in job.history[-1]['process_model']


def test_job_follows_connected_print_fold_finish_sequence():
    job=PrintJob('A')
    with pytest.raises(ValueError):
        job.record_operation('folder',paper_supported=True,roller_delta=.6,clamp_displacement=.06)
    job.record_operation('press',paper_supported=True,roller_delta=.6)
    with pytest.raises(ValueError):
        job.record_operation('folder',paper_supported=True,roller_delta=.6,clamp_displacement=0)
    job.record_operation('folder',paper_supported=True,roller_delta=.6,clamp_displacement=.06)
    assert job.stage=='folded'
    job.record_operation('trim',paper_supported=True,clamp_displacement=.06)
    assert job.stage=='finished'
    assert len(job.history)==3
    assert PrintJob('B',stage='folded').stage=='folded'


def test_printing_press_has_driven_rollers_without_finishing_clamp_obstacles():
    root=printing_press_xml()
    frame=root.find('worldbody/body')
    assert len(root.findall('.//joint'))==2
    assert frame.find("body[@name='clamp']") is None
    assert not [g for g in frame.findall('geom') if g.get('name','').startswith('clamp_')]
    assert [j.get('name') for j in root.findall('.//joint')]==['roller_a','roller_b']

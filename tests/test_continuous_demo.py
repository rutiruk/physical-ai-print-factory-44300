import importlib.util
import json
from pathlib import Path

import av
import numpy as np
import pytest


def composer():
    path=Path(__file__).parents[1]/'scripts/compose_continuous_jeff_video.py'
    spec=importlib.util.spec_from_file_location('continuous_video_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_single_job_preserves_leaflet_recipe_and_keeps_multi_scenario():
    from print_factory.scenarios import factory_jobs,scenario_targets
    jobs=factory_jobs('single')
    assert [(j.id,j.arrival,j.pages,j.copies) for j in jobs]==[('B',0.,4,100)]
    assert scenario_targets('single')==dict(jobs=1,copies=100,pushes=4)
    assert scenario_targets('multi')==dict(jobs=3,copies=300,pushes=16)
    with pytest.raises(ValueError):factory_jobs('unrecognized')


def test_continuous_plan_rejects_over_three_minutes_without_omissions():
    module=composer()
    plan=module.continuous_plan(7200)
    assert plan['frame_count']==7200 and plan['fps']==40
    assert plan['duration_seconds']==180 and plan['cuts']==[]
    with pytest.raises(ValueError,match='180'):module.continuous_plan(7201)


def test_encoder_retains_every_source_frame_in_order_at_double_fps(tmp_path):
    from print_factory.video import VideoWriter
    folder=tmp_path/'single';folder.mkdir()
    colors=[(170,20,20),(20,170,20),(20,20,170),(150,150,20)]
    writer=VideoWriter(folder/'factory_raw.mp4',20)
    for color in colors:writer.append_data(np.full((900,1440,3),color,dtype=np.uint8))
    writer.close()
    result=dict(success=True,status='complete',scenario='single',simulation_seconds=.2,
                state=dict(jobs=[dict(id='B',copies=100,completed=.1)]))
    (folder/'result.json').write_text(json.dumps(result),encoding='utf8')
    output=tmp_path/'continuous.mp4'
    plan=composer().compose(folder,output)
    with av.open(str(output)) as source:
        assert float(source.streams.video[0].average_rate)==40
        frames=list(source.decode(video=0))
    assert len(frames)==len(colors)==plan['source_frame_count']
    for frame,color in zip(frames,colors):
        np.testing.assert_allclose(frame.to_ndarray(format='rgb24')[400,700],color,atol=6)


def test_audit_rejects_a_cut_even_if_video_is_under_three_minutes():
    path=Path(__file__).parents[1]/'scripts/check_jeff_artifacts.py'
    spec=importlib.util.spec_from_file_location('continuous_audit_test',path)
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    plan=composer().continuous_plan(4000)
    assert audit.continuous_errors(plan,200.)==[]
    plan['cuts']=[[70.,80.]]
    assert any('cuts' in error for error in audit.continuous_errors(plan,200.))
    plan['cuts']=[];plan['frame_count']-=1
    assert any('omitted source frames' in error for error in audit.continuous_errors(plan,200.))


def test_continuous_audit_accepts_physics_clock_float_roundoff():
    path=Path(__file__).parents[1]/'scripts/check_jeff_artifacts.py'
    spec=importlib.util.spec_from_file_location('continuous_float_audit',path)
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    assert audit.continuous_errors(composer().continuous_plan(3714),185.70000000000002)==[]

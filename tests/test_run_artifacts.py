import json
from print_factory.run_artifacts import begin_run,safe_manifest,write_result


def test_start_of_new_run_invalidates_previous_success(tmp_path):
    path=tmp_path/'result.json';path.write_text('{"success":true}')
    result=begin_run(path,'robobrain')
    assert not json.loads(path.read_text())['success']
    assert result['status']=='running'


def test_crashed_model_does_not_prevent_failure_record(tmp_path):
    class Crashed:
        def request(self,payload):raise BrokenPipeError('worker died')
    result={'success':False,'error':'inference failed','foundation_model':safe_manifest(Crashed())}
    path=tmp_path/'result.json';write_result(path,result)
    saved=json.loads(path.read_text())
    assert not saved['success']
    assert saved['foundation_model']['unavailable']=='worker died'

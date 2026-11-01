"""Contract tests keep image evidence and candidate identities intact."""
import math

import pytest

from print_factory.jeff_policy import JeffPolicy, build_decision, decision_result


def test_build_decision_passes_camera_image_and_descriptions(tmp_path):
    image = tmp_path / "camera.png"
    image.write_bytes(b"image is opened by Jeff, not the request adapter")
    row = build_decision(image, {"queue": ["job-a"]}, [
        {"id": "start-a", "description": "Start job A on the empty printer"},
        {"id": "wait", "description": "Wait for a free printer"},
    ])
    assert row["images"] == [str(image.resolve())]
    assert row["state"] == {"queue": ["job-a"]}
    assert row["question"]["criteria"] == {
        "start-a": "Start job A on the empty printer", "wait": "Wait for a free printer"}


@pytest.mark.parametrize("candidates", [[], [
    {"id": "wait", "description": "Wait"}, {"id": "wait", "description": "Wait twice"}],
    [{"id": "12", "description": "Numeric key"}]])
def test_invalid_choices_fail_before_inference(tmp_path, candidates):
    image = tmp_path / "camera.png"
    image.touch()
    with pytest.raises(ValueError):
        build_decision(image, {}, candidates)


def test_result_chooses_candidate_and_rejects_invalid_model_output():
    result = decision_result(["start", "wait"], [0.1, 0.9], 42, {"revision": "abc"})
    assert result["choice"] == "wait"
    assert result["probabilities"] == {"start": 0.1, "wait": 0.9}
    assert result["latency_ms"] == 42
    assert result["model"]["revision"] == "abc"
    for values in ([math.nan, 1], [1], [-1, 2], [0, 0]):
        with pytest.raises(ValueError):
            decision_result(["start", "wait"], values, 1, {})


@pytest.mark.parametrize("vision_values,expected,excluded", [
    ([0.1, 0.9], "carry@south", ["carry@direct"]),
    ([0.9, 0.1], "carry@direct", []),
])
@pytest.mark.parametrize("plan_text_only", [False, True])
def test_corridor_ai_gate_filters_only_direct_routes_retains_wait_and_stage_evidence(
        tmp_path, vision_values, expected, excluded, plan_text_only):
    image, corridor = tmp_path / "factory.png", tmp_path / "corridor.png"
    image.write_bytes(b"factory-image")
    corridor.write_bytes(b"corridor-image")
    state = {"jobs": ["urgent"]}
    candidates = [
        {"id": "carry@direct", "route": "direct", "description": "Carry through direct corridor"},
        {"id": "carry@south", "route": "south", "description": "Carry through south detour"},
        {"id": "wait", "description": "Wait at staging"}]
    # Only replace the external GPU forward pass; request construction, filtering,
    # stage results, hashing and candidate selection execute production code.
    class Model:
        def __init__(self):
            self.rows = []

        def predict(self, rows, batch_size):
            row = rows[0]
            self.rows.append(row)
            if len(self.rows) == 1:
                return [vision_values]
            return [[0.8] + [0.2 / (len(row["question"]["criteria"]) - 1)] *
                    (len(row["question"]["criteria"]) - 1)]

    policy = object.__new__(JeffPolicy)
    policy.model, policy.metadata, policy.device = Model(), {"id": "test-external-model"}, "cpu"
    result = policy.decide(image, state, candidates, corridor_image_path=corridor,
                           plan_text_only=plan_text_only)
    assert result["choice"] == expected
    assert result["excluded_candidate_ids"] == excluded
    assert "wait" in result["probabilities"]
    assert ("carry@direct" in result["probabilities"]) == (not excluded)
    assert result["visual"]["probabilities"] == dict(zip(["direct", "south"], vision_values))
    assert result["planning"]["probabilities"] == result["probabilities"]
    assert result["latency_ms"] >= result["planning"]["latency_ms"]
    assert result["visual"]["image_sha256"] != result["image_sha256"]
    assert policy.model.rows[0]["images"] == [str(corridor)]
    assert policy.model.rows[1]["images"] == ([] if plan_text_only else [str(image)])
    assert result["planning"]["modalities"] == (["text"] if plan_text_only else ["text", "image"])
    assert result["planning"]["image_used"] is not plan_text_only
    assert result["visual"]["modalities"] == ["text", "image"]
    assert policy.model.rows[1]["state"]["vision_result"]["choice"] == result["visual"]["choice"]
    assert state == {"jobs": ["urgent"]}

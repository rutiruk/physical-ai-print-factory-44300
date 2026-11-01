"""Official Jeff one-pass image/choice inference in its isolated Python runtime.

The published base is documented as English/text-only: accepting image tensors
does not establish visual accuracy. No model or calibration is trained here.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time

MODEL_ID = "mstrasser/Jeff-Qwen3.5-0.8B"
MODEL_REVISION = "f0a2b523f1b64c567d4628fadd60caea03cc6847"
VENDOR_REVISION = "3720e7c66d73b79a6e90189f3d5b0d6ecf03ddc0"
CORRIDOR_STATE = "The image is a closeup of the direct factory corridor. Is a red obstacle present in this corridor? Select the route based only on this camera observation."
CORRIDOR_CANDIDATES = [
    {"id": "direct", "description": "No red obstacle is present: use the direct corridor."},
    {"id": "south", "description": "A red obstacle is present: avoid this corridor and use the south detour."}]


def build_decision(image_path, state, candidates):
    image = Path(image_path).resolve(strict=True)
    if not 1 <= len(candidates) <= 254:
        raise ValueError("Jeff requires 1 to 254 candidates")
    criteria = {}
    for candidate in candidates:
        key, description = candidate["id"], candidate["description"]
        if not isinstance(key, str) or not key.strip() or key.isdecimal() or key in criteria:
            raise ValueError("Candidate IDs must be unique descriptive strings, not bare numbers")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("Each candidate needs a description")
        criteria[key] = description
    return {"state": state, "images": [str(image)], "question": {
        "type": "choice", "criteria": criteria,
        "instructions": "Inspect the supplied factory camera image and state. Choose the best feasible next action from the listed candidates. Use visible evidence and the provided constraints."}}


def decision_result(keys, values, latency_ms, metadata):
    if len(keys) != len(values) or not values or any(not math.isfinite(v) or v < 0 for v in values) or sum(values) <= 0:
        raise ValueError("Jeff returned an invalid probability distribution")
    total = sum(values)
    probabilities = {key: float(value / total) for key, value in zip(keys, values)}
    return {"choice": max(probabilities, key=probabilities.get), "probabilities": probabilities,
            "latency_ms": latency_ms, "model": metadata}


class JeffPolicy:
    def __init__(self, checkpoint, device="cuda:1"):
        import torch
        from jeff.model import DecisionModel
        self.torch = torch
        self.device = device
        self.checkpoint = Path(checkpoint).resolve(strict=True)
        self.model = DecisionModel(checkpoint=self.checkpoint, train=False, device=device)
        provenance = self.checkpoint / "factory_provenance.json"
        self.metadata = {"id": MODEL_ID, "revision": MODEL_REVISION, "release": "v1.2",
                         "vendor_revision": VENDOR_REVISION, "device": device,
                         "visual_accuracy": "unvalidated; upstream base documented English/text-only",
                         "training": "none", "adapter": None}
        if provenance.exists():
            self.metadata.update(json.loads(provenance.read_text(encoding="utf-8")))

    def decide(self, image_path, state, candidates, corridor_image_path=None, plan_text_only=False):
        if corridor_image_path is not None:
            visual = self._decide_once(corridor_image_path, CORRIDOR_STATE, CORRIDOR_CANDIDATES)
            excluded = [candidate["id"] for candidate in candidates
                        if visual["choice"] == "south" and candidate.get("route") == "direct"]
            feasible = [candidate for candidate in candidates if candidate["id"] not in excluded]
            vision_result = {"choice": visual["choice"], "probabilities": visual["probabilities"],
                             "source": "Jeff direct-corridor camera inference",
                             "constraint": "Avoid direct-route candidates when the visual model selects south."}
            enriched = dict(state) if isinstance(state, dict) else {"factory_state": state}
            enriched["vision_result"] = vision_result
            planning = self._decide_once(image_path, enriched, feasible, text_only=plan_text_only)
            return {**planning, "visual": visual, "planning": planning,
                    "excluded_candidate_ids": excluded,
                    "latency_ms": visual["latency_ms"] + planning["latency_ms"]}
        return self._decide_once(image_path, state, candidates)

    def _decide_once(self, image_path, state, candidates, text_only=False):
        row = build_decision(image_path, state, candidates)
        if text_only:
            row["images"] = []
            row["question"]["instructions"] = "Choose the best feasible next factory action using the supplied production state, camera assessment and candidate effects."
        if self.device.startswith("cuda"):
            self.torch.cuda.synchronize(self.device)
        started = time.perf_counter()
        values = self.model.predict([row], batch_size=1)[0]
        if self.device.startswith("cuda"):
            self.torch.cuda.synchronize(self.device)
        result = decision_result(list(row["question"]["criteria"]), values,
                                 (time.perf_counter() - started) * 1000, self.metadata)
        result["image_sha256"] = hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
        result["modalities"] = ["text"] if text_only else ["text", "image"]
        result["image_used"] = not text_only
        return result

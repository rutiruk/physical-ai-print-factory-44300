"""Probe a fixed camera ROI; image preprocessing never chooses an action."""
import argparse
import contextlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "vendor/jeff/src")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "models/jeff-2b-v1.2")
    args = parser.parse_args()
    from PIL import Image
    output = ROOT / "output/jeff_factory"
    # Fixed coordinates cover the existing renderer's A DIRECT camera closeup.
    # Exactly the same crop is applied to every input; no pixel classifier runs.
    box = (5, 545, 185, 605)
    images = {}
    for condition in ("clear", "blocked"):
        path = output / f"jeff_probe_roi_{condition}.png"
        with Image.open(ROOT / f"output/printing/comparison_{condition}.png") as frame:
            frame.crop(box).save(path)
        images[condition] = path
    state = "The image is a closeup of the direct factory corridor. Is a red obstacle present in this corridor? Select the route based only on this camera observation."
    candidates = [{"id": "direct", "description": "No red obstacle is present: use the direct corridor."},
                  {"id": "south", "description": "A red obstacle is present: avoid this corridor and use the south detour."}]
    with contextlib.redirect_stdout(sys.stderr):
        from print_factory.jeff_policy import JeffPolicy
        policy = JeffPolicy(args.checkpoint, "cuda:1")
        warmup = policy.decide(images["clear"], state, candidates)
        trials = []
        for repetition in range(2):
            for condition, path in images.items():
                result = policy.decide(path, state, candidates)
                result.update(condition=condition, repetition=repetition,
                              expected="direct" if condition == "clear" else "south")
                trials.append(result)
    latencies = sorted(r["latency_ms"] for r in trials)
    report = {"model": policy.metadata, "crop_box": list(box), "same_text_and_crop_for_both_conditions": True,
              "state": state, "candidates": candidates, "trials": trials,
              "warmup_latency_ms": warmup["latency_ms"], "warm_median_ms": statistics.median(latencies),
              "warm_p95_ms": latencies[-1], "p95_method": "nearest rank, n=4",
              "correct_choices": sum(r["choice"] == r["expected"] for r in trials)}
    (output / "jeff_probe_2b_roi.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

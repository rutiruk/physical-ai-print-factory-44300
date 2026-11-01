"""Controlled image-pair and global dispatch probes of the published Jeff base."""
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
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "models/jeff-v1.2")
    parser.add_argument("--output", type=Path, default=ROOT / "output/jeff_factory/jeff_probe_controlled.json")
    args = parser.parse_args()
    with contextlib.redirect_stdout(sys.stderr):
        from print_factory.jeff_policy import JeffPolicy
        policy = JeffPolicy(args.checkpoint, "cuda:1")
    state = {
        "task": "Choose the route from the left printer to the right printer.",
        "rule": "Use A DIRECT when its corridor is clear. If a red crate obstructs A DIRECT, take B SOUTH. Both routes are shown in the camera and their bottom closeups.",
        "obstruction": "Determine from the supplied image; no obstruction label is provided in state."
    }
    candidates = [
        {"id": "direct", "description": "Take A DIRECT: the shorter upper corridor. Select only if its camera closeup shows no red crate blocking the route."},
        {"id": "south", "description": "Take B SOUTH: the longer lower detour. Select if the camera closeup shows a red crate blocking A DIRECT."}]
    images = {name: ROOT / f"output/printing/comparison_{name}.png" for name in ("clear", "blocked")}
    records = []
    with contextlib.redirect_stdout(sys.stderr):
        warmup = policy.decide(images["clear"], state, candidates)
        for repetition in range(2):
            for condition, path in images.items():
                result = policy.decide(path, state, candidates)
                result.update(condition=condition, repetition=repetition, expected="direct" if condition == "clear" else "south")
                records.append(result)
        dispatch_state = {
            "task": "Choose one next global factory dispatch from the feasible candidates.",
            "time": 120, "robot": {"position": "central staging", "carrying": None, "battery": 0.82},
            "printers": {"cyan": {"status": "idle", "loaded_material": "PLA"},
                         "magenta": {"status": "busy", "remaining_seconds": 45},
                         "yellow": {"status": "idle", "loaded_material": "PETG"}},
            "jobs": [{"id": "urgent", "material": "PLA", "due_seconds": 40, "print_seconds": 20, "release": True},
                     {"id": "later", "material": "PETG", "due_seconds": 180, "print_seconds": 45, "release": True}],
            "constraints": "Prioritize a released job that can finish before its due time. Do not interrupt busy printers. The aisle may require a visual detour."
        }
        dispatch_candidates = [
            {"id": "urgent_cyan", "description": "Deliver the urgent PLA job to idle cyan printer now; it can complete before its due time."},
            {"id": "later_yellow", "description": "Deliver the later PETG job to idle yellow printer first; the urgent job will wait."},
            {"id": "urgent_magenta", "description": "Wait 45 seconds for busy magenta before starting the urgent job; it will miss its due time."},
            {"id": "hold", "description": "Hold the robot at staging while both idle printers remain unused."}]
        dispatch = policy.decide(images["blocked"], dispatch_state, dispatch_candidates)
    latencies = sorted(item["latency_ms"] for item in records)
    clear = statistics.mean(r["probabilities"]["south"] for r in records if r["condition"] == "clear")
    blocked = statistics.mean(r["probabilities"]["south"] for r in records if r["condition"] == "blocked")
    report = {"model": policy.metadata, "same_text_state_and_options": True,
              "warmup_latency_ms": warmup["latency_ms"], "warm_median_ms": statistics.median(latencies),
              "warm_p95_ms": latencies[-1], "p95_method": "nearest rank, n=4",
              "south_probability_increase_blocked_minus_clear": blocked-clear,
              "correct_choices": sum(r["choice"] == r["expected"] for r in records),
              "image_trials": records, "dispatch_request": {"state": dispatch_state, "candidates": dispatch_candidates},
              "dispatch_result": dispatch,
              "limitation": "Two synthetic views and four trials are a functional probe, not a visual accuracy benchmark. Upstream documents the base as English/text-only."}
    destination = args.output
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in ("image_trials", "dispatch_request", "model")}, indent=2))


if __name__ == "__main__":
    main()

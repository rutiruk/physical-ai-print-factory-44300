"""JSON-lines boundary; run exclusively with .venv-jeff/Scripts/python.exe."""
import argparse
import contextlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "vendor/jeff/src")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default=str(ROOT / "models/jeff-v1.2"))
    parser.add_argument("--device", default="cuda:1")
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with contextlib.redirect_stdout(sys.stderr):
        from print_factory.jeff_policy import JeffPolicy
        policy = JeffPolicy(args.checkpoint, args.device)
    print(json.dumps({"status": "ready", "model": policy.metadata}), flush=True)
    if args.probe:
        request = json.loads(args.probe.read_text(encoding="utf-8"))
        with contextlib.redirect_stdout(sys.stderr):
            result = policy.decide(**request)
        payload = json.dumps(result, ensure_ascii=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload + "\n", encoding="utf-8")
        print(payload, flush=True)
        return
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.get("command") == "quit":
                break
            with contextlib.redirect_stdout(sys.stderr):
                result = policy.decide(**request)
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as error:
            print(json.dumps({"error": str(error), "error_type": type(error).__name__}), flush=True)


if __name__ == "__main__":
    main()

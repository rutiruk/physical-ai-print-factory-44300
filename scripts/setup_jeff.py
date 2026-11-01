"""Download only published inference files; never invoke Jeff training commands.

Environment (PowerShell, once Python 3.12 is available):
  uv venv .venv-jeff --python .runtime/python/cpython-3.12.11-windows-x86_64-none/python.exe
  uv pip install --python .venv-jeff/Scripts/python.exe torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
  uv pip install --python .venv-jeff/Scripts/python.exe transformers==5.17.0 pillow==12.3.0 safetensors==0.8.0 numpy huggingface-hub
  .venv-jeff/Scripts/python.exe scripts/setup_jeff.py
Vendor source is imported directly; incompatible upstream torch pins are not installed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from print_factory.jeff_policy import MODEL_ID, MODEL_REVISION, VENDOR_REVISION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--revision", default=MODEL_REVISION)
    parser.add_argument("--target", type=Path, default=ROOT / "models/jeff-v1.2")
    args = parser.parse_args()
    from huggingface_hub import snapshot_download
    target = args.target.resolve()
    snapshot_download(args.model_id, revision=args.revision, local_dir=str(target),
                      allow_patterns=["*.json", "*.jinja", "*.safetensors", "README.md", "LICENSE", "NOTICE"])
    hashes = {}
    for path in sorted(target.glob("*.safetensors")):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
        hashes[path.name] = digest.hexdigest()
    provenance = {"id": args.model_id, "revision": args.revision, "release": "v1.2",
                  "vendor_revision": VENDOR_REVISION, "checkpoint_sha256": hashes,
                  "training": "none", "adapter": None}
    (target / "factory_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()

# Jeff factory inference runtime

The factory uses the official public Jeff-Qwen3.5-2B v1.2 checkpoint for image decisions and global dispatch. No fine-tuning, adapter, additional training data or recalibration is performed. Inference observations and test camera frames are not training data.

## Windows setup

Prerequisites: Git and uv on PATH, an existing `.venv` with Genesis, and the tested NVIDIA driver 573 / CUDA 12.8 setup with two RTX A4000 16 GB GPUs. The simulator uses GPU0; Jeff and the navigation worker use GPU1. The setup downloads Python 3.12.11 under `.runtime/python` and installs Jeff dependencies only into `.venv-jeff`. Navigation extras use `.venv-nav`. Matching global CUDA torch packages may be reused read-only; otherwise the exact cu128 torch/torchvision wheels are installed locally in `.venv-nav`. A nested venv does not inherit its parent venv's packages. Existing `.venv` and `.venv-policy` dependencies are not reinstalled.

From the project root:

```powershell
.\setup-jeff-factory.ps1
```

An existing Python 3.12 interpreter can be selected with `-Python312 C:\path\to\python.exe`. `-BasePython` selects the existing simulator interpreter. If base Genesis is missing, prepare it first using the project's base requirements:

```powershell
py -3.10 -m venv .venv
.venv\Scripts\python.exe -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

These prerequisite commands are for a missing base environment; do not rerun them over a working installation. `setup-printing.ps1` sets up the older separate factory policy environment and does not create base Genesis. The new setup checks base Genesis before installing anything and then invokes `scripts/setup_navigation.ps1` for the published ViNT/NoMaD workers.

The tested Jeff stack is Python 3.12.11, torch 2.8.0+cu128, torchvision 0.23.0+cu128, transformers 5.17.0, Pillow 12.3.0 and safetensors 0.8.0. `requirements-jeff.txt` records every installed distribution. The official current Jeff package pins newer torch/CUDA dependencies; this project imports its pinned vendor source directly rather than installing those package dependencies. PyTorch reference kernels are used because Windows does not have the optional causal-conv1d/flash-linear-attention kernels installed.

## Sources, pins and artifact provenance

| Artifact | Source | Immutable pin |
|---|---|---|
| Jeff code | https://github.com/firelex/jeff | `3720e7c66d73b79a6e90189f3d5b0d6ecf03ddc0` |
| Jeff 2B v1.2 weights | https://huggingface.co/jeff-legacy/Jeff-Qwen3.5-2B | `d2ffa3a22f3dea8cfdd67bac595d4e8ad3681b2e` |
| Main model SHA256 | `model.safetensors` | `ccb083d62bfd84e32b9013d40f206200df509d55727c8e1e33144b01c3759b2c` |
| Readout SHA256 | `readout.safetensors` | `4387eddad3d463c808ff89a44908255fab1134f818d86ec82eaf85f90762f939` |

The older official `mstrasser/Jeff-Qwen3.5-2B` URL redirects to `jeff-legacy`. Downloads go to `models/jeff-2b-v1.2`; `factory_provenance.json` stores source, revision and file hashes. Only inference checkpoint/configuration/tokenizer/license files are requested. Models, Python runtimes and virtual environments must not be bundled with the source submission. Download them with setup. Retain provenance and upstream license files.

## Worker protocol

```powershell
.venv-jeff\Scripts\python.exe scripts/jeff_worker.py --checkpoint models/jeff-2b-v1.2 --device cuda:1
```

The worker first emits a JSON object with `status: "ready"` and model provenance. Each subsequent input line is a JSON request with `image_path`, `state` and `candidates`, where each candidate has a descriptive unique string `id` and `description`. Output contains `choice`, per-candidate `probabilities`, `latency_ms`, `image_sha256` and model provenance. Send `{"command":"quit"}` to exit. Model loading and diagnostics go to stderr; stdout is JSON-lines only.

An optional `corridor_image_path` enables two stages on the same pretrained model. First, Jeff reads a fixed corridor-camera observation and chooses `direct` or `south` from explicit red-obstacle descriptions. When its visual choice is `south`, candidates whose `route` field is `direct` are excluded. Wait and other nonroute actions remain available. Jeff then reads the full factory image and state enriched with the actual visual probabilities and chooses a dispatch. The response preserves full `visual` and `planning` stage results, `excluded_candidate_ids`, and summed inference latency. No image pixel threshold or simulator obstacle label supplies the visual decision.

With that two-stage request, `plan_text_only: true` removes the overhead image from the planning forward pass after Jeff's actual corridor image inference. The planner receives production state, candidate effects and the first stage's camera assessment. This helps avoid treating a transport obstruction as a reason to stop a safe local machine process. Each result records `modalities` and `image_used`; a text-only planning result retains `image_sha256` solely as the supplied observation asset's provenance. The visual stage always consumes its camera image. Omit the flag for the original full-image planning behavior.

## Verification and limitations

```powershell
.venv\Scripts\python.exe -m pytest tests/test_jeff_policy.py -q
.venv-jeff\Scripts\python.exe scripts/jeff_probe.py --checkpoint models/jeff-2b-v1.2 --output output/jeff_factory/jeff_probe_2b_controlled.json
.venv-jeff\Scripts\python.exe scripts/jeff_probe_roi.py --checkpoint models/jeff-2b-v1.2
```

Nine focused contract tests verify candidate identities, invalid distributions and both branches of the two-stage gate, including retention of wait, stage evidence and correct planning image/text modalities. GPU probes preserve raw probabilities and image hashes. Two repetitions per condition gave 4/4 correct route choices for Jeff 2B on the clear/blocked pair. Full-frame blocked SOUTH probability was only 0.5137; fixed corridor closeups improved it to 0.8231, with clear DIRECT 0.9365. ROI warm median was 154.78 ms and nearest-rank p95 156.69 ms for four calls. The separate complex dispatch selected the urgent available printer with probability 0.9042. These are narrow functional probes, not a general visual accuracy benchmark. The smaller 0.8B model failed the blocked route test; its original evidence remains saved.

The actual integrated corridor camera is a fixed 384x128 Genesis render; its blocked observation produced SOUTH probability 0.7395 in the first integrated decision. Integrated decisions are recorded under `output/jeff_factory/jeff/result.json`; stage latencies include preprocessing/forward inference and CUDA synchronization, but exclude model startup. Conventional simulation, legal-action construction, navigation control and collision checks remain code. Global dispatch choices and red-obstacle perception come from Jeff inference.

The upstream README and v1.2 model card explicitly caution **English and text only**. Although the published checkpoint contains a vision tower and the official runtime accepts image tensors, image reliability must be assessed for the actual observation/task. This implementation does not erase that caveat. v1.3 is adapter-first; upstream recommends v1.2 for zero-shot use without adapters.

## Licenses

Jeff code is MIT, retaining the upstream AutoJev copyright notice in `vendor/jeff/LICENSE`. Published base weights are Apache 2.0; retain the downloaded checkpoint `LICENSE` and `NOTICE`. No domain adapters are used, so adapter-specific license permissions are not implied. ViNT/NoMaD and diffusion-policy retain their own upstream license notices; navigation source/checkpoint provenance is documented by their setup and worker files. Do not redistribute checkpoint files as part of the source archive.

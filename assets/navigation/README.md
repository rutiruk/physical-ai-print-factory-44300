# Official navigation policies

Run `powershell -File scripts/setup_navigation.ps1` from the repository root, after creating `.venv`. The script creates `.venv-nav` with `--system-site-packages`. This exposes the base Python installation's **global** packages; it does not inherit packages installed only inside `.venv`. Matching global packages are reused read-only. If torch/torchvision are missing or differ, setup installs the explicit official CUDA 12.8 wheels `torch==2.8.0+cu128` and `torchvision==0.23.0+cu128` into `.venv-nav` only. It checks both imported versions and torch's compiled CUDA version before continuing. These checks do not allocate GPU memory.

Setup pins NumPy 2.1.2, Pillow 11.3.0, PyYAML 6.0.1, and pytest 8.4.1, plus the navigation dependencies in `requirements-navigation.txt`. Missing or mismatched dependencies install locally in `.venv-nav`; setup never runs pip through `.venv` or the global interpreter and does not change their packages. Recorded probes used Python 3.10 and these torch/torchvision/NumPy/Pillow/PyYAML versions. `assets/navigation/requirements-navigation-lock.txt` records the extra packages installed locally on the original machine; it is not a complete fresh-machine dependency list.

The full ViNT checkpoint contains a serialized module/optimizer and needs `warmup-scheduler` to unpickle; only trusted official checkpoints are loaded.

## Provenance

- Official source: https://github.com/robodhruv/visualnav-transformer at `dca79815b704e5aa9c6bdc3082351f9e3b2848c2`.
- Official diffusion architecture dependency: https://github.com/real-stanford/diffusion_policy at `5ba07ac6661db573af695b419a7947ecb704690f`.
- Authors' checkpoints linked from repository README: https://drive.google.com/drive/folders/1a9yWR2iooXFAqjQHetz263--4_2FFggg .
- `vint.pth`: Drive ID `1ckrceGb5m_uUtq3pD8KHwnqtJgPl6kF5`, SHA256 `155fd72de2e98ae0e2fef9404072e1aefa79dae5f7f2411d4bcf7e384b83aa1f`, 29,662,397 parameters.
- `nomad.pth`: Drive ID `1YJhkkMJAYOiKNyCaelbS_alpUpAJsOUb`, SHA256 `70f79b8262527e20e56ced64a3e3d7ef91855bc9e7c3fa348d78edcb83c6a333`, 19,049,675 parameters.

Both architectures are instantiated from official code and loaded with `strict=True`; missing or unexpected keys fail. No training, fine tuning, newly collected training dataset, random weights, synthetic waypoint substitute, A*, or goal-coordinate planner is used by this adapter. ViNT is the deterministic transformer regression model; NoMaD is the separate goal-conditioned diffusion policy using a ViNT vision encoder, ten official DDPM denoising steps and the official training delta ranges. NoMaD's Gaussian starting sample is its intended inference algorithm, not random model weights. `seed` permits reproducible sampling.

## Process contract

Start `.venv-nav/Scripts/python.exe scripts/navigation_worker.py --device cuda:1`. The process emits one JSON line `{"ready":true,"models":{...},"device":"cuda:1"}` after both models load. Standard output contains JSON only; errors/warnings from dependencies use standard error. Send one line per inference request:

```json
{"id":1,"model":"vint","observation_paths":["old.png","latest.png"],"goal_path":"goal.png","max_v":0.2,"frame_rate":4,"seed":0}
```

`model` is `vint` or `nomad`. Image paths are local RGB files, with observation history oldest to newest. ViNT uses six frames, NoMaD four; excess history is trimmed and insufficient history is padded by repeating the oldest available frame. This initialization padding must not be described as observed motion. Image preprocessing reproduces official inference: RGB, PIL resize (ViNT 85x64, NoMaD 96x96), ImageNet normalization, no center crop. The goal must be a matching forward-view RGB image captured from the desired position and orientation; overhead scheduler images are not valid substitute goals.

Responses include `id`, `model`, `waypoints`, `normalized_waypoints`, `distance`, `latency_ms`, `device`, checkpoint SHA256, and strict-load metadata. ViNT supplies five XY positions; NoMaD supplies eight. XY positions are cumulative relative to the current robot frame: X forward, Y left. `waypoints` are meters, `normalized_waypoints` are model output units. As in the official `deployment/src/navigate.py`, metric scale is `max_v/frame_rate` (default 0.05m/unit from official robot config). The adapter does not reinterpret normalized values as exact physical distances. `distance` is learned temporal distance, not meters or a reliable arrival threshold in a new simulator. Upstream deployment uses waypoint index 2 for local PD control. Safety clipping belongs in the downstream controller, and must not replace the direction from the learned waypoint with a geometric goal direction.

NoMaD goal masking is disabled (mask=0), providing the goal-conditioned navigation mode. It samples one trajectory per request, with ten denoising steps. Errors are JSON `{"error":"Type: message","id":...}`. Load failures terminate before the ready line.

## Verification and limits

Run `.venv-nav/Scripts/python.exe -m pytest tests/test_navigation_policy.py -q`. Run an actual GPU probe with `.venv-nav/Scripts/python.exe scripts/navigation_probe.py --observation path/to/forward.png --goal path/to/goal.png`. The probe warms up each model, records a second real inference, validates finite outputs and horizon lengths, and saves `output/jeff_factory/navigation_probe.json`.

The first recorded GPU probe uses existing printing overhead images strictly to verify loading and execution; it does not establish successful navigation. The result showed NVIDIA RTX A4000 GPU 1 inference at about 175ms ViNT / 452ms NoMaD. Zero-shot transfer to the synthetic factory, obstacle avoidance, docking, and closed-loop goal completion must be measured separately on robot forward views. These public visual-navigation policies do not predict manipulator joint actions or operate the printing machines.

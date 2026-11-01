param(
    [string]$BasePython = '.venv\Scripts\python.exe',
    [string]$Python312 = ''
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:UV_LINK_MODE = 'copy'
$env:HF_HUB_DISABLE_XET = '1'

function Assert-NativeSuccess([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw $Message }
}

# The simulator environment is a prerequisite, never an installation target.
if (!(Test-Path -LiteralPath $BasePython)) {
    throw 'Missing base Genesis environment. Create .venv and install CUDA torch 2.8/cu128 plus requirements.txt first (see docs/superpowers/README_JEFF_RUNTIME.md). setup-printing.ps1 prepares the separate older policy environment only.'
}
& $BasePython -c "import importlib.util; assert importlib.util.find_spec('genesis'), 'Install requirements.txt in base .venv first'"
Assert-NativeSuccess 'Base Genesis dependency check failed; this setup does not modify .venv.'
if (!(Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv is required on PATH. Install uv separately, then rerun; base .venv will not be modified.'
}
if (!(Get-Command git -ErrorAction SilentlyContinue)) { throw 'git is required on PATH.' }

$JeffCommit = '3720e7c66d73b79a6e90189f3d5b0d6ecf03ddc0'
if (!(Test-Path -LiteralPath 'vendor\jeff')) {
    New-Item -ItemType Directory -Force vendor | Out-Null
    & git clone https://github.com/firelex/jeff.git vendor/jeff
    Assert-NativeSuccess 'Official Jeff clone failed.'
    & git -C vendor/jeff checkout --detach $JeffCommit
    Assert-NativeSuccess 'Pinned Jeff checkout failed.'
}
$ActualCommit = & git -C vendor/jeff rev-parse HEAD
Assert-NativeSuccess 'Cannot verify vendor/jeff checkout; preserve its .git provenance.'
if ($ActualCommit.Trim() -ne $JeffCommit) {
    throw "vendor/jeff is not at required commit $JeffCommit. Existing checkout is preserved; resolve it explicitly before rerunning."
}

if (!$Python312) {
    $ManagedPython = '.runtime\python\cpython-3.12.11-windows-x86_64-none\python.exe'
    if (!(Test-Path -LiteralPath $ManagedPython)) {
        & uv python install 3.12.11 --install-dir .runtime/python
        Assert-NativeSuccess 'Local Python 3.12.11 download failed.'
    }
    $Python312 = $ManagedPython
}
& $Python312 -c "import sys; assert sys.version_info[:2] == (3,12), 'Jeff requires Python 3.12'"
Assert-NativeSuccess 'Python 3.12 interpreter check failed.'
if (!(Test-Path -LiteralPath '.venv-jeff\Scripts\python.exe')) {
    & uv venv .venv-jeff --python $Python312
    Assert-NativeSuccess 'Isolated Jeff environment creation failed.'
}
$JeffPython = Join-Path $PSScriptRoot '.venv-jeff\Scripts\python.exe'
& $JeffPython -c "import sys; assert sys.version_info[:2] == (3,12), 'Existing .venv-jeff must use Python 3.12'"
Assert-NativeSuccess 'Existing Jeff interpreter check failed.'
& uv pip install --python $JeffPython --index-strategy unsafe-best-match --extra-index-url https://download.pytorch.org/whl/cu128 -r requirements-jeff.txt
Assert-NativeSuccess 'Pinned isolated Jeff dependency install failed.'
& $JeffPython -c "import torch, torchvision, transformers; assert torch.__version__ == '2.8.0+cu128'; assert torchvision.__version__ == '0.23.0+cu128'; assert transformers.__version__ == '5.17.0'; assert torch.cuda.device_count() >= 2, 'Runtime uses GPU1; two CUDA GPUs required'"
Assert-NativeSuccess 'Jeff CUDA/runtime verification failed.'
& $JeffPython scripts/setup_jeff.py --model-id jeff-legacy/Jeff-Qwen3.5-2B --revision d2ffa3a22f3dea8cfdd67bac595d4e8ad3681b2e --target models/jeff-2b-v1.2
Assert-NativeSuccess 'Official pinned Jeff checkpoint download failed.'
$ExpectedCheckpointHashes = @{
    'model.safetensors' = 'ccb083d62bfd84e32b9013d40f206200df509d55727c8e1e33144b01c3759b2c'
    'readout.safetensors' = '4387eddad3d463c808ff89a44908255fab1134f818d86ec82eaf85f90762f939'
}
foreach ($CheckpointName in $ExpectedCheckpointHashes.Keys) {
    $CheckpointPath = Join-Path 'models\jeff-2b-v1.2' $CheckpointName
    if ((Get-FileHash -LiteralPath $CheckpointPath -Algorithm SHA256).Hash.ToLower() -ne $ExpectedCheckpointHashes[$CheckpointName]) {
        throw "Jeff checkpoint SHA256 mismatch: $CheckpointPath"
    }
}

# Navigation extras install into .venv-nav; base torch is inherited read-only.
& (Join-Path $PSScriptRoot 'scripts\setup_navigation.ps1') -BasePython $BasePython
Write-Output 'Ready: .venv-jeff\Scripts\python.exe scripts/jeff_worker.py --checkpoint models/jeff-2b-v1.2 --device cuda:1'

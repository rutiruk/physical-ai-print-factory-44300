param([string]$BasePython = '.venv\Scripts\python.exe')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
# --system-site-packages exposes GLOBAL packages, not BasePython venv packages.
# Matching global packages are reused read-only; replacements stay in .venv-nav.
if (!(Test-Path '.venv-nav\Scripts\python.exe')) {
    & $BasePython -m venv --system-site-packages .venv-nav
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
}
$NavPython = Join-Path (Get-Location) '.venv-nav\Scripts\python.exe'
# Bootstrap core pins before a dependency can select a newer NumPy.
& $NavPython -m pip install numpy==2.1.2 Pillow==11.3.0 PyYAML==6.0.1 pytest==8.4.1
if ($LASTEXITCODE -ne 0) { throw 'navigation core dependency installation failed' }
$TorchVersionProbe = @'
import sys
try:
    import torch
    import torchvision
    valid = (torch.__version__ == "2.8.0+cu128"
             and torchvision.__version__ == "0.23.0+cu128"
             and torch.version.cuda == "12.8")
except Exception:
    valid = False
sys.exit(0 if valid else 1)
'@
# Import/version checks do not allocate GPU memory or load a model.
& $NavPython -c $TorchVersionProbe 2>$null
if ($LASTEXITCODE -ne 0) {
    & $NavPython -m pip install --index-url https://download.pytorch.org/whl/cu128 torch==2.8.0+cu128 torchvision==0.23.0+cu128 numpy==2.1.2 Pillow==11.3.0
    if ($LASTEXITCODE -ne 0) { throw 'navigation CUDA wheel installation failed' }
}
& $NavPython -c $TorchVersionProbe
if ($LASTEXITCODE -ne 0) { throw 'navigation requires torch 2.8.0+cu128 and torchvision 0.23.0+cu128' }
& $NavPython -m pip install -r requirements-navigation.txt
if ($LASTEXITCODE -ne 0) { throw 'navigation dependency installation failed' }
if (!(Test-Path 'vendor\visualnav-transformer')) {
    git clone https://github.com/robodhruv/visualnav-transformer.git vendor/visualnav-transformer
    git -C vendor/visualnav-transformer checkout dca79815b704e5aa9c6bdc3082351f9e3b2848c2
}
if (!(Test-Path 'vendor\diffusion_policy')) {
    git clone https://github.com/real-stanford/diffusion_policy.git vendor/diffusion_policy
    git -C vendor/diffusion_policy checkout 5ba07ac6661db573af695b419a7947ecb704690f
}
New-Item -ItemType Directory -Force assets/navigation | Out-Null
$Checkpoints = @(
    @{Name='vint'; Id='1ckrceGb5m_uUtq3pD8KHwnqtJgPl6kF5'; Hash='155fd72de2e98ae0e2fef9404072e1aefa79dae5f7f2411d4bcf7e384b83aa1f'},
    @{Name='nomad'; Id='1YJhkkMJAYOiKNyCaelbS_alpUpAJsOUb'; Hash='70f79b8262527e20e56ced64a3e3d7ef91855bc9e7c3fa348d78edcb83c6a333'}
)
foreach ($Checkpoint in $Checkpoints) {
    $CheckpointPath = "assets/navigation/$($Checkpoint.Name).pth"
    if (!(Test-Path $CheckpointPath)) {
        & $NavPython -m gdown $Checkpoint.Id -O $CheckpointPath
        if ($LASTEXITCODE -ne 0) { throw 'checkpoint download failed' }
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $CheckpointPath).Hash.ToLower() -ne $Checkpoint.Hash) {
        throw "Checkpoint SHA256 mismatch: $CheckpointPath"
    }
}
& $NavPython -m pytest tests/test_navigation_policy.py -q
if ($LASTEXITCODE -ne 0) { throw 'navigation tests failed' }
Write-Output 'Ready: .venv-nav\Scripts\python.exe scripts/navigation_worker.py --device cuda:1'

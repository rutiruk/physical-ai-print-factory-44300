param([double]$MaxSeconds=360)
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
$env:PYTHONUTF8='1'
& '.venv\Scripts\python.exe' -u scripts/mechanical_factory_v2.py --seconds $MaxSeconds
if ($LASTEXITCODE -ne 0) { throw 'V2 experiment failed; inspect output/v2/latest_run.json and its result.json.' }
$v2Run = Get-Content -LiteralPath 'output/v2/latest_run.json' -Raw | ConvertFrom-Json
if (-not $v2Run.success) { throw "V2 did not complete successfully: $($v2Run.status). Inspect $($v2Run.folder)." }
& '.venv\Scripts\python.exe' scripts/compose_v2_video.py $v2Run.folder --workers 4
if ($LASTEXITCODE -ne 0) { throw 'V2 video composition failed.' }
& '.venv\Scripts\python.exe' scripts/audit_v2_video.py $v2Run.folder
if ($LASTEXITCODE -ne 0) { throw 'V2 video audit failed.' }

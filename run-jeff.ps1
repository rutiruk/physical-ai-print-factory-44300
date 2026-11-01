param(
    [ValidateSet('jeff','rules')][string]$Policy='jeff',
    [double]$MaxSeconds=1200,
    [ValidateSet('single','multi')][string]$Scenario='single'
)
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
$env:PYTHONUTF8='1'
& '.venv\Scripts\python.exe' scripts/jeff_factory_demo.py --policy $Policy --scenario $Scenario --max-seconds $MaxSeconds
if ($LASTEXITCODE -ne 0) { throw 'Factory run failed; inspect output/jeff_factory and the terminal log.' }

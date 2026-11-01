param(
    [ValidateSet('jeff','rules')][string]$Policy='jeff',
    [double]$MaxSeconds=1200
)
$ErrorActionPreference='Stop'
& (Join-Path $PSScriptRoot 'run-jeff.ps1') -Policy $Policy -MaxSeconds $MaxSeconds

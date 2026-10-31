$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Repo
if (-not (Test-Path '.\tools\studio_candidate.py')) {
    throw 'Run this script from the full CutSceneAI repository (V9 development branch).'
}
if (-not (Test-Path '.\apps\studio-web\index.html')) {
    throw 'UI files are missing; extract the integration ZIP into the repository root.'
}
Write-Host 'CutSceneAI Studio local UI: http://127.0.0.1:8765'
python .\tools\studio_local_bridge.py

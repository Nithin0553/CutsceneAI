$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Repo

$Python = Join-Path $Repo '.venv-studio\Scripts\python.exe'
if (-not (Test-Path $Python -PathType Leaf)) {
    throw 'Studio Python environment is missing. First run: .\tools\install_studio.ps1'
}
if (-not (Test-Path '.\tools\check_studio_setup.py')) {
    throw 'Studio setup checker is missing. Use the full CutSceneAI checkout.'
}
& $Python '.\tools\check_studio_setup.py' --strict
if ($LASTEXITCODE -ne 0) {
    throw 'Studio setup checks failed. Rerun .\tools\install_studio.ps1 to repair the local environment.'
}

Write-Host 'CutSceneAI Studio local UI: http://127.0.0.1:8765'
Write-Host 'Native Unity and Unreal companions are checked separately after launch.'
& $Python '.\tools\studio_local_bridge.py'
if ($LASTEXITCODE -ne 0) {
    throw "Studio server exited with status $LASTEXITCODE."
}

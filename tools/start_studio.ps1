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
# The Studio host can rotate itself on safe Python changes. Only this Python
# process restarts; Unity and Unreal Editor continue running and reconnect via
# their existing project-bound heartbeats and durable local file queues.
while ($true) {
    & $Python '.\tools\studio_local_bridge.py' --watch
    $HostExit = $LASTEXITCODE
    if ($HostExit -eq 75) {
        Write-Host 'Studio localhost code refreshed. Unity and Unreal remain open; reconnecting automatically.'
        continue
    }
    if ($HostExit -ne 0) {
        throw "Studio server exited with status $HostExit. Engine editors were not restarted."
    }
    break
}

param(
    [string]$Python = 'python',
    [switch]$SkipStartupSmoke
)
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvPython = Join-Path $Repo '.venv-studio\Scripts\python.exe'

# Explicit user invocation: install only the isolated Studio Python environment.
# Never start Unity, Unreal, a native transfer or an external AI provider.
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    Write-Host 'Installing the isolated CutSceneAI Studio environment...'
    & (Join-Path $PSScriptRoot 'install_studio.ps1') -Python $Python
    if ($LASTEXITCODE -ne 0) { throw 'Studio dependency installation failed.' }
}

& $VenvPython (Join-Path $PSScriptRoot 'check_studio_setup.py') --repo $Repo --strict
if ($LASTEXITCODE -ne 0) {
    throw 'Studio preflight failed. Run .\tools\install_studio.ps1 to repair dependencies.'
}

if (-not $SkipStartupSmoke) {
    Write-Host 'Smoke testing the real localhost Studio UI in a temporary, isolated workspace...'
    & $VenvPython (Join-Path $PSScriptRoot 'studio_startup_smoke.py') --repo $Repo
    if ($LASTEXITCODE -ne 0) {
        throw 'Studio localhost startup smoke failed. No native transfer was started.'
    }
}

Write-Host 'Pre-engine Studio launch checks passed.'
Write-Host 'Open http://127.0.0.1:8765 in your browser after the server starts.'
Write-Host 'Do not begin a source transfer until both engine companions are connected and'
Write-Host 'the exact source/project/level evidence and permissions are reviewed.'
& (Join-Path $PSScriptRoot 'start_studio.ps1')
if ($LASTEXITCODE -ne 0) {
    throw "Studio local launcher exited with code $LASTEXITCODE."
}

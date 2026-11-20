param(
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Repo

# Fail before creating an incomplete environment. Avoid modifying Unity,
# Unreal or any scene/asset. This installer touches only .venv-studio.
& $Python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
if ($LASTEXITCODE -ne 0) {
    throw 'Python 3.11+ is required. Install a supported Python and rerun with -Python <executable>.'
}
$Venv = Join-Path $Repo '.venv-studio'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path $VenvPython -PathType Leaf)) {
    & $Python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated Studio environment.' }
}
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Could not install Studio pip tooling.' }
& $VenvPython -m pip install -e "${Repo}[agents]"
if ($LASTEXITCODE -ne 0) { throw 'Studio Python dependencies failed to install.' }
& $VenvPython '.\tools\check_studio_setup.py' --strict
if ($LASTEXITCODE -ne 0) { throw 'Studio setup diagnostic failed after installation.' }
Write-Host 'Local Python prerequisites installed and verified.'
Write-Host 'Start Studio with: .\tools\start_studio.ps1'
Write-Host 'Unity and Unreal companion setup remains an explicit in-editor action.'

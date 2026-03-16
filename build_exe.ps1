$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$specFile = Join-Path $projectRoot "CrackWidthInspector.spec"

if (-not (Test-Path $pythonExe)) {
    throw "Virtual environment not found. Expected: $pythonExe"
}

if (-not (Test-Path $specFile)) {
    throw "Spec file not found. Expected: $specFile"
}

& $pythonExe -m PyInstaller --noconfirm --clean $specFile

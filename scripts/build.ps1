$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $projectPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $projectPython)) {
        throw 'Create .venv with Python 3.12 x64, then install requirements.lock.txt and this project in editable mode.'
    }
    & $projectPython -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Offline checks failed.' }
    $buildOutput = Join-Path $projectRoot ('work/portable-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    & $projectPython -m PyInstaller --noconfirm --distpath $buildOutput lasermaker-agent.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
    & $projectPython scripts/release.py --runtime (Join-Path $buildOutput 'lasermaker-agent')
    if ($LASTEXITCODE -ne 0) { throw 'Release assembly failed.' }
} finally { Pop-Location }

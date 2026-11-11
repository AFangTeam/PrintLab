$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Python = Join-Path $Root 'Runtime/venv/Scripts/python.exe'
if (!(Test-Path $Python)) { throw 'Run scripts/setup.ps1 first.' }
$env:PYTHONPATH = Join-Path $Root 'Harness'
& $Python -X utf8 -m printlab.cli @args
exit $LASTEXITCODE

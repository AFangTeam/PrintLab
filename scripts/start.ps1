$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$Root = Split-Path $PSScriptRoot -Parent
$Python = Join-Path $Root 'Runtime/venv/Scripts/python.exe'
if (!(Test-Path $Python) -or !(Test-Path (Join-Path $Root 'Harness/studio/dist/index.html'))) {
    throw 'Run scripts/setup.ps1 first.'
}
$env:PRINTLAB_ROOT = $Root
& $Python -X utf8 (Join-Path $Root 'Harness/serve.py') studio @args
exit $LASTEXITCODE

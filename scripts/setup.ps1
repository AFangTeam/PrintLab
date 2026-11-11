$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$Setup = Join-Path $PSScriptRoot 'setup.py'
if ($env:PRINTLAB_PYTHON) {
    & $env:PRINTLAB_PYTHON -X utf8 $Setup
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -X utf8 $Setup
} else {
    & python -X utf8 $Setup
}
exit $LASTEXITCODE

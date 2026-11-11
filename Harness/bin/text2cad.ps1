$ErrorActionPreference = 'Stop'
$env:CADGEN_TELEMETRY = '0'
$env:DO_NOT_TRACK = '1'
$cadCommand = $env:PRINTLAB_CAD_COMMAND
if (-not $cadCommand) {
    foreach ($candidate in @('cad', 'cadgen')) {
        $installed = Get-Command $candidate -CommandType Application,ExternalScript -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($installed) {
            $cadCommand = $installed.Source
            break
        }
    }
}
if (-not $cadCommand) {
    Write-Error 'Install Text-to-CAD independently using docs/CAD_SETUP.md before running this command.'
    exit 1
}
& $cadCommand @args
if ($null -ne $LASTEXITCODE) {
    exit $LASTEXITCODE
}

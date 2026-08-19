$ErrorActionPreference = 'Stop'

# Use the official loader so Vivado initializes its complete runtime.
$vivado = 'G:\Xilinx\Vivado\2024.1\bin\vivado.bat'
$root = $PSScriptRoot
$reportDirectory = Join-Path $root 'vivado_tile_reports'
$tcl = Join-Path $root 'vivado_tile_synth.tcl'
$log = Join-Path $reportDirectory 'vivado_run.log'
$sourceFiles = @(
    'digital_lif_engine.sv',
    'digital_snn_tile_4x2x2.sv',
    'vivado_tile_synth.tcl',
    'run_vivado_tile_synth.ps1'
) | ForEach-Object { Join-Path $root $_ }
$requiredReports = @(
    'signoff_summary.txt',
    'timing_impl.rpt',
    'utilization_impl.rpt',
    'route_status_impl.rpt',
    'drc_impl.rpt',
    'methodology_impl.rpt',
    'power_impl.rpt',
    'digital_snn_tile_4x2x2_impl.dcp',
    'vivado_run.log'
)

if (-not (Test-Path -LiteralPath $vivado -PathType Leaf)) {
    throw "Vivado loader does not exist: $vivado"
}
foreach ($sourceFile in $sourceFiles) {
    if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
        throw "Tile signoff source does not exist: $sourceFile"
    }
}

# Only clean the fixed report directory owned by this runner.
$resolvedRoot = [IO.Path]::GetFullPath($root).TrimEnd([IO.Path]::DirectorySeparatorChar)
$resolvedReportDirectory = [IO.Path]::GetFullPath($reportDirectory)
$expectedPrefix = $resolvedRoot + [IO.Path]::DirectorySeparatorChar
if (-not $resolvedReportDirectory.StartsWith($expectedPrefix, [StringComparison]::OrdinalIgnoreCase) -or
    [IO.Path]::GetFileName($resolvedReportDirectory) -ne 'vivado_tile_reports') {
    throw "Refusing to clean an unexpected report directory: $resolvedReportDirectory"
}
if (Test-Path -LiteralPath $resolvedReportDirectory) {
    Remove-Item -LiteralPath $resolvedReportDirectory -Recurse -Force
}
New-Item -ItemType Directory -Path $resolvedReportDirectory | Out-Null

$newestSourceTimestamp = ($sourceFiles | Get-Item |
    Measure-Object -Property LastWriteTimeUtc -Maximum).Maximum
Write-Host 'ENeuron Tile: launching Vivado 2024.1 OOC implementation'
Write-Host "Newest signoff source: $($newestSourceTimestamp.ToString('o'))"

$commandLine = '"' + $vivado + '" -mode batch -nolog -nojournal -notrace -source "' + $tcl + '"'
Push-Location $root
try {
    & $env:ComSpec /d /s /c $commandLine 2>&1 | Tee-Object -FilePath $log
    $vivadoExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($vivadoExitCode -ne 0) {
    throw "Vivado Tile OOC implementation failed with exit code $vivadoExitCode"
}

$missingReports = @()
$staleReports = @()
foreach ($reportName in $requiredReports) {
    $reportPath = Join-Path $resolvedReportDirectory $reportName
    if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) {
        $missingReports += $reportPath
        continue
    }
    if ((Get-Item -LiteralPath $reportPath).LastWriteTimeUtc -le $newestSourceTimestamp) {
        $staleReports += $reportPath
    }
}
if ($missingReports.Count -ne 0) {
    throw "Missing Tile signoff reports: $($missingReports -join ', ')"
}
if ($staleReports.Count -ne 0) {
    throw "Tile reports are not newer than all signoff sources: $($staleReports -join ', ')"
}

$summaryPath = Join-Path $resolvedReportDirectory 'signoff_summary.txt'
$summary = Get-Content -LiteralPath $summaryPath -Raw
if ($summary -notmatch '(?m)^RESULT=PASS\r?$') {
    throw "Tile signoff summary does not contain RESULT=PASS: $summaryPath"
}

Write-Host 'ENeuron Tile: OOC implementation and all gates passed'
Get-Content -LiteralPath $summaryPath

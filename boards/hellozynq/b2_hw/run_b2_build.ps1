param(
    [string]$VivadoRoot = $env:VIVADO_ROOT
)

$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot
$repoRoot = (& git -C $scriptDir rev-parse --show-toplevel).Trim()
$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
$gitStatus = (& git -C $repoRoot status --porcelain=v1) -join "`n"
$outDir = Join-Path $scriptDir 'build'
$logPath = Join-Path $outDir 'vivado_run.log'
$summaryPath = Join-Path $outDir 'signoff_summary.txt'
$bitstreamPath = Join-Path $outDir 'hello_zynq_b2.bit'
$xsaPath = Join-Path $outDir 'hello_zynq_b2.xsa'
$manifestPath = Join-Path $outDir 'build_manifest.json'

function Assert-B2TimingGreen {
    param(
        [Parameter(Mandatory = $true)][string]$TimingReportPath,
        [Parameter(Mandatory = $true)][string]$RouteReportPath,
        [Parameter(Mandatory = $true)][string]$DrcReportPath
    )

    foreach ($path in @($TimingReportPath, $RouteReportPath, $DrcReportPath)) {
        if (-not (Test-Path -LiteralPath $path)) { throw "Missing B2 signoff report: $path" }
    }

    $timingText = Get-Content -LiteralPath $TimingReportPath -Raw
    $timingRow = [regex]::Match(
        $timingText,
        '(?m)^\s*([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+\d+\s+\d+\s+([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+\d+\s+\d+'
    )
    if (-not $timingRow.Success) { throw 'Unable to parse Design Timing Summary from timing_impl.rpt' }

    $culture = [Globalization.CultureInfo]::InvariantCulture
    $wns = [double]::Parse($timingRow.Groups[1].Value, $culture)
    $tns = [double]::Parse($timingRow.Groups[2].Value, $culture)
    $whs = [double]::Parse($timingRow.Groups[3].Value, $culture)
    $ths = [double]::Parse($timingRow.Groups[4].Value, $culture)
    if (($wns -lt 0) -or ($tns -ne 0) -or ($whs -lt 0) -or ($ths -ne 0)) {
        throw ("B2 timing gate failed: WNS={0} TNS={1} WHS={2} THS={3}" -f $wns, $tns, $whs, $ths)
    }

    $routeText = Get-Content -LiteralPath $RouteReportPath -Raw
    $routeMatch = [regex]::Match($routeText, '(?m)# of nets with routing errors.*?:\s*(\d+)')
    if (-not $routeMatch.Success) { throw 'Unable to parse routing error count from route_status_impl.rpt' }
    $routeErrors = [int]$routeMatch.Groups[1].Value
    if ($routeErrors -ne 0) { throw "B2 route gate failed: routing errors=$routeErrors" }

    $drcText = Get-Content -LiteralPath $DrcReportPath -Raw
    $drcHardErrors = 0
    foreach ($match in [regex]::Matches($drcText, '(?im)^\|[^|\r\n]*\|\s*(Error|Critical Warning)\s*\|[^|\r\n]*\|\s*(\d+)\s*\|')) {
        $drcHardErrors += [int]$match.Groups[2].Value
    }
    if ($drcHardErrors -ne 0) { throw "B2 DRC gate failed: error/critical-warning violations=$drcHardErrors" }

    return [ordered]@{
        WNS = $wns
        TNS = $tns
        WHS = $whs
        THS = $ths
        route_errors = $routeErrors
        drc_hard_errors = $drcHardErrors
    }
}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$vivadoBat = if ($VivadoRoot) { Join-Path $VivadoRoot 'bin\vivado.bat' } else { 'G:\Xilinx\Vivado\2024.1\bin\vivado.bat' }
if (-not (Test-Path -LiteralPath $vivadoBat)) { throw "Vivado not found: $vivadoBat" }

& $vivadoBat -mode batch -nolog -nojournal -notrace -source (Join-Path $scriptDir 'build_b2.tcl') -tclargs $gitHead $outDir 2>&1 | Tee-Object -FilePath $logPath
if ($LASTEXITCODE -ne 0) { throw "Vivado B2 build failed with exit code $LASTEXITCODE" }
foreach ($required in @($summaryPath, $bitstreamPath, $xsaPath)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing B2 artifact: $required" }
}
if (-not (Select-String -LiteralPath $logPath -SimpleMatch 'B2_BUILD_PASS' -Quiet)) { throw 'Vivado log does not contain B2_BUILD_PASS' }

$timingPath = Join-Path $outDir 'timing_impl.rpt'
$routePath = Join-Path $outDir 'route_status_impl.rpt'
$drcPath = Join-Path $outDir 'drc_impl.rpt'
$signoffChecks = Assert-B2TimingGreen -TimingReportPath $timingPath -RouteReportPath $routePath -DrcReportPath $drcPath
Write-Host ("B2_TIMING_PASS WNS={0} TNS={1} WHS={2} THS={3} ROUTE_ERRORS={4} DRC_HARD_ERRORS={5}" -f $signoffChecks.WNS, $signoffChecks.TNS, $signoffChecks.WHS, $signoffChecks.THS, $signoffChecks.route_errors, $signoffChecks.drc_hard_errors)

$sourceFiles = @('axis_stream_probe.v', 'create_b2_bd.tcl', 'build_b2.tcl', 'run_b2_build.ps1')
$sourceHashes = [ordered]@{}
foreach ($name in $sourceFiles) {
    $sourceHashes[$name] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $scriptDir $name)).Hash.ToLowerInvariant()
}
$summary = [ordered]@{}
foreach ($line in Get-Content -LiteralPath $summaryPath) {
    $parts = $line -split '=', 2
    if ($parts.Count -eq 2) { $summary[$parts[0]] = $parts[1] }
}
$summary['B2_TIMING_PASS'] = '1'
$invariantCulture = [Globalization.CultureInfo]::InvariantCulture
$summary['B2_WNS_NS'] = $signoffChecks.WNS.ToString($invariantCulture)
$summary['B2_TNS_NS'] = $signoffChecks.TNS.ToString($invariantCulture)
$summary['B2_WHS_NS'] = $signoffChecks.WHS.ToString($invariantCulture)
$summary['B2_THS_NS'] = $signoffChecks.THS.ToString($invariantCulture)
$summary['B2_ROUTE_ERRORS'] = $signoffChecks.route_errors
$summary['B2_DRC_HARD_ERRORS'] = $signoffChecks.drc_hard_errors
$manifest = [ordered]@{
    schema_version = 1
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
    git_head = $gitHead
    git_worktree_clean = [string]::IsNullOrEmpty($gitStatus)
    vivado = (& $vivadoBat -version 2>&1 | Select-String -Pattern '^vivado ' | Select-Object -First 1).Line.Trim()
    part = 'xc7z020clg484-2'
    top = 'design_1_wrapper'
    source_sha256 = $sourceHashes
    bitstream_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $bitstreamPath).Hash.ToLowerInvariant()
    xsa_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $xsaPath).Hash.ToLowerInvariant()
    reports_sha256 = [ordered]@{
        utilization_impl = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $outDir 'utilization_impl.rpt')).Hash.ToLowerInvariant()
        timing_impl = (Get-FileHash -Algorithm SHA256 -LiteralPath $timingPath).Hash.ToLowerInvariant()
        route_status_impl = (Get-FileHash -Algorithm SHA256 -LiteralPath $routePath).Hash.ToLowerInvariant()
        drc_impl = (Get-FileHash -Algorithm SHA256 -LiteralPath $drcPath).Hash.ToLowerInvariant()
    }
    signoff = $summary
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Host "B2_BUILD_DONE summary=$summaryPath"
Write-Host "B2_BUILD_MANIFEST=$manifestPath"
Write-Host "B2_BITSTREAM_SHA256=$($manifest.bitstream_sha256)"
Write-Host "B2_XSA_SHA256=$($manifest.xsa_sha256)"

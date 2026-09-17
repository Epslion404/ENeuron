param(
    [string]$VivadoRoot = $env:VIVADO_ROOT,
    [ValidateSet('dense', 'lossless_zero_group_skip', 'dense_pl_replay', 'lossless_zero_group_skip_pl_replay', 'dense_pl_distribution_replay', 'lossless_zero_group_skip_pl_distribution_replay')]
    [string]$NpuMode = 'dense',
    [string]$OutDir = ''
)

$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot
$repoRoot = (& git -C $scriptDir rev-parse --show-toplevel).Trim()
$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
$gitStatus = (& git -C $repoRoot status --porcelain=v1) -join "`n"
$outDir = if ($OutDir) { [IO.Path]::GetFullPath($OutDir) } else { Join-Path $scriptDir 'build' }
$logPath = Join-Path $outDir 'vivado_run.log'
$summaryPath = Join-Path $outDir 'signoff_summary.txt'
$bitstreamPath = Join-Path $outDir 'hello_zynq_b2.bit'
$xsaPath = Join-Path $outDir 'hello_zynq_b2.xsa'
$manifestPath = Join-Path $outDir 'build_manifest.json'

function Get-B2SignoffMetrics {
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
    $timingPass = ($wns -ge 0) -and ($tns -eq 0) -and ($whs -ge 0) -and ($ths -eq 0)

    $routeText = Get-Content -LiteralPath $RouteReportPath -Raw
    $routeMatch = [regex]::Match($routeText, '(?m)# of nets with routing errors.*?:\s*(\d+)')
    if (-not $routeMatch.Success) { throw 'Unable to parse routing error count from route_status_impl.rpt' }
    $routeErrors = [int]$routeMatch.Groups[1].Value
    $routePass = $routeErrors -eq 0

    $drcText = Get-Content -LiteralPath $DrcReportPath -Raw
    $drcHardErrors = 0
    foreach ($match in [regex]::Matches($drcText, '(?im)^\|[^|\r\n]*\|\s*(Error|Critical Warning)\s*\|[^|\r\n]*\|\s*(\d+)\s*\|')) {
        $drcHardErrors += [int]$match.Groups[2].Value
    }
    $drcPass = $drcHardErrors -eq 0

    return [ordered]@{
        WNS = $wns
        TNS = $tns
        WHS = $whs
        THS = $ths
        route_errors = $routeErrors
        drc_hard_errors = $drcHardErrors
        timing_pass = $timingPass
        route_pass = $routePass
        drc_pass = $drcPass
        signoff_pass = $timingPass -and $routePass -and $drcPass
    }
}

function Get-FileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $sha = [System.Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $stream.Dispose()
        $sha.Dispose()
    }
}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$vivadoBat = if ($VivadoRoot) { Join-Path $VivadoRoot 'bin\vivado.bat' } else { 'G:\Xilinx\Vivado\2024.1\bin\vivado.bat' }
if (-not (Test-Path -LiteralPath $vivadoBat)) { throw "Vivado not found: $vivadoBat" }

& $vivadoBat -mode batch -nolog -nojournal -notrace -source (Join-Path $scriptDir 'build_b2.tcl') -tclargs $gitHead $outDir $NpuMode 2>&1 | Tee-Object -FilePath $logPath
if ($LASTEXITCODE -ne 0) { throw "Vivado B2 build failed with exit code $LASTEXITCODE" }
foreach ($required in @($summaryPath, $bitstreamPath, $xsaPath)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing B2 artifact: $required" }
}
if (-not (Select-String -LiteralPath $logPath -SimpleMatch 'B2_BUILD_PASS' -Quiet)) { throw 'Vivado log does not contain B2_BUILD_PASS' }

$timingPath = Join-Path $outDir 'timing_impl.rpt'
$routePath = Join-Path $outDir 'route_status_impl.rpt'
$drcPath = Join-Path $outDir 'drc_impl.rpt'
$signoffChecks = Get-B2SignoffMetrics -TimingReportPath $timingPath -RouteReportPath $routePath -DrcReportPath $drcPath

$probeSourceName = 'axis_stream_probe.v'
$sourceFiles = @(
    "boards/hellozynq/b2_hw/$probeSourceName",
    'boards/hellozynq/b2_hw/b2_npu_status_probe.v',
    'boards/hellozynq/b2_hw/b2_npu_axis_top.v',
    'boards/hellozynq/b2_hw/create_b2_bd.tcl',
    'boards/hellozynq/b2_hw/build_b2.tcl',
    'boards/hellozynq/b2_hw/run_b2_build.ps1',
    'b2_npu_packet_adapter.sv',
    'b2_packet_ingress.sv',
    'b2_packet_bram.sv',
    'b2_packet_egress.sv',
    'b3_pl_replay_shim.sv',
    'b3_pl_distribution_replay_shim.sv',
    'npu_zynq7020_t1_wrapper.sv',
    'npu_eneuron_single_clock_skeleton.sv'
)
$sourceHashes = [ordered]@{}
foreach ($relativePath in $sourceFiles) {
    $sourceHashes[$relativePath] = Get-FileSha256 -Path (Join-Path $repoRoot $relativePath)
}
$summary = [ordered]@{}
foreach ($line in Get-Content -LiteralPath $summaryPath) {
    $parts = $line -split '=', 2
    if ($parts.Count -eq 2) { $summary[$parts[0]] = $parts[1] }
}
if ([string]$summary['B2_NPU_MODE'] -ne $NpuMode) {
    throw "B2 NPU mode mismatch: requested=$NpuMode built=$($summary['B2_NPU_MODE'])"
}
$summary['B2_TIMING_PASS'] = if ($signoffChecks.timing_pass) { '1' } else { '0' }
$summary['B2_ROUTE_PASS'] = if ($signoffChecks.route_pass) { '1' } else { '0' }
$summary['B2_DRC_PASS'] = if ($signoffChecks.drc_pass) { '1' } else { '0' }
$summary['B2_SIGNOFF_PASS'] = if ($signoffChecks.signoff_pass) { '1' } else { '0' }
$invariantCulture = [Globalization.CultureInfo]::InvariantCulture
$summary['B2_WNS_NS'] = $signoffChecks.WNS.ToString($invariantCulture)
$summary['B2_TNS_NS'] = $signoffChecks.TNS.ToString($invariantCulture)
$summary['B2_WHS_NS'] = $signoffChecks.WHS.ToString($invariantCulture)
$summary['B2_THS_NS'] = $signoffChecks.THS.ToString($invariantCulture)
$summary['B2_ROUTE_ERRORS'] = $signoffChecks.route_errors
$summary['B2_DRC_HARD_ERRORS'] = $signoffChecks.drc_hard_errors
$summary.GetEnumerator() | ForEach-Object { "{0}={1}" -f $_.Key, $_.Value } |
    Set-Content -LiteralPath $summaryPath -Encoding UTF8
$manifest = [ordered]@{
    schema_version = 1
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
    git_head = $gitHead
    git_worktree_clean = [string]::IsNullOrEmpty($gitStatus)
    vivado = (& $vivadoBat -version 2>&1 | Select-String -Pattern '^vivado ' | Select-Object -First 1).Line.Trim()
    part = 'xc7z020clg484-2'
    top = 'design_1_wrapper'
    npu_mode = $NpuMode
    verilog_defines = @(
        if ($NpuMode -like 'lossless_zero_group_skip*') { 'LOSSLESS_ZERO_GROUP_SKIP'; 'B3_USE_XPM' }
        if ($NpuMode -like '*_pl_replay' -and $NpuMode -notlike '*_pl_distribution_replay') { 'B3_PL_REPLAY_BENCHMARK'; 'B3_PL_REPLAY_WARMUP_SAMPLES=1000'; 'B3_PL_REPLAY_MEASURE_SAMPLES=10000' }
        if ($NpuMode -like '*_pl_distribution_replay') { 'B3_PL_DISTRIBUTION_REPLAY_BENCHMARK'; 'B3_PL_REPLAY_INPUT_SAMPLES=397'; 'B3_PL_REPLAY_WARMUP_SAMPLES=1000'; 'B3_PL_REPLAY_MEASURE_SAMPLES=10000' }
    )
    source_sha256 = $sourceHashes
    bitstream_sha256 = Get-FileSha256 -Path $bitstreamPath
    xsa_sha256 = Get-FileSha256 -Path $xsaPath
    reports_sha256 = [ordered]@{
        utilization_impl = Get-FileSha256 -Path (Join-Path $outDir 'utilization_impl.rpt')
        timing_impl = Get-FileSha256 -Path $timingPath
        route_status_impl = Get-FileSha256 -Path $routePath
        drc_impl = Get-FileSha256 -Path $drcPath
    }
    signoff = $summary
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Host "B2_BUILD_MANIFEST=$manifestPath"
Write-Host "B2_BITSTREAM_SHA256=$($manifest.bitstream_sha256)"
Write-Host "B2_XSA_SHA256=$($manifest.xsa_sha256)"
$dspCountText = [string]$summary['B2_NPU_DSP48E1_COUNT']
$dspExpectedText = [string]$summary['B2_NPU_DSP_EXPECTED']
if ($dspCountText -ne '4' -or $dspExpectedText -ne '4') {
    throw "B2 DSP gate failed: DSP48E1_COUNT=$dspCountText expected=4"
}
if (-not $signoffChecks.signoff_pass) {
    throw ("B2 signoff gate failed: WNS={0} TNS={1} WHS={2} THS={3} route_errors={4} drc_hard_errors={5}" -f $signoffChecks.WNS, $signoffChecks.TNS, $signoffChecks.WHS, $signoffChecks.THS, $signoffChecks.route_errors, $signoffChecks.drc_hard_errors)
}
Write-Host ("B2_TIMING_PASS WNS={0} TNS={1} WHS={2} THS={3} ROUTE_ERRORS={4} DRC_HARD_ERRORS={5}" -f $signoffChecks.WNS, $signoffChecks.TNS, $signoffChecks.WHS, $signoffChecks.THS, $signoffChecks.route_errors, $signoffChecks.drc_hard_errors)
Write-Host "B2_BUILD_DONE summary=$summaryPath"

param(
    [ValidateSet('dense', 'lossless_zero_group_skip')]
    [string]$Mode,
    [Parameter(Mandatory = $true)]
    [string]$HardwareBuildDir,
    [ValidateRange(0, 396)]
    [int]$QatSampleIndex = 201,
    [string]$QatManifest = '',
    [string]$PortName = '',
    [string]$XsctPath = 'G:\Xilinx\Vitis\2024.1\bin\xsct.bat',
    [string]$HwServerPath = 'G:\Xilinx\Vivado\2024.1\bin\hw_server.bat',
    [string]$BuildTag = '',
    [switch]$AllowDirty
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..\..')).Path
$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
$HardwareBuildDir = (Resolve-Path -LiteralPath $HardwareBuildDir).Path
if ([string]::IsNullOrWhiteSpace($QatManifest)) {
    $QatManifest = Join-Path $repoRoot 'tools\repro\b3_qat_model_manifest.json'
} else {
    $QatManifest = (Resolve-Path -LiteralPath $QatManifest).Path
}
if ([string]::IsNullOrWhiteSpace($BuildTag)) {
    $BuildTag = "cp5a_${Mode}_replay"
}
if ($BuildTag -notmatch '^[A-Za-z0-9._-]+$') { throw "Invalid BuildTag: $BuildTag" }

$hardwareManifestPath = Join-Path $HardwareBuildDir 'build_manifest.json'
if (-not (Test-Path -LiteralPath $hardwareManifestPath)) {
    throw "Missing hardware build manifest: $hardwareManifestPath"
}
$hardwareManifest = Get-Content -LiteralPath $hardwareManifestPath -Raw | ConvertFrom-Json
$expectedHardwareMode = "${Mode}_pl_replay"
if ([string]$hardwareManifest.npu_mode -ne $expectedHardwareMode) {
    throw "Replay hardware mode mismatch: expected=$expectedHardwareMode actual=$($hardwareManifest.npu_mode)"
}
$defines = @($hardwareManifest.verilog_defines)
foreach ($required in @(
    'B3_PL_REPLAY_BENCHMARK',
    'B3_PL_REPLAY_WARMUP_SAMPLES=1000',
    'B3_PL_REPLAY_MEASURE_SAMPLES=10000'
)) {
    if ($required -notin $defines) { throw "Replay hardware manifest missing define: $required" }
}
if ([string]$hardwareManifest.signoff.B2_SIGNOFF_PASS -ne '1') {
    throw 'Replay hardware did not pass physical signoff'
}
$hardwareSameHead = [string]$hardwareManifest.git_head -eq $gitHead
$hardwareClean = [bool]$hardwareManifest.git_worktree_clean
if (-not $AllowDirty -and (-not $hardwareClean -or -not $hardwareSameHead)) {
    throw 'Formal replay evidence requires clean signed hardware from the current HEAD'
}

$buildScript = Join-Path $scriptRoot 'run_b2_packet_sw_build.ps1'
& $buildScript -XsctPath $XsctPath -B3Dense -B3QatManifest $QatManifest `
    -B3QatSampleIndex $QatSampleIndex -HardwareBuildDir $HardwareBuildDir -BuildTag $BuildTag
if ($LASTEXITCODE -ne 0) { throw "Replay packet software build failed: $LASTEXITCODE" }

$boardScript = Join-Path $scriptRoot 'run_b2_packet_board.ps1'
$boardParams = @{
    PortName = $PortName
    XsctPath = $XsctPath
    HwServerPath = $HwServerPath
    BuildTag = $BuildTag
    ListenSeconds = 90
}
if ($AllowDirty) { $boardParams.AllowDirty = $true }
& $boardScript @boardParams
if ($LASTEXITCODE -ne 0) { throw "Replay packet board run failed: $LASTEXITCODE" }

$buildRoot = Join-Path $scriptRoot (Join-Path 'build' (Join-Path $gitHead $BuildTag))
$packetManifestPath = Join-Path $buildRoot 'packet_build_manifest.json'
$packetManifest = Get-Content -LiteralPath $packetManifestPath -Raw | ConvertFrom-Json
$runRoot = Get-ChildItem -LiteralPath (Join-Path $buildRoot 'runs') -Directory |
    Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $runRoot) { throw 'Replay packet run directory was not created' }
$packetRunPath = Join-Path $runRoot.FullName 'run_manifest.json'
$packetRun = Get-Content -LiteralPath $packetRunPath -Raw | ConvertFrom-Json
if ([string]$packetRun.status -ne 'PASS') { throw 'Replay packet run did not pass' }

$probeOut = Join-Path $runRoot.FullName 'pl_replay_probe.log'
$probeErr = Join-Path $runRoot.FullName 'pl_replay_probe.err'
$probe = Start-Process -FilePath $XsctPath -ArgumentList @(
    (Join-Path $scriptRoot 'probe_b3_pl_replay_benchmark.tcl')
) -RedirectStandardOutput $probeOut -RedirectStandardError $probeErr -WindowStyle Hidden -PassThru
if (-not $probe.WaitForExit(30000)) {
    $probe.Kill()
    throw 'PL replay probe timed out'
}
$probe.Refresh()
if ([int]$probe.ExitCode -ne 0) { throw "PL replay probe failed: $($probe.ExitCode)" }
$probeText = [string](Get-Content -LiteralPath $probeOut -Raw)
function Get-ProbeU32 {
    param([string]$Key)
    $match = [regex]::Match($probeText, "(?m)^$([regex]::Escape($Key))=(\S+)")
    if (-not $match.Success) { throw "Replay probe missing $Key" }
    return [uint32]$match.Groups[1].Value
}
function Convert-ManifestUInt32 {
    param([object]$Value)
    $text = [string]$Value
    if ($text -match '^0x') { return [Convert]::ToUInt32($text.Substring(2), 16) }
    return [uint32]$Value
}

$statusValue = Get-ProbeU32 'B3_PL_REPLAY_STATUS'
$completed = Get-ProbeU32 'B3_PL_REPLAY_COMPLETED'
$cycles = Get-ProbeU32 'B3_PL_REPLAY_CYCLES'
$executeGroups = Get-ProbeU32 'B3_PL_REPLAY_EXECUTE_GROUPS'
$skipGroups = Get-ProbeU32 'B3_PL_REPLAY_SKIP_GROUPS'
$lastComputeCycles = Get-ProbeU32 'B3_PL_REPLAY_LAST_COMPUTE_CYCLES'
$protocolErrors = Get-ProbeU32 'B3_PL_REPLAY_PROTOCOL_ERRORS'
$totalReplayRuns = 1 + 1000 + 10000
$expectedGroupInstances = [uint64]$totalReplayRuns * 592
$observedGroupInstances = [uint64]$executeGroups + [uint64]$skipGroups
$modeGroupPass = if ($Mode -eq 'dense') {
    $skipGroups -eq 0
} else {
    $skipGroups -gt 0 -and $executeGroups -gt 0
}
$runPass = $statusValue -eq 4 -and $completed -eq 10000 -and $cycles -gt 0 -and
    $lastComputeCycles -gt 0 -and $protocolErrors -eq 0 -and
    $observedGroupInstances -eq $expectedGroupInstances -and $modeGroupPass
$cyclesPerSample = if ($completed -gt 0) { $cycles / [double]$completed } else { 0.0 }
$samplesPerSecond = if ($cycles -gt 0) { 200000000.0 * $completed / $cycles } else { 0.0 }
$formalEvidence = -not $AllowDirty -and $hardwareClean -and $hardwareSameHead -and
    [bool]$packetManifest.git_tracked_worktree_clean

$summary = [ordered]@{
    schema = 'eneuron_b3_cp5a_pl_replay_v1'
    status = if ($runPass) { 'CP5A_BRINGUP_PASS' } else { 'FAIL' }
    mode = $Mode
    scope = 'single_representative_qat_sample_pl_replay'
    formal_evidence = $formalEvidence
    git_head = $gitHead
    target_part = [string]$hardwareManifest.part
    clock_hz = 200000000
    hardware_manifest = $hardwareManifestPath
    hardware_manifest_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $hardwareManifestPath).Hash.ToLowerInvariant()
    packet_manifest = $packetManifestPath
    packet_manifest_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $packetManifestPath).Hash.ToLowerInvariant()
    packet_run = $packetRunPath
    packet_run_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $packetRunPath).Hash.ToLowerInvariant()
    qat_manifest = $QatManifest
    qat_manifest_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $QatManifest).Hash.ToLowerInvariant()
    qat_sample_index = $QatSampleIndex
    sample_id = 0
    warmup_samples = 1000
    measured_samples = $completed
    total_replay_runs = $totalReplayRuns
    expected_group_instances = $expectedGroupInstances
    observed_group_instances = $observedGroupInstances
    measured_cycles = $cycles
    cycles_per_sample = [Math]::Round($cyclesPerSample, 6)
    samples_per_second = [Math]::Round($samplesPerSecond, 3)
    last_compute_cycles = $lastComputeCycles
    execute_groups_total = $executeGroups
    skip_groups_total = $skipGroups
    protocol_error_count = $protocolErrors
    boundary = 'CP5a 单个代表性 QAT 样本的纯 PL replay bring-up；不覆盖 397 样本分布，不关闭正式 CP5/B3-SPEED-GATE。'
}
$qat = Get-Content -LiteralPath $QatManifest -Raw | ConvertFrom-Json
$summary.sample_id = Convert-ManifestUInt32 $qat.samples[$QatSampleIndex].sample_id
$summaryPath = Join-Path $runRoot.FullName 'b3_pl_replay_benchmark.json'
$summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $summaryPath -Encoding utf8
Write-Output "B3_PL_REPLAY_STATUS=$($summary.status)"
Write-Output "B3_PL_REPLAY_SUMMARY=$summaryPath"
if (-not $runPass) { exit 1 }

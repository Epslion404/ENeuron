param(
    [ValidateSet('dense', 'lossless_zero_group_skip')]
    [string]$Mode,
    [Parameter(Mandatory = $true)]
    [string]$HardwareBuildDir,
    [ValidateRange(0, 396)]
    [int]$QatSampleIndex = 201,
    [string]$QatManifest = '',
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
$hardwareClean = [bool]$hardwareManifest.git_worktree_clean
$hardwareSourceClosurePass = $true
$hardwareSourceMismatches = @()
foreach ($entry in $hardwareManifest.source_sha256.PSObject.Properties) {
    $sourcePath = Join-Path $repoRoot ([string]$entry.Name)
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        $hardwareSourceClosurePass = $false
        $hardwareSourceMismatches += "missing:$($entry.Name)"
        continue
    }
    $actualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourcePath).Hash.ToLowerInvariant()
    if ($actualSha -ne ([string]$entry.Value).ToLowerInvariant()) {
        $hardwareSourceClosurePass = $false
        $hardwareSourceMismatches += "sha:$($entry.Name)"
    }
}
if (-not $AllowDirty -and (-not $hardwareClean -or -not $hardwareSourceClosurePass)) {
    throw "Hardware source closure mismatch: $($hardwareSourceMismatches -join ',')"
}

$buildScript = Join-Path $scriptRoot 'run_b2_packet_sw_build.ps1'
& $buildScript -XsctPath $XsctPath -B3Dense -B3QatManifest $QatManifest `
    -B3QatSampleIndex $QatSampleIndex -HardwareBuildDir $HardwareBuildDir -BuildTag $BuildTag
if ($LASTEXITCODE -ne 0) { throw "Replay packet software build failed: $LASTEXITCODE" }

$buildRoot = Join-Path $scriptRoot (Join-Path 'build' (Join-Path $gitHead $BuildTag))
$packetManifestPath = Join-Path $buildRoot 'packet_build_manifest.json'
$packetManifest = Get-Content -LiteralPath $packetManifestPath -Raw | ConvertFrom-Json
$runRoot = Join-Path $buildRoot (Join-Path 'runs' (Join-Path 'b3_pl_replay' ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))))
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null

function Ensure-HwServer {
    try {
        $client = [Net.Sockets.TcpClient]::new('127.0.0.1', 3121)
        $client.Dispose()
        return
    } catch {}
    Start-Process -FilePath $HwServerPath -ArgumentList '-s', 'tcp::3121' -WindowStyle Hidden | Out-Null
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 250
        try {
            $client = [Net.Sockets.TcpClient]::new('127.0.0.1', 3121)
            $client.Dispose()
            return
        } catch {}
    }
    throw 'hw_server did not start on tcp:3121'
}

Ensure-HwServer
$ps7Init = Join-Path $buildRoot 'ps7_init.tcl'
if (-not (Test-Path -LiteralPath $ps7Init)) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead([string]$packetManifest.xsa)
    try {
        $entry = $archive.GetEntry('ps7_init.tcl')
        if (-not $entry) { throw 'ps7_init.tcl is absent from XSA' }
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $ps7Init, $false)
    } finally { $archive.Dispose() }
}

$programOut = Join-Path $runRoot 'program.log'
$programErr = Join-Path $runRoot 'program.err'
& $XsctPath (Join-Path $scriptRoot 'program_b2.tcl') ([string]$packetManifest.bitstream) `
    $ps7Init ([string]$packetManifest.elf) > $programOut 2> $programErr
$programExitCode = $LASTEXITCODE
$programText = [string](Get-Content -LiteralPath $programOut -Raw)
if ($programExitCode -ne 0) { throw "Replay programming failed: $programExitCode" }
foreach ($marker in @('B2_FPGA_PROGRAM_PASS', 'B2_ELF_DOWNLOAD_PASS', 'B2_CPU_RUN_PASS')) {
    if ($programText -notmatch [regex]::Escape($marker)) {
        throw "Replay programming log missing $marker"
    }
}

$probeText = $null
$probeAttempts = 0
$probeExitCode = $null
$deadline = [DateTime]::UtcNow.AddSeconds(30)
while ([DateTime]::UtcNow -lt $deadline) {
    ++$probeAttempts
    $probeOut = Join-Path $runRoot ("probe_{0:D3}.log" -f $probeAttempts)
    $probeErr = Join-Path $runRoot ("probe_{0:D3}.err" -f $probeAttempts)
    $probe = Start-Process -FilePath $XsctPath -ArgumentList @(
        (Join-Path $scriptRoot 'probe_b3_pl_replay_benchmark.tcl')
    ) -RedirectStandardOutput $probeOut -RedirectStandardError $probeErr -WindowStyle Hidden -PassThru
    if (-not $probe.WaitForExit(30000)) {
        $probe.Kill()
        throw 'PL replay probe timed out'
    }
    $probe.Refresh()
    $probeExitCode = [int]$probe.ExitCode
    if ($probeExitCode -eq 0) {
        $candidate = [string](Get-Content -LiteralPath $probeOut -Raw)
        if ($candidate -match '(?m)^B3_PL_REPLAY_STATUS=4\r?$' -and
            $candidate -match '(?m)^B3_PL_REPLAY_COMPLETED=10000\r?$') {
            $probeText = $candidate
            break
        }
    }
    Start-Sleep -Milliseconds 250
}
if ($null -eq $probeText) { throw 'PL replay record did not reach PASS within 30 seconds' }
function Get-ProbeU32 {
    param([string]$Key)
    $match = [regex]::Match($probeText, "(?m)^$([regex]::Escape($Key))=(\S+)")
    if (-not $match.Success) { throw "Replay probe missing $Key" }
    $value = $match.Groups[1].Value
    if ($value -like '0x*') { return [Convert]::ToUInt32($value.Substring(2), 16) }
    return [uint32]$value
}
function Convert-ManifestUInt32 {
    param([object]$Value)
    $text = [string]$Value
    if ($text -match '^0x') { return [Convert]::ToUInt32($text.Substring(2), 16) }
    return [uint32]$Value
}
function Update-Crc32Word {
    param([uint32]$Crc, [uint32]$Data)
    for ($byteIndex = 0; $byteIndex -lt 4; ++$byteIndex) {
        $value = ($Data -shr (8 * $byteIndex)) -band 0xFF
        $Crc = $Crc -bxor [uint32]$value
        for ($bitIndex = 0; $bitIndex -lt 8; ++$bitIndex) {
            $mask = if (($Crc -band 1) -ne 0) { [uint32]::MaxValue } else { [uint32]0 }
            $Crc = [uint32](($Crc -shr 1) -bxor ([uint32]3988292384 -band $mask))
        }
    }
    return $Crc
}

$statusValue = Get-ProbeU32 'B3_PL_REPLAY_STATUS'
$completed = Get-ProbeU32 'B3_PL_REPLAY_COMPLETED'
$cycles = Get-ProbeU32 'B3_PL_REPLAY_CYCLES'
$executeGroups = Get-ProbeU32 'B3_PL_REPLAY_EXECUTE_GROUPS'
$skipGroups = Get-ProbeU32 'B3_PL_REPLAY_SKIP_GROUPS'
$lastComputeCycles = Get-ProbeU32 'B3_PL_REPLAY_LAST_COMPUTE_CYCLES'
$protocolErrors = Get-ProbeU32 'B3_PL_REPLAY_PROTOCOL_ERRORS'
$rxWords = @()
for ($index = 0; $index -lt 19; ++$index) {
    $rxWords += Get-ProbeU32 ('B3_PL_REPLAY_RX_WORD_{0:D2}' -f $index)
}
$qat = Get-Content -LiteralPath $QatManifest -Raw | ConvertFrom-Json
$expectedSample = $qat.samples[$QatSampleIndex]
$expectedSampleId = Convert-ManifestUInt32 $expectedSample.sample_id
$expectedLogits = @($expectedSample.dense_logits)
$resultFramePass = $rxWords[0] -eq 0x32424E45 -and $rxWords[1] -eq 0x08000401 -and
    $rxWords[2] -eq 40 -and $rxWords[4] -eq $expectedSampleId -and
    $rxWords[5] -eq 3 -and $rxWords[6] -eq 1 -and $rxWords[7] -eq 0
for ($index = 0; $index -lt 10; ++$index) {
    $actual = [BitConverter]::ToInt32([BitConverter]::GetBytes([uint32]$rxWords[8 + $index]), 0)
    if ([int64]$actual -ne [int64]$expectedLogits[$index]) { $resultFramePass = $false }
}
$crc = [uint32]::MaxValue
for ($index = 0; $index -lt 18; ++$index) {
    $crc = Update-Crc32Word -Crc $crc -Data ([uint32]$rxWords[$index])
}
$expectedResultCrc = [uint32](-bnot $crc)
if ($rxWords[18] -ne $expectedResultCrc) { $resultFramePass = $false }
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
    $observedGroupInstances -eq $expectedGroupInstances -and $modeGroupPass -and
    $resultFramePass
$cyclesPerSample = if ($completed -gt 0) { $cycles / [double]$completed } else { 0.0 }
$samplesPerSecond = if ($cycles -gt 0) { 200000000.0 * $completed / $cycles } else { 0.0 }
$formalEvidence = -not $AllowDirty -and $hardwareClean -and $hardwareSourceClosurePass -and
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
    hardware_git_head = [string]$hardwareManifest.git_head
    hardware_source_closure_pass = $hardwareSourceClosurePass
    hardware_source_mismatches = $hardwareSourceMismatches
    packet_manifest = $packetManifestPath
    packet_manifest_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $packetManifestPath).Hash.ToLowerInvariant()
    program_log = $programOut
    program_log_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $programOut).Hash.ToLowerInvariant()
    program_exit_code = $programExitCode
    probe_attempts = $probeAttempts
    probe_exit_code = $probeExitCode
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
    result_frame_pass = $resultFramePass
    result_crc = $rxWords[18]
    boundary = 'CP5a 单个代表性 QAT 样本的纯 PL replay bring-up；不覆盖 397 样本分布，不关闭正式 CP5/B3-SPEED-GATE。'
}
$summary.sample_id = $expectedSampleId
$summaryPath = Join-Path $runRoot 'b3_pl_replay_benchmark.json'
$summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $summaryPath -Encoding utf8
Write-Output "B3_PL_REPLAY_STATUS=$($summary.status)"
Write-Output "B3_PL_REPLAY_SUMMARY=$summaryPath"
if (-not $runPass) { exit 1 }

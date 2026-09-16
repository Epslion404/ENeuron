param(
    [ValidateSet('dense', 'static_mixed', 'calibrated_static', 'live_eneuron')]
    [string]$Mode = 'live_eneuron',
    [ValidateRange(1, 397)]
    [int]$Samples = 64,
    [ValidateSet(1, 16, 32, 64)]
    [int]$LiveMaskBatchK = 1,
    [string]$BenchmarkManifest = '',
    [string]$QatManifest = '',
    [switch]$CaptureLogits,
    [switch]$AllowDirty,
    [string]$XsctPath = 'G:\Xilinx\Vitis\2024.1\bin\xsct.bat',
    [string]$HwServerPath = 'G:\Xilinx\Vivado\2024.1\bin\hw_server.bat',
    [string]$HardwareBuildDir = '',
    [string]$BuildTag = 'direct'
)

$ErrorActionPreference = 'Stop'
if ($Mode -ne 'live_eneuron' -and $LiveMaskBatchK -ne 1) {
    throw 'LiveMaskBatchK greater than 1 is only valid for live_eneuron mode'
}
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..\..')).Path
if ($BuildTag -notmatch '^[A-Za-z0-9._-]+$') { throw "Invalid BuildTag: $BuildTag" }
$HardwareBuildDir = if ([string]::IsNullOrWhiteSpace($HardwareBuildDir)) {
    Join-Path $repoRoot 'boards\hellozynq\b2_hw\build'
} else {
    (Resolve-Path -LiteralPath $HardwareBuildDir).Path
}
if ([string]::IsNullOrWhiteSpace($BenchmarkManifest)) {
    $BenchmarkManifest = if ([string]::IsNullOrWhiteSpace($QatManifest)) {
        Join-Path $repoRoot 'tools\repro\b3_multi_input_manifest.json'
    } else {
        $QatManifest
    }
} elseif (-not [string]::IsNullOrWhiteSpace($QatManifest)) {
    throw 'BenchmarkManifest and QatManifest are mutually exclusive'
}
$benchmarkSchema = (Get-Content -LiteralPath $BenchmarkManifest -Raw | ConvertFrom-Json).schema
$isQatManifest = $benchmarkSchema -eq 'eneuron_b3_qat_model_v1'
if ($isQatManifest -and $Mode -ne 'dense') {
    throw 'QAT speed benchmark currently supports dense mode only'
}
$buildScript = Join-Path $scriptRoot 'run_b2_packet_sw_build.ps1'
$buildParams = @{
    XsctPath = $XsctPath
    B3SpeedBenchmark = $true
    B3AccuracyBenchmark = $CaptureLogits
    B3LiveMaskBatchK = $LiveMaskBatchK
    B3BenchmarkSampleCount = $Samples
    HardwareBuildDir = $HardwareBuildDir
    BuildTag = $BuildTag
}
if ($isQatManifest) {
    $buildParams.B3QatManifest = $BenchmarkManifest
} else {
    $buildParams.B3BenchmarkManifest = $BenchmarkManifest
}
switch ($Mode) {
    'dense' { $buildParams.B3Dense = $true }
    'static_mixed' { $buildParams.B3StaticMixed = $true }
    'calibrated_static' { $buildParams.B3CalibratedStatic = $true }
    'live_eneuron' { $buildParams.B3LiveEneuron = $true }
}

& $buildScript @buildParams
if ($LASTEXITCODE -ne 0) { throw "B3 speed benchmark software build failed: $LASTEXITCODE" }

$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
$buildRoot = Join-Path $scriptRoot (Join-Path 'build' (Join-Path $gitHead $BuildTag))
$manifestPath = Join-Path $buildRoot 'packet_build_manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw "Missing packet build manifest: $manifestPath" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if (-not [bool]$manifest.speed_benchmark -or [int]$manifest.speed_benchmark_samples -ne $Samples) {
    throw 'Packet build manifest is not a frozen B3 speed benchmark build'
}
if ([int]$manifest.live_mask_batch_k -ne $LiveMaskBatchK) {
    throw "Packet build manifest live mask batch mismatch: expected $LiveMaskBatchK"
}
$benchmarkManifestSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $BenchmarkManifest).Hash.ToLowerInvariant()
if ([string]$manifest.benchmark_manifest_sha256 -ne $benchmarkManifestSha256) {
    throw 'Benchmark manifest SHA-256 does not match the packet build manifest'
}
if ([int]$manifest.benchmark_unique_input_count -ne $Samples) {
    throw 'Benchmark manifest does not contain one unique input per sample'
}
$benchmarkData = Get-Content -LiteralPath $BenchmarkManifest -Raw | ConvertFrom-Json
$allBenchmarkSamples = @($benchmarkData.samples)
if ($allBenchmarkSamples.Count -lt $Samples) { throw 'Benchmark manifest contains fewer samples than requested' }
$benchmarkSamples = @($allBenchmarkSamples | Select-Object -First $Samples)
if ($benchmarkSamples.Count -ne $Samples) { throw 'Benchmark manifest sample count mismatch' }
$expectedMaskUpdates = if ($Mode -eq 'live_eneuron') { [int][Math]::Ceiling($Samples / [double]$LiveMaskBatchK) } else { 0 }
if ([int]$manifest.live_mask_update_count -ne $expectedMaskUpdates) {
    throw "Packet build manifest live mask update count mismatch: expected $expectedMaskUpdates"
}
$expectedApplicationMode = "b3_$Mode"
if ([string]$manifest.application_mode -ne $expectedApplicationMode) {
    throw "Packet build manifest mode mismatch: expected $expectedApplicationMode"
}
if (-not $AllowDirty -and -not [bool]$manifest.git_tracked_worktree_clean) {
    throw 'Formal B3 speed evidence requires a clean tracked worktree; use -AllowDirty only for development'
}
$packetSourcePath = Join-Path $scriptRoot 'src\packet_main.c'
if (-not (Test-Path -LiteralPath $packetSourcePath)) { throw "Required file not found: $packetSourcePath" }
$packetSourceSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $packetSourcePath).Hash.ToLowerInvariant()
if ([string]$manifest.packet_source_sha256 -ne $packetSourceSha256) {
    throw 'Packet source SHA-256 does not match the speed benchmark manifest'
}
foreach ($path in @($XsctPath, $HwServerPath, [string]$manifest.bitstream,
                    [string]$manifest.xsa, [string]$manifest.elf)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required file not found: $path" }
}

function Invoke-XsctProbe {
    param([Parameter(Mandatory = $true)][string]$OutPath,
          [Parameter(Mandatory = $true)][string]$ErrPath)
    $probeTimeoutMs = if ($CaptureLogits -and $Samples -gt 64) { 600000 } else { 120000 }
    $probeArgs = @((Join-Path $scriptRoot 'probe_b3_speed_benchmark.tcl'), [string]$Samples)
    if ($CaptureLogits) { $probeArgs += 'capture_logits' }
    $probe = Start-Process -FilePath $XsctPath -ArgumentList $probeArgs `
        -RedirectStandardOutput $OutPath -RedirectStandardError $ErrPath `
        -WindowStyle Hidden -PassThru
    if (-not $probe.WaitForExit($probeTimeoutMs)) {
        $probe.Kill()
        throw "B3 speed probe timed out after ${probeTimeoutMs}ms: $OutPath"
    }
    $probe.Refresh()
    return [int]$probe.ExitCode
}

function Get-U32 {
    param([Parameter(Mandatory = $true)][string]$Text,
          [Parameter(Mandatory = $true)][string]$Key)
    $match = [regex]::Match($Text, "(?m)^$([regex]::Escape($Key))=(\S+)")
    if (-not $match.Success) { throw "Probe log missing $Key" }
    $value = $match.Groups[1].Value
    if ($value -like '0x*') { return [Convert]::ToUInt32($value.Substring(2), 16) }
    return [uint32]$value
}

function Get-I32 {
    param([Parameter(Mandatory = $true)][string]$Text,
          [Parameter(Mandatory = $true)][string]$Key)
    $rawLogit = Get-U32 -Text $Text -Key $Key
    $bits = [BitConverter]::ToInt32([BitConverter]::GetBytes($rawLogit), 0)
    if ($rawLogit -ge [uint32]2147483648) {
        return [int64]$bits
    }
    return [int64]$bits
}

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
    $archive = [IO.Compression.ZipFile]::OpenRead([string]$manifest.xsa)
    try {
        $entry = $archive.GetEntry('ps7_init.tcl')
        if (-not $entry) { throw 'ps7_init.tcl is absent from XSA' }
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $ps7Init, $false)
    } finally { $archive.Dispose() }
}

$runRoot = Join-Path $buildRoot (Join-Path 'runs' (Join-Path 'b3_speed' ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))))
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
$xsctStdout = Join-Path $runRoot 'xsct_stdout.log'
$xsctStderr = Join-Path $runRoot 'xsct_stderr.log'
& $XsctPath (Join-Path $scriptRoot 'program_b2.tcl') ([string]$manifest.bitstream) $ps7Init ([string]$manifest.elf) `
    > $xsctStdout 2> $xsctStderr
$programExitCode = $LASTEXITCODE
$programText = [string](Get-Content -LiteralPath $xsctStdout -Raw)
if ($programExitCode -ne 0) { throw "XSCT programming failed with exit code $programExitCode" }
foreach ($marker in @('B2_FPGA_PROGRAM_PASS', 'B2_ELF_DOWNLOAD_PASS', 'B2_CPU_RUN_PASS')) {
    if ($programText -notmatch [regex]::Escape($marker)) { throw "XSCT programming log missing $marker" }
}

$probeText = $null
$lastProbeCandidate = $null
$probeErrors = @()
$probeExit = $null
$probeAttempts = 0
$deadline = [DateTime]::UtcNow.AddSeconds($(if ($CaptureLogits -and $Samples -gt 64) { 630 } else { 30 }))
while ([DateTime]::UtcNow -lt $deadline) {
    ++$probeAttempts
    $attemptOut = Join-Path $runRoot ("probe_attempt_{0:D3}.log" -f $probeAttempts)
    $attemptErr = Join-Path $runRoot ("probe_attempt_{0:D3}.err" -f $probeAttempts)
    try {
        $probeExit = Invoke-XsctProbe -OutPath $attemptOut -ErrPath $attemptErr
        $candidate = [string](Get-Content -LiteralPath $attemptOut -Raw)
        if ($candidate -and (Get-U32 -Text $candidate -Key 'B3_SPEED_MAGIC') -eq 0x42335350) {
            $lastProbeCandidate = $candidate
            $speedReady = (Get-U32 -Text $candidate -Key 'B3_SPEED_STATUS') -eq 2 -and
                (Get-U32 -Text $candidate -Key 'B3_SPEED_SAMPLE_COUNT') -eq $Samples
            $accuracyReady = -not $CaptureLogits -or (
                (Get-U32 -Text $candidate -Key 'B3_ACCURACY_MAGIC') -eq 0x42334143 -and
                (Get-U32 -Text $candidate -Key 'B3_ACCURACY_STATUS') -eq 2 -and
                (Get-U32 -Text $candidate -Key 'B3_ACCURACY_SAMPLE_COUNT') -eq $Samples)
            if ($speedReady -and $accuracyReady) {
                $probeText = $candidate
                break
            }
        }
    } catch {
        $probeErrors += $_.Exception.Message
    }
    Start-Sleep -Milliseconds 500
}
if ($null -eq $probeText) {
    if ($null -ne $lastProbeCandidate) {
        $speedStatus = Get-U32 -Text $lastProbeCandidate -Key 'B3_SPEED_STATUS'
        $speedSampleCount = Get-U32 -Text $lastProbeCandidate -Key 'B3_SPEED_SAMPLE_COUNT'
        $message = "B3 speed benchmark record observed but not ready: status=$speedStatus sample_count=$speedSampleCount"
        if ($CaptureLogits) {
            $accuracyStatus = Get-U32 -Text $lastProbeCandidate -Key 'B3_ACCURACY_STATUS'
            $accuracySampleCount = Get-U32 -Text $lastProbeCandidate -Key 'B3_ACCURACY_SAMPLE_COUNT'
            $message += "; accuracy_status=$accuracyStatus accuracy_sample_count=$accuracySampleCount"
        }
        throw $message
    }
    $errorSuffix = if ($probeErrors.Count -gt 0) { "; last_probe_error=$($probeErrors[-1])" } else { '' }
    throw "B3 speed benchmark record was not observed over JTAG$errorSuffix"
}
$probePath = Join-Path $runRoot 'probe.log'
$probeText | Set-Content -LiteralPath $probePath -Encoding utf8

$rows = @()
function Get-ExpectedMaskEpoch {
    param([Parameter(Mandatory = $true)][int]$Index,
          [Parameter(Mandatory = $true)][object]$Expected)
    if ($Mode -eq 'dense') {
        if ($isQatManifest) { return [uint32]1 }
        if ($null -eq $Expected.dense_mask_epoch) { throw 'Benchmark manifest sample missing dense_mask_epoch' }
        return [uint32]$Expected.dense_mask_epoch
    }
    if ($Mode -eq 'live_eneuron') {
        if ($null -eq $Expected.live_mask_epoch) { throw 'Benchmark manifest sample missing live_mask_epoch' }
        return [uint32]$Expected.live_mask_epoch
    }
    if ($null -eq $Expected.mask_epoch) { throw 'Benchmark manifest sample missing mask_epoch' }
    return [uint32]$Expected.mask_epoch
}
for ($index = 0; $index -lt $Samples; ++$index) {
    $prefix = 'B3_SPEED_SAMPLE_{0:D2}_' -f $index
    $rows += [ordered]@{
        sequence = Get-U32 $probeText ($prefix + 'SEQUENCE')
        sample_id = Get-U32 $probeText ($prefix + 'ID')
        mask_epoch = Get-U32 $probeText ($prefix + 'MASK_EPOCH')
        input_crc = Get-U32 $probeText ($prefix + 'INPUT_CRC')
        status = Get-U32 $probeText ($prefix + 'STATUS')
        ps_us = Get-U32 $probeText ($prefix + 'PS_US')
        dma_us = Get-U32 $probeText ($prefix + 'DMA_US')
        result_us = Get-U32 $probeText ($prefix + 'RESULT_US')
        total_us = Get-U32 $probeText ($prefix + 'TOTAL_US')
        npu_cycles = Get-U32 $probeText ($prefix + 'NPU_CYCLES')
        execute_groups = Get-U32 $probeText ($prefix + 'EXECUTE_GROUPS')
        skip_groups = Get-U32 $probeText ($prefix + 'SKIP_GROUPS')
        protocol_errors = Get-U32 $probeText ($prefix + 'PROTOCOL_ERRORS')
        result_crc = Get-U32 $probeText ($prefix + 'RESULT_CRC')
        mask_compute_us = Get-U32 $probeText ($prefix + 'MASK_COMPUTE_US')
        mask_submit_us = Get-U32 $probeText ($prefix + 'MASK_SUBMIT_US')
    }
    $expected = $benchmarkSamples[$index]
    if ($null -ne $expected.label) { $rows[-1].label = [int]$expected.label }
    $expectedMaskEpoch = Get-ExpectedMaskEpoch -Index $index -Expected $expected
    if ($rows[-1].sample_id -ne [uint32]$expected.sample_id -or
        $rows[-1].input_crc -ne [uint32]$expected.input_crc -or
        $rows[-1].mask_epoch -ne $expectedMaskEpoch) {
        throw "B3 sample identity mismatch at index $index"
    }
}
$accuracyCapture = $null
if ($CaptureLogits) {
    $accuracyCapture = [ordered]@{
        status = Get-U32 $probeText 'B3_ACCURACY_STATUS'
        mode_id = Get-U32 $probeText 'B3_ACCURACY_MODE_ID'
        sample_count = Get-U32 $probeText 'B3_ACCURACY_SAMPLE_COUNT'
        result_failures = Get-U32 $probeText 'B3_ACCURACY_RESULT_FAILURES'
        failure_stage = Get-U32 $probeText 'B3_ACCURACY_FAILURE_STAGE'
        failure_sample_index = Get-U32 $probeText 'B3_ACCURACY_FAILURE_SAMPLE_INDEX'
        samples = @()
    }
    if ($accuracyCapture.status -ne 2 -or $accuracyCapture.sample_count -ne $Samples -or
        $accuracyCapture.result_failures -ne 0) {
        throw 'B3 accuracy logits capture is incomplete or failed'
    }
    $captureRows = @()
    for ($index = 0; $index -lt $Samples; ++$index) {
        $prefix = 'B3_ACCURACY_SAMPLE_{0:D2}_' -f $index
        $logits = @()
        for ($logit = 0; $logit -lt 10; ++$logit) {
            $logits += [int32](Get-I32 $probeText ($prefix + ('LOGIT_{0:D2}' -f $logit)))
        }
        if ($isQatManifest) {
            $expectedLogits = @($benchmarkSamples[$index].dense_logits)
            for ($logit = 0; $logit -lt 10; ++$logit) {
                if ([int64]$logits[$logit] -ne [int64]$expectedLogits[$logit]) {
                    throw "B3 QAT logit mismatch at sample $index logit $logit`: expected=$($expectedLogits[$logit]) actual=$($logits[$logit])"
                }
            }
        }
        $captureRows += [ordered]@{
            sample_index = $index
            sample_id = $rows[$index].sample_id
            input_sha256 = [string]$benchmarkSamples[$index].input_sha256
            mask_epoch = Get-U32 $probeText ($prefix + 'MASK_EPOCH')
            input_crc = Get-U32 $probeText ($prefix + 'INPUT_CRC')
            status = Get-U32 $probeText ($prefix + 'STATUS')
            result_crc = Get-U32 $probeText ($prefix + 'RESULT_CRC')
            logits = $logits
        }
        if ($null -ne $benchmarkSamples[$index].label) {
            $captureRows[-1].label = [int]$benchmarkSamples[$index].label
        }
        $expectedMaskEpoch = Get-ExpectedMaskEpoch -Index $index -Expected $benchmarkSamples[$index]
        if ($captureRows[-1].mask_epoch -ne $expectedMaskEpoch -or
            $captureRows[-1].input_crc -ne $rows[$index].input_crc -or
            $captureRows[-1].result_crc -ne $rows[$index].result_crc -or
            $captureRows[-1].status -ne 2) {
            throw "B3 accuracy capture identity mismatch at index $index"
        }
    }
    $accuracyCapture.samples = $captureRows
}
$status = if ($programExitCode -eq 0 -and $probeExit -eq 0 -and
             (Get-U32 $probeText 'B3_SPEED_STATUS') -eq 2 -and
             (Get-U32 $probeText 'B3_SPEED_SAMPLE_COUNT') -eq $Samples -and
             (Get-U32 $probeText 'B3_SPEED_RESULT_FAILURES') -eq 0 -and
             ($rows | Where-Object { $_.status -ne 2 -or $_.protocol_errors -ne 0 }).Count -eq 0) { 'PASS' } else { 'FAIL' }
$summary = [ordered]@{
    schema = 'eneuron_b3_speed_benchmark_v1'
    status = $status
    mode = "b3_$Mode"
    git_head = $gitHead
    bitstream_sha256 = [string]$manifest.bitstream_sha256
    xsa_sha256 = [string]$manifest.xsa_sha256
    elf_sha256 = [string]$manifest.elf_sha256
    git_tracked_worktree_clean = [bool]$manifest.git_tracked_worktree_clean
    formal_evidence = (-not $AllowDirty -and [bool]$manifest.git_tracked_worktree_clean)
    sample_count = $Samples
    model_id = 3
    preprocess = 'uint4_64_low_nibble_first_v1'
    live_mask_batch_k = $LiveMaskBatchK
    live_mask_update_count = $expectedMaskUpdates
    capture_logits = [bool]$CaptureLogits
    benchmark_manifest = $BenchmarkManifest
    benchmark_manifest_sha256 = $benchmarkManifestSha256
    input_manifest_sha256 = $benchmarkManifestSha256
    benchmark_unique_input_count = [int]$manifest.benchmark_unique_input_count
    probe_attempts = $probeAttempts
    program_exit_code = [int]$programExitCode
    probe_exit_code = $probeExit
    setup_us = Get-U32 $probeText 'B3_SPEED_SETUP_US'
    mask_us = Get-U32 $probeText 'B3_SPEED_MASK_US'
    mask_compute_us = Get-U32 $probeText 'B3_SPEED_MASK_COMPUTE_US'
    mask_submit_us = Get-U32 $probeText 'B3_SPEED_MASK_SUBMIT_US'
    fence_us = Get-U32 $probeText 'B3_SPEED_FENCE_US'
    failure_stage = Get-U32 $probeText 'B3_SPEED_FAILURE_STAGE'
    failure_sample_index = Get-U32 $probeText 'B3_SPEED_FAILURE_SAMPLE_INDEX'
    failure_check_mask = Get-U32 $probeText 'B3_SPEED_FAILURE_CHECK_MASK'
    failure_response_words = Get-U32 $probeText 'B3_SPEED_FAILURE_RESPONSE_WORDS'
    failure_response_sequence = Get-U32 $probeText 'B3_SPEED_FAILURE_RESPONSE_SEQUENCE'
    total_min_us = Get-U32 $probeText 'B3_SPEED_TOTAL_MIN_US'
    total_max_us = Get-U32 $probeText 'B3_SPEED_TOTAL_MAX_US'
    dma_min_us = Get-U32 $probeText 'B3_SPEED_DMA_MIN_US'
    dma_max_us = Get-U32 $probeText 'B3_SPEED_DMA_MAX_US'
    ps_min_us = Get-U32 $probeText 'B3_SPEED_PS_MIN_US'
    ps_max_us = Get-U32 $probeText 'B3_SPEED_PS_MAX_US'
    samples = $rows
}
if ($CaptureLogits) { $summary.accuracy_capture = $accuracyCapture }
if ($CaptureLogits -and $isQatManifest) { $summary.logit_exact_match_count = $Samples }
$summaryPath = Join-Path $runRoot 'b3_speed_benchmark.json'
$summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $summaryPath -Encoding utf8
Write-Output "B3_SPEED_BENCHMARK_STATUS=$status"
Write-Output "B3_SPEED_BENCHMARK_RUN=$runRoot"
Write-Output "B3_SPEED_BENCHMARK_SUMMARY=$summaryPath"
if ($status -ne 'PASS') { exit 1 }

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('idle', 'full')]
    [string]$State,
    [Parameter(Mandatory = $true)]
    [ValidateSet('dense', 'lossless_zero_group_skip')]
    [string]$Mode,
    [Parameter(Mandatory = $true)]
    [string]$HardwareBuildDir,
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
    # idle/full 共用构建身份，确保两态复用同一 bit/XSA/ELF。
    $BuildTag = "cp8_${Mode}_power"
}
if ($BuildTag -notmatch '^[A-Za-z0-9._-]+$') { throw "Invalid BuildTag: $BuildTag" }

# CP8 状态块寄存器偏移（base=0x40430000）。
$cp8ControlOffset = 0x74
$cp8ReplayStatusOffset = 0x64
$cp8CompletedOffset = 0x68
$cp8CyclesOffset = 0x6C
$cp8CaptureOffset = 0x70
$cp8ProtocolOffset = 0x60

$hardwareManifestPath = Join-Path $HardwareBuildDir 'build_manifest.json'
$hardwareManifest = Get-Content -LiteralPath $hardwareManifestPath -Raw | ConvertFrom-Json
$expectedHardwareMode = "${Mode}_pl_power_replay"
if ([string]$hardwareManifest.npu_mode -ne $expectedHardwareMode) {
    throw "CP8 power hardware mode mismatch: expected=$expectedHardwareMode actual=$($hardwareManifest.npu_mode)"
}
foreach ($required in @(
    'B3_PL_DISTRIBUTION_REPLAY_BENCHMARK',
    'B3_CP8_POWER_MEASUREMENT',
    'B3_PL_REPLAY_INPUT_SAMPLES=397',
    'B3_PL_REPLAY_WARMUP_SAMPLES=1000',
    'B3_PL_REPLAY_MEASURE_SAMPLES=10000',
    'B3_PL_REPLAY_CONTINUOUS=1'
)) {
    if ($required -notin @($hardwareManifest.verilog_defines)) {
        throw "CP8 power hardware manifest missing define: $required"
    }
}
if ([string]$hardwareManifest.signoff.B2_SIGNOFF_PASS -ne '1') {
    throw 'CP8 power hardware did not pass physical signoff'
}
$hardwareClean = [bool]$hardwareManifest.git_worktree_clean
$hardwareSourceClosurePass = $true
$hardwareSourceMismatches = @()
$hardwareSourceCanonicalFallbacks = @()
$nonSynthBuildRunner = 'boards/hellozynq/b2_hw/run_b2_build.ps1'
foreach ($entry in $hardwareManifest.source_sha256.PSObject.Properties) {
    $relativePath = [string]$entry.Name
    $sourcePath = Join-Path $repoRoot $relativePath
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        $hardwareSourceClosurePass = $false
        $hardwareSourceMismatches += "missing:$relativePath"
        continue
    }
    $actualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourcePath).Hash.ToLowerInvariant()
    if ($actualSha -eq ([string]$entry.Value).ToLowerInvariant()) { continue }

    # 外层构建 runner 不进入综合；只在其当前 Git blob 与 manifest 声称的 HEAD blob 相同时接受回退。
    if ($relativePath -eq $nonSynthBuildRunner) {
        $expectedSpec = "{0}:{1}" -f ([string]$hardwareManifest.git_head), $nonSynthBuildRunner
        $expectedBlob = (& git -C $repoRoot rev-parse $expectedSpec 2>$null).Trim()
        $expectedBlobExit = $LASTEXITCODE
        $currentBlob = (& git -C $repoRoot hash-object "--path=$nonSynthBuildRunner" $sourcePath 2>$null).Trim()
        $currentBlobExit = $LASTEXITCODE
        if ($expectedBlobExit -eq 0 -and $currentBlobExit -eq 0 -and $currentBlob -eq $expectedBlob) {
            $hardwareSourceCanonicalFallbacks += "git-blob:$nonSynthBuildRunner"
            continue
        }
    }

    $hardwareSourceClosurePass = $false
    $hardwareSourceMismatches += "sha:$relativePath"
}
if (-not $AllowDirty -and (-not $hardwareClean -or -not $hardwareSourceClosurePass)) {
    throw "Hardware source closure mismatch: $($hardwareSourceMismatches -join ',')"
}

$buildScript = Join-Path $scriptRoot 'run_b2_packet_sw_build.ps1'
& $buildScript -XsctPath $XsctPath -B3Cp8PowerMeasurement -B3QatManifest $QatManifest `
    -HardwareBuildDir $HardwareBuildDir -BuildTag $BuildTag
if ($LASTEXITCODE -ne 0) { throw "CP8 power packet build failed: $LASTEXITCODE" }

$buildRoot = Join-Path $scriptRoot (Join-Path 'build' (Join-Path $gitHead $BuildTag))
$packetManifestPath = Join-Path $buildRoot 'packet_build_manifest.json'
$packetManifest = Get-Content -LiteralPath $packetManifestPath -Raw | ConvertFrom-Json
if ([string]$packetManifest.application_mode -ne 'b3_cp8_power') {
    throw "CP8 packet application mode mismatch: $($packetManifest.application_mode)"
}
if (-not [bool]$packetManifest.cp8_power_measurement) {
    throw 'CP8 packet manifest cp8_power_measurement is not true'
}
if ([int]$packetManifest.cp8_power_samples -ne 397) {
    throw "CP8 packet manifest cp8_power_samples mismatch: $($packetManifest.cp8_power_samples)"
}

$runRoot = Join-Path $buildRoot (Join-Path 'runs' ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')))
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
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
$programOut = Join-Path $runRoot 'program.log'
$programErr = Join-Path $runRoot 'program.err'
& $XsctPath (Join-Path $scriptRoot 'program_b2.tcl') ([string]$packetManifest.bitstream) `
    $ps7Init ([string]$packetManifest.elf) > $programOut 2> $programErr
$programExitCode = $LASTEXITCODE
$programText = [string](Get-Content -LiteralPath $programOut -Raw)
if ($programExitCode -ne 0) { throw "CP8 power programming failed: $programExitCode" }
foreach ($marker in @('B2_FPGA_PROGRAM_PASS', 'B2_ELF_DOWNLOAD_PASS', 'B2_CPU_RUN_PASS')) {
    if ($programText -notmatch [regex]::Escape($marker)) {
        throw "CP8 power programming log missing $marker"
    }
}

$probeScript = Join-Path $scriptRoot 'probe_b3_cp8_power_state.tcl'
$probeOut = Join-Path $runRoot ("probe_{0}.log" -f $State)
$probeErr = Join-Path $runRoot ("probe_{0}.err" -f $State)
$probe = Start-Process -FilePath $XsctPath -ArgumentList @($probeScript, $State) `
    -RedirectStandardOutput $probeOut -RedirectStandardError $probeErr -WindowStyle Hidden -PassThru
if (-not $probe.WaitForExit(120000)) {
    $probe.Kill()
    throw 'CP8 power probe timed out'
}
$probe.Refresh()
$probeExitCode = [int]$probe.ExitCode
$probeText = [string](Get-Content -LiteralPath $probeOut -Raw)
if ($probeExitCode -ne 0) { throw "CP8 power probe failed: $probeExitCode`n$probeText" }
if ($probeText -notmatch '(?m)^B3_CP8_POWER_PROBE_PASS=1\r?$') {
    throw "CP8 power probe did not report PASS`n$probeText"
}

function Get-ProbeU32 {
    param([string]$Key)
    $match = [regex]::Match($probeText, "(?m)^$([regex]::Escape($Key))=(\S+)")
    if (-not $match.Success) { throw "CP8 probe missing $Key" }
    $value = $match.Groups[1].Value
    if ($value -like '0x*') { return [Convert]::ToUInt32($value.Substring(2), 16) }
    return [uint32]$value
}

$controlValue = Get-ProbeU32 'B3_CP8_POWER_CONTROL'
$statusValue = Get-ProbeU32 'B3_CP8_POWER_REPLAY_STATUS'
$captureValue = Get-ProbeU32 'B3_CP8_POWER_CAPTURE'
$completedValue = Get-ProbeU32 'B3_CP8_POWER_COMPLETED'
$cyclesValue = Get-ProbeU32 'B3_CP8_POWER_CYCLES'
$protocolValue = Get-ProbeU32 'B3_CP8_POWER_PROTOCOL'
$completedFirst = Get-ProbeU32 'B3_CP8_POWER_COMPLETED_FIRST'
$completedSecond = Get-ProbeU32 'B3_CP8_POWER_COMPLETED_SECOND'

if ($State -eq 'idle') {
    $statePass = $controlValue -eq 0x43503849 -and $statusValue -eq 1 -and
        $captureValue -eq 0 -and $completedValue -eq 0 -and $protocolValue -eq 0
} else {
    $statePass = $controlValue -eq 0x43503852 -and $statusValue -eq 3 -and
        $captureValue -eq 397 -and $protocolValue -eq 0 -and
        $completedSecond -ne $completedFirst
}
if (-not $statePass) {
    throw ("CP8 power state validation failed: state=$State control=$controlValue " +
        "status=$statusValue capture=$captureValue completed=$completedValue " +
        "first=$completedFirst second=$completedSecond protocol=$protocolValue")
}

$formalEvidence = -not $AllowDirty -and $hardwareClean -and $hardwareSourceClosurePass -and
    [bool]$packetManifest.git_tracked_worktree_clean

$manifest = [ordered]@{
    schema = 'eneuron_b3_cp8_power_state_v1'
    status = 'CP8_POWER_STATE_PASS'
    state = $State
    mode = $Mode
    phase = 'B3-PAPER-CP8'
    generated_at = [DateTime]::UtcNow.ToString('o')
    git_head = $gitHead
    hardware_build_dir = $HardwareBuildDir
    hardware_manifest = $hardwareManifestPath
    hardware_manifest_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $hardwareManifestPath).Hash.ToLowerInvariant()
    hardware_npu_mode = [string]$hardwareManifest.npu_mode
    hardware_git_head = [string]$hardwareManifest.git_head
    hardware_source_closure_pass = $hardwareSourceClosurePass
    hardware_source_mismatches = $hardwareSourceMismatches
    hardware_source_canonical_fallbacks = $hardwareSourceCanonicalFallbacks
    bitstream = [string]$packetManifest.bitstream
    bitstream_sha256 = [string]$packetManifest.bitstream_sha256
    xsa = [string]$packetManifest.xsa
    xsa_sha256 = [string]$packetManifest.xsa_sha256
    packet_manifest = $packetManifestPath
    packet_manifest_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $packetManifestPath).Hash.ToLowerInvariant()
    application_mode = [string]$packetManifest.application_mode
    cp8_power_measurement = [bool]$packetManifest.cp8_power_measurement
    cp8_power_samples = [int]$packetManifest.cp8_power_samples
    elf = [string]$packetManifest.elf
    elf_sha256 = [string]$packetManifest.elf_sha256
    qat_manifest = $QatManifest
    qat_manifest_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $QatManifest).Hash.ToLowerInvariant()
    program_log = $programOut
    program_log_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $programOut).Hash.ToLowerInvariant()
    program_exit_code = $programExitCode
    probe_log = $probeOut
    probe_exit_code = $probeExitCode
    register_offsets = [ordered]@{
        control = $cp8ControlOffset
        replay_status = $cp8ReplayStatusOffset
        completed = $cp8CompletedOffset
        cycles = $cp8CyclesOffset
        capture = $cp8CaptureOffset
        protocol = $cp8ProtocolOffset
    }
    control = $controlValue
    replay_status = $statusValue
    capture_count = $captureValue
    completed_count = $completedValue
    completed_first = $completedFirst
    completed_second = $completedSecond
    measured_cycles = $cyclesValue
    protocol_error_count = $protocolValue
    formal_evidence = $formalEvidence
    boundary = ('CP8 四态功耗的板级负载状态冻结：复用 CP5b 397 样本 PL-internal distribution replay，' +
        'PL 内 1000 warmup 后持续运行，PS 不参与逐样本决策。本 manifest 只记录整板外部 B10 仪表测量所需的板级状态，' +
        '不包含功耗读数，不得写成纯 NPU 功耗；JTAG 仅用于通信，状态保持运行，不 reset、不停止 CPU。')
}
$manifestPath = Join-Path $runRoot ("b3_cp8_power_state_{0}_{1}.json" -f $State, $Mode)
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8

Write-Output "B3_CP8_POWER_STATE=$State"
Write-Output "B3_CP8_POWER_MODE=$Mode"
Write-Output "B3_CP8_POWER_STATE_JSON=$manifestPath"
Write-Output "状态持续运行，可开始人工 B10 拍照"

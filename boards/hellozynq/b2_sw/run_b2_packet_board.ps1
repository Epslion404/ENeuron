param(
    [string]$PortName = '',
    # 默认匹配 VID_1A86/PID_7523 的 CH340 UART。
    [string]$UsbVid = '1A86',
    [string]$UsbPid = '7523',
    [int]$ListenSeconds = 90,
    [string]$XsctPath = 'G:\Xilinx\Vitis\2024.1\bin\xsct.bat',
    [string]$HwServerPath = 'G:\Xilinx\Vivado\2024.1\bin\hw_server.bat'
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($UsbVid)) { $UsbVid = '1A86' }
if ([string]::IsNullOrWhiteSpace($UsbPid)) { $UsbPid = '7523' }

function Resolve-SerialPortName {
    param([string]$RequestedPort, [string]$Vid, [string]$ProductId)
    if ($RequestedPort) { return $RequestedPort }
    $matches = @(Get-PnpDevice -PresentOnly -Class Ports -ErrorAction SilentlyContinue | Where-Object {
        $_.InstanceId -match "VID_$($Vid.ToUpperInvariant())&PID_$($ProductId.ToUpperInvariant())" -and
        $_.FriendlyName -match '\((COM\d+)\)'
    })
    if ($matches.Count -ne 1) { throw "Expected one USB serial device, found $($matches.Count)" }
    return ([regex]::Match($matches[0].FriendlyName, '\((COM\d+)\)')).Groups[1].Value
}

function Open-SerialPort {
    param([string]$Name)
    $port = [System.IO.Ports.SerialPort]::new($Name, 115200, 'None', 8, 'One')
    $port.ReadTimeout = 100
    $port.DtrEnable = $false
    $port.RtsEnable = $false
    $port.Open()
    return $port
}

function Invoke-B2StateProbe {
    param(
        [Parameter(Mandatory = $true)][string]$OutPath,
        [Parameter(Mandatory = $true)][string]$ErrPath,
        [int]$TimeoutMs = 20000
    )
    $probe = Start-Process -FilePath $XsctPath -ArgumentList @(
        (Join-Path $scriptRoot 'probe_b2_state.tcl')
    ) -RedirectStandardOutput $OutPath -RedirectStandardError $ErrPath -WindowStyle Hidden -PassThru
    if (-not $probe.WaitForExit($TimeoutMs)) {
        $probe.Kill()
        throw "probe_b2_state.tcl timed out: $OutPath"
    }
    return [int]$probe.ExitCode
}

function Get-ProbeU32 {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Key
    )
    $match = [regex]::Match($Text, "(?m)^$([regex]::Escape($Key))=(\S+)")
    if (-not $match.Success) { throw "probe log missing $Key" }
    $value = $match.Groups[1].Value
    if ($value -like '0x*') { return [Convert]::ToUInt32($value.Substring(2), 16) }
    return [uint32]$value
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..\..')).Path
$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
$buildRoot = Join-Path $scriptRoot (Join-Path 'build' (Join-Path $gitHead 'direct'))
$manifestPath = Join-Path $buildRoot 'packet_build_manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Run run_b2_packet_sw_build.ps1 first: $manifestPath"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if (-not [bool]$manifest.git_tracked_worktree_clean) {
    throw 'Packet build manifest was produced from a dirty tracked worktree'
}
$packetSourcePath = Join-Path $scriptRoot 'src\packet_main.c'
$packetSourceSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $packetSourcePath).Hash.ToLowerInvariant()
if ($packetSourceSha256 -ne ([string]$manifest.packet_source_sha256).ToLowerInvariant()) {
    throw 'Packet source hash mismatch'
}
$applicationMode = [string]$manifest.application_mode
if ([string]::IsNullOrWhiteSpace($applicationMode)) { $applicationMode = 'b2_packet_smoke' }
$markerByMode = @{
    b3_dense = 'B3_DENSE_PASS'
    b3_full_open = 'B3_FULL_OPEN_PASS'
    b3_bypass = 'B3_BYPASS_PASS'
    b3_static_mixed = 'B3_STATIC_MIXED_PASS'
    b3_live_eneuron = 'B3_LIVE_ENEURON_PASS'
    b3_epoch_overlap = 'B3_EPOCH_OVERLAP_PASS'
}
$terminalMarker = if ($markerByMode.ContainsKey($applicationMode)) { $markerByMode[$applicationMode] } else { 'B2_PACKET_PASS' }
$resultMarker = if ($markerByMode.ContainsKey($applicationMode)) { $markerByMode[$applicationMode] } else { 'B2_PACKET_RESULT_PASS' }
$bitstream = [string]$manifest.bitstream
if (-not $bitstream) { $bitstream = Join-Path $repoRoot 'boards\hellozynq\b2_hw\build\hello_zynq_b2.bit' }
$xsa = [string]$manifest.xsa
$elf = [string]$manifest.elf
foreach ($path in @($XsctPath, $bitstream, $xsa, $elf)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required file not found: $path" }
}
if ((Split-Path -Leaf $bitstream) -ne 'hello_zynq_b2.bit') { throw 'Unexpected B2 bitstream name' }
$hashErrors = @()
foreach ($item in @(
    @{ Name = 'bitstream'; Path = $bitstream; Expected = [string]$manifest.bitstream_sha256 },
    @{ Name = 'xsa'; Path = $xsa; Expected = [string]$manifest.xsa_sha256 },
    @{ Name = 'elf'; Path = $elf; Expected = [string]$manifest.elf_sha256 }
)) {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $item.Path).Hash.ToLowerInvariant()
    if ($actual -ne $item.Expected.ToLowerInvariant()) {
        $hashErrors += "$($item.Name) expected=$($item.Expected) actual=$actual"
    }
}
if ($hashErrors.Count -gt 0) { throw "Packet artifact hash mismatch: $($hashErrors -join '; ')" }

$serverReady = $false
try {
    $client = [Net.Sockets.TcpClient]::new('127.0.0.1', 3121)
    $client.Dispose()
    $serverReady = $true
} catch {
    if (-not (Test-Path -LiteralPath $HwServerPath)) { throw "hw_server not found: $HwServerPath" }
    Start-Process -FilePath $HwServerPath -ArgumentList '-s', 'tcp::3121' -WindowStyle Hidden | Out-Null
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while (-not $serverReady -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 250
        try {
            $client = [Net.Sockets.TcpClient]::new('127.0.0.1', 3121)
            $client.Dispose()
            $serverReady = $true
        } catch {}
    }
}
if (-not $serverReady) { throw 'hw_server did not start on tcp:3121' }

$ps7Init = Join-Path $buildRoot 'ps7_init.tcl'
if (-not (Test-Path -LiteralPath $ps7Init)) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($xsa)
    try {
        $entry = $archive.GetEntry('ps7_init.tcl')
        if (-not $entry) { throw 'ps7_init.tcl is absent from XSA' }
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $ps7Init, $false)
    } finally { $archive.Dispose() }
}

$runRoot = Join-Path $buildRoot (Join-Path 'runs' ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')))
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
$PortName = Resolve-SerialPortName $PortName $UsbVid $UsbPid
$xsctStdout = Join-Path $runRoot 'xsct_stdout.log'
$xsctStderr = Join-Path $runRoot 'xsct_stderr.log'
$serialLog = Join-Path $runRoot 'uart.log'
$serial = Open-SerialPort $PortName
$serialReconnects = [uint32]0
$serial.DiscardInBuffer()
$received = [Text.StringBuilder]::new()
$process = Start-Process -FilePath $XsctPath -ArgumentList @(
    (Join-Path $scriptRoot 'program_b2.tcl'), $bitstream, $ps7Init, $elf
) -RedirectStandardOutput $xsctStdout -RedirectStandardError $xsctStderr -WindowStyle Hidden -PassThru
$programDeadline = [DateTime]::UtcNow.AddSeconds(60)
$listenDeadline = $null
$runStarted = $false
$packetStarted = $false
$uartWatch = $null
$pendingHoldProbed = $false
$holdProbeOut = Join-Path $runRoot 'pending_hold_probe.log'
$holdProbeErr = Join-Path $runRoot 'pending_hold_probe.err'
$postProbeOut = Join-Path $runRoot 'post_pass_probe.log'
$postProbeErr = Join-Path $runRoot 'post_pass_probe.err'
try {
    while ($true) {
        $xsctText = if (Test-Path -LiteralPath $xsctStdout) { [string](Get-Content -LiteralPath $xsctStdout -Raw) } else { '' }
        if ($null -eq $xsctText) { $xsctText = '' }
        if (-not $runStarted -and $xsctText -like '*B2_CPU_RUN_PASS*') {
            $runStarted = $true
            $listenDeadline = [DateTime]::UtcNow.AddSeconds($ListenSeconds)
        }
        if ($runStarted -and $received.ToString() -like '*B2_PACKET_BEGIN*') {
            $packetStarted = $true
            if ($null -eq $uartWatch) { $uartWatch = [Diagnostics.Stopwatch]::StartNew() }
        }
        if ($runStarted -and -not $pendingHoldProbed -and $received.ToString() -like '*B3_11_PENDING_HOLD*') {
            $pendingHoldProbed = $true
            if ($null -ne $listenDeadline) { $listenDeadline = $listenDeadline.AddSeconds(30) }
            [void](Invoke-B2StateProbe -OutPath $holdProbeOut -ErrPath $holdProbeErr)
        }
        if ($runStarted -and $packetStarted -and $received.ToString() -like "*$terminalMarker*" -and
            $received.ToString() -like '*B2_PACKET_FENCE_PASS*' -and
            $received.ToString() -like "*$resultMarker*" -and
            $received.ToString() -like '*B3_SPEED_SPLIT*') {
            break
        }
        if ($runStarted -and $packetStarted -and
            (($received.ToString() -like '*B2_PACKET_FAIL*') -or
             ($received.ToString() -like '*B3_LOGIT_FAIL*'))) { break }
        if (-not $runStarted -and $process.HasExited) { break }
        if (-not $runStarted -and [DateTime]::UtcNow -ge $programDeadline) { break }
        if ($runStarted -and [DateTime]::UtcNow -ge $listenDeadline) { break }
        try {
            if ($null -eq $serial -or -not $serial.IsOpen) {
                if ($serial) { $serial.Dispose() }
                $serial = Open-SerialPort $PortName
                ++$serialReconnects
            }
            $chunk = $serial.ReadExisting()
        } catch [System.IO.IOException] {
            if ($serial) { $serial.Dispose() }
            $serial = $null
            ++$serialReconnects
            Start-Sleep -Milliseconds 100
            continue
        } catch [System.InvalidOperationException] {
            if ($serial) { $serial.Dispose() }
            $serial = $null
            ++$serialReconnects
            Start-Sleep -Milliseconds 100
            continue
        }
        if ($chunk.Length -gt 0) {
            [void]$received.Append($chunk)
            Write-Host -NoNewline $chunk
        }
        Start-Sleep -Milliseconds 50
    }
} finally {
    if ($serial) {
        if ($serial.IsOpen) { $serial.Close() }
        $serial.Dispose()
    }
}
if (-not $process.WaitForExit(30000)) { $process.Kill(); throw 'XSCT programming process did not exit' }
$uartText = $received.ToString()
$uartText | Set-Content -LiteralPath $serialLog -Encoding utf8
$xsctText = [string](Get-Content -LiteralPath $xsctStdout -Raw)
if ($null -eq $xsctText) { $xsctText = '' }
$xsctStderrText = if (Test-Path -LiteralPath $xsctStderr) { [string](Get-Content -LiteralPath $xsctStderr -Raw) } else { '' }
if ($null -eq $xsctStderrText) { $xsctStderrText = '' }
$xsctExitCode = [int]$process.ExitCode
$packetOffset = $uartText.IndexOf('B2_PACKET_BEGIN', [StringComparison]::Ordinal)
$packetText = if ($packetOffset -ge 0) { $uartText.Substring($packetOffset) } else { '' }
$uartPass = ($packetText -like '*B2_PACKET_BEGIN*') -and
    ($packetText -like '*B2_PACKET_FENCE_PASS*') -and
    ($packetText -like "*$resultMarker*") -and
    ($packetText -like "*$terminalMarker*")
$xsctProgramPass = $xsctText -like '*B2_FPGA_PROGRAM_PASS*'
$xsctDownloadPass = $xsctText -like '*B2_ELF_DOWNLOAD_PASS*'
# XSCT 包装器可能在 Tcl error 时仍返回 0；明确识别“available targets: none”。
$jtagTargetUnavailable = $xsctStderrText -match 'available targets:\s*none'
$epochHoldPass = $true
$epochHoldActive = $null
$epochHoldPending = $null
if ($applicationMode -eq 'b3_epoch_overlap') {
    if (-not $pendingHoldProbed -or -not (Test-Path -LiteralPath $holdProbeOut)) {
        $epochHoldPass = $false
    } else {
        $holdText = [string](Get-Content -LiteralPath $holdProbeOut -Raw)
        if ($null -eq $holdText) { $holdText = '' }
        try {
            $epochHoldActive = Get-ProbeU32 -Text $holdText -Key 'B2_NPU_ACTIVE_MASK_EPOCH'
            $epochHoldPending = Get-ProbeU32 -Text $holdText -Key 'B2_NPU_PENDING_MASK_EPOCH'
            if ($epochHoldActive -ne 0 -or $epochHoldPending -ne 1) { $epochHoldPass = $false }
        } catch {
            $epochHoldPass = $false
        }
    }
}
$hostUartUs = $null
if ($null -ne $uartWatch) {
    $hostUartUs = [Math]::Max(1, [int]($uartWatch.Elapsed.TotalMilliseconds * 1000))
}
$postProbeExit = $null
if ($uartPass -and -not $jtagTargetUnavailable) {
    $postProbeExit = Invoke-B2StateProbe -OutPath $postProbeOut -ErrPath $postProbeErr
}
$status = if ($jtagTargetUnavailable) { 'JTAG_TARGET_UNAVAILABLE' } elseif ($applicationMode -eq 'b3_epoch_overlap' -and -not $epochHoldPass) { 'EPOCH_HOLD_MISMATCH' } elseif ($uartPass -and $xsctExitCode -eq 0 -and $xsctProgramPass -and $xsctDownloadPass) { 'PASS' } elseif ($packetText -like '*B2_PACKET_FAIL*') { 'FAIL' } else { 'NO_TERMINAL_MARKER' }
$bitstreamHash = [string]((Get-FileHash -Algorithm SHA256 -LiteralPath $bitstream).Hash)
$xsaHash = [string]((Get-FileHash -Algorithm SHA256 -LiteralPath $xsa).Hash)
$elfHash = [string]((Get-FileHash -Algorithm SHA256 -LiteralPath $elf).Hash)
$uartLogHash = [string]((Get-FileHash -Algorithm SHA256 -LiteralPath $serialLog).Hash)
$runManifest = [ordered]@{
    schema_version = 1
    generated_at = [DateTime]::UtcNow.ToString('o')
    status = $status
    application_mode = $applicationMode
    terminal_marker = $terminalMarker
    git_head = $gitHead
    port = $PortName
    usb_vid = [string]$UsbVid
    usb_pid = [string]$UsbPid
    baud = 115200
    bitstream_sha256 = $bitstreamHash
    xsa_sha256 = $xsaHash
    elf_sha256 = $elfHash
    xsct_exit_code = $xsctExitCode
    jtag_target_unavailable = $jtagTargetUnavailable
    xsct_program_pass = $xsctProgramPass
    xsct_download_pass = $xsctDownloadPass
    uart_pass = $uartPass
    uart_terminal_marker = $status
    uart_reconnects = $serialReconnects
    uart_log_sha256 = $uartLogHash
    pending_hold_probed = $pendingHoldProbed
    epoch_hold_pass = $epochHoldPass
    epoch_hold_active = $epochHoldActive
    epoch_hold_pending = $epochHoldPending
    post_probe_exit_code = $postProbeExit
    host_uart_us = $hostUartUs
}
$runManifestPath = Join-Path $runRoot 'run_manifest.json'
$runManifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $runManifestPath -Encoding utf8
Write-Output "B2_PACKET_STATUS=$status"
Write-Output "B2_PACKET_RUN_MANIFEST=$runManifestPath"
if ($status -ne 'PASS') { exit 1 }

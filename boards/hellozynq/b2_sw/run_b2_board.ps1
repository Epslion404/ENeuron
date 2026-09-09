param(
    [string]$PortName = '',
    [string]$UsbVid = '1A86',
    [string]$UsbPid = '7523',
    [int]$ListenSeconds = 20,
    [string]$XsctPath = 'G:\Xilinx\Vitis\2024.1\bin\xsct.bat',
    [string]$HwServerPath = 'G:\Xilinx\Vivado\2024.1\bin\hw_server.bat'
)

$ErrorActionPreference = 'Stop'

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

function Get-ProbeValue {
    param([string]$Text, [string]$Key)
    $match = [regex]::Match($Text, "(?m)^" + [regex]::Escape($Key) + "=(\d+)\s*$")
    if ($match.Success) { return [uint64]$match.Groups[1].Value }
    return $null
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..\..')).Path
$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
$buildRoot = Join-Path $scriptRoot (Join-Path 'build' (Join-Path $gitHead 'direct'))
$manifestPath = Join-Path $buildRoot 'build_manifest.json'
$bitstream = Join-Path $repoRoot 'boards\hellozynq\b2_hw\build\hello_zynq_b2.bit'
$xsaCopy = Join-Path $buildRoot 'hello_zynq_b2.xsa'
$ps7Init = Join-Path $buildRoot 'ps7_init.tcl'

if (-not (Test-Path -LiteralPath $manifestPath)) { throw "Run run_b2_sw_build.ps1 first: $manifestPath" }
$buildManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$elf = $buildManifest.elf
foreach ($path in @($XsctPath, $bitstream, $xsaCopy, $elf)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required file not found: $path" }
}
$actualBitstreamSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $bitstream).Hash.ToLowerInvariant()
$actualXsaSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $xsaCopy).Hash.ToLowerInvariant()
$actualElfSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $elf).Hash.ToLowerInvariant()
$expectedBitstreamSha256 = ([string]$buildManifest.bitstream_sha256).ToLowerInvariant()
$expectedXsaSha256 = ([string]$buildManifest.xsa_sha256).ToLowerInvariant()
$expectedElfSha256 = ([string]$buildManifest.elf_sha256).ToLowerInvariant()
$artifactHashErrors = @()
if ($actualBitstreamSha256 -ne $expectedBitstreamSha256) {
    $artifactHashErrors += "bitstream expected=$expectedBitstreamSha256 actual=$actualBitstreamSha256"
}
if ($actualXsaSha256 -ne $expectedXsaSha256) {
    $artifactHashErrors += "xsa expected=$expectedXsaSha256 actual=$actualXsaSha256"
}
if ($actualElfSha256 -ne $expectedElfSha256) {
    $artifactHashErrors += "elf expected=$expectedElfSha256 actual=$actualElfSha256"
}
if ($artifactHashErrors.Count -gt 0) {
    throw "B2 artifact hash mismatch: $($artifactHashErrors -join '; ')"
}

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

if (-not (Test-Path -LiteralPath $ps7Init)) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($xsaCopy)
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
$probeTcl = Join-Path $scriptRoot 'probe_b2_state.tcl'
$probeStdout = Join-Path $runRoot 'probe_stdout.log'
$probeStderr = Join-Path $runRoot 'probe_stderr.log'
$serialLog = Join-Path $runRoot 'uart.log'
$serial = Open-SerialPort $PortName
$serialReconnects = [uint32]0

$process = Start-Process -FilePath $XsctPath -ArgumentList @(
    (Join-Path $scriptRoot 'program_b2.tcl'), $bitstream, $ps7Init, $elf
) -RedirectStandardOutput $xsctStdout -RedirectStandardError $xsctStderr -WindowStyle Hidden -PassThru
$programDeadline = [DateTime]::UtcNow.AddSeconds(60)
$listenDeadline = $null
$currentRunStarted = $false
$received = [Text.StringBuilder]::new()
try {
    while ($true) {
        $xsctProgress = if (Test-Path -LiteralPath $xsctStdout) {
            [string](Get-Content -LiteralPath $xsctStdout -Raw)
        } else {
            ''
        }
        if ($null -eq $xsctProgress) { $xsctProgress = '' }
        if (-not $currentRunStarted -and $xsctProgress.Contains('B2_CPU_RUN_PASS')) {
            $currentRunStarted = $true
            $listenDeadline = [DateTime]::UtcNow.AddSeconds($ListenSeconds)
            [void]$received.Clear()
            if ($serial -and $serial.IsOpen) { $serial.DiscardInBuffer() }
        }
        if (-not $currentRunStarted -and $process.HasExited) { break }
        if (-not $currentRunStarted -and [DateTime]::UtcNow -ge $programDeadline) { break }
        if ($currentRunStarted -and [DateTime]::UtcNow -ge $listenDeadline) { break }
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
            if ($currentRunStarted) {
                [void]$received.Append($chunk)
                Write-Host -NoNewline $chunk
                if (($received.ToString().Contains('B2_PRESSURE_PASS') -and
                     $received.ToString().Contains('B2_BACKPRESSURE_PASS') -and
                     $received.ToString().Contains('B2_WRAP_PASS') -and
                     $received.ToString().Contains('B2_RECOVERY_PASS') -and
                     $received.ToString().Contains('B2_GAP_PASS') -and
                     $received.ToString().Contains('B2_DMA_PASS frames=')) -or
                    $received.ToString().Contains('B2_DMA_FAIL')) { break }
            }
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
$process.Refresh()
$uartText = $received.ToString()
$uartText | Set-Content -LiteralPath $serialLog -Encoding utf8
$xsctText = [string](Get-Content -LiteralPath $xsctStdout -Raw)
$probeExitCode = $null
$probeText = ''
if (Test-Path -LiteralPath $probeTcl) {
    & $XsctPath $probeTcl > $probeStdout 2> $probeStderr
    $probeExitCode = $LASTEXITCODE
    $probeText = if (Test-Path -LiteralPath $probeStdout) {
        [string](Get-Content -LiteralPath $probeStdout -Raw)
    } else {
        ''
    }
}
$probeReadAvailable = $probeText.Contains('B2_PROBE_MM2S_BYTES=') -and $probeText.Contains('B2_PROBE_S2MM_BYTES=')
$jtagPressureStatus = Get-ProbeValue $probeText 'B2_STATUS_PRESSURE_STATUS'
$jtagPressureTotal = Get-ProbeValue $probeText 'B2_STATUS_PRESSURE_TOTAL'
$jtagPressurePassed = Get-ProbeValue $probeText 'B2_STATUS_PRESSURE_PASSED'
$jtagPressureFailed = Get-ProbeValue $probeText 'B2_STATUS_PRESSURE_FAILED'
$jtagBackpressureStatus = Get-ProbeValue $probeText 'B2_STATUS_BACKPRESSURE_STATUS'
$jtagBackpressureTotal = Get-ProbeValue $probeText 'B2_STATUS_BACKPRESSURE_TOTAL'
$jtagBackpressurePassed = Get-ProbeValue $probeText 'B2_STATUS_BACKPRESSURE_PASSED'
$jtagBackpressureFailed = Get-ProbeValue $probeText 'B2_STATUS_BACKPRESSURE_FAILED'
$jtagBackpressureStallCycles = Get-ProbeValue $probeText 'B2_STATUS_BACKPRESSURE_STALL_CYCLES'
$jtagWrapStatus = Get-ProbeValue $probeText 'B2_STATUS_WRAP_STATUS'
$jtagWrapTotal = Get-ProbeValue $probeText 'B2_STATUS_WRAP_TOTAL'
$jtagWrapPassed = Get-ProbeValue $probeText 'B2_STATUS_WRAP_PASSED'
$jtagWrapFailed = Get-ProbeValue $probeText 'B2_STATUS_WRAP_FAILED'
$jtagWrapSlotMaskLo = Get-ProbeValue $probeText 'B2_STATUS_WRAP_SLOT_MASK_LO'
$jtagWrapSlotMaskHi = Get-ProbeValue $probeText 'B2_STATUS_WRAP_SLOT_MASK_HI'
$jtagWrapRollovers = Get-ProbeValue $probeText 'B2_STATUS_WRAP_ROLLOVERS'
$jtagWrapFirstTxAddress = Get-ProbeValue $probeText 'B2_STATUS_WRAP_FIRST_TX_ADDR'
$jtagWrapFirstRxAddress = Get-ProbeValue $probeText 'B2_STATUS_WRAP_FIRST_RX_ADDR'
$jtagWrapLastTxAddress = Get-ProbeValue $probeText 'B2_STATUS_WRAP_LAST_TX_ADDR'
$jtagWrapLastRxAddress = Get-ProbeValue $probeText 'B2_STATUS_WRAP_LAST_RX_ADDR'
$jtagRecoveryStatus = Get-ProbeValue $probeText 'B2_STATUS_RECOVERY_STATUS'
$jtagRecoveryTimeout = Get-ProbeValue $probeText 'B2_STATUS_RECOVERY_TIMEOUT'
$jtagRecoveryReset = Get-ProbeValue $probeText 'B2_STATUS_RECOVERY_RESET'
$jtagRecoveryPassed = Get-ProbeValue $probeText 'B2_STATUS_RECOVERY_PASSED'
$jtagRecoveryFailed = Get-ProbeValue $probeText 'B2_STATUS_RECOVERY_FAILED'
$jtagRecoveryReadyBefore = Get-ProbeValue $probeText 'B2_STATUS_RECOVERY_READY_BEFORE'
$jtagRecoveryReadyStopped = Get-ProbeValue $probeText 'B2_STATUS_RECOVERY_READY_STOPPED'
$jtagRecoveryReadyAfterReset = Get-ProbeValue $probeText 'B2_STATUS_RECOVERY_READY_AFTER_RESET'
$jtagGapStatus = Get-ProbeValue $probeText 'B2_STATUS_GAP_STATUS'
$jtagGapTotal = Get-ProbeValue $probeText 'B2_STATUS_GAP_TOTAL'
$jtagGapPassed = Get-ProbeValue $probeText 'B2_STATUS_GAP_PASSED'
$jtagGapFailed = Get-ProbeValue $probeText 'B2_STATUS_GAP_FAILED'
$jtagGapRequestedUs = Get-ProbeValue $probeText 'B2_STATUS_GAP_REQUESTED_US'
$jtagGapFirstSequence = Get-ProbeValue $probeText 'B2_STATUS_GAP_FIRST_SEQUENCE'
$jtagGapSecondSequence = Get-ProbeValue $probeText 'B2_STATUS_GAP_SECOND_SEQUENCE'
$jtagGapFirstLength = Get-ProbeValue $probeText 'B2_STATUS_GAP_FIRST_LENGTH'
$jtagGapSecondLength = Get-ProbeValue $probeText 'B2_STATUS_GAP_SECOND_LENGTH'
$jtagGapCrcXor = Get-ProbeValue $probeText 'B2_STATUS_GAP_CRC_XOR'
$jtagMm2sStall = Get-ProbeValue $probeText 'B2_PROBE_MM2S_STALL'
$jtagS2mmStall = Get-ProbeValue $probeText 'B2_PROBE_S2MM_STALL'
$jtagUartCr = Get-ProbeValue $probeText 'B2_UART_CR'
$jtagUartMr = Get-ProbeValue $probeText 'B2_UART_MR'
$jtagUartBaudgen = Get-ProbeValue $probeText 'B2_UART_BAUDGEN'
$jtagUartSr = Get-ProbeValue $probeText 'B2_UART_SR'
$jtagUartBauddiv = Get-ProbeValue $probeText 'B2_UART_BAUDDIV'
$jtagUartConfigured = $null -ne $jtagUartCr -and $null -ne $jtagUartMr -and
    $null -ne $jtagUartBaudgen -and $null -ne $jtagUartBauddiv -and
    (($jtagUartCr -band 0x14) -eq 0x14) -and $jtagUartMr -eq 0x20 -and
    $jtagUartBaudgen -eq 124 -and $jtagUartBauddiv -eq 6
$jtagPass = $probeExitCode -eq 0 -and $probeReadAvailable -and
    $jtagPressureStatus -eq 2 -and $jtagPressureFailed -eq 0 -and
    $jtagBackpressureStatus -eq 2 -and $jtagBackpressureFailed -eq 0 -and
    $jtagBackpressureStallCycles -gt 0 -and
    $jtagWrapStatus -eq 2 -and $jtagWrapTotal -eq 256 -and
    $jtagWrapPassed -eq 256 -and $jtagWrapFailed -eq 0 -and
    $jtagWrapSlotMaskLo -eq 4294967295 -and
    $jtagWrapSlotMaskHi -eq 4294967295 -and
    $jtagWrapRollovers -eq 3 -and
    $jtagWrapFirstTxAddress -eq 0x01006000 -and
    $jtagWrapFirstRxAddress -eq 0x01007000 -and
    $jtagWrapLastTxAddress -eq 0x01006FC0 -and
    $jtagWrapLastRxAddress -eq 0x01007FC0 -and
    $jtagRecoveryStatus -eq 2 -and
    $jtagRecoveryTimeout -eq 1 -and
    $jtagRecoveryReset -eq 1 -and
    $jtagRecoveryPassed -eq 1 -and
    $jtagRecoveryFailed -eq 0 -and
    $jtagRecoveryReadyBefore -eq 1 -and
    $jtagRecoveryReadyStopped -eq 0 -and
    $jtagRecoveryReadyAfterReset -eq 1 -and
    $jtagGapStatus -eq 2 -and
    $jtagGapTotal -eq 2 -and
    $jtagGapPassed -eq 2 -and
    $jtagGapFailed -eq 0 -and
    $jtagGapRequestedUs -eq 1000 -and
    $jtagGapFirstSequence -eq 10330 -and
    $jtagGapSecondSequence -eq 10331 -and
    $jtagGapFirstLength -eq 4 -and
    $jtagGapSecondLength -eq 64
$jtagStatus = if ($jtagPass) { 'PASS' } elseif ($probeReadAvailable) { 'FAIL' } else { 'UNAVAILABLE' }
$uartPass = $uartText.Contains('B2_PRESSURE_PASS') -and
    $uartText.Contains('B2_BACKPRESSURE_PASS') -and
    $uartText.Contains('B2_WRAP_PASS') -and
    $uartText.Contains('B2_RECOVERY_PASS') -and
    $uartText.Contains('B2_GAP_PASS') -and
    $uartText.Contains('B2_DMA_PASS frames=')
$xsctExitCode = if ($process.HasExited) { [int]$process.ExitCode } else { $null }
$status = if ($uartPass -and $jtagPass -and $xsctExitCode -eq 0 -and
    $xsctText.Contains('B2_FPGA_PROGRAM_PASS') -and
    $xsctText.Contains('B2_ELF_DOWNLOAD_PASS')) { 'PASS' } elseif ($uartText.Contains('B2_DMA_FAIL')) { 'FAIL' } else { 'NO_TERMINAL_MARKER' }
$runManifest = [ordered]@{
    schema_version = 1
    generated_at = [DateTime]::UtcNow.ToString('o')
    status = $status
    git_head = $gitHead
    port = $PortName
    port_selector = if ($PSBoundParameters.ContainsKey('PortName') -and $PSBoundParameters['PortName']) { 'explicit' } else { 'vid_pid' }
    usb_vid = $UsbVid.ToUpperInvariant()
    usb_pid = $UsbPid.ToUpperInvariant()
    baud = 115200
    bitstream_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $bitstream).Hash.ToLowerInvariant()
    xsa_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $xsaCopy).Hash.ToLowerInvariant()
    elf_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $elf).Hash.ToLowerInvariant()
    xsct_exit_code = $xsctExitCode
    xsct_program_pass = $xsctText.Contains('B2_FPGA_PROGRAM_PASS')
    xsct_download_pass = $xsctText.Contains('B2_ELF_DOWNLOAD_PASS')
    probe_exit_code = $probeExitCode
    probe_read_available = $probeReadAvailable
    jtag_status = $jtagStatus
    jtag_pressure_status = $jtagPressureStatus
    jtag_pressure_total = $jtagPressureTotal
    jtag_pressure_passed = $jtagPressurePassed
    jtag_pressure_failed = $jtagPressureFailed
    jtag_backpressure_status = $jtagBackpressureStatus
    jtag_backpressure_total = $jtagBackpressureTotal
    jtag_backpressure_passed = $jtagBackpressurePassed
    jtag_backpressure_failed = $jtagBackpressureFailed
    jtag_backpressure_stall_cycles = $jtagBackpressureStallCycles
    jtag_wrap_status = $jtagWrapStatus
    jtag_wrap_total = $jtagWrapTotal
    jtag_wrap_passed = $jtagWrapPassed
    jtag_wrap_failed = $jtagWrapFailed
    jtag_wrap_slot_mask_lo = $jtagWrapSlotMaskLo
    jtag_wrap_slot_mask_hi = $jtagWrapSlotMaskHi
    jtag_wrap_rollovers = $jtagWrapRollovers
    jtag_wrap_first_tx_address = $jtagWrapFirstTxAddress
    jtag_wrap_first_rx_address = $jtagWrapFirstRxAddress
    jtag_wrap_last_tx_address = $jtagWrapLastTxAddress
    jtag_wrap_last_rx_address = $jtagWrapLastRxAddress
    jtag_recovery_status = $jtagRecoveryStatus
    jtag_recovery_timeout = $jtagRecoveryTimeout
    jtag_recovery_reset = $jtagRecoveryReset
    jtag_recovery_passed = $jtagRecoveryPassed
    jtag_recovery_failed = $jtagRecoveryFailed
    jtag_recovery_ready_before = $jtagRecoveryReadyBefore
    jtag_recovery_ready_stopped = $jtagRecoveryReadyStopped
    jtag_recovery_ready_after_reset = $jtagRecoveryReadyAfterReset
    jtag_gap_status = $jtagGapStatus
    jtag_gap_total = $jtagGapTotal
    jtag_gap_passed = $jtagGapPassed
    jtag_gap_failed = $jtagGapFailed
    jtag_gap_requested_us = $jtagGapRequestedUs
    jtag_gap_first_sequence = $jtagGapFirstSequence
    jtag_gap_second_sequence = $jtagGapSecondSequence
    jtag_gap_first_length = $jtagGapFirstLength
    jtag_gap_second_length = $jtagGapSecondLength
    jtag_gap_crc_xor = $jtagGapCrcXor
    jtag_mm2s_stall = $jtagMm2sStall
    jtag_s2mm_stall = $jtagS2mmStall
    jtag_uart_cr = $jtagUartCr
    jtag_uart_mr = $jtagUartMr
    jtag_uart_baudgen = $jtagUartBaudgen
    jtag_uart_sr = $jtagUartSr
    jtag_uart_bauddiv = $jtagUartBauddiv
    jtag_uart_configured = $jtagUartConfigured
    probe_log_sha256 = if (Test-Path -LiteralPath $probeStdout) {
        (Get-FileHash -Algorithm SHA256 -LiteralPath $probeStdout).Hash.ToLowerInvariant()
    } else {
        $null
    }
    uart_reconnects = $serialReconnects
    uart_pass = $uartPass
    uart_terminal_marker = $status
    uart_log_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $serialLog).Hash.ToLowerInvariant()
}
$runManifestPath = Join-Path $runRoot 'run_manifest.json'
$runManifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $runManifestPath -Encoding utf8
Write-Output "B2_BOARD_STATUS=$status"
Write-Output "B2_JTAG_STATUS=$jtagStatus"
Write-Output "B2_RUN_MANIFEST=$runManifestPath"
if ($status -ne 'PASS' -or $process.ExitCode -ne 0 -or -not $runManifest.xsct_program_pass -or -not $runManifest.xsct_download_pass) { exit 1 }

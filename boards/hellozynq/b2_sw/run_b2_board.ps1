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
$deadline = [DateTime]::UtcNow.AddSeconds($ListenSeconds)
$received = [Text.StringBuilder]::new()
try {
    while ([DateTime]::UtcNow -lt $deadline) {
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
            if ($received.ToString().Contains('B2_PRESSURE_PASS') -or
                $received.ToString().Contains('B2_DMA_FAIL')) { break }
        }
        Start-Sleep -Milliseconds 50
    }
} finally {
    if ($serial) {
        if ($serial.IsOpen) { $serial.Close() }
        $serial.Dispose()
    }
}

if (-not $process.WaitForExit(10000)) { $process.Kill(); throw 'XSCT programming process did not exit' }
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
$status = if ($uartText.Contains('B2_DMA_PASS')) { 'PASS' } elseif ($uartText.Contains('B2_DMA_FAIL')) { 'FAIL' } else { 'NO_TERMINAL_MARKER' }
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
    xsct_exit_code = $process.ExitCode
    xsct_program_pass = $xsctText.Contains('B2_FPGA_PROGRAM_PASS')
    xsct_download_pass = $xsctText.Contains('B2_ELF_DOWNLOAD_PASS')
    probe_exit_code = $probeExitCode
    probe_read_available = $probeText.Contains('B2_PROBE_MM2S_BYTES=') -and $probeText.Contains('B2_PROBE_S2MM_BYTES=')
    probe_log_sha256 = if (Test-Path -LiteralPath $probeStdout) {
        (Get-FileHash -Algorithm SHA256 -LiteralPath $probeStdout).Hash.ToLowerInvariant()
    } else {
        $null
    }
    uart_reconnects = $serialReconnects
    uart_terminal_marker = $status
    uart_log_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $serialLog).Hash.ToLowerInvariant()
}
$runManifestPath = Join-Path $runRoot 'run_manifest.json'
$runManifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $runManifestPath -Encoding utf8
Write-Output "B2_BOARD_STATUS=$status"
Write-Output "B2_RUN_MANIFEST=$runManifestPath"
if ($status -ne 'PASS' -or $process.ExitCode -ne 0 -or -not $runManifest.xsct_program_pass -or -not $runManifest.xsct_download_pass) { exit 1 }

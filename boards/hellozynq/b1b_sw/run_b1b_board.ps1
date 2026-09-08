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
    if ($RequestedPort) {
        return $RequestedPort
    }
    $vidToken = $Vid.ToUpperInvariant()
    $pidToken = $ProductId.ToUpperInvariant()
    $matches = @(Get-PnpDevice -PresentOnly -Class Ports -ErrorAction SilentlyContinue | Where-Object {
        $_.InstanceId -match "VID_$vidToken&PID_$pidToken" -and $_.FriendlyName -match '\((COM\d+)\)'
    })
    if ($matches.Count -ne 1) {
        throw "Expected exactly one USB serial device VID_$vidToken`&PID_$pidToken, found $($matches.Count)"
    }
    return ([regex]::Match($matches[0].FriendlyName, '\((COM\d+)\)')).Groups[1].Value
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..\..')).Path
$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
$buildRoot = Join-Path $scriptRoot (Join-Path 'build' (Join-Path $gitHead 'direct'))
$manifestPath = Join-Path $buildRoot 'build_manifest.json'
$bitstream = Join-Path $repoRoot 'boards\hellozynq\b1a_hw\build\hello_zynq_b1a.bit'
$xsaCopy = Join-Path $buildRoot 'hello_zynq_b1a.xsa'
$ps7Init = Join-Path $buildRoot 'ps7_init.tcl'

if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Run run_b1b_build.ps1 first: $manifestPath"
}
$buildManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$elf = $buildManifest.elf
foreach ($path in @($XsctPath, $bitstream, $xsaCopy, $elf)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required file not found: $path"
    }
}

$serverReady = $false
try {
    $client = [Net.Sockets.TcpClient]::new('127.0.0.1', 3121)
    $client.Dispose()
    $serverReady = $true
} catch {
    if (-not (Test-Path -LiteralPath $HwServerPath)) {
        throw "hw_server not found: $HwServerPath"
    }
    Start-Process -FilePath $HwServerPath -ArgumentList '-s', 'tcp::3121' -WindowStyle Hidden | Out-Null
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while (-not $serverReady -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 250
        try {
            $client = [Net.Sockets.TcpClient]::new('127.0.0.1', 3121)
            $client.Dispose()
            $serverReady = $true
        } catch {
        }
    }
}
if (-not $serverReady) {
    throw 'hw_server did not start on tcp:3121'
}

if (-not (Test-Path -LiteralPath $ps7Init)) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($xsaCopy)
    try {
        $entry = $archive.GetEntry('ps7_init.tcl')
        if (-not $entry) {
            throw 'ps7_init.tcl is absent from XSA'
        }
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $ps7Init, $false)
    } finally {
        $archive.Dispose()
    }
}

$runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$runRoot = Join-Path $buildRoot (Join-Path 'runs' $runId)
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
$PortName = Resolve-SerialPortName $PortName $UsbVid $UsbPid
$xsctStdout = Join-Path $runRoot 'xsct_stdout.log'
$xsctStderr = Join-Path $runRoot 'xsct_stderr.log'
$serialLog = Join-Path $runRoot 'uart.log'

$serial = [System.IO.Ports.SerialPort]::new($PortName, 115200, 'None', 8, 'One')
$serial.ReadTimeout = 100
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.Open()

$arguments = @(
    (Join-Path $scriptRoot 'program_b1b.tcl'),
    $bitstream,
    $ps7Init,
    $elf
)
$process = Start-Process -FilePath $XsctPath -ArgumentList $arguments -RedirectStandardOutput $xsctStdout -RedirectStandardError $xsctStderr -WindowStyle Hidden -PassThru
$deadline = [DateTime]::UtcNow.AddSeconds($ListenSeconds)
$received = [Text.StringBuilder]::new()
try {
    while ([DateTime]::UtcNow -lt $deadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk.Length -gt 0) {
            [void]$received.Append($chunk)
            Write-Host -NoNewline $chunk
            if ($received.ToString().Contains('ENEURON_B1B_PASS') -or $received.ToString().Contains('ENEURON_B1B_FAIL')) {
                break
            }
        }
        Start-Sleep -Milliseconds 50
    }
} finally {
    $serial.Close()
}

if (-not $process.WaitForExit(10000)) {
    $process.Kill()
    throw 'XSCT programming process did not exit'
}
$process.Refresh()
$uartText = $received.ToString()
$uartText | Set-Content -LiteralPath $serialLog -Encoding utf8
$xsctText = [string](Get-Content -LiteralPath $xsctStdout -Raw)
$xsctErrorText = [string](Get-Content -LiteralPath $xsctStderr -Raw)
if ($null -eq $xsctText) {
    $xsctText = ''
}
if ($null -eq $xsctErrorText) {
    $xsctErrorText = ''
}

$status = if ($uartText.Contains('ENEURON_B1B_PASS')) { 'PASS' } elseif ($uartText.Contains('ENEURON_B1B_FAIL')) { 'FAIL' } else { 'NO_TERMINAL_MARKER' }
$xsctProgramPass = $xsctText.Contains('B1B_FPGA_PROGRAM_PASS')
$xsctDownloadPass = $xsctText.Contains('B1B_ELF_DOWNLOAD_PASS')
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
    bitstream_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $bitstream).Hash.ToLower()
    xsa_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $xsaCopy).Hash.ToLower()
    elf_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $elf).Hash.ToLower()
    xsct_exit_code = $process.ExitCode
    xsct_program_pass = $xsctProgramPass
    xsct_download_pass = $xsctDownloadPass
    uart_terminal_marker = $status
    uart_log_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $serialLog).Hash.ToLower()
}
$runManifestPath = Join-Path $runRoot 'run_manifest.json'
$runManifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $runManifestPath -Encoding utf8

Write-Output "`nB1B_BOARD_STATUS=$status"
Write-Output "B1B_XSCT_EXIT_CODE=$($process.ExitCode)"
Write-Output "B1B_FPGA_PROGRAM_STATUS=$(if ($xsctProgramPass) { 'PASS' } else { 'FAIL' })"
Write-Output "B1B_ELF_DOWNLOAD_STATUS=$(if ($xsctDownloadPass) { 'PASS' } else { 'FAIL' })"
Write-Output "B1B_RUN_MANIFEST=$runManifestPath"
if ($xsctErrorText.Trim().Length -gt 0) {
    Write-Output 'B1B_XSCT_STDERR_BEGIN'
    Write-Output $xsctErrorText
    Write-Output 'B1B_XSCT_STDERR_END'
}
if ($status -ne 'PASS' -or
    $process.ExitCode -ne 0 -or
    -not $xsctProgramPass -or
    -not $xsctDownloadPass) {
    exit 1
}

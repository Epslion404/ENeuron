param(
    [string]$PortName = 'COM10',
    [int]$ListenSeconds = 20,
    [string]$XsctPath = 'G:\Xilinx\Vitis\2024.1\bin\xsct.bat',
    [string]$HwServerPath = 'G:\Xilinx\Vivado\2024.1\bin\hw_server.bat'
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..\..')).Path
$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
$buildRoot = Join-Path $scriptRoot (Join-Path 'build' (Join-Path $gitHead 'high_diag'))
$manifestPath = Join-Path $buildRoot 'build_manifest.json'
$bitstream = Join-Path $repoRoot 'boards\hellozynq\b1a_hw\build\hello_zynq_b1a.bit'
$xsaCopy = Join-Path $buildRoot 'hello_zynq_b1a.xsa'
$ps7Init = Join-Path $buildRoot 'ps7_init.tcl'

if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Run run_b1b_high_diag_build.ps1 first: $manifestPath"
}
$buildManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$elf = $buildManifest.elf
$source = Join-Path $scriptRoot 'src\high_diag.c'
$linker = Join-Path $scriptRoot 'ocm_high_diag.ld'
foreach ($path in @($XsctPath, $bitstream, $xsaCopy, $elf, $source, $linker)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required file not found: $path"
    }
}
if ($buildManifest.git_head -ne $gitHead) {
    throw 'High diagnostic build manifest Git HEAD does not match the current checkout'
}
if (-not $buildManifest.git_worktree_clean) {
    throw 'High diagnostic ELF was not built from a clean worktree'
}
if ([bool](& git -C $repoRoot status --porcelain --untracked-files=all)) {
    throw 'Current worktree is not clean; commit the diagnostic sources and rebuild before board access'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $elf).Hash.ToLower() -ne $buildManifest.elf_sha256) {
    throw 'High diagnostic ELF hash does not match build manifest'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $bitstream).Hash.ToLower() -ne $buildManifest.bitstream_sha256) {
    throw 'B1A bitstream hash does not match high diagnostic build manifest'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $xsaCopy).Hash.ToLower() -ne $buildManifest.xsa_sha256) {
    throw 'B1A XSA hash does not match high diagnostic build manifest'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLower() -ne $buildManifest.source_sha256) {
    throw 'High diagnostic source hash does not match build manifest'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $linker).Hash.ToLower() -ne $buildManifest.linker_sha256) {
    throw 'High diagnostic linker hash does not match build manifest'
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
$programStdout = Join-Path $runRoot 'program_stdout.log'
$programStderr = Join-Path $runRoot 'program_stderr.log'
$armStdout = Join-Path $runRoot 'arm_stdout.log'
$armStderr = Join-Path $runRoot 'arm_stderr.log'
$armResult = Join-Path $runRoot 'ocm_preflight.txt'
$probeStdout = Join-Path $runRoot 'probe_stdout.log'
$probeStderr = Join-Path $runRoot 'probe_stderr.log'
$probeResult = Join-Path $runRoot 'ocm_cpu_result.txt'
$serialLog = Join-Path $runRoot 'uart.log'

$serial = [System.IO.Ports.SerialPort]::new($PortName, 115200, 'None', 8, 'One')
$serial.ReadTimeout = 100
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$received = [Text.StringBuilder]::new()
$programProcess = $null
$armProcess = $null
$programExitCode = -1
$armExitCode = -1
$probeExitCode = -1
$runError = $null
try {
    $serial.Open()
    $arguments = @((Join-Path $scriptRoot 'program_b1b.tcl'), $bitstream, $ps7Init, $elf)
    $programProcess = Start-Process -FilePath $XsctPath -ArgumentList $arguments -RedirectStandardOutput $programStdout -RedirectStandardError $programStderr -WindowStyle Hidden -PassThru
    $readyDeadline = [DateTime]::UtcNow.AddSeconds(10)
    $ready = $false
    while ([DateTime]::UtcNow -lt $readyDeadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk.Length -gt 0) {
            [void]$received.Append($chunk)
            Write-Host -NoNewline $chunk
            if ($received.ToString().Contains('ENEURON_B1B_HIGH_DIAG_READY')) {
                $ready = $true
                break
            }
        }
        Start-Sleep -Milliseconds 50
    }

    if ($programProcess -and -not $programProcess.WaitForExit(10000)) {
        $programProcess.Kill()
        throw 'XSCT programming process did not exit'
    }
    if ($programProcess) {
        $programExitCode = $programProcess.ExitCode
    }
    if (-not $ready) {
        throw 'OCM diagnostic did not reach READY before DDR access'
    }

    $armArguments = @((Join-Path $scriptRoot 'arm_b1b_high_diag.tcl'), $armResult)
    $armProcess = Start-Process -FilePath $XsctPath -ArgumentList $armArguments -RedirectStandardOutput $armStdout -RedirectStandardError $armStderr -WindowStyle Hidden -PassThru -Wait
    $armExitCode = $armProcess.ExitCode
    if ($armProcess.ExitCode -ne 0) {
        throw "OCM preflight/GO failed with exit code $($armProcess.ExitCode)"
    }

    $resultDeadline = [DateTime]::UtcNow.AddSeconds($ListenSeconds)
    while ([DateTime]::UtcNow -lt $resultDeadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk.Length -gt 0) {
            [void]$received.Append($chunk)
            Write-Host -NoNewline $chunk
            $text = $received.ToString()
            if ($text.Contains('ENEURON_B1B_HIGH_DIAG_PASS') -or $text.Contains('ENEURON_B1B_HIGH_DIAG_FAIL')) {
                break
            }
        }
        Start-Sleep -Milliseconds 50
    }
} catch {
    $runError = $_.Exception.Message
} finally {
    if ($serial.IsOpen) {
        $serial.Close()
    }
}

$received.ToString() | Set-Content -LiteralPath $serialLog -Encoding utf8

$probeProcess = $null
try {
    $probeArguments = @((Join-Path $scriptRoot 'probe_b1b_high_diag.tcl'), $probeResult)
    $probeProcess = Start-Process -FilePath $XsctPath -ArgumentList $probeArguments -RedirectStandardOutput $probeStdout -RedirectStandardError $probeStderr -WindowStyle Hidden -PassThru -Wait
    $probeExitCode = $probeProcess.ExitCode
} catch {
    if (-not $runError) {
        $runError = "OCM/CPU probe failed: $($_.Exception.Message)"
    }
}
$probeText = if (Test-Path -LiteralPath $probeResult) { [string](Get-Content -LiteralPath $probeResult -Raw) } else { '' }
$uartText = $received.ToString()
$programText = if (Test-Path -LiteralPath $programStdout) { [string](Get-Content -LiteralPath $programStdout -Raw) } else { '' }
$programExitCode = if ($programProcess) { $programProcess.ExitCode } else { $programExitCode }
$armExitCode = if ($armProcess) { $armProcess.ExitCode } else { $armExitCode }
$status = if ($uartText.Contains('ENEURON_B1B_HIGH_DIAG_PASS')) { 'PASS' } elseif ($uartText.Contains('ENEURON_B1B_HIGH_DIAG_FAIL')) { 'FAIL' } else { 'NO_TERMINAL_MARKER' }
$ocmStatus = if ($probeText -match 'B1B_HIGH_STATUS=(\d+)') { [int]$Matches[1] } else { -1 }
$programPass = $programText.Contains('B1B_FPGA_PROGRAM_PASS')
$downloadPass = $programText.Contains('B1B_ELF_DOWNLOAD_PASS')

$runManifest = [ordered]@{
    schema_version = 1
    generated_at = [DateTime]::UtcNow.ToString('o')
    status = $status
    git_head = $gitHead
    protocol = 'B1B_HIGH_DIAG_V1'
    port = $PortName
    bitstream_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $bitstream).Hash.ToLower()
    xsa_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $xsaCopy).Hash.ToLower()
    elf_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $elf).Hash.ToLower()
    program_exit_code = $programExitCode
    arm_exit_code = $armExitCode
    probe_exit_code = $probeExitCode
    runner_error = $runError
    program_pass = $programPass
    download_pass = $downloadPass
    ocm_status = $ocmStatus
    uart_log_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $serialLog).Hash.ToLower()
    ocm_cpu_result_sha256 = if (Test-Path -LiteralPath $probeResult) { (Get-FileHash -Algorithm SHA256 -LiteralPath $probeResult).Hash.ToLower() } else { $null }
    ocm_preflight_sha256 = if (Test-Path -LiteralPath $armResult) { (Get-FileHash -Algorithm SHA256 -LiteralPath $armResult).Hash.ToLower() } else { $null }
}
$runManifestPath = Join-Path $runRoot 'run_manifest.json'
$runManifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $runManifestPath -Encoding utf8

Write-Output "`nB1B_HIGH_DIAG_BOARD_STATUS=$status"
Write-Output "B1B_HIGH_DIAG_OCM_STATUS=$ocmStatus"
Write-Output "B1B_HIGH_DIAG_PROGRAM_STATUS=$(if ($programPass) { 'PASS' } else { 'FAIL' })"
Write-Output "B1B_HIGH_DIAG_DOWNLOAD_STATUS=$(if ($downloadPass) { 'PASS' } else { 'FAIL' })"
Write-Output "B1B_HIGH_DIAG_RUN_MANIFEST=$runManifestPath"
if ($runError -or $status -ne 'PASS' -or $ocmStatus -ne 2 -or -not $programPass -or -not $downloadPass -or $armExitCode -ne 0 -or $probeExitCode -ne 0) {
    exit 1
}

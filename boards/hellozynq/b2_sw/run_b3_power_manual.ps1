param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('b3_idle', 'b3_dense', 'b3_static_mixed', 'b3_live_eneuron')]
    [string]$Mode,
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 1000)]
    [int]$Round,
    [ValidateRange(300, 86400)]
    [int]$WindowSeconds = 600,
    [ValidateRange(5, 300)]
    [int]$StartDelaySeconds = 30,
    [ValidateRange(1000, 1000000)]
    [int]$WarmupSamples = 1000,
    [ValidateRange(10000, 1000000000)]
    [int]$MinimumValidInferences = 10000,
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$InstrumentModel,
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$InstrumentAccuracy,
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$PowerSource,
    [string]$EvidenceRoot,
    [string]$XsctPath = 'G:\Xilinx\Vitis\2024.1\bin\xsct.bat',
    [string]$HwServerPath = 'G:\Xilinx\Vivado\2024.1\bin\unwrapped\win64.o\hw_server.exe'
)

$ErrorActionPreference = 'Stop'
# Vivado 2024.1 默认禁用 FTDI/Digilent 后端；显式启用，避免依赖外部 shell 环境。
$env:HW_SERVER_FTDIMGR_DISABLE = '0'
$env:HW_SERVER_DJTG_DISABLE = '0'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot '..\..\..')).Path
if ([string]::IsNullOrWhiteSpace($EvidenceRoot)) {
    $EvidenceRoot = Join-Path $repoRoot 'artifacts\logs\b3_power_manual'
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Confirm-JtagPhysicalConnection {
    $answer = Read-Host 'Confirm the physical JTAG connection is unchanged for all rounds. Type YES'
    if ($answer -cne 'YES') {
        throw 'The physical JTAG connection was not confirmed'
    }
    return $true
}

function Read-DisplayedDecimal([string]$Label) {
    $value = (Read-Host "$Label (enter exactly one integer digit and five fractional digits, for example 5.00000)").Trim()
    if ($value -notmatch '^\d\.\d{5}$') {
        throw "$Label does not match the six-digit meter display: $value"
    }
    return $value
}

function Read-DisplayedInteger([string]$Label) {
    $value = (Read-Host "$Label (enter one to seven integer digits without units)").Trim()
    if ($value -notmatch '^\d{1,7}$') {
        throw "$Label does not match the integer meter display: $value"
    }
    return $value
}

function Resolve-Photo([string]$Label) {
    $path = (Read-Host "$Label photo path").Trim()
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "$Label photo does not exist: $path"
    }
    return (Resolve-Path -LiteralPath $path).Path
}

function Read-MeterObservation(
    [string]$Kind,
    [int]$ElapsedSeconds,
    [bool]$IncludeCumulative,
    [bool]$IncludePhoto
) {
    Write-Host "Record $Kind at scheduled window time ${ElapsedSeconds}s"
    $row = [ordered]@{
        kind = $Kind
        scheduled_elapsed_seconds = $ElapsedSeconds
        observed_at_utc = [DateTime]::UtcNow.ToString('o')
        voltage_v = Read-DisplayedDecimal 'V'
        current_a = Read-DisplayedDecimal 'A'
        power_w = Read-DisplayedDecimal 'W'
        mah = ''
        mwh = ''
        photo = ''
    }
    if ($IncludeCumulative) {
        $row.mah = Read-DisplayedInteger 'mAh'
        $row.mwh = Read-DisplayedInteger 'mWh'
    }
    if ($IncludePhoto) {
        $row.photo = Resolve-Photo $Kind
    }
    return [pscustomobject]$row
}

function Assert-NoExistingJtagService {
    $existing = @(Get-Process -Name 'xsct','hw_server' -ErrorAction SilentlyContinue)
    if ($existing.Count -gt 0) {
        $description = ($existing | ForEach-Object { "$($_.ProcessName):$($_.Id)" }) -join ', '
        throw "Existing JTAG service detected; formal measurement will not take ownership: $description"
    }
}

function Start-OwnedHwServer {
    if (-not (Test-Path -LiteralPath $HwServerPath -PathType Leaf)) {
        throw "hw_server not found: $HwServerPath"
    }
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $HwServerPath
    $startInfo.Arguments = '-s tcp::3121'
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.EnvironmentVariables['HW_SERVER_FTDIMGR_DISABLE'] = '0'
    $startInfo.EnvironmentVariables['HW_SERVER_DJTG_DISABLE'] = '0'
    $ownedHwServer = [Diagnostics.Process]::Start($startInfo)
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds(10)
        while ([DateTime]::UtcNow -lt $deadline) {
            if ($ownedHwServer.HasExited) {
                throw "Owned hw_server exited early, exit=$($ownedHwServer.ExitCode)"
            }
            try {
                $client = [Net.Sockets.TcpClient]::new('127.0.0.1', 3121)
                $client.Dispose()
                return $ownedHwServer
            } catch {
                Start-Sleep -Milliseconds 250
            }
        }
        throw 'Owned hw_server did not become ready on tcp:3121'
    } catch {
        if ($null -ne $ownedHwServer -and -not $ownedHwServer.HasExited) {
            Stop-Process -Id $ownedHwServer.Id -Force
            Wait-Process -Id $ownedHwServer.Id -Timeout 10 -ErrorAction SilentlyContinue
        }
        throw
    }
}

function Stop-OwnedHwServer([Diagnostics.Process]$ownedHwServer) {
    if ($null -ne $ownedHwServer -and -not $ownedHwServer.HasExited) {
        Stop-Process -Id $ownedHwServer.Id -Force
        Wait-Process -Id $ownedHwServer.Id -Timeout 10 -ErrorAction SilentlyContinue
    }
}

function Assert-JtagToolsSilent {
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $active = @(Get-Process -Name 'xsct','hw_server' -ErrorAction SilentlyContinue)
        if ($active.Count -eq 0) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'XSCT/hw_server did not stop before the integration window'
}

function Invoke-Xsct(
    [string]$TclPath,
    [string[]]$Arguments,
    [string]$StdoutPath,
    [string]$StderrPath
) {
    $argumentList = @($TclPath)
    $argumentList += $Arguments
    $process = Start-Process -FilePath $XsctPath -ArgumentList $argumentList `
        -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath `
        -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(180000)) {
        $process.Kill()
        throw "XSCT timed out: $TclPath"
    }
    if ($process.ExitCode -ne 0) {
        $stderr = if (Test-Path -LiteralPath $StderrPath) { Get-Content -LiteralPath $StderrPath -Raw } else { '' }
        throw "XSCT failed, exit=$($process.ExitCode): $stderr"
    }
    return [string](Get-Content -LiteralPath $StdoutPath -Raw)
}

function Get-XsctU32([string]$Text, [string]$Name) {
    $match = [regex]::Match($Text, "(?m)^$([regex]::Escape($Name))=(0x[0-9A-Fa-f]+|\d+)\s*$")
    if (-not $match.Success) { throw "XSCT output is missing $Name" }
    $value = $match.Groups[1].Value
    if ($value.StartsWith('0x', [StringComparison]::OrdinalIgnoreCase)) {
        return [Convert]::ToUInt32($value.Substring(2), 16)
    }
    return [Convert]::ToUInt32($value, 10)
}

function Wait-UntilUtc([DateTime]$Target) {
    while ([DateTime]::UtcNow -lt $Target) {
        $remaining = ($Target - [DateTime]::UtcNow).TotalSeconds
        Start-Sleep -Milliseconds ([Math]::Max(50, [Math]::Min(500, [int]($remaining * 1000))))
    }
}

$forwardOrder = @('b3_idle', 'b3_dense', 'b3_static_mixed', 'b3_live_eneuron')
$reverseOrder = @('b3_live_eneuron', 'b3_static_mixed', 'b3_dense', 'b3_idle')
$campaignCsv = Join-Path $EvidenceRoot 'manual_power.csv'
$existingRows = if (Test-Path -LiteralPath $campaignCsv) { @(Import-Csv -LiteralPath $campaignCsv) } else { @() }
$expectedRound = [int]([Math]::Floor($existingRows.Count / 4) + 1)
$expectedIndex = $existingRows.Count % 4
$expectedOrder = if (($expectedRound % 2) -eq 1) { $forwardOrder } else { $reverseOrder }
if ($Round -ne $expectedRound -or $Mode -ne $expectedOrder[$expectedIndex]) {
    throw "The next window must be round=$expectedRound mode=$($expectedOrder[$expectedIndex])"
}

$contractPath = Join-Path $repoRoot 'tools\repro\b3_power_instrument_contract.json'
$contract = Get-Content -LiteralPath $contractPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($contract.schema -ne 'eneuron_b3_power_instrument_contract_v2' -or
    [int]$contract.minimum_duration_seconds -ne 300 -or
    [int]$contract.minimum_valid_inferences -ne 10000 -or
    [int]$contract.minimum_delta_mwh -ne 200) {
    throw 'B3 manual power contract does not match the frozen thresholds'
}

$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
$gitStatus = @(& git -C $repoRoot status --porcelain --untracked-files=no)
if ($gitStatus.Count -ne 0) { throw 'Formal power measurement requires a clean tracked worktree' }
$buildRoot = Join-Path $scriptRoot (Join-Path 'build' (Join-Path $gitHead 'direct'))
$manifestPath = Join-Path $buildRoot 'packet_build_manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Run run_b2_packet_sw_build.ps1 -B3PowerBench first: $manifestPath"
}
$buildManifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($buildManifest.application_mode -ne 'b3_power_bench' -or -not [bool]$buildManifest.git_tracked_worktree_clean) {
    throw 'Power benchmark manifest is not a clean b3_power_bench build'
}
$bitstream = [string]$buildManifest.bitstream
$xsa = [string]$buildManifest.xsa
$elf = [string]$buildManifest.elf
$packetSource = Join-Path $scriptRoot 'src\packet_main.c'
foreach ($item in @(
    @{ Path = $bitstream; Hash = [string]$buildManifest.bitstream_sha256 },
    @{ Path = $xsa; Hash = [string]$buildManifest.xsa_sha256 },
    @{ Path = $elf; Hash = [string]$buildManifest.elf_sha256 },
    @{ Path = $packetSource; Hash = [string]$buildManifest.packet_source_sha256 }
)) {
    if (-not (Test-Path -LiteralPath $item.Path -PathType Leaf) -or (Get-Sha256 $item.Path) -ne $item.Hash.ToLowerInvariant()) {
        throw "Power measurement artifact identity mismatch: $($item.Path)"
    }
}

$ps7Init = Join-Path $buildRoot 'ps7_init.tcl'
if (-not (Test-Path -LiteralPath $ps7Init -PathType Leaf)) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($xsa)
    try {
        $entry = $archive.GetEntry('ps7_init.tcl')
        if (-not $entry) { throw 'ps7_init.tcl is absent from the XSA' }
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $ps7Init, $false)
    } finally {
        $archive.Dispose()
    }
}

[void](Confirm-JtagPhysicalConnection)
Assert-NoExistingJtagService
New-Item -ItemType Directory -Path $EvidenceRoot -Force | Out-Null
$timestamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$runRoot = Join-Path $EvidenceRoot ('round_{0:D2}_{1}_{2}' -f $Round, $Mode, $timestamp)
if (Test-Path -LiteralPath $runRoot) { throw "Evidence directory already exists: $runRoot" }
New-Item -ItemType Directory -Path $runRoot | Out-Null

$startOut = Join-Path $runRoot 'start_xsct_stdout.log'
$startErr = Join-Path $runRoot 'start_xsct_stderr.log'
$probeOut = Join-Path $runRoot 'result_xsct_stdout.log'
$probeErr = Join-Path $runRoot 'result_xsct_stderr.log'
$traceCsv = Join-Path $runRoot 'meter_trace.csv'
$runManifestPath = Join-Path $runRoot 'run_manifest.json'
$modeId = @{ b3_idle = 0; b3_dense = 1; b3_static_mixed = 2; b3_live_eneuron = 3 }[$Mode]
$requestedWarmup = if ($Mode -eq 'b3_idle') { 0 } else { $WarmupSamples }
$requestedMinimum = if ($Mode -eq 'b3_idle') { 0 } else { $MinimumValidInferences }

$ownedHwServer = $null
try {
    $ownedHwServer = Start-OwnedHwServer
    $startText = Invoke-Xsct `
        -TclPath (Join-Path $scriptRoot 'start_b3_power_window.tcl') `
        -Arguments @($bitstream, $ps7Init, $elf, $Mode, $requestedWarmup, $WindowSeconds, $StartDelaySeconds, $requestedMinimum) `
        -StdoutPath $startOut -StderrPath $startErr
} finally {
    Stop-OwnedHwServer $ownedHwServer
}
Assert-JtagToolsSilent
if ($startText -notlike '*B3_POWER_READY_PASS*' -or $startText -notlike '*B3_POWER_GO_WRITE_PASS*') {
    throw 'Start Tcl did not confirm both READY and GO'
}
$goEpoch = Get-XsctU32 $startText 'B3_POWER_GO_EPOCH_SECONDS'
$windowStartUtc = [DateTimeOffset]::FromUnixTimeSeconds($goEpoch).UtcDateTime.AddSeconds($StartDelaySeconds)
$windowEndUtc = $windowStartUtc.AddSeconds($WindowSeconds)

Write-Host "GO written and hw_server/XSCT stopped. Window start UTC: $($windowStartUtc.ToString('o'))"
Wait-UntilUtc $windowStartUtc
Write-Host 'Window started. Photograph the meter now and enter the start readings from the photo.'
$trace = @()
$startObservation = Read-MeterObservation -Kind 'start' -ElapsedSeconds 0 -IncludeCumulative $true -IncludePhoto $true
$trace += $startObservation
for ($elapsed = 60; $elapsed -lt $WindowSeconds; $elapsed += 60) {
    Wait-UntilUtc $windowStartUtc.AddSeconds($elapsed)
    $trace += Read-MeterObservation -Kind 'minute' -ElapsedSeconds $elapsed -IncludeCumulative $false -IncludePhoto $false
}
Wait-UntilUtc $windowEndUtc
Write-Host 'Window ended. Photograph the meter now and enter the end readings from the photo.'
$endObservation = Read-MeterObservation -Kind 'end' -ElapsedSeconds $WindowSeconds -IncludeCumulative $true -IncludePhoto $true
$trace += $endObservation
$trace | Export-Csv -LiteralPath $traceCsv -NoTypeInformation -Encoding utf8

Assert-NoExistingJtagService
try {
    $ownedHwServer = Start-OwnedHwServer
    $probeText = Invoke-Xsct -TclPath (Join-Path $scriptRoot 'probe_b3_power_result.tcl') `
        -Arguments @() -StdoutPath $probeOut -StderrPath $probeErr
} finally {
    Stop-OwnedHwServer $ownedHwServer
}
Assert-JtagToolsSilent

$result = [ordered]@{
    magic = Get-XsctU32 $probeText 'B3_POWER_RESULT_MAGIC'
    schema_version = Get-XsctU32 $probeText 'B3_POWER_RESULT_SCHEMA_VERSION'
    status = Get-XsctU32 $probeText 'B3_POWER_RESULT_STATUS'
    mode = Get-XsctU32 $probeText 'B3_POWER_RESULT_MODE'
    warmup_completed = Get-XsctU32 $probeText 'B3_POWER_WARMUP_COMPLETED'
    valid_inferences = Get-XsctU32 $probeText 'B3_POWER_VALID_INFERENCES'
    failed_inferences = Get-XsctU32 $probeText 'B3_POWER_FAILED_INFERENCES'
    protocol_error_count = Get-XsctU32 $probeText 'B3_POWER_PROTOCOL_ERROR_COUNT'
    elapsed_seconds = Get-XsctU32 $probeText 'B3_POWER_ELAPSED_SECONDS'
    last_compute_cycles = Get-XsctU32 $probeText 'B3_POWER_LAST_COMPUTE_CYCLES'
    execute_group_count = Get-XsctU32 $probeText 'B3_POWER_EXECUTE_GROUP_COUNT'
    skip_group_count = Get-XsctU32 $probeText 'B3_POWER_SKIP_GROUP_COUNT'
    last_sequence = Get-XsctU32 $probeText 'B3_POWER_LAST_SEQUENCE'
    error_code = Get-XsctU32 $probeText 'B3_POWER_ERROR_CODE'
}
$resultPass = $result.magic -eq 0x33534552 -and $result.schema_version -eq 1 -and `
    $result.status -eq 4 -and $result.mode -eq $modeId -and `
    $result.failed_inferences -eq 0 -and $result.protocol_error_count -eq 0 -and `
    $result.error_code -eq 0 -and $result.elapsed_seconds -ge $WindowSeconds -and `
    (($Mode -eq 'b3_idle' -and $result.valid_inferences -eq 0) -or `
     ($Mode -ne 'b3_idle' -and $result.valid_inferences -ge $MinimumValidInferences))

$startMwh = [int]$startObservation.mwh
$endMwh = [int]$endObservation.mwh
$deltaMwh = $endMwh - $startMwh
$measurementPass = $resultPass -and $deltaMwh -ge 200
$runManifest = [ordered]@{
    schema = 'eneuron_b3_manual_power_window_v2'
    generated_at = [DateTime]::UtcNow.ToString('o')
    status = if ($measurementPass) { 'PASS' } elseif (-not $resultPass) { 'BOARD_RESULT_FAIL' } else { 'INSUFFICIENT_ENERGY_DELTA' }
    round = $Round
    mode = $Mode
    instrument_model = $InstrumentModel
    instrument_accuracy = $InstrumentAccuracy
    power_source = $PowerSource
    jtag_physically_connected = $true
    xsct_active_during_window = $false
    hw_server_active_during_window = $false
    scan_active_during_window = $false
    window_start_utc = $windowStartUtc.ToString('o')
    window_end_utc = $windowEndUtc.ToString('o')
    window_seconds = $WindowSeconds
    delta_mwh = $deltaMwh
    git_head = $gitHead
    bitstream_sha256 = Get-Sha256 $bitstream
    xsa_sha256 = Get-Sha256 $xsa
    elf_sha256 = Get-Sha256 $elf
    packet_source_sha256 = Get-Sha256 $packetSource
    contract_sha256 = Get-Sha256 $contractPath
    meter_trace_csv = $traceCsv
    meter_trace_sha256 = Get-Sha256 $traceCsv
    start_photo_sha256 = Get-Sha256 $startObservation.photo
    end_photo_sha256 = Get-Sha256 $endObservation.photo
    result = $result
}
$runManifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $runManifestPath -Encoding utf8
if (-not $measurementPass) {
    Write-Output "B3_POWER_RUN_MANIFEST=$runManifestPath"
    throw "Power window failed: board_result_pass=$resultPass delta_mwh=$deltaMwh"
}

$campaignRow = [pscustomobject][ordered]@{
    round = $Round
    mode = $Mode
    duration_seconds = $WindowSeconds
    start_mwh = $startObservation.mwh
    end_mwh = $endObservation.mwh
    start_mah = $startObservation.mah
    end_mah = $endObservation.mah
    voltage_start_v = $startObservation.voltage_v
    voltage_end_v = $endObservation.voltage_v
    current_start_a = $startObservation.current_a
    current_end_a = $endObservation.current_a
    power_start_w = $startObservation.power_w
    power_end_w = $endObservation.power_w
    valid_inferences = $result.valid_inferences
    protocol_error_count = $result.protocol_error_count
    jtag_physically_connected = 'true'
    xsct_active_during_window = 'false'
    hw_server_active_during_window = 'false'
    start_photo = $startObservation.photo
    end_photo = $endObservation.photo
    meter_trace_csv = $traceCsv
    board_result_manifest = $runManifestPath
    instrument_model = $InstrumentModel
    instrument_accuracy = $InstrumentAccuracy
    power_source_description = $PowerSource
}
if (Test-Path -LiteralPath $campaignCsv) {
    $campaignRow | Export-Csv -LiteralPath $campaignCsv -NoTypeInformation -Encoding utf8 -Append
} else {
    $campaignRow | Export-Csv -LiteralPath $campaignCsv -NoTypeInformation -Encoding utf8
}

Write-Output 'B3_POWER_MANUAL_WINDOW_PASS'
Write-Output "B3_POWER_RUN_MANIFEST=$runManifestPath"
Write-Output "B3_POWER_CAMPAIGN_CSV=$campaignCsv"

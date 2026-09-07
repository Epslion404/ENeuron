param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$EvidenceLabel,
    [string]$VivadoRoot = $env:VIVADO_ROOT
)

$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir '..\..\..')).Path
$evidenceDir = Join-Path $repoRoot "artifacts\logs\hellozynq_b0\$EvidenceLabel"
if (Test-Path -LiteralPath $evidenceDir) {
    throw "B0 power-off evidence already exists and will not be overwritten: $evidenceDir"
}
New-Item -ItemType Directory -Path $evidenceDir | Out-Null

$expectedTarget = 'localhost:3121/xilinx_tcf/Digilent/210251A08870'
$resultPath = Join-Path $evidenceDir 'power_off_probe_result.txt'
$logPath = Join-Path $evidenceDir 'power_off_probe_run.txt'
$tclPath = Join-Path $scriptDir 'probe_b0_power_off.tcl'
$vivadoBat = if ($VivadoRoot) {
    Join-Path $VivadoRoot 'bin\vivado.bat'
} else {
    'G:\Xilinx\Vivado\2024.1\bin\vivado.bat'
}
if (-not (Test-Path -LiteralPath $vivadoBat -PathType Leaf)) {
    throw "Vivado not found: $vivadoBat"
}

& $vivadoBat -mode batch -nolog -nojournal -notrace `
    -source $tclPath -tclargs $expectedTarget $resultPath 2>&1 |
    Tee-Object -FilePath $logPath
if ($LASTEXITCODE -ne 0) {
    throw "Vivado B0 power-off probe failed with exit code $LASTEXITCODE"
}
if (-not (Select-String -LiteralPath $logPath -SimpleMatch 'B0_COMPLETE_POWER_OFF_JTAG_INACCESSIBLE=PASS' -Quiet)) {
    throw 'Power-off probe transcript does not contain the PASS marker'
}
if (-not (Select-String -LiteralPath $resultPath -SimpleMatch 'B0_POWER_OFF_MATCHING_TARGET_COUNT=1' -Quiet)) {
    throw 'Power-off probe did not find exactly one expected cable target'
}
if (-not (Select-String -LiteralPath $resultPath -SimpleMatch 'B0_POWER_OFF_ACCESSIBLE_DEVICE_COUNT=0' -Quiet)) {
    throw 'Power-off probe still found an accessible FPGA device'
}

$manifest = [ordered]@{
    schema_version = 1
    evidence_label = $EvidenceLabel
    git_head = (& git -C $repoRoot rev-parse HEAD).Trim()
    git_worktree_clean = [string]::IsNullOrWhiteSpace(((& git -C $repoRoot status --porcelain=v1) -join "`n"))
    expected_target = $expectedTarget
    accessible_device_count = 0
    result = 'PASS'
    result_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $resultPath).Hash.ToLowerInvariant()
    transcript_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $logPath).Hash.ToLowerInvariant()
    tcl_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $tclPath).Hash.ToLowerInvariant()
    runner_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $PSCommandPath).Hash.ToLowerInvariant()
}
$manifestPath = Join-Path $evidenceDir 'power_off_probe_manifest.json'
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "B0_POWER_OFF_ARCHIVE_PASS evidence_dir=$evidenceDir"
Write-Host "B0_POWER_OFF_TRANSCRIPT_SHA256=$($manifest.transcript_sha256)"

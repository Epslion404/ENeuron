param(
    [string]$VivadoRoot = $env:VIVADO_ROOT
)

$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot
$repoRoot = (& git -C $scriptDir rev-parse --show-toplevel).Trim()
$gitHead = (& git -C $repoRoot rev-parse HEAD).Trim()
$gitStatus = (& git -C $repoRoot status --porcelain=v1) -join "`n"
$outDir = Join-Path $scriptDir 'build'
$logPath = Join-Path $outDir 'vivado_run.log'
$summaryPath = Join-Path $outDir 'signoff_summary.txt'
$bitstreamPath = Join-Path $outDir 'hello_zynq_b0_smoke.bit'
$manifestPath = Join-Path $outDir 'build_manifest.json'

New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$vivadoBat = if ($VivadoRoot) {
    Join-Path $VivadoRoot 'bin\vivado.bat'
} else {
    'G:\Xilinx\Vivado\2024.1\bin\vivado.bat'
}
if (-not (Test-Path -LiteralPath $vivadoBat)) {
    throw "Vivado not found: $vivadoBat"
}

& $vivadoBat -mode batch -nolog -nojournal -notrace `
    -source (Join-Path $scriptDir 'build_b0.tcl') `
    -tclargs $gitHead $outDir 2>&1 | Tee-Object -FilePath $logPath
if ($LASTEXITCODE -ne 0) {
    throw "Vivado B0 build failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $summaryPath)) {
    throw "Missing B0 summary: $summaryPath"
}
if (-not (Test-Path -LiteralPath $bitstreamPath)) {
    throw "Missing B0 bitstream: $bitstreamPath"
}
if (-not (Select-String -LiteralPath $logPath -SimpleMatch 'B0_BUILD_PASS' -Quiet)) {
    throw 'Vivado log does not contain B0_BUILD_PASS'
}

$sourceFiles = @(
    'hello_zynq_b0_smoke.sv',
    'hello_zynq_b0_smoke.xdc',
    'build_b0.tcl',
    'run_b0_build.ps1',
    'program_b0.tcl',
    'run_b0_program.ps1'
)
$sourceHashes = [ordered]@{}
foreach ($name in $sourceFiles) {
    $path = Join-Path $scriptDir $name
    $sourceHashes[$name] = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
}

$manifest = [ordered]@{
    schema_version = 1
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
    git_head = $gitHead
    git_worktree_clean = [string]::IsNullOrEmpty($gitStatus)
    vivado = (& $vivadoBat -version | Select-Object -First 1).Trim()
    part = 'xc7z020clg484-2'
    top = 'hello_zynq_b0_smoke'
    clock_period_ns = 20.000
    bitstream_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $bitstreamPath).Hash.ToLowerInvariant()
    source_sha256 = $sourceHashes
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "B0_BUILD_DONE summary=$summaryPath"
Write-Host "B0_BUILD_MANIFEST=$manifestPath"
Write-Host "B0_BITSTREAM_SHA256=$($manifest.bitstream_sha256)"

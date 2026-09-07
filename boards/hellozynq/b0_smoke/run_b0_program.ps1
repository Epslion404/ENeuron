param(
    [string]$VivadoRoot = $env:VIVADO_ROOT,
    [string]$BitstreamPath = ''
)

$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot
$outDir = Join-Path $scriptDir 'build'
$logPath = Join-Path $outDir 'program_run.log'
$resultPath = Join-Path $outDir 'program_result.txt'
$manifestPath = Join-Path $outDir 'build_manifest.json'

if (-not $BitstreamPath) {
    $BitstreamPath = Join-Path $outDir 'hello_zynq_b0_smoke.bit'
}
$BitstreamPath = (Resolve-Path -LiteralPath $BitstreamPath).Path
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Missing B0 build manifest: $manifestPath"
}

$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $BitstreamPath).Hash.ToLowerInvariant()
if ($actualHash -ne $manifest.bitstream_sha256) {
    throw "Bitstream hash mismatch: expected $($manifest.bitstream_sha256), got $actualHash"
}

$vivadoBat = if ($VivadoRoot) {
    Join-Path $VivadoRoot 'bin\vivado.bat'
} else {
    'G:\Xilinx\Vivado\2024.1\bin\vivado.bat'
}
if (-not (Test-Path -LiteralPath $vivadoBat)) {
    throw "Vivado not found: $vivadoBat"
}

& $vivadoBat -mode batch -nolog -nojournal -notrace `
    -source (Join-Path $scriptDir 'program_b0.tcl') `
    -tclargs $BitstreamPath $resultPath 2>&1 | Tee-Object -FilePath $logPath
if ($LASTEXITCODE -ne 0) {
    throw "Vivado B0 program failed with exit code $LASTEXITCODE"
}
if (-not (Select-String -LiteralPath $logPath -SimpleMatch 'B0_PROGRAM_PASS' -Quiet)) {
    throw 'Vivado log does not contain B0_PROGRAM_PASS'
}

Write-Host "B0_PROGRAM_DONE result=$resultPath"
Write-Host "B0_PROGRAMMED_SHA256=$actualHash"

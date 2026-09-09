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
$bitstreamPath = Join-Path $outDir 'hello_zynq_b2.bit'
$xsaPath = Join-Path $outDir 'hello_zynq_b2.xsa'
$manifestPath = Join-Path $outDir 'build_manifest.json'

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$vivadoBat = if ($VivadoRoot) { Join-Path $VivadoRoot 'bin\vivado.bat' } else { 'G:\Xilinx\Vivado\2024.1\bin\vivado.bat' }
if (-not (Test-Path -LiteralPath $vivadoBat)) { throw "Vivado not found: $vivadoBat" }

& $vivadoBat -mode batch -nolog -nojournal -notrace -source (Join-Path $scriptDir 'build_b2.tcl') -tclargs $gitHead $outDir 2>&1 | Tee-Object -FilePath $logPath
if ($LASTEXITCODE -ne 0) { throw "Vivado B2 build failed with exit code $LASTEXITCODE" }
foreach ($required in @($summaryPath, $bitstreamPath, $xsaPath)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing B2 artifact: $required" }
}
if (-not (Select-String -LiteralPath $logPath -SimpleMatch 'B2_BUILD_PASS' -Quiet)) { throw 'Vivado log does not contain B2_BUILD_PASS' }

$sourceFiles = @('create_b2_bd.tcl', 'build_b2.tcl', 'run_b2_build.ps1')
$sourceHashes = [ordered]@{}
foreach ($name in $sourceFiles) {
    $sourceHashes[$name] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $scriptDir $name)).Hash.ToLowerInvariant()
}
$summary = [ordered]@{}
foreach ($line in Get-Content -LiteralPath $summaryPath) {
    $parts = $line -split '=', 2
    if ($parts.Count -eq 2) { $summary[$parts[0]] = $parts[1] }
}
$manifest = [ordered]@{
    schema_version = 1
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
    git_head = $gitHead
    git_worktree_clean = [string]::IsNullOrEmpty($gitStatus)
    vivado = (& $vivadoBat -version 2>&1 | Select-String -Pattern '^vivado ' | Select-Object -First 1).Line.Trim()
    part = 'xc7z020clg484-2'
    top = 'design_1_wrapper'
    source_sha256 = $sourceHashes
    bitstream_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $bitstreamPath).Hash.ToLowerInvariant()
    xsa_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $xsaPath).Hash.ToLowerInvariant()
    reports_sha256 = [ordered]@{
        utilization_impl = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $outDir 'utilization_impl.rpt')).Hash.ToLowerInvariant()
        timing_impl = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $outDir 'timing_impl.rpt')).Hash.ToLowerInvariant()
        route_status_impl = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $outDir 'route_status_impl.rpt')).Hash.ToLowerInvariant()
        drc_impl = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $outDir 'drc_impl.rpt')).Hash.ToLowerInvariant()
    }
    signoff = $summary
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Host "B2_BUILD_DONE summary=$summaryPath"
Write-Host "B2_BUILD_MANIFEST=$manifestPath"
Write-Host "B2_BITSTREAM_SHA256=$($manifest.bitstream_sha256)"
Write-Host "B2_XSA_SHA256=$($manifest.xsa_sha256)"

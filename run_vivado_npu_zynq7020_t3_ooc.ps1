param(
    [string]$VivadoRoot = $env:VIVADO_ROOT
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$out = Join-Path $root 'vivado_npu_zynq7020_t3_ooc_reports'
$log = Join-Path $out 'vivado_run.log'
$head = (& git -C $root rev-parse HEAD).Trim()
New-Item -ItemType Directory -Force -Path $out | Out-Null

$vivadoBat = if ($VivadoRoot) { Join-Path $VivadoRoot 'bin\vivado.bat' } else { 'G:\Xilinx\Vivado\2024.1\bin\vivado.bat' }
if (-not (Test-Path -LiteralPath $vivadoBat)) { throw "Vivado not found: $vivadoBat. Set VIVADO_ROOT or pass -VivadoRoot." }
& $vivadoBat -mode batch -nolog -nojournal -notrace `
    -source (Join-Path $root 'vivado_npu_zynq7020_t3_ooc.tcl') `
    -tclargs $head $out 2>&1 | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) { throw "Vivado T3 OOC failed with exit code $LASTEXITCODE" }

$summary = Join-Path $out 'signoff_summary.txt'
if (-not (Test-Path -LiteralPath $summary)) { throw "Missing T3 OOC signoff summary: $summary" }
Write-Host "NPU_ZYNQ7020_T3_OOC_DONE summary=$summary"

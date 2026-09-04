$ErrorActionPreference = 'Stop'

# 使用项目记录的 Vivado 2024.1；bat 负责建立完整 Vivado 环境。

$root = $PSScriptRoot
$out = Join-Path $root 'vivado_npu_single_clock_ooc_reports'
$summary = Join-Path $out 'signoff_summary.txt'
$log = Join-Path $out 'vivado_run.log'
$head = (& git -C $root rev-parse HEAD).Trim()
New-Item -ItemType Directory -Force -Path $out | Out-Null

& 'G:\Xilinx\Vivado\2024.1\bin\vivado.bat' -mode batch -nolog -nojournal -notrace `
    -source (Join-Path $root 'vivado_npu_single_clock_ooc.tcl') `
    -tclargs $head $out 2>&1 | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    throw "Vivado failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $summary)) {
    throw "Missing OOC signoff summary: $summary"
}
Write-Host "NPU_SINGLE_CLOCK_OOC_DONE summary=$summary"

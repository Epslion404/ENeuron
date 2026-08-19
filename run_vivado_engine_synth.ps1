$ErrorActionPreference = 'Stop'

# 必须通过 Vivado 官方包装脚本启动，以建立完整运行环境。
$vivado = 'G:\Xilinx\Vivado\2024.1\bin\vivado.bat'
$root = (Get-Location).Path
$reportDirectory = Join-Path $root 'vivado_engine_reports'
$log = Join-Path $reportDirectory 'vivado_run.log'

New-Item -ItemType Directory -Force -Path $reportDirectory | Out-Null
& $vivado -mode batch -nolog -nojournal -notrace -source (Join-Path $root 'vivado_engine_synth.tcl') 2>&1 |
    Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    throw "Vivado failed with exit code $LASTEXITCODE"
}

$ErrorActionPreference = 'Stop'
$vivado = 'G:\Xilinx\Vivado\2024.1\bin\vivado.bat'
$root = (Get-Location).Path
$log = Join-Path $root 'vivado_reports\vivado_run.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
& $vivado -mode batch -nolog -nojournal -notrace -source (Join-Path $root 'vivado_synth.tcl') 2>&1 | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) { throw "Vivado failed with exit code $LASTEXITCODE" }

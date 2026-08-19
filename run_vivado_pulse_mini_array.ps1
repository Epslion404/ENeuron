$ErrorActionPreference = 'Stop'
$vivado = 'G:\Xilinx\Vivado\2024.1\bin\vivado.bat'
$root = $PSScriptRoot
$out = Join-Path $root 'vivado_pulse_mini_array_reports'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$log = Join-Path $out 'vivado_run.log'
& $vivado -mode batch -nolog -nojournal -notrace -source (Join-Path $root 'vivado_pulse_mini_array.tcl') 2>&1 |
    Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) { throw "Vivado failed with exit code $LASTEXITCODE" }
Write-Host "PULSE_MINI_ARRAY_VIVADO_PASS reports=$out"

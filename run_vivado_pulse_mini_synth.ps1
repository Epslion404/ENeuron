$ErrorActionPreference = 'Stop'
$vivado = 'G:\Xilinx\Vivado\2024.1\bin\vivado.bat'
$root = $PSScriptRoot
$out = Join-Path $root 'vivado_pulse_mini_reports'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$log = Join-Path $out 'vivado_run.log'
& $vivado -mode batch -nolog -nojournal -notrace -source (Join-Path $root 'vivado_pulse_mini_synth.tcl') 2>&1 |
    Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) { throw "Vivado failed with exit code $LASTEXITCODE" }
if (-not (Test-Path (Join-Path $out 'signoff_summary.txt'))) { throw 'Missing Pulse-Mini signoff summary' }
Write-Host "PULSE_MINI_VIVADO_ROUTED summary=$(Join-Path $out 'signoff_summary.txt')"

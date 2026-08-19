$ErrorActionPreference = 'Stop'
$yosys = 'C:\msys64\ucrt64\bin\yosys.exe'
$root = $PSScriptRoot
$log = Join-Path $root 'formal_pulse_mini_l2.log'
& $yosys -Q -s (Join-Path $root 'formal_pulse_mini_l2.ys') 2>&1 |
    Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) { throw "Pulse-Mini-L2 formal proof failed with exit code $LASTEXITCODE" }
Write-Host 'PULSE_MINI_L2_FORMAL_PASS depth=20'

$ErrorActionPreference = 'Stop'
$yosys = 'C:\msys64\ucrt64\bin\yosys.exe'
$root = $PSScriptRoot
$log = Join-Path $root 'formal_pulse_mini.log'
& $yosys -Q -s (Join-Path $root 'formal_pulse_mini.ys') 2>&1 |
    Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) { throw "Pulse-Mini formal proof failed with exit code $LASTEXITCODE" }
Write-Host 'PULSE_MINI_FORMAL_PASS depth=20'

$ErrorActionPreference = 'Stop'
$vivado = 'G:\Xilinx\Vivado\2024.1\bin\vivado.bat'
$root = $PSScriptRoot
$out = Join-Path $root 'vivado_pulse_original_reports'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$log = Join-Path $out 'vivado_run.log'
& $vivado -mode batch -nolog -nojournal -notrace -source (Join-Path $root 'vivado_pulse_original_synth.tcl') 2>&1 |
    Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) { throw "Vivado failed with exit code $LASTEXITCODE" }
$summary = Join-Path $out 'signoff_summary.txt'
if (-not (Test-Path $summary)) { throw "Missing $summary" }
if (-not (Select-String -Path $summary -Pattern '^RESULT=PASS$')) { throw "Pulse original signoff failed" }
Write-Host "PULSE_ORIGINAL_VIVADO_PASS summary=$summary"

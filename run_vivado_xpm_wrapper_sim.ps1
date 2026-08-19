$ErrorActionPreference = 'Stop'

# The official loader initializes RDI_DATADIR/PATH, then launches this exact exe.
$vivadoExe = 'G:\Xilinx\Vivado\2024.1\bin\unwrapped\win64.o\vivado.exe'
$vivado = 'G:\Xilinx\Vivado\2024.1\bin\vivado.bat'
$root = (Get-Location).Path
$outDirectory = Join-Path $root 'vivado_xpm_wrapper_sim'
$log = Join-Path $outDirectory 'vivado_xpm_wrapper_run.log'
$tcl = Join-Path $root 'vivado_xpm_wrapper_sim.tcl'

if (-not (Test-Path -LiteralPath $vivadoExe)) {
    throw "Vivado executable not found: $vivadoExe"
}
if (-not (Test-Path -LiteralPath $vivado)) {
    throw "Vivado loader not found: $vivado"
}

New-Item -ItemType Directory -Force -Path $outDirectory | Out-Null
Write-Host 'ENeuron Host Bridge: launching Vivado 2024.1 real XPM/xsim signoff'
& $vivado -mode batch -nolog -nojournal -notrace -source $tcl 2>&1 |
    Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    throw "Vivado XPM wrapper signoff failed with exit code $LASTEXITCODE; log=$log"
}

$summary = Join-Path $outDirectory 'vivado_xpm_wrapper_summary.txt'
if (-not (Test-Path -LiteralPath $summary)) {
    throw "Vivado completed without summary: $summary"
}
Write-Host "ENeuron Host Bridge: XPM/xsim signoff complete; summary=$summary"

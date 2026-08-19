$ErrorActionPreference = 'Stop'

# Use the installed MSYS2 Yosys build and preserve a reproducible proof log.
$yosys = 'C:\msys64\ucrt64\bin\yosys.exe'
$root = (Get-Location).Path
$log = Join-Path $root 'formal_tile_protocol.log'

Write-Host 'ENeuron Tile: running Yosys SAT protocol proof'
& $yosys -Q -s (Join-Path $root 'formal_tile_protocol.ys') 2>&1 |
    Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    throw "Yosys formal proof failed with exit code $LASTEXITCODE"
}

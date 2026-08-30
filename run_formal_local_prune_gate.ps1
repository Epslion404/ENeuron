$ErrorActionPreference = 'Stop'

# Native Windows Yosys is not published upstream, so this check must also run with the
# official YosysHQ WebAssembly build (yowasp-yosys), whose sandbox only exposes the current
# directory. Pass the scripts as names relative to $root and execute from $root.
$yosys = if ($env:YOSYS) { $env:YOSYS } else { 'C:\msys64\ucrt64\bin\yosys.exe' }
$root = $PSScriptRoot
$log = Join-Path $root 'formal_local_prune_gate.log'
$reachLog = Join-Path $root 'formal_local_prune_gate_reach.log'
Push-Location -LiteralPath $root

Write-Host 'Local prune gate: running Yosys SAT depth-32 checks'
& $yosys -Q -s 'formal_local_prune_gate.ys' 2>&1 |
    Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    throw "Local prune gate finite formal check failed with exit code $LASTEXITCODE"
}

Write-Host 'Local prune gate: checking successful commit reachability'
& $yosys -Q -s 'formal_local_prune_gate_reach.ys' 2>&1 |
    Tee-Object -FilePath $reachLog
if ($LASTEXITCODE -ne 0) {
    throw "Local prune gate reachability check failed with exit code $LASTEXITCODE"
}
$reachText = Get-Content -LiteralPath $reachLog -Raw
if ($reachText -notmatch 'SAT solving finished - model found:') {
    throw 'Local prune gate reachability check did not reach a successful commit'
}
if (-not (Test-Path -LiteralPath (Join-Path $root 'formal_local_prune_gate_success.vcd'))) {
    throw 'Local prune gate successful commit witness is missing'
}
Pop-Location
Write-Host 'LOCAL_PRUNE_GATE_FORMAL_PASS depth=32 commit_reachable=1'

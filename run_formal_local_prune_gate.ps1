$ErrorActionPreference = 'Stop'

$yosys = 'C:\msys64\ucrt64\bin\yosys.exe'
$root = $PSScriptRoot
$log = Join-Path $root 'formal_local_prune_gate.log'
$reachLog = Join-Path $root 'formal_local_prune_gate_reach.log'

Write-Host 'Local prune gate: running Yosys SAT depth-32 checks'
& $yosys -Q -s (Join-Path $root 'formal_local_prune_gate.ys') 2>&1 |
    Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    throw "Local prune gate finite formal check failed with exit code $LASTEXITCODE"
}

Write-Host 'Local prune gate: checking successful commit reachability'
& $yosys -Q -s (Join-Path $root 'formal_local_prune_gate_reach.ys') 2>&1 |
    Tee-Object -FilePath $reachLog
if ($LASTEXITCODE -ne 0) {
    throw "Local prune gate reachability check failed with exit code $LASTEXITCODE"
}
$reachText = Get-Content -LiteralPath $reachLog -Raw
if ($reachText -notmatch 'SAT solving finished - model found:') {
    throw 'Local prune gate reachability check did not reach a successful commit'
}
Write-Host 'LOCAL_PRUNE_GATE_FORMAL_PASS depth=32 commit_reachable=1'

$ErrorActionPreference = 'Stop'
$yosys = 'C:\msys64\ucrt64\bin\yosys.exe'
$root = $PSScriptRoot
$log = Join-Path $root 'formal_eneuron_prune_wrapper.log'

'FORMAL_LOG_SCHEMA=np4b5_eneuron_wrapper_v1 target=eneuron property=mod_observe_atomic_public_state' |
    Tee-Object -FilePath $log

& $yosys -Q -s (Join-Path $root 'formal_eneuron_prune_wrapper.ys') 2>&1 |
    Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) {
    throw "ENeuron prune wrapper invariant proof failed with exit code $LASTEXITCODE"
}

& $yosys -Q -s (Join-Path $root 'formal_eneuron_prune_wrapper_reach.ys') 2>&1 |
    Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) {
    throw "ENeuron prune wrapper reachability failed with exit code $LASTEXITCODE"
}

'ENEURON_PRUNE_WRAPPER_FORMAL_PASS depth=32 invariant=mod_observe_atomic_public_state reach=public_nonzero_snapshot_mod_done' |
    Tee-Object -FilePath $log -Append

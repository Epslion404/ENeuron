$ErrorActionPreference = 'Stop'
$yosys = 'C:\msys64\ucrt64\bin\yosys.exe'
$root = $PSScriptRoot
$log = Join-Path $root 'formal_pulse_mini_prune_wrapper.log'

'FORMAL_LOG_SCHEMA=np4b5_wrapper_v1 target=pulse_mini_l property=feedback_observe_utility_order' |
    Tee-Object -FilePath $log

& $yosys -Q -s (Join-Path $root 'formal_pulse_mini_prune_wrapper.ys') 2>&1 |
    Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) {
    throw "Pulse prune wrapper invariant proof failed with exit code $LASTEXITCODE"
}

& $yosys -Q -s (Join-Path $root 'formal_pulse_mini_prune_wrapper_reach.ys') 2>&1 |
    Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) {
    throw "Pulse prune wrapper reachability failed with exit code $LASTEXITCODE"
}

'PULSE_PRUNE_WRAPPER_FORMAL_PASS depth=32 invariant=feedback_observe_utility_order reach=successful_nonzero_feedback' |
    Tee-Object -FilePath $log -Append

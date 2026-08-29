$ErrorActionPreference = 'Stop'
$yosys = 'C:\msys64\ucrt64\bin\yosys.exe'
$root = $PSScriptRoot
& $yosys -Q -s (Join-Path $root 'formal_local_prune_commit_barrier.ys') 2>&1 | Tee-Object -FilePath (Join-Path $root 'formal_local_prune_commit_barrier.log')
if ($LASTEXITCODE -ne 0) { throw 'barrier proof failed' }
& $yosys -Q -s (Join-Path $root 'formal_local_prune_commit_barrier_reach.ys') 2>&1 | Tee-Object -FilePath (Join-Path $root 'formal_local_prune_commit_barrier_reach.log')
if ($LASTEXITCODE -ne 0) { throw 'barrier reach failed' }
Write-Host 'LOCAL_PRUNE_COMMIT_BARRIER_FORMAL_PASS depth=32 participants=10'

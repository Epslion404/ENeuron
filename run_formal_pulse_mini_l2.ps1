$ErrorActionPreference = 'Stop'
$yosys = 'C:\msys64\ucrt64\bin\yosys.exe'
$root = $PSScriptRoot
$log = Join-Path $root 'formal_pulse_mini_l2.log'

# v1 日志来自不可释放复位的空轨迹，不再作为有效证据；本脚本覆盖写入 v2 日志。
'FORMAL_LOG_SCHEMA=np4b5_v2 old_v1_logs_invalid=1 reset=one_startup_cycle' |
    Tee-Object -FilePath $log

& $yosys -Q -s (Join-Path $root 'formal_pulse_mini_l2.ys') 2>&1 |
    Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { throw "Pulse-Mini-L2 formal invariant proof failed with exit code $LASTEXITCODE" }

& $yosys -Q -s (Join-Path $root 'formal_pulse_mini_l2_reach.ys') 2>&1 |
    Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { throw "Pulse-Mini-L2 formal reachability failed with exit code $LASTEXITCODE" }

'PULSE_MINI_L2_FORMAL_PASS depth=20 reach=tick,capture,feedback,capture_then_feedback' |
    Tee-Object -FilePath $log -Append

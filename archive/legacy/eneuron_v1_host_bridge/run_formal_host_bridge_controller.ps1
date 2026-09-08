$ErrorActionPreference = 'Stop'

$yosys = 'C:\msys64\ucrt64\bin\yosys.exe'
$root = (Get-Location).Path
$log = Join-Path $root 'formal_host_bridge_controller.log'
$vcd = (Join-Path $root 'formal_host_bridge_controller_cex.vcd').Replace('\', '/')
$redLog = Join-Path $root 'formal_host_bridge_controller_red.log'
$redVcd = (Join-Path $root 'formal_host_bridge_controller_red.vcd').Replace('\', '/')

$observed = @(
    'state', 'active_action', 'active_command_reg', 'ep_end_flush_spikes',
    'episode_active', 'episode_train', 'active_episode_id', 'next_tick_ext',
    'tick_open', 'expected_event_count', 'seen_event_count', 'seen_mask',
    'pending_arch_valid', 'pending_episode_active', 'pending_episode_train',
    'pending_active_episode_id', 'pending_next_tick_ext', 'pending_tick_open',
    'pending_expected_event_count', 'pending_seen_event_count',
    'pending_seen_mask', 'fatal_error', 'fatal_opcode', 'fatal_phase'
)

$selectObserved = ($observed | ForEach-Object { "w:$_" }) -join ' '
$connectObserved = ($observed | ForEach-Object {
    "connect -port dut $_ observed_$_"
}) -join '; '

$prepareCommands = @(
    'read_verilog -formal -sv digital_snn_host_bridge_controller.sv formal_host_bridge_controller.sv',
    'hierarchy -top formal_host_bridge_controller',
    'proc',
    "cd digital_snn_host_bridge_controller; select $selectObserved; expose",
    "cd formal_host_bridge_controller; $connectObserved",
    'prep -top formal_host_bridge_controller -flatten',
    'async2sync',
    'opt_clean'
) -join '; '

$redCommands = $prepareCommands + '; ' +
    ("sat -seq 4 -set-assumes -set-init-zero -set break_tile_contract 0 " +
     "-set-at 3 break_tile_contract 1 -set-at 3 untrusted_tile_done 1 " +
     "-prove abstract_tile_contract_ok 1 -falsify -dump_vcd $redVcd")

Write-Host 'ENeuron Host Bridge controller: negative Tile-contract control'
$redOutput = & $yosys -Q -p $redCommands 2>&1 | Tee-Object -FilePath $redLog
if ($LASTEXITCODE -ne 0) {
    throw "Negative Tile-contract control failed with exit code $LASTEXITCODE"
}
if (($redOutput -join "`n") -notmatch 'SAT proof finished - model found') {
    throw 'Negative Tile-contract control did not reproduce the expected counterexample'
}

$safetyCommands = $prepareCommands + '; ' +
    "sat -seq 20 -set-assumes -set-init-zero -set break_tile_contract 0 " +
    "-prove-asserts -verify -dump_vcd $vcd"

Write-Host 'ENeuron Host Bridge controller: bounded SAT depth 20'
& $yosys -Q -p $safetyCommands 2>&1 | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    throw "Host Bridge controller formal failed with exit code $LASTEXITCODE"
}

$reachability = @(
    @{ Name = 'response_stall'; Signal = 'cover_response_stall'; Depth = 8 },
    @{ Name = 'arch_commit'; Signal = 'cover_arch_commit'; Depth = 10 },
    @{ Name = 'protocol_error'; Signal = 'cover_protocol_error'; Depth = 8 },
    @{ Name = 'fatal'; Signal = 'cover_fatal'; Depth = 14 },
    @{ Name = 'weight_read'; Signal = 'cover_weight_read'; Depth = 12 },
    @{ Name = 'train_ep_end'; Signal = 'cover_train_ep_end'; Depth = 20 }
)

foreach ($target in $reachability) {
    $coverLog = Join-Path $root ("formal_host_bridge_controller_cover_{0}.log" -f $target.Name)
    $coverVcd = (Join-Path $root ("formal_host_bridge_controller_cover_{0}.vcd" -f $target.Name)).Replace('\', '/')
    $coverCommands = $prepareCommands + '; chformal -assert -assert2assume; ' +
        ("sat -seq {0} -set-assumes -set-init-zero -set-at {0} {1} 1 " +
         "-set break_tile_contract 0 -show {1} -show-inputs -dump_vcd {2}") -f
         $target.Depth, $target.Signal, $coverVcd

    Write-Host ("ENeuron Host Bridge controller: reachability {0} depth {1}" -f
        $target.Name, $target.Depth)
    $coverOutput = & $yosys -Q -p $coverCommands 2>&1 | Tee-Object -FilePath $coverLog
    if ($LASTEXITCODE -ne 0) {
        throw "Reachability $($target.Name) failed with exit code $LASTEXITCODE"
    }
    if (($coverOutput -join "`n") -notmatch 'SAT solving finished - model found') {
        throw "Reachability $($target.Name) has no witness at depth $($target.Depth)"
    }
}

Write-Host 'VIVADO_ENEURON_HOST_BRIDGE_FORMAL_PASS safety_depth=20 covers=6'

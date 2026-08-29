"""Pulse-Mini 4→8→2 网络随机长事务 Python/Icarus 协同仿真。"""

from __future__ import annotations

import random
import json
import logging
import subprocess
import tempfile
from dataclasses import astuple
from pathlib import Path
from typing import Sequence

from pulse_mini_pruned_network_4x8x2_cosim import _public_interface_tb, _sources
from pulse_mini_pruned_network_reference import (
    N_NEURONS,
    NetworkTransaction,
    PulseMiniPrunedNetworkReference,
)
from pulse_mini_reference import Mode
from rtl_tile_cosim import find_tool


ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)


def make_transactions(seed: int, count: int) -> tuple[NetworkTransaction, ...]:
    """生成 dense→OBSERVE→commit→sparse→INFER 的合法事务序列。"""

    if count < 64:
        raise ValueError("transaction_count 必须至少为 64")
    rng = random.Random(seed)
    result = [
        *(NetworkTransaction("weight_write", True, arg0=lane, arg1=2) for lane in range(4)),
        NetworkTransaction("mode", True, arg0=1),
    ]
    commit_at = count // 3
    infer_at = (2 * count) // 3
    while len(result) < count:
        index = len(result)
        if index == commit_at:
            result.append(NetworkTransaction("commit", command_id=0x7000 + seed, backpressure=2))
            continue
        if index == infer_at:
            result.append(NetworkTransaction("mode", True, arg0=2, backpressure=1))
            continue
        if index < commit_at:
            if index % 7 == 5 and index + 1 < commit_at:
                broadcast = rng.random() < 0.5
                neuron = rng.randrange(10)
                result.extend((
                    NetworkTransaction("capture", broadcast, neuron),
                    NetworkTransaction("feedback", broadcast, neuron, arg0=1,
                                       backpressure=rng.randrange(3)),
                ))
            else:
                result.append(NetworkTransaction(
                    "tick", arg0=rng.randrange(16), hidden_post=rng.randrange(256),
                    output_post=rng.randrange(4), backpressure=rng.randrange(3),
                ))
        elif index < infer_at:
            if index % 8 == 0 and index + 1 < infer_at:
                result.extend((
                    NetworkTransaction("capture", True),
                    NetworkTransaction("feedback", True, arg0=rng.choice((0, 1)),
                                       backpressure=rng.randrange(2)),
                ))
            else:
                result.append(NetworkTransaction(
                    "tick", arg0=rng.randrange(16), hidden_post=rng.randrange(256),
                    output_post=rng.randrange(4), backpressure=rng.randrange(3),
                ))
        else:
            kind = rng.choice(("tick", "tick", "flush", "clear", "weight_read"))
            if kind == "tick":
                result.append(NetworkTransaction(kind, arg0=rng.randrange(16),
                                                 backpressure=rng.randrange(3)))
            elif kind == "flush":
                result.append(NetworkTransaction(kind, backpressure=rng.randrange(3)))
            elif kind == "clear":
                result.append(NetworkTransaction(kind, rng.random() < 0.2,
                                                 rng.randrange(10)))
            else:
                result.append(NetworkTransaction(kind, False, rng.randrange(10),
                                                 arg0=rng.randrange(4)))
    return tuple(result[:count])


def _state_line() -> str:
    names = (
        "hidden_spikes", "output_spikes", "pending_hidden_state", "commit_epoch_state",
        "issue_masks_flat", "structural_masks_flat", "mask_valids_state",
        "pending_valids_state", "mode_states_flat", "weights_flat_state",
        "soma_states_flat", "refractory_states_flat", "leak_timer_states_flat",
        "pre_age_flat_state", "post_age_states_flat", "positive_evidence_flat_state",
        "negative_evidence_flat_state", "captured_direction_flat_state",
        "utility_flat_state", "observe_counts_flat_state", "refractory_skips_flat_state",
        "network_hidden_dense_reads_state", "network_hidden_reads_issued_state",
        "network_hidden_reads_saved_state", "network_output_dense_reads_state",
        "network_output_reads_issued_state", "network_output_reads_saved_state",
    )
    return "      $display(\"STATE %0d " + " ".join("%h" for _ in names) + "\", tx, " + ", ".join(names) + ");"


def make_testbench(transactions: Sequence[NetworkTransaction], *, l2: bool) -> str:
    module = "pulse_mini_l2_pruned_network_4x8x2" if l2 else "pulse_mini_l_pruned_network_4x8x2"
    prefix = _public_interface_tb(module).rsplit("  initial begin", 1)[0]
    lines = [prefix,
        "  integer timeout, tx, lane;",
        "  task automatic emit; begin", _state_line(), "  end endtask",
        "  task automatic host(input integer op,input integer bc,input integer addr,input integer a0,input integer a1,input integer bp); integer saved_status,saved_addr,saved_data,saved_spike; begin",
        "    @(negedge clk); host_cmd_opcode=op; host_cmd_broadcast=bc; host_neuron_addr=addr; host_cmd_arg0=a0; host_cmd_arg1=a1; host_cmd_valid=1; #1;",
        "    if(!host_cmd_ready) $fatal(1,\"HOST_READY tx=%0d\",tx); @(posedge clk); #1; host_cmd_valid=0; timeout=0;",
        "    while(!host_rsp_valid) begin @(posedge clk); #1; timeout=timeout+1; if(timeout>300)$fatal(1,\"HOST_TIMEOUT\"); end",
        "    if(host_rsp_status!=0)$fatal(1,\"HOST_STATUS tx=%0d status=%0d\",tx,host_rsp_status); saved_status=host_rsp_status; saved_addr=host_rsp_neuron_addr; saved_data=host_rsp_data; saved_spike=host_rsp_spike;",
        "    repeat(bp) begin @(posedge clk); #1; if(!host_rsp_valid || host_rsp_status!=saved_status || host_rsp_neuron_addr!=saved_addr || host_rsp_data!=saved_data || host_rsp_spike!=saved_spike)$fatal(1,\"HOST_BP\"); end",
        "    host_rsp_ready=1; @(posedge clk); #1; host_rsp_ready=0; emit(); end endtask",
        "  task automatic tick(input integer mask,input integer hp,input integer op,input integer bp); integer saved_status,saved_hidden,saved_output; begin",
        "    @(negedge clk); input_spikes=mask; hidden_train_post=hp; output_train_post=op; tick_valid=1; #1;",
        "    if(!tick_ready)$fatal(1,\"TICK_READY tx=%0d\",tx);",
        "    for(lane=0;lane<8;lane=lane+1) if(issue_masks_flat[lane*4 +:4] !== (mask & (mask_valids_state[lane]?structural_masks_flat[lane*4 +:4]:4'hf))) $fatal(1,\"ISSUE_HIDDEN\");",
        "    for(lane=0;lane<2;lane=lane+1) if(issue_masks_flat[(lane+8)*4 +:4] !== (pending_hidden_state[lane*4 +:4] & (mask_valids_state[lane+8]?structural_masks_flat[(lane+8)*4 +:4]:4'hf))) $fatal(1,\"ISSUE_OUTPUT\");",
        "    @(posedge clk); #1; tick_valid=0; input_spikes=0; timeout=0; while(!tick_rsp_valid) begin @(posedge clk); #1; timeout=timeout+1; if(timeout>300)$fatal(1,\"TICK_TIMEOUT\"); end",
        "    if(tick_rsp_status!=0)$fatal(1,\"TICK_STATUS\"); saved_status=tick_rsp_status; saved_hidden=hidden_spikes; saved_output=output_spikes; repeat(bp) begin @(posedge clk); #1; if(!tick_rsp_valid || tick_rsp_status!=saved_status || hidden_spikes!=saved_hidden || output_spikes!=saved_output)$fatal(1,\"TICK_BP\"); end",
        "    tick_rsp_ready=1; @(posedge clk); #1; tick_rsp_ready=0; emit(); end endtask",
        "  task automatic flush(input integer bp); integer saved_status,saved_hidden,saved_output; begin @(negedge clk); input_spikes=0; hidden_train_post=0; output_train_post=0; route_flush_valid=1; #1; if(!route_flush_ready)$fatal(1,\"FLUSH_READY\"); for(lane=0;lane<2;lane=lane+1) if(issue_masks_flat[(lane+8)*4 +:4] !== (pending_hidden_state[lane*4 +:4] & (mask_valids_state[lane+8]?structural_masks_flat[(lane+8)*4 +:4]:4'hf))) $fatal(1,\"FLUSH_ISSUE_OUTPUT\"); @(posedge clk); #1; route_flush_valid=0; timeout=0; while(!tick_rsp_valid) begin @(posedge clk); #1; timeout=timeout+1; if(timeout>300)$fatal(1,\"FLUSH_TIMEOUT\"); end if(tick_rsp_status!=0)$fatal(1,\"FLUSH_STATUS status=%0d\",tick_rsp_status); saved_status=tick_rsp_status; saved_hidden=hidden_spikes; saved_output=output_spikes; repeat(bp) begin @(posedge clk); #1; if(!tick_rsp_valid || tick_rsp_status!=saved_status || hidden_spikes!=saved_hidden || output_spikes!=saved_output)$fatal(1,\"FLUSH_BP\"); end tick_rsp_ready=1; @(posedge clk); #1; tick_rsp_ready=0; emit(); end endtask",
        "  task automatic commit(input integer id,input integer bp); integer saved_status,saved_id; reg [39:0] saved_masks; begin @(negedge clk); prune_commit_id=id; prune_commit_valid=1; #1; if(!prune_commit_ready)$fatal(1,\"COMMIT_READY\"); @(posedge clk); #1; prune_commit_valid=0; timeout=0; while(!prune_rsp_valid) begin if(tick_ready||host_cmd_ready||route_flush_ready)$fatal(1,\"COMMIT_BLOCK\"); @(posedge clk); #1; timeout=timeout+1; if(timeout>500)$fatal(1,\"COMMIT_TIMEOUT\"); end if(prune_rsp_status!=0 || prune_rsp_id!=id)$fatal(1,\"COMMIT_STATUS\"); for(lane=0;lane<10;lane=lane+1) if($countones(structural_masks_flat[lane*4 +:4])!=2)$fatal(1,\"EXACT_TWO\"); saved_status=prune_rsp_status; saved_id=prune_rsp_id; saved_masks=prune_rsp_masks_flat; repeat(bp) begin @(posedge clk); #1; if(!prune_rsp_valid || prune_rsp_status!=saved_status || prune_rsp_id!=saved_id || prune_rsp_masks_flat!=saved_masks)$fatal(1,\"COMMIT_BP\"); end prune_rsp_ready=1; @(posedge clk); #1; prune_rsp_ready=0; emit(); end endtask",
        "  initial begin rst=1; tick_valid=0; route_flush_valid=0; input_spikes=0; hidden_train_post=0; output_train_post=0; tick_rsp_ready=0; host_cmd_valid=0; host_cmd_opcode=0; host_cmd_broadcast=0; host_neuron_addr=0; host_cmd_arg0=0; host_cmd_arg1=0; host_rsp_ready=0; prune_commit_valid=0; prune_commit_id=0; prune_rsp_ready=0; repeat(3) @(posedge clk); rst=0; #1;",
    ]
    opcodes = {"mode": 0, "clear": 1, "capture": 3, "feedback": 4,
               "weight_write": 5, "weight_read": 6}
    for index, tx in enumerate(transactions):
        lines.append(f"    tx={index};")
        if tx.kind == "tick":
            lines.append(f"    tick({tx.arg0},{tx.hidden_post},{tx.output_post},{tx.backpressure});")
        elif tx.kind == "flush":
            lines.append(f"    flush({tx.backpressure});")
        elif tx.kind == "commit":
            lines.append(f"    commit({tx.command_id},{tx.backpressure});")
        else:
            lines.append(f"    host({opcodes[tx.kind]},{int(tx.broadcast)},{tx.neuron},{tx.arg0},{tx.arg1},{tx.backpressure});")
    lines.extend(["    $display(\"PULSE_RANDOM_DONE\"); $finish;", "  end", "endmodule"])
    return "\n".join(lines) + "\n"


def _lane(packed: int, index: int, width: int) -> int:
    return (packed >> (index * width)) & ((1 << width) - 1)


def _expected(
    transactions: Sequence[NetworkTransaction], *, l2: bool
) -> tuple[list[tuple[int, ...]], dict[str, int]]:
    model = PulseMiniPrunedNetworkReference(l2=l2)
    result: list[tuple[int, ...]] = []
    stats = {
        "commits": 0,
        "exact_two_checks": 0,
        "pruned_lane_checks": 0,
        "pruned_weight_changes": 0,
        "pruned_evidence_changes": 0,
        "pruned_utility_changes": 0,
        "infer_transactions": 0,
        "backpressure_cycles": sum(tx.backpressure for tx in transactions),
        "issue_mask_acceptance_checks": 0,
    }
    pruned_baseline: dict[tuple[int, int], tuple[int, ...]] = {}
    infer = False
    before = model.state()
    for index, tx in enumerate(transactions):
        after = model.execute(tx)
        if tx.kind == "commit":
            stats["commits"] += 1
            for neuron in range(N_NEURONS):
                mask = _lane(after.structural_masks, neuron, 4)
                if not _lane(after.mask_valids, neuron, 1) or mask.bit_count() != 2:
                    raise AssertionError(f"Python oracle commit 非严格 2:4: tx={index} neuron={neuron}")
                for lane in range(4):
                    if mask & (1 << lane):
                        continue
                    flat_lane = neuron * 4 + lane
                    evidence_width = 2 if l2 else 1
                    pruned_baseline[(neuron, lane)] = (
                        _lane(after.weights, flat_lane, 4),
                        _lane(after.pre_age, flat_lane, 4),
                        _lane(after.positive, neuron * (4 if l2 else 8) + lane, evidence_width),
                        _lane(after.negative, neuron * (4 if l2 else 8) + lane, evidence_width),
                        _lane(after.captured, flat_lane, 3),
                        _lane(after.utility, flat_lane, 4),
                    )
        if pruned_baseline:
            for neuron in range(N_NEURONS):
                mask = _lane(after.structural_masks, neuron, 4)
                if not _lane(after.mask_valids, neuron, 1) or mask.bit_count() != 2:
                    raise AssertionError(f"Python oracle mask epoch 破坏: tx={index} neuron={neuron}")
                stats["exact_two_checks"] += 1
                for lane in range(4):
                    key = (neuron, lane)
                    if key not in pruned_baseline:
                        continue
                    flat_lane = neuron * 4 + lane
                    evidence_width = 2 if l2 else 1
                    current = (
                        _lane(after.weights, flat_lane, 4),
                        _lane(after.pre_age, flat_lane, 4),
                        _lane(after.positive, neuron * (4 if l2 else 8) + lane, evidence_width),
                        _lane(after.negative, neuron * (4 if l2 else 8) + lane, evidence_width),
                        _lane(after.captured, flat_lane, 3),
                        _lane(after.utility, flat_lane, 4),
                    )
                    baseline = pruned_baseline[key]
                    stats["pruned_lane_checks"] += 1
                    if current[0] != baseline[0]:
                        stats["pruned_weight_changes"] += 1
                    if current[1:5] != baseline[1:5]:
                        stats["pruned_evidence_changes"] += 1
                    if current[5] != baseline[5]:
                        stats["pruned_utility_changes"] += 1
        entering_infer = tx.kind == "mode" and tx.broadcast and tx.arg0 == int(Mode.INFER)
        if infer or entering_infer:
            stats["infer_transactions"] += 1
            fixed_before = (
                before.weights, before.structural_masks, before.mask_valids,
                before.utility, before.observe_counts,
            )
            fixed_after = (
                after.weights, after.structural_masks, after.mask_valids,
                after.utility, after.observe_counts,
            )
            if fixed_before != fixed_after:
                raise AssertionError(f"Python oracle INFER 固定学习状态变化: tx={index}")
            if tx.kind != "clear":
                dynamic_before = (
                    before.pre_age, before.post_age, before.positive,
                    before.negative, before.captured,
                )
                dynamic_after = (
                    after.pre_age, after.post_age, after.positive,
                    after.negative, after.captured,
                )
                if dynamic_before != dynamic_after:
                    raise AssertionError(f"Python oracle INFER 学习历史变化: tx={index}")
        if tx.kind == "tick":
            stats["issue_mask_acceptance_checks"] += N_NEURONS
        elif tx.kind == "flush":
            stats["issue_mask_acceptance_checks"] += 2
        if entering_infer:
            infer = True
        result.append((index, *astuple(after)))
        before = after
    for key in ("pruned_weight_changes", "pruned_evidence_changes", "pruned_utility_changes"):
        if stats[key] != 0:
            raise AssertionError(f"Python oracle {key}={stats[key]}")
    final = model.state()
    stats.update({
        "hidden_dense_reads": final.hidden_dense,
        "hidden_reads_issued": final.hidden_issued,
        "hidden_reads_saved": final.hidden_saved,
        "output_dense_reads": final.output_dense,
        "output_reads_issued": final.output_issued,
        "output_reads_saved": final.output_saved,
    })
    return result, stats


def _parse(output: str) -> list[tuple[int, ...]]:
    result = []
    for line in output.splitlines():
        if not line.startswith("STATE "):
            continue
        values = line.split()[1:]
        result.append((int(values[0], 10), *(int(value, 16) for value in values[1:])))
    return result


def run_seed(seed: int, transaction_count: int, *, l2: bool) -> dict[str, int]:
    iverilog, vvp = find_tool("iverilog"), find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 Icarus Verilog")
    transactions = make_transactions(seed, transaction_count)
    with tempfile.TemporaryDirectory(prefix="pulse_network_random_") as temp:
        work = Path(temp); tb = work / "tb.sv"; sim = work / "sim.vvp"
        tb.write_text(make_testbench(transactions, l2=l2), encoding="utf-8")
        compiled = subprocess.run([str(iverilog), "-g2012", "-s", "tb", "-o", str(sim),
                                  *(str(path) for path in _sources()), str(tb)],
                                  cwd=ROOT, capture_output=True, text=True, check=False)
        if compiled.returncode:
            raise AssertionError(compiled.stdout + compiled.stderr)
        ran = subprocess.run([str(vvp), str(sim)], cwd=ROOT, capture_output=True,
                             text=True, check=False)
        if ran.returncode:
            raise AssertionError("\n".join((ran.stdout + ran.stderr).splitlines()[-60:]))
    actual = _parse(ran.stdout)
    expected, stats = _expected(transactions, l2=l2)
    if actual != expected:
        for index, (got, want) in enumerate(zip(actual, expected)):
            if got != want:
                raise AssertionError(f"seed={seed} tx={index} {transactions[index]}\nactual={got}\nexpected={want}")
        raise AssertionError(f"state count actual={len(actual)} expected={len(expected)}")
    return stats


def run_matrix(
    *, seeds: Sequence[int], transaction_count: int, l2: bool
) -> dict[str, int | str]:
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("seeds 必须非空且互不重复")
    per_seed = [run_seed(seed, transaction_count, l2=l2) for seed in seeds]
    summary: dict[str, int | str] = {
        "model": "Pulse-Mini-L2" if l2 else "Pulse-Mini-L",
        "seeds": len(seeds),
        "transactions_per_seed": transaction_count,
        "transactions": len(seeds) * transaction_count,
    }
    for key in per_seed[0]:
        summary[key] = sum(stats[key] for stats in per_seed)
    marker = "PULSE_L2_NP4B4_PASS" if l2 else "PULSE_L_NP4B4_PASS"
    summary["status"] = marker
    LOGGER.info("%s %s", marker, json.dumps(summary, sort_keys=True))
    return summary


__all__ = ["make_transactions", "run_matrix", "run_seed"]

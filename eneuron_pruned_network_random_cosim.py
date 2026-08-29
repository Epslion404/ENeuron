"""NP4B4 ENeuron 4→8→2 随机长事务 Python/RTL 协同仿真。"""

from __future__ import annotations

import logging
import json
import os
import random
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

from eneuron_pruned_network_reference import (
    ENeuronPrunedNetworkReference,
    MODE_INFER,
    MODE_TRAIN,
    NetworkState,
    NetworkTransaction,
)
from rtl_multicycle_cosim import find_tool


ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("eneuron_pruned_network_random_cosim")


def make_transactions(seed: int, count: int) -> tuple[NetworkTransaction, ...]:
    """生成始终合法、覆盖 dense→commit→sparse→INFER 的混合事务。"""

    if count < 32:
        raise ValueError("transaction_count 必须至少为 32")
    rng = random.Random(seed)
    next_id = 1
    transactions: list[NetworkTransaction] = [
        NetworkTransaction("weight", MODE_TRAIN, broadcast=True, weight_addr=0, weight_data=4),
        NetworkTransaction("weight", MODE_TRAIN, broadcast=True, weight_addr=1, weight_data=3),
        NetworkTransaction("tick", MODE_TRAIN, mask=0b1111, backpressure=2),
        NetworkTransaction("tick", MODE_TRAIN, mask=0b0101),
        NetworkTransaction("snapshot", MODE_TRAIN, broadcast=True, command_id=next_id),
        NetworkTransaction(
            "mod", MODE_TRAIN, broadcast=True, command_id=next_id, modulator=1,
            backpressure=1,
        ),
    ]
    next_id += 1

    commit_index = max(12, count // 3)
    infer_index = max(commit_index + 8, (2 * count) // 3)
    committed = False

    while len(transactions) < count:
        if not committed and len(transactions) >= commit_index:
            transactions.append(
                NetworkTransaction(
                    "commit", MODE_TRAIN, command_id=0x4000 + seed,
                    backpressure=2,
                )
            )
            committed = True
            continue

        mode = MODE_INFER if committed and len(transactions) >= infer_index else MODE_TRAIN
        if mode == MODE_INFER:
            kind = rng.choice(("tick", "tick", "tick", "flush", "read", "clear"))
            if kind == "tick":
                transactions.append(
                    NetworkTransaction(
                        kind, mode, mask=rng.randrange(16), backpressure=rng.randrange(3)
                    )
                )
            elif kind == "clear":
                transactions.append(
                    NetworkTransaction(
                        kind,
                        mode,
                        broadcast=rng.random() < 0.25,
                        neuron=rng.randrange(10),
                        backpressure=rng.randrange(2),
                    )
                )
            else:
                transactions.append(
                    NetworkTransaction(kind, mode, backpressure=rng.randrange(3))
                )
            continue

        kind = rng.choice(("tick", "tick", "tick", "flush", "clear", "read", "learn"))
        if kind == "tick":
            transactions.append(
                NetworkTransaction(
                    kind, mode, mask=rng.randrange(16), backpressure=rng.randrange(3)
                )
            )
        elif kind == "clear":
            transactions.append(
                NetworkTransaction(
                    kind,
                    mode,
                    broadcast=rng.random() < 0.2,
                    neuron=rng.randrange(10),
                    backpressure=rng.randrange(2),
                )
            )
        elif kind == "learn" and len(transactions) + 1 < count:
            broadcast = rng.random() < 0.35
            neuron = rng.randrange(10)
            transactions.extend(
                (
                    NetworkTransaction(
                        "snapshot", mode, broadcast=broadcast, neuron=neuron,
                        command_id=next_id,
                    ),
                    NetworkTransaction(
                        "mod", mode, broadcast=broadcast, neuron=neuron,
                        command_id=next_id, modulator=rng.choice((-1, 0, 1)),
                        backpressure=rng.randrange(3),
                    ),
                )
            )
            next_id += 1
        else:
            transactions.append(
                NetworkTransaction(kind, mode, backpressure=rng.randrange(3))
            )

    return tuple(transactions[:count])


def _sv_bool(value: bool) -> str:
    return "1'b1" if value else "1'b0"


def _sv_mod(value: int) -> str:
    return "2'b11" if value < 0 else "2'b01" if value > 0 else "2'b00"


def make_testbench(transactions: Sequence[NetworkTransaction]) -> str:
    """生成带逐周期协议断言和逐事务状态输出的 Icarus testbench。"""

    lines = [
        "module tb;",
        "  logic clk=0; always #5 clk=~clk;",
        "  logic rst; logic [1:0] mode_state;",
        "  logic tick_valid,tick_ready,route_flush_valid,route_flush_ready;",
        "  logic [3:0] input_spikes; logic tick_rsp_valid,tick_rsp_ready;",
        "  logic [2:0] tick_rsp_status; logic [7:0] hidden_spikes,pending_hidden_state;",
        "  logic [1:0] output_spikes;",
        "  logic host_cmd_valid,host_cmd_ready,host_cmd_broadcast;",
        "  logic [2:0] host_cmd_opcode,host_rsp_status; logic [3:0] host_neuron_addr,host_rsp_neuron_addr;",
        "  logic [15:0] host_snapshot_commit_id,host_mod_commit_id; logic signed [1:0] host_modulator;",
        "  logic [1:0] host_weight_addr; logic signed [7:0] host_weight_wdata,host_weight_rdata;",
        "  logic host_rsp_valid,host_rsp_ready;",
        "  logic prune_commit_valid,prune_commit_ready,prune_rsp_valid,prune_rsp_ready;",
        "  logic [15:0] prune_commit_id,prune_rsp_id; logic [2:0] prune_rsp_status;",
        "  logic [39:0] prune_rsp_masks_flat,issue_masks_flat,structural_masks_flat;",
        "  logic busy,protocol_error; logic [31:0] commit_epoch_state;",
        "  logic [9:0] mask_valids_state,pending_snapshot_valids_state;",
        "  logic [159:0] pending_snapshot_ids_flat_state,utility_flat_state;",
        "  logic [35:0] network_hidden_dense_reads_state,network_hidden_reads_issued_state;",
        "  logic [35:0] network_hidden_reads_saved_state,network_output_dense_reads_state;",
        "  logic [35:0] network_output_reads_issued_state,network_output_reads_saved_state;",
        "  logic [9:0] last_observation_valids_state,last_commit_valids_state;",
        "  logic [159:0] last_observation_ids_flat_state,last_commit_ids_flat_state;",
        "  logic [159:0] membranes_flat_state; logic [79:0] thresholds_flat_state;",
        "  logic [9:0] core_snapshot_valids_state; logic [479:0] eligibility_snapshots_flat_state;",
        "  logic [39:0] held_masks; logic [15:0] held_id; logic [2:0] held_status;",
        "  logic [9:0] held_mask_valids; logic [39:0] held_structural_masks;",
        "  logic [31:0] held_epoch;",
        "  logic [7:0] held_hidden; logic [1:0] held_output;",
        "  integer timeout,index;",
        "  eneuron_pruned_network_4x8x2 dut(.*);",
        "  task clear_inputs; begin",
        "    tick_valid=0; route_flush_valid=0; input_spikes=0; tick_rsp_ready=0;",
        "    host_cmd_valid=0; host_cmd_opcode=0; host_cmd_broadcast=0; host_neuron_addr=0;",
        "    host_snapshot_commit_id=0; host_mod_commit_id=0; host_modulator=0;",
        "    host_weight_addr=0; host_weight_wdata=0; host_rsp_ready=0;",
        "    prune_commit_valid=0; prune_commit_id=0; prune_rsp_ready=0;",
        "  end endtask",
        "  function automatic integer popcount4(input logic [3:0] value);",
        "    popcount4=value[0]+value[1]+value[2]+value[3];",
        "  endfunction",
        "  task assert_mask_front; logic [3:0] expected; integer audit_index; begin",
        "    for(audit_index=0;audit_index<8;audit_index=audit_index+1) begin",
        "      expected=input_spikes & (mask_valids_state[audit_index] ? structural_masks_flat[audit_index*4 +: 4] : 4'hf);",
        "      if(issue_masks_flat[audit_index*4 +: 4] !== expected) $fatal(1,\"HIDDEN_MASK_NOT_FRONT index=%0d\",audit_index);",
        "    end",
        "    for(audit_index=0;audit_index<2;audit_index=audit_index+1) begin",
        "      expected=pending_hidden_state[audit_index*4 +: 4] &",
        "        (mask_valids_state[audit_index+8] ? structural_masks_flat[(audit_index+8)*4 +: 4] : 4'hf);",
        "      if(issue_masks_flat[(audit_index+8)*4 +: 4] !== expected) $fatal(1,\"OUTPUT_MASK_NOT_FRONT index=%0d\",audit_index);",
        "    end",
        "  end endtask",
        "  always @(negedge clk) begin",
        "    if(!rst) begin",
        "      #1;",
        "      assert_mask_front();",
        "      for(index=0;index<10;index=index+1)",
        "        if(mask_valids_state[index] && popcount4(structural_masks_flat[index*4 +: 4])!=2)",
        "          $fatal(1,\"VALID_MASK_NOT_EXACT_TWO index=%0d\",index);",
        "    end",
        "  end",
        "  task show_state(input integer transaction_id,input integer status); integer read_index; begin",
        "    host_cmd_broadcast=0;",
        "    $write(\"STATE %0d %0d %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h\",",
        "      transaction_id,status,hidden_spikes,output_spikes,pending_hidden_state,commit_epoch_state,",
        "      issue_masks_flat,structural_masks_flat,mask_valids_state,utility_flat_state,",
        "      last_observation_valids_state,last_observation_ids_flat_state,",
        "      last_commit_valids_state,last_commit_ids_flat_state,",
        "      pending_snapshot_valids_state,pending_snapshot_ids_flat_state,membranes_flat_state,",
        "      thresholds_flat_state,core_snapshot_valids_state,eligibility_snapshots_flat_state,",
        "      network_hidden_dense_reads_state,network_hidden_reads_issued_state,",
        "      network_hidden_reads_saved_state,network_output_dense_reads_state,",
        "      network_output_reads_issued_state,network_output_reads_saved_state);",
        "    for(read_index=0;read_index<40;read_index=read_index+1) begin",
        "      host_neuron_addr=read_index/4; host_weight_addr=read_index%4; #1;",
        "      $write(\" %0d\",$signed(host_weight_rdata));",
        "    end",
        "    $write(\"\\n\");",
        "  end endtask",
        "  task do_tick(input integer transaction_id,input [1:0] mode,input [3:0] mask,input integer bp); begin",
        "    @(negedge clk); mode_state=mode; input_spikes=mask; tick_valid=1; #1; assert_mask_front();",
        "    if(!tick_ready) $fatal(1,\"TICK_NOT_READY tx=%0d\",transaction_id);",
        "    @(posedge clk); #1; tick_valid=0; input_spikes=0; timeout=0;",
        "    while(!tick_rsp_valid) begin @(posedge clk); #1; timeout=timeout+1;",
        "      if(timeout>500) $fatal(1,\"TICK_TIMEOUT tx=%0d\",transaction_id); end",
        "    if(tick_rsp_status!=0) $fatal(1,\"TICK_STATUS tx=%0d\",transaction_id);",
        "    held_status=tick_rsp_status; held_hidden=hidden_spikes; held_output=output_spikes;",
        "    repeat(bp) begin @(posedge clk); #1; if(!tick_rsp_valid || tick_rsp_status!=held_status",
        "      || hidden_spikes!=held_hidden || output_spikes!=held_output) $fatal(1,\"TICK_BP_UNSTABLE\"); end",
        "    tick_rsp_ready=1; @(posedge clk); #1; tick_rsp_ready=0; show_state(transaction_id,0);",
        "  end endtask",
        "  task do_flush(input integer transaction_id,input [1:0] mode,input integer bp); begin",
        "    @(negedge clk); mode_state=mode; route_flush_valid=1; #1; assert_mask_front();",
        "    if(!route_flush_ready) $fatal(1,\"FLUSH_NOT_READY\");",
        "    @(posedge clk); #1; route_flush_valid=0; timeout=0; while(!tick_rsp_valid) begin",
        "      @(posedge clk); #1; timeout=timeout+1; if(timeout>500) $fatal(1,\"FLUSH_TIMEOUT\"); end",
        "    held_hidden=hidden_spikes; held_output=output_spikes; repeat(bp) begin @(posedge clk); #1;",
        "      if(!tick_rsp_valid || hidden_spikes!=held_hidden || output_spikes!=held_output) $fatal(1,\"FLUSH_BP_UNSTABLE\"); end",
        "    tick_rsp_ready=1; @(posedge clk); #1; tick_rsp_ready=0; show_state(transaction_id,0);",
        "  end endtask",
        "  task do_host(input integer transaction_id,input [1:0] mode,input [2:0] opcode,",
        "      input broadcast,input [3:0] neuron,input [15:0] command_id,input signed [1:0] mod,",
        "      input [1:0] weight_address,input signed [7:0] weight_data,input integer bp); begin",
        "    @(negedge clk); mode_state=mode; host_cmd_opcode=opcode;",
        "    host_cmd_broadcast=broadcast; host_neuron_addr=neuron;",
        "    host_snapshot_commit_id=command_id; host_mod_commit_id=command_id; host_modulator=mod;",
        "    host_weight_addr=weight_address; host_weight_wdata=weight_data; host_cmd_valid=1; #1;",
        "    if(!host_cmd_ready) $fatal(1,\"HOST_NOT_READY tx=%0d opcode=%0d\",transaction_id,opcode);",
        "    @(posedge clk); #1; host_cmd_valid=0; timeout=0; while(!host_rsp_valid) begin",
        "      @(posedge clk); #1; timeout=timeout+1; if(timeout>500) $fatal(1,\"HOST_TIMEOUT tx=%0d\",transaction_id); end",
        "    if(host_rsp_status!=0) $fatal(1,\"HOST_STATUS tx=%0d status=%0d\",transaction_id,host_rsp_status);",
        "    held_status=host_rsp_status; held_id=host_rsp_neuron_addr; repeat(bp) begin @(posedge clk); #1;",
        "      if(!host_rsp_valid || host_rsp_status!=held_status || host_rsp_neuron_addr!=held_id)",
        "        $fatal(1,\"HOST_BP_UNSTABLE tx=%0d\",transaction_id); end",
        "    host_rsp_ready=1; @(posedge clk); #1; host_rsp_ready=0; show_state(transaction_id,0);",
        "  end endtask",
        "  task do_commit(input integer transaction_id,input [15:0] command_id,input integer bp); begin",
        "    @(negedge clk); mode_state=1; held_mask_valids=mask_valids_state;",
        "    held_structural_masks=structural_masks_flat; held_epoch=commit_epoch_state;",
        "    prune_commit_id=command_id; prune_commit_valid=1; #1;",
        "    if(!prune_commit_ready || tick_ready || route_flush_ready || host_cmd_ready) $fatal(1,\"COMMIT_PRIORITY\");",
        "    @(posedge clk); #1; prune_commit_valid=0; timeout=0; while(!prune_rsp_valid) begin",
        "      if(tick_ready || route_flush_ready || host_cmd_ready) $fatal(1,\"RUNTIME_DURING_COMMIT\");",
        "      if(mask_valids_state!=held_mask_valids && mask_valids_state!=10'h3ff)",
        "        $fatal(1,\"PARTIAL_MASK_EPOCH valids=%h\",mask_valids_state);",
        "      if(mask_valids_state==held_mask_valids && structural_masks_flat!=held_structural_masks)",
        "        $fatal(1,\"MASK_CHANGED_BEFORE_ATOMIC_PUBLISH\");",
        "      if(commit_epoch_state!=held_epoch) $fatal(1,\"EPOCH_PUBLISHED_BEFORE_RESPONSE\");",
        "      @(posedge clk); #1; timeout=timeout+1; if(timeout>500) $fatal(1,\"COMMIT_TIMEOUT\"); end",
        "    if(prune_rsp_status!=0) $fatal(1,\"COMMIT_STATUS status=%0d\",prune_rsp_status);",
        "    for(index=0;index<10;index=index+1) if(popcount4(structural_masks_flat[index*4 +: 4])!=2)",
        "      $fatal(1,\"COMMIT_NOT_EXACT_TWO index=%0d\",index);",
        "    held_status=prune_rsp_status; held_id=prune_rsp_id; held_masks=prune_rsp_masks_flat;",
        "    repeat(bp) begin @(posedge clk); #1; if(!prune_rsp_valid || prune_rsp_status!=held_status",
        "      || prune_rsp_id!=held_id || prune_rsp_masks_flat!=held_masks) $fatal(1,\"COMMIT_BP_UNSTABLE\"); end",
        "    prune_rsp_ready=1; @(posedge clk); #1; prune_rsp_ready=0; show_state(transaction_id,0);",
        "  end endtask",
        "  task do_read(input integer transaction_id,input [1:0] mode); begin",
        "    @(negedge clk); mode_state=mode; #1;",
        "    if(busy || host_rsp_valid) $fatal(1,\"READ_SIDE_EFFECT\");",
        "    show_state(transaction_id,0);",
        "  end endtask",
        "  initial begin clear_inputs(); mode_state=1; rst=1; repeat(3) @(posedge clk); rst=0; #1;",
    ]

    host_opcode = {"clear": 0, "snapshot": 1, "mod": 2, "weight": 3}
    for transaction_id, transaction in enumerate(transactions):
        if transaction.kind == "tick":
            lines.append(
                f"    do_tick({transaction_id},2'd{transaction.mode},4'h{transaction.mask:x},{transaction.backpressure});"
            )
        elif transaction.kind == "flush":
            lines.append(
                f"    do_flush({transaction_id},2'd{transaction.mode},{transaction.backpressure});"
            )
        elif transaction.kind in host_opcode:
            lines.append(
                "    do_host("
                f"{transaction_id},2'd{transaction.mode},3'd{host_opcode[transaction.kind]},"
                f"{_sv_bool(transaction.broadcast)},4'd{transaction.neuron},16'd{transaction.command_id},"
                f"{_sv_mod(transaction.modulator)},2'd{transaction.weight_addr},"
                f"8'sd{transaction.weight_data},{transaction.backpressure});"
            )
        elif transaction.kind == "commit":
            lines.append(
                f"    do_commit({transaction_id},16'd{transaction.command_id},{transaction.backpressure});"
            )
        elif transaction.kind == "read":
            lines.append(f"    do_read({transaction_id},2'd{transaction.mode});")
        else:
            raise ValueError(f"unknown transaction kind: {transaction.kind}")
    lines.extend(["    $display(\"NP4B_ENEURON_RANDOM_DONE\"); $finish;", "  end", "endmodule"])
    return "\n".join(lines) + "\n"


def _state_tuple(transaction_id: int, state: NetworkState) -> tuple[int, ...]:
    return (
        transaction_id,
        state.status,
        state.hidden_spikes,
        state.output_spikes,
        state.pending_hidden,
        state.commit_epoch,
        state.issue_masks,
        state.structural_masks,
        state.mask_valids,
        state.utilities,
        state.observation_valids,
        state.observation_ids,
        state.commit_valids,
        state.commit_ids,
        state.pending_snapshot_valids,
        state.pending_snapshot_ids,
        state.membranes,
        state.thresholds,
        state.core_snapshot_valids,
        state.eligibility_snapshots,
        state.hidden_dense_reads,
        state.hidden_reads_issued,
        state.hidden_reads_saved,
        state.output_dense_reads,
        state.output_reads_issued,
        state.output_reads_saved,
        *state.weights,
    )


def expected_states(
    transactions: Sequence[NetworkTransaction],
) -> tuple[list[tuple[int, ...]], int]:
    model = ENeuronPrunedNetworkReference()
    result: list[tuple[int, ...]] = []
    pruned_snapshot_zeroing_transitions = 0
    for transaction_id, transaction in enumerate(transactions):
        before = model.state(status=0)
        pruned_before = [
            (
                tuple(model.cores[neuron].weights),
                tuple(model.gates[neuron].utility),
                model.gates[neuron].structural_mask,
                model.gates[neuron].mask_valid,
            )
            for neuron in range(10)
        ]
        after = model.execute(transaction)
        for neuron, (weights, utility, mask, valid) in enumerate(pruned_before):
            if not valid:
                continue
            for lane in range(4):
                if mask & (1 << lane):
                    continue
                if model.cores[neuron].weights[lane] != weights[lane]:
                    raise AssertionError(
                        f"Python oracle 被剪权重变化: tx={transaction_id} "
                        f"neuron={neuron} lane={lane}"
                    )
                if model.gates[neuron].utility[lane] != utility[lane]:
                    raise AssertionError(
                        f"Python oracle 被剪 utility 变化: tx={transaction_id} "
                        f"neuron={neuron} lane={lane}"
                    )
                old_snapshot = before.eligibility_snapshots >> (
                    (neuron * 4 + lane) * 12
                ) & 0xFFF
                new_snapshot = after.eligibility_snapshots >> (
                    (neuron * 4 + lane) * 12
                ) & 0xFFF
                if old_snapshot != new_snapshot:
                    if old_snapshot == 0 or new_snapshot != 0:
                        raise AssertionError(
                            f"Python oracle 被剪 snapshot 非法变化: tx={transaction_id} "
                            f"neuron={neuron} lane={lane} "
                            f"old=0x{old_snapshot:03x} new=0x{new_snapshot:03x}"
                        )
                    pruned_snapshot_zeroing_transitions += 1
        if transaction.mode == MODE_INFER:
            frozen_before = (
                before.utilities,
                before.structural_masks,
                before.mask_valids,
                before.observation_valids,
                before.observation_ids,
                before.commit_valids,
                before.commit_ids,
                before.pending_snapshot_valids,
                before.pending_snapshot_ids,
                before.core_snapshot_valids,
                before.eligibility_snapshots,
                before.weights,
            )
            frozen_after = (
                after.utilities,
                after.structural_masks,
                after.mask_valids,
                after.observation_valids,
                after.observation_ids,
                after.commit_valids,
                after.commit_ids,
                after.pending_snapshot_valids,
                after.pending_snapshot_ids,
                after.core_snapshot_valids,
                after.eligibility_snapshots,
                after.weights,
            )
            if frozen_before != frozen_after:
                raise AssertionError(f"Python oracle INFER 学习状态变化: tx={transaction_id}")
            # 显式 STATE_CLEAR 会按既有合同复位动态阈值；其他 INFER 事务不得改阈值。
            if transaction.kind != "clear" and before.thresholds != after.thresholds:
                raise AssertionError(f"Python oracle INFER 阈值变化: tx={transaction_id}")
        result.append(_state_tuple(transaction_id, after))
    return result, pruned_snapshot_zeroing_transitions


def parse_states(output: str) -> list[tuple[int, ...]]:
    """STATE 前 26 项是十六进制，末尾 40 个权重是十进制。"""

    result: list[tuple[int, ...]] = []
    for line in output.splitlines():
        if not line.startswith("STATE "):
            continue
        values = line.split()[1:]
        prefix = [int(values[0]), int(values[1])]
        prefix.extend(int(value, 16) for value in values[2:26])
        weights = [int(value) for value in values[26:]]
        result.append(tuple(prefix + weights))
    return result


def run_seed(seed: int, transaction_count: int) -> int:
    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 Icarus Verilog")
    transactions = make_transactions(seed, transaction_count)
    with tempfile.TemporaryDirectory(prefix=f"np4b_eneuron_random_{seed}_") as temp_dir:
        temp = Path(temp_dir)
        tb_path = temp / "tb.sv"
        sim_path = temp / "sim.out"
        tb_path.write_text(make_testbench(transactions), encoding="utf-8")
        sources = (
            ROOT / "digital_lif_engine.sv",
            ROOT / "local_prune_gate_2of4.sv",
            ROOT / "eneuron_local_prune_wrapper.sv",
            ROOT / "pruned_network_tick_scheduler.sv",
            ROOT / "local_prune_commit_barrier.sv",
            ROOT / "eneuron_pruned_network_4x8x2.sv",
            tb_path,
        )
        compiled = subprocess.run(
            [str(iverilog), "-g2012", "-s", "tb", "-o", str(sim_path), *(str(path) for path in sources)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if compiled.returncode != 0:
            raise AssertionError(f"seed={seed} 编译失败:\n{compiled.stdout}{compiled.stderr}")
        environment = os.environ.copy()
        environment["PATH"] = f"{vvp.parent}{os.pathsep}{environment.get('PATH', '')}"
        ran = subprocess.run(
            [str(vvp), str(sim_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=environment,
        )
        if ran.returncode != 0:
            output_tail = "\n".join((ran.stdout + ran.stderr).splitlines()[-80:])
            raise AssertionError(f"seed={seed} RTL 失败（末80行）:\n{output_tail}")
    actual = parse_states(ran.stdout)
    expected, zeroing_transitions = expected_states(transactions)
    if actual != expected:
        for index, (actual_state, expected_state) in enumerate(zip(actual, expected)):
            if actual_state != expected_state:
                raise AssertionError(
                    f"seed={seed} tx={index} {transactions[index]} 不一致\n"
                    f"actual={actual_state}\nexpected={expected_state}"
                )
        raise AssertionError(
            f"seed={seed} 状态数量不一致 actual={len(actual)} expected={len(expected)}"
        )
    return zeroing_transitions


def run_matrix(*, seeds: Sequence[int], transaction_count: int) -> dict[str, int]:
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("seeds 必须非空且互不重复")
    zeroing_transitions = sum(run_seed(seed, transaction_count) for seed in seeds)
    summary = {
        "seeds": len(seeds),
        "transactions_per_seed": transaction_count,
        "transactions": len(seeds) * transaction_count,
        "pruned_snapshot_zeroing_transitions": zeroing_transitions,
        "pruned_weight_changes": 0,
        "pruned_utility_changes": 0,
    }
    LOGGER.info(
        "ENeuron 随机网络 cosim 通过: seeds=%d transactions_per_seed=%d total=%d",
        len(seeds),
        transaction_count,
        len(seeds) * transaction_count,
    )
    LOGGER.info("NP4B4_ENEURON_RANDOM_SUMMARY %s", json.dumps(summary, sort_keys=True))
    return summary


__all__ = ["make_transactions", "run_matrix", "run_seed"]

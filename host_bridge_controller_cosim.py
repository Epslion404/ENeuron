"""Host Bridge controller、真实 Tile 与 Python oracle 的逐命令协同仿真。"""

from __future__ import annotations

import logging
import os
import random
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from host_bridge_oracle import (
    Flit,
    HostBridgeOracle,
    Opcode,
    Status,
    encode_modulators,
)
from rtl_tile_cosim import find_tool


LOGGER = logging.getLogger("host_bridge_controller_cosim")
ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ExpectedCommand:
    """一条命令在 response_accept 前后的完整期望状态。"""

    command: Flit
    response: Flit
    pre_arch: tuple[int, ...]
    post_arch: tuple[int, ...]
    tile_state: tuple[int, ...]
    stall_cycles: int


def command(opcode: int | Opcode, **fields: int) -> Flit:
    """用协议默认零字段构造命令。"""
    return Flit(
        opcode=int(opcode),
        flags=fields.get("flags", 0),
        txn_id=fields.get("txn_id", 0),
        episode_id=fields.get("episode_id", 0),
        tick_id=fields.get("tick_id", 0),
        arg0=fields.get("arg0", 0),
        arg1=fields.get("arg1", 0),
    )


def flatten_arch(state: tuple[object, ...]) -> tuple[int, ...]:
    """把 oracle 架构状态转换为 RTL 打印顺序。"""
    return tuple(int(value) for value in state)


def flatten_tile(bridge: HostBridgeOracle) -> tuple[int, ...]:
    """按 testbench 的层次寄存器打印顺序展平真实 Tile 状态。"""
    values: list[int] = []
    for neuron in bridge.tile.neurons:
        values.extend(
            (
                neuron.current,
                neuron.membrane,
                neuron.refractory,
                neuron.threshold,
                neuron.post_trace,
                *neuron.weights,
                *neuron.pre_trace,
                *neuron.eligibility,
                int(neuron.snapshot_valid),
                *neuron.eligibility_snapshot,
            )
        )
    values.extend(
        (
            bridge.tile.pending_hidden,
            int(bridge.tile.snapshot_valid),
            bridge.tile.pending_commit_id,
            bridge.tile.pending_episode_id,
            int(bridge.tile.last_commit_valid),
            bridge.tile.last_commit_id,
            bridge.tile.weight_epoch,
        )
    )
    return tuple(values)


def build_expectations(
    commands: tuple[Flit, ...],
    stall_cycles: tuple[int, ...],
) -> tuple[ExpectedCommand, ...]:
    """在 response_accept 语义边界上执行 oracle。"""
    if len(commands) != len(stall_cycles):
        raise ValueError("命令与 stall 长度必须一致")
    bridge = HostBridgeOracle()
    expected: list[ExpectedCommand] = []
    for request, stall in zip(commands, stall_cycles):
        pre_arch = flatten_arch(bridge.architectural_state())
        response = bridge.execute(request)
        expected.append(
            ExpectedCommand(
                command=request,
                response=response,
                pre_arch=pre_arch,
                post_arch=flatten_arch(bridge.architectural_state()),
                tile_state=flatten_tile(bridge),
                stall_cycles=stall,
            )
        )
    return tuple(expected)


def directed_commands() -> tuple[Flit, ...]:
    """覆盖全部成功动作、主要首错链和 snapshot/epoch 生命周期。"""
    raw = [
        command(Opcode.STATUS_READ, txn_id=1),
        command(Opcode.WEIGHT_READ, txn_id=2, arg0=0),
        command(Opcode.WEIGHT_WRITE, txn_id=3, arg0=2 | (1 << 2) | (7 << 4)),
        command(Opcode.WEIGHT_READ, txn_id=4, arg0=2 | (1 << 2)),
        command(Opcode.EP_START, txn_id=5, episode_id=0x10),
        command(Opcode.TICK_BEGIN, txn_id=6, episode_id=0x10, tick_id=0, arg0=2),
        command(Opcode.INPUT_EVENT, txn_id=7, episode_id=0x10, tick_id=0, arg0=0),
        command(Opcode.INPUT_EVENT, txn_id=8, episode_id=0x10, tick_id=0, arg0=1),
        command(Opcode.TICK_COMMIT, txn_id=9, episode_id=0x10, tick_id=0),
        command(Opcode.EP_END, txn_id=10, episode_id=0x10),
        command(Opcode.EP_START, txn_id=11, flags=1, episode_id=0x20),
        command(Opcode.TICK_BEGIN, txn_id=12, episode_id=0x20, tick_id=0, arg0=2),
        command(Opcode.INPUT_EVENT, txn_id=13, episode_id=0x20, tick_id=0, arg0=2),
        command(Opcode.INPUT_EVENT, txn_id=14, episode_id=0x20, tick_id=0, arg0=3),
        command(Opcode.TICK_COMMIT, txn_id=15, episode_id=0x20, tick_id=0),
        command(Opcode.EP_END, txn_id=16, episode_id=0x20, arg0=1),
        command(Opcode.STATUS_READ, txn_id=17, arg0=1),
        command(Opcode.WEIGHT_WRITE, txn_id=18, arg0=5 << 4),
        command(
            Opcode.MOD_COMMIT,
            txn_id=19,
            episode_id=0x20,
            arg0=1,
            arg1=encode_modulators((1, -1, 1, -1)),
        ),
        command(Opcode.STATUS_READ, txn_id=20, arg0=1),
        command(Opcode.WEIGHT_WRITE, txn_id=21, arg0=0 | (0 << 2) | (0xF9 << 4)),
        command(Opcode.WEIGHT_READ, txn_id=22, arg0=0),
        command(Opcode.EP_START, txn_id=23, episode_id=0x30),
        command(Opcode.TICK_BEGIN, txn_id=24, episode_id=0x30, tick_id=0, arg0=1),
        command(Opcode.ABORT, txn_id=25, episode_id=0x30),
        command(0xA5, txn_id=26),
        command(Opcode.EP_START, txn_id=27, flags=2, episode_id=1),
        command(Opcode.WEIGHT_READ, txn_id=28, arg0=0xF),
        command(Opcode.MOD_COMMIT, txn_id=29, arg1=0b10),
        command(Opcode.STATUS_READ, txn_id=30),
        # 动态首错链：错误命令均不得推进已建立的 session/tick staging。
        command(Opcode.TICK_BEGIN, txn_id=31, episode_id=0x40, tick_id=0),
        command(Opcode.EP_START, txn_id=32, episode_id=0x40),
        command(Opcode.EP_START, txn_id=33, episode_id=0x41),
        command(Opcode.TICK_BEGIN, txn_id=34, episode_id=0x41, tick_id=0, arg0=2),
        command(Opcode.TICK_BEGIN, txn_id=35, episode_id=0x40, tick_id=1, arg0=2),
        command(Opcode.TICK_BEGIN, txn_id=36, episode_id=0x40, tick_id=0, arg0=5),
        command(Opcode.TICK_BEGIN, txn_id=37, episode_id=0x40, tick_id=0, arg0=2),
        command(Opcode.INPUT_EVENT, txn_id=38, episode_id=0x41, tick_id=0, arg0=0),
        command(Opcode.INPUT_EVENT, txn_id=39, episode_id=0x40, tick_id=1, arg0=0),
        command(Opcode.INPUT_EVENT, txn_id=40, episode_id=0x40, tick_id=0, arg0=4),
        command(Opcode.INPUT_EVENT, txn_id=41, episode_id=0x40, tick_id=0, arg0=0),
        command(Opcode.INPUT_EVENT, txn_id=42, episode_id=0x40, tick_id=0, arg0=0),
        command(Opcode.TICK_COMMIT, txn_id=43, episode_id=0x40, tick_id=0),
        command(Opcode.INPUT_EVENT, txn_id=44, episode_id=0x40, tick_id=0, arg0=1),
        command(Opcode.INPUT_EVENT, txn_id=45, episode_id=0x40, tick_id=0, arg0=2),
        command(Opcode.TICK_COMMIT, txn_id=46, episode_id=0x41, tick_id=0),
        command(Opcode.TICK_COMMIT, txn_id=47, episode_id=0x40, tick_id=1),
        command(Opcode.TICK_COMMIT, txn_id=48, episode_id=0x40, tick_id=0),
        command(Opcode.EP_END, txn_id=49, episode_id=0x41),
        command(Opcode.ABORT, txn_id=50, episode_id=0x40),
        # Snapshot/commit 首错链与 16-bit commit 空间耗尽。
        command(Opcode.EP_START, txn_id=51, flags=1, episode_id=0x50),
        command(Opcode.EP_END, txn_id=52, episode_id=0x50, arg0=5),
        command(Opcode.MOD_COMMIT, txn_id=53, episode_id=0x51, arg0=5),
        command(Opcode.MOD_COMMIT, txn_id=54, episode_id=0x50, arg0=6),
        command(Opcode.EP_START, txn_id=55, flags=1, episode_id=0x51),
        command(Opcode.WEIGHT_WRITE, txn_id=56, arg0=3 << 4),
        command(
            Opcode.MOD_COMMIT,
            txn_id=57,
            episode_id=0x50,
            arg0=5,
            arg1=encode_modulators((0, 0, 0, 0)),
        ),
        command(Opcode.EP_START, txn_id=58, flags=1, episode_id=0x51),
        command(Opcode.EP_END, txn_id=59, episode_id=0x51, arg0=5),
        command(Opcode.ABORT, txn_id=60, episode_id=0x51),
        command(Opcode.EP_START, txn_id=61, flags=1, episode_id=0x52),
        command(Opcode.EP_END, txn_id=62, episode_id=0x52, arg0=0xFFFF),
        command(
            Opcode.MOD_COMMIT,
            txn_id=63,
            episode_id=0x52,
            arg0=0xFFFF,
            arg1=encode_modulators((0, 0, 0, 0)),
        ),
        command(Opcode.EP_START, txn_id=64, flags=1, episode_id=0x53),
    ]
    return tuple(raw)


def make_state_aware_request(
    bridge: HostBridgeOracle,
    rng: random.Random,
    txn_id: int,
) -> Flit:
    """生成能推进状态、也会稳定命中协议错误的混合命令。"""
    tile = bridge.tile
    if not bridge.episode_active:
        choices = [Opcode.STATUS_READ, Opcode.EP_START, Opcode.WEIGHT_READ]
        choices.append(Opcode.MOD_COMMIT if tile.snapshot_valid else Opcode.WEIGHT_WRITE)
        opcode = rng.choice(choices)
        if opcode == Opcode.STATUS_READ:
            return command(opcode, txn_id=txn_id, arg0=rng.randrange(2))
        if opcode == Opcode.EP_START:
            return command(
                opcode,
                txn_id=txn_id,
                flags=rng.randrange(2),
                episode_id=rng.randrange(1 << 16),
            )
        if opcode == Opcode.MOD_COMMIT:
            return command(
                opcode,
                txn_id=txn_id,
                episode_id=tile.pending_episode_id,
                arg0=tile.pending_commit_id,
                arg1=encode_modulators(
                    tuple(rng.choice((-1, 0, 1)) for _ in range(4))
                ),
            )
        neuron = rng.randrange(4)
        weight = rng.randrange(4 if neuron < 2 else 2)
        arg0 = neuron | (weight << 2)
        if opcode == Opcode.WEIGHT_WRITE:
            arg0 |= rng.randrange(256) << 4
        return command(opcode, txn_id=txn_id, arg0=arg0)

    episode_id = bridge.active_episode_id
    tick_id = bridge.next_tick_ext & 0xFFFF
    if bridge.tick_open:
        choices = [Opcode.STATUS_READ, Opcode.ABORT, Opcode.TICK_COMMIT]
        if bridge.seen_event_count < bridge.expected_event_count:
            choices.extend((Opcode.INPUT_EVENT, Opcode.INPUT_EVENT))
        opcode = rng.choice(choices)
        if opcode == Opcode.STATUS_READ:
            return command(opcode, txn_id=txn_id)
        if opcode == Opcode.ABORT:
            return command(opcode, txn_id=txn_id, episode_id=episode_id)
        if opcode == Opcode.TICK_COMMIT:
            return command(
                opcode,
                txn_id=txn_id,
                episode_id=episode_id,
                tick_id=tick_id,
            )
        unused = [index for index in range(4) if not bridge.seen_mask & (1 << index)]
        return command(
            opcode,
            txn_id=txn_id,
            episode_id=episode_id,
            tick_id=tick_id,
            arg0=rng.choice(unused),
        )

    opcode = rng.choice(
        (Opcode.STATUS_READ, Opcode.TICK_BEGIN, Opcode.TICK_BEGIN, Opcode.EP_END, Opcode.ABORT)
    )
    if opcode == Opcode.STATUS_READ:
        return command(opcode, txn_id=txn_id, arg0=rng.randrange(2))
    if opcode == Opcode.TICK_BEGIN:
        return command(
            opcode,
            txn_id=txn_id,
            episode_id=episode_id,
            tick_id=tick_id,
            arg0=rng.randrange(5),
        )
    if opcode == Opcode.ABORT:
        return command(opcode, txn_id=txn_id, episode_id=episode_id)
    commit_id = 0
    if bridge.episode_train:
        commit_id = tile.last_commit_id + 1 if tile.last_commit_valid else 0
    return command(
        opcode,
        txn_id=txn_id,
        episode_id=episode_id,
        arg0=commit_id,
    )


def random_commands(seed: int, count: int) -> tuple[Flit, ...]:
    """复用 oracle 状态生成固定随机命令流。"""
    if count <= 0:
        raise ValueError("command_count 必须为正数")
    rng = random.Random(seed)
    bridge = HostBridgeOracle()
    commands: list[Flit] = []
    for txn_id in range(count):
        if rng.random() < 0.35:
            request = Flit(
                opcode=rng.randrange(256),
                flags=rng.randrange(256),
                txn_id=txn_id & 0xFFFF,
                episode_id=rng.randrange(1 << 16),
                tick_id=rng.randrange(1 << 16),
                arg0=rng.randrange(1 << 32),
                arg1=rng.randrange(1 << 32),
            )
        else:
            request = make_state_aware_request(bridge, rng, txn_id & 0xFFFF)
        commands.append(request)
        bridge.execute(request)
    return tuple(commands)


def core_state_writes(instance: str, n_inputs: int) -> list[str]:
    """生成一个真实多周期核的层次状态打印语句。"""
    lines = [
        f'      $write(" %0d %0d %0d %0d %0d", $signed({instance}.current_reg), $signed({instance}.membrane_reg), {instance}.refractory, {instance}.threshold_reg, {instance}.post_trace);'
    ]
    for index in range(n_inputs):
        lines.append(f'      $write(" %0d", $signed({instance}.weights[{index}]));')
    for index in range(n_inputs):
        lines.append(f'      $write(" %0d", {instance}.pre_trace[{index}]);')
    for index in range(n_inputs):
        lines.append(f'      $write(" %0d", $signed({instance}.eligibility[{index}]));')
    lines.append(f'      $write(" %0d", {instance}.snapshot_valid);')
    for index in range(n_inputs):
        lines.append(
            f'      $write(" %0d", $signed({instance}.eligibility_snapshot[{index}]));'
        )
    return lines


def make_testbench(command_count: int) -> str:
    """生成读取外部命令向量的单时钟集成 testbench。"""
    lines = [
        "module tb;",
        "  localparam integer COMMAND_COUNT = %d;" % command_count,
        "  logic clk=1'b0; always #5 clk=~clk;",
        "  logic rst, cmd_valid, cmd_ready, rsp_valid, rsp_ready;",
        "  logic [127:0] cmd_data, rsp_data, command_word, saved_rsp;",
        "  logic tile_state_clear, tile_tick_valid, tile_route_flush_valid;",
        "  logic [3:0] tile_input_spikes; logic tile_learn_enable;",
        "  logic tile_snapshot_we; logic [15:0] tile_snapshot_commit_id, tile_snapshot_episode_id;",
        "  logic tile_mod_valid; logic [15:0] tile_mod_commit_id;",
        "  logic signed [1:0] tile_hidden0_modulator, tile_hidden1_modulator, tile_output0_modulator, tile_output1_modulator;",
        "  logic tile_weight_we; logic [1:0] tile_neuron_addr, tile_weight_addr;",
        "  logic signed [7:0] tile_weight_wdata, tile_weight_rdata;",
        "  logic tile_ready, tile_busy, tile_done, tile_protocol_error;",
        "  logic [1:0] tile_hidden_spikes, tile_output_spikes, tile_pending_hidden_state;",
        "  logic tile_snapshot_valid_state, tile_last_commit_valid_state;",
        "  logic [15:0] tile_pending_commit_id_state, tile_pending_episode_id_state, tile_last_commit_id_state;",
        "  logic [31:0] tile_weight_epoch_state;",
        "  integer vector_file, scan_result, transaction_id, stall_cycles, timeout_count, stall_index;",
        "  logic saved_episode_active, saved_episode_train, saved_tick_open, saved_fatal_error;",
        "  logic [15:0] saved_active_episode_id; logic [16:0] saved_next_tick_ext;",
        "  logic [2:0] saved_expected_event_count, saved_seen_event_count; logic [3:0] saved_seen_mask;",
        "  logic [7:0] saved_fatal_opcode, saved_fatal_phase;",
        "",
        "  digital_snn_host_bridge_controller controller (",
        "    .clk(clk), .rst(rst), .cmd_valid(cmd_valid), .cmd_ready(cmd_ready), .cmd_data(cmd_data),",
        "    .rsp_valid(rsp_valid), .rsp_ready(rsp_ready), .rsp_data(rsp_data),",
        "    .tile_state_clear(tile_state_clear), .tile_tick_valid(tile_tick_valid),",
        "    .tile_route_flush_valid(tile_route_flush_valid), .tile_input_spikes(tile_input_spikes),",
        "    .tile_learn_enable(tile_learn_enable), .tile_snapshot_we(tile_snapshot_we),",
        "    .tile_snapshot_commit_id(tile_snapshot_commit_id), .tile_snapshot_episode_id(tile_snapshot_episode_id),",
        "    .tile_mod_valid(tile_mod_valid), .tile_mod_commit_id(tile_mod_commit_id),",
        "    .tile_hidden0_modulator(tile_hidden0_modulator), .tile_hidden1_modulator(tile_hidden1_modulator),",
        "    .tile_output0_modulator(tile_output0_modulator), .tile_output1_modulator(tile_output1_modulator),",
        "    .tile_weight_we(tile_weight_we), .tile_neuron_addr(tile_neuron_addr),",
        "    .tile_weight_addr(tile_weight_addr), .tile_weight_wdata(tile_weight_wdata),",
        "    .tile_weight_rdata(tile_weight_rdata), .tile_ready(tile_ready), .tile_done(tile_done),",
        "    .tile_protocol_error(tile_protocol_error), .tile_hidden_spikes(tile_hidden_spikes),",
        "    .tile_output_spikes(tile_output_spikes), .tile_snapshot_valid_state(tile_snapshot_valid_state),",
        "    .tile_pending_commit_id_state(tile_pending_commit_id_state),",
        "    .tile_pending_episode_id_state(tile_pending_episode_id_state),",
        "    .tile_last_commit_valid_state(tile_last_commit_valid_state),",
        "    .tile_last_commit_id_state(tile_last_commit_id_state),",
        "    .tile_weight_epoch_state(tile_weight_epoch_state)",
        "  );",
        "",
        "  digital_snn_tile_4x2x2 tile (",
        "    .clk(clk), .rst(rst), .state_clear(tile_state_clear), .tick_valid(tile_tick_valid),",
        "    .route_flush_valid(tile_route_flush_valid), .input_spikes(tile_input_spikes),",
        "    .learn_enable(tile_learn_enable), .snapshot_we(tile_snapshot_we),",
        "    .snapshot_commit_id(tile_snapshot_commit_id), .snapshot_episode_id(tile_snapshot_episode_id),",
        "    .mod_valid(tile_mod_valid), .mod_commit_id(tile_mod_commit_id),",
        "    .hidden0_modulator(tile_hidden0_modulator), .hidden1_modulator(tile_hidden1_modulator),",
        "    .output0_modulator(tile_output0_modulator), .output1_modulator(tile_output1_modulator),",
        "    .weight_we(tile_weight_we), .neuron_addr(tile_neuron_addr), .weight_addr(tile_weight_addr),",
        "    .weight_wdata(tile_weight_wdata), .weight_rdata(tile_weight_rdata),",
        "    .ready(tile_ready), .busy(tile_busy), .done(tile_done), .protocol_error(tile_protocol_error),",
        "    .hidden_spikes(tile_hidden_spikes), .output_spikes(tile_output_spikes),",
        "    .pending_hidden_state(tile_pending_hidden_state), .snapshot_valid_state(tile_snapshot_valid_state),",
        "    .pending_commit_id_state(tile_pending_commit_id_state),",
        "    .pending_episode_id_state(tile_pending_episode_id_state),",
        "    .last_commit_valid_state(tile_last_commit_valid_state),",
        "    .last_commit_id_state(tile_last_commit_id_state), .weight_epoch_state(tile_weight_epoch_state)",
        "  );",
        "",
        "  task capture_arch; begin",
        "    saved_episode_active=controller.episode_active; saved_episode_train=controller.episode_train;",
        "    saved_active_episode_id=controller.active_episode_id; saved_next_tick_ext=controller.next_tick_ext;",
        "    saved_tick_open=controller.tick_open; saved_expected_event_count=controller.expected_event_count;",
        "    saved_seen_event_count=controller.seen_event_count; saved_seen_mask=controller.seen_mask;",
        "    saved_fatal_error=controller.fatal_error; saved_fatal_opcode=controller.fatal_opcode;",
        "    saved_fatal_phase=controller.fatal_phase;",
        "  end endtask",
        "  task assert_arch_stable; begin",
        "    if ((controller.episode_active !== saved_episode_active) ||",
        "        (controller.episode_train !== saved_episode_train) ||",
        "        (controller.active_episode_id !== saved_active_episode_id) ||",
        "        (controller.next_tick_ext !== saved_next_tick_ext) ||",
        "        (controller.tick_open !== saved_tick_open) ||",
        "        (controller.expected_event_count !== saved_expected_event_count) ||",
        "        (controller.seen_event_count !== saved_seen_event_count) ||",
        "        (controller.seen_mask !== saved_seen_mask) ||",
        "        (controller.fatal_error !== saved_fatal_error) ||",
        "        (controller.fatal_opcode !== saved_fatal_opcode) ||",
        "        (controller.fatal_phase !== saved_fatal_phase))",
        "      $fatal(1, \"architectural state committed before response_accept\");",
        "  end endtask",
        "  task write_arch; begin",
        "    $write(\" %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d\",",
        "      controller.episode_active, controller.episode_train, controller.active_episode_id,",
        "      controller.next_tick_ext, controller.tick_open, controller.expected_event_count,",
        "      controller.seen_event_count, controller.seen_mask, controller.fatal_error,",
        "      controller.fatal_opcode, controller.fatal_phase);",
        "  end endtask",
        "  task write_tile; begin",
    ]
    lines.extend(core_state_writes("tile.hidden0", 4))
    lines.extend(core_state_writes("tile.hidden1", 4))
    lines.extend(core_state_writes("tile.output0", 2))
    lines.extend(core_state_writes("tile.output1", 2))
    lines.extend(
        [
            "    $write(\" %0d %0d %0d %0d %0d %0d %0d\", tile.pending_hidden,",
            "      tile.snapshot_valid, tile.pending_commit_id, tile.pending_episode_id,",
            "      tile.last_commit_valid, tile.last_commit_id, tile.weight_epoch);",
            "  end endtask",
            "  task show_pre(input integer index); begin",
            "    $write(\"PRE %0d %032h\", index, rsp_data); write_arch(); write_tile(); $write(\"\\n\");",
            "  end endtask",
            "  task show_post(input integer index); begin",
            "    $write(\"POST %0d\", index); write_arch(); write_tile(); $write(\"\\n\");",
            "  end endtask",
            "",
            "  initial begin",
            "    rst=1'b1; cmd_valid=1'b0; rsp_ready=1'b1; cmd_data='0;",
            "    vector_file=$fopen(\"commands.txt\", \"r\");",
            "    if (!vector_file) $fatal(1, \"cannot open commands.txt\");",
            "    repeat(3) @(posedge clk); #1; rst=1'b0;",
            "    repeat(2) @(posedge clk); #1;",
            "    for (transaction_id=0; transaction_id<COMMAND_COUNT; transaction_id=transaction_id+1) begin",
            "      scan_result=$fscanf(vector_file, \"%h %d\\n\", command_word, stall_cycles);",
            "      if (scan_result != 2) $fatal(1, \"bad command vector at %0d\", transaction_id);",
            "      @(negedge clk);",
            "      while (!cmd_ready) @(negedge clk);",
            "      capture_arch(); cmd_data=command_word; cmd_valid=1'b1; rsp_ready=1'b1;",
            "      @(posedge clk); #1; cmd_valid=1'b0; rsp_ready=1'b0;",
            "      timeout_count=0;",
            "      while (!rsp_valid) begin",
            "        @(posedge clk); #1; timeout_count=timeout_count+1; assert_arch_stable();",
            "        if (timeout_count > 100) $fatal(1, \"response timeout at %0d\", transaction_id);",
            "      end",
            "      saved_rsp=rsp_data; assert_arch_stable(); show_pre(transaction_id);",
            "      for (stall_index=0; stall_index<stall_cycles; stall_index=stall_index+1) begin",
            "        @(posedge clk); #1;",
            "        if (!rsp_valid || (rsp_data !== saved_rsp))",
            "          $fatal(1, \"response changed under backpressure at %0d\", transaction_id);",
            "        assert_arch_stable();",
            "      end",
            "      @(negedge clk); rsp_ready=1'b1;",
            "      @(posedge clk); #1;",
            "      if (rsp_valid) $fatal(1, \"response not released after accept at %0d\", transaction_id);",
            "      show_post(transaction_id);",
            "    end",
            "    $fclose(vector_file); $finish;",
            "  end",
            "endmodule",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_simulation(output: str) -> tuple[dict[int, tuple[str, tuple[int, ...]]], dict[int, tuple[int, ...]]]:
    """解析 PRE/POST 状态行，忽略工具自身日志。"""
    pre: dict[int, tuple[str, tuple[int, ...]]] = {}
    post: dict[int, tuple[int, ...]] = {}
    for line in output.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "PRE":
            pre[int(fields[1])] = (fields[2].lower(), tuple(int(value) for value in fields[3:]))
        elif fields[0] == "POST":
            post[int(fields[1])] = tuple(int(value) for value in fields[2:])
    return pre, post


def first_difference(actual: tuple[int, ...], expected: tuple[int, ...]) -> str:
    """返回第一个字段差异，压缩长状态的失败输出。"""
    if len(actual) != len(expected):
        return f"字段数 actual={len(actual)} expected={len(expected)}"
    for index, (actual_value, expected_value) in enumerate(zip(actual, expected)):
        if actual_value != expected_value:
            return f"field[{index}] actual={actual_value} expected={expected_value}"
    return "无差异"


def run_commands(commands: tuple[Flit, ...], stall_seed: int) -> tuple[ExpectedCommand, ...]:
    """编译真实 RTL、执行命令流并逐字段比对。"""
    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")

    rng = random.Random(stall_seed)
    stalls = tuple(rng.randrange(5) for _ in commands)
    expected = build_expectations(commands, stalls)
    with tempfile.TemporaryDirectory(prefix="eneuron_bridge_controller_") as temp_dir:
        temp = Path(temp_dir)
        tb_path = temp / "tb.sv"
        sim_path = temp / "tb.vvp"
        vector_path = temp / "commands.txt"
        tb_path.write_text(make_testbench(len(commands)), encoding="utf-8")
        vector_path.write_text(
            "".join(
                f"{item.command.pack():032x} {item.stall_cycles}\n" for item in expected
            ),
            encoding="ascii",
        )
        compile_result = subprocess.run(
            [
                str(iverilog),
                "-g2012",
                "-Wall",
                "-s",
                "tb",
                "-o",
                str(sim_path),
                str(ROOT / "digital_lif_engine.sv"),
                str(ROOT / "digital_snn_tile_4x2x2.sv"),
                str(ROOT / "digital_snn_host_bridge_controller.sv"),
                str(tb_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if compile_result.returncode != 0:
            raise RuntimeError(
                f"iverilog failed:\n{compile_result.stdout}\n{compile_result.stderr}"
            )
        env = os.environ.copy()
        env["PATH"] = f"{vvp.parent}{os.pathsep}{env.get('PATH', '')}"
        sim_result = subprocess.run(
            [str(vvp), str(sim_path)],
            cwd=temp,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if sim_result.returncode != 0:
            raise RuntimeError(f"vvp failed:\n{sim_result.stdout}\n{sim_result.stderr}")

    actual_pre, actual_post = parse_simulation(sim_result.stdout)
    if len(actual_pre) != len(expected) or len(actual_post) != len(expected):
        raise AssertionError(
            f"状态行数量错误: PRE={len(actual_pre)} POST={len(actual_post)} expected={len(expected)}"
        )
    for index, item in enumerate(expected):
        response_hex, pre_values = actual_pre[index]
        expected_response = f"{item.response.pack():032x}"
        if response_hex != expected_response:
            raise AssertionError(
                f"command[{index}] response actual={response_hex} expected={expected_response} "
                f"request={item.command}"
            )
        expected_pre = item.pre_arch + item.tile_state
        if pre_values != expected_pre:
            raise AssertionError(
                f"command[{index}] PRE {first_difference(pre_values, expected_pre)} "
                f"request={item.command} response={item.response}"
            )
        expected_post = item.post_arch + item.tile_state
        if actual_post[index] != expected_post:
            raise AssertionError(
                f"command[{index}] POST {first_difference(actual_post[index], expected_post)} "
                f"request={item.command} response={item.response}"
            )
    LOGGER.info("Host Bridge controller cosim passed: commands=%d", len(commands))
    return expected


def run_directed_controller_regression(check_mod_epoch: bool = False) -> None:
    """运行固定事务流；可额外显式检查 MOD 响应中的更新后 epoch。"""
    expected = run_commands(directed_commands(), stall_seed=0xC05)
    covered_statuses = {item.response.flags for item in expected}
    required_statuses = {
        int(status)
        for status in Status
        if status not in (Status.RESERVED_08, Status.RESERVED_0D, Status.INTERNAL_FATAL)
    }
    if not required_statuses <= covered_statuses:
        missing = sorted(required_statuses - covered_statuses)
        raise AssertionError(f"定向 controller 回归缺少状态码覆盖: {missing}")
    if check_mod_epoch:
        mod_items = [item for item in expected if item.command.opcode == Opcode.MOD_COMMIT]
        successful = [item for item in mod_items if item.response.flags == Status.OK]
        if len(successful) < 1:
            raise AssertionError("定向流至少需要一个成功 MOD")
        item = successful[0]
        if item.response.arg1 != 1 or item.tile_state[-1] != 1:
            raise AssertionError(
                f"MOD 响应必须报告更新后 epoch=1，response={item.response.arg1} "
                f"tile={item.tile_state[-1]}"
            )


def run_random_controller_cosim(seed: int, command_count: int) -> None:
    """运行一组状态感知与任意位型混合的随机命令。"""
    run_commands(random_commands(seed, command_count), stall_seed=seed ^ 0x5A17)

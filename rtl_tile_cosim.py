"""4->2->2 数字 SNN tile 的事务级 Icarus/Python 协同仿真。"""

from __future__ import annotations

import argparse
import logging
import os
import random
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rtl_reference import RtlReferenceNeuron, RtlState


LOGGER = logging.getLogger("rtl_tile_cosim")
ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class TileTransaction:
    """一个在 tile ready 时提交的原子命令。"""

    kind: str
    mask: int = 0
    learn_enable: bool = True
    commit_id: int = 0
    episode_id: int = 0
    modulators: tuple[int, int, int, int] = (0, 0, 0, 0)
    neuron_addr: int = 0
    weight_addr: int = 0
    weight_wdata: int = 0
    busy_noise: str = ""


@dataclass
class TileOracle:
    """只描述 tile 事务语义，不模拟内部 all-done FSM。"""

    hidden: list[RtlReferenceNeuron]
    output: list[RtlReferenceNeuron]
    pending_hidden: int = 0
    snapshot_valid: bool = False
    pending_commit_id: int = 0
    pending_episode_id: int = 0
    last_commit_id: int = 0
    last_commit_valid: bool = False
    weight_epoch: int = 0

    @classmethod
    def create(cls) -> TileOracle:
        return cls(
            hidden=[RtlReferenceNeuron(n_inputs=4, threshold=4) for _ in range(2)],
            output=[RtlReferenceNeuron(n_inputs=2, threshold=2) for _ in range(2)],
        )

    @property
    def neurons(self) -> tuple[RtlReferenceNeuron, ...]:
        return tuple(self.hidden + self.output)


def find_tool(name: str) -> Path | None:
    discovered = shutil.which(name)
    if discovered:
        return Path(discovered)
    for candidate in (
        Path("C:/msys64/ucrt64/bin") / f"{name}.exe",
        Path("C:/msys64/mingw64/bin") / f"{name}.exe",
    ):
        if candidate.exists():
            return candidate
    return None


def make_transactions(seed: int, count: int) -> tuple[TileTransaction, ...]:
    """定向覆盖协议边界后，再追加随机合法/非法事务。"""
    if count < 20:
        raise ValueError("count 必须至少为 20")
    transactions = [
        TileTransaction("weight", neuron_addr=2, weight_addr=0, weight_wdata=2),
        TileTransaction("weight", neuron_addr=2, weight_addr=1, weight_wdata=1),
        TileTransaction("weight", neuron_addr=3, weight_addr=0, weight_wdata=1),
        TileTransaction("weight", neuron_addr=3, weight_addr=1, weight_wdata=2),
        TileTransaction("tick", mask=0b0011, busy_noise="clear"),
        TileTransaction("tick", mask=0, busy_noise="snapshot"),
        TileTransaction("tick", mask=0b1100),
        TileTransaction("snapshot", commit_id=10, episode_id=3, busy_noise="tick"),
        TileTransaction("clear", busy_noise="mod"),
        TileTransaction("mod", commit_id=9, modulators=(1, -1, 1, -1)),
        TileTransaction("mod", commit_id=10, modulators=(1, -1, 1, -1), busy_noise="weight"),
        TileTransaction("snapshot", learn_enable=False, commit_id=11, episode_id=4),
        TileTransaction("snapshot", commit_id=10, episode_id=4),
        TileTransaction("snapshot", commit_id=11, episode_id=4),
        TileTransaction("mod", commit_id=11, modulators=(0, 0, 0, 0)),
        TileTransaction("weight", learn_enable=False, neuron_addr=0, weight_addr=0, weight_wdata=-7),
        TileTransaction("weight", neuron_addr=2, weight_addr=3, weight_wdata=7),
        TileTransaction("tick", mask=0b1111, learn_enable=False, busy_noise="mod"),
        TileTransaction("clear"),
        TileTransaction("reset"),
    ]

    rng = random.Random(seed)
    next_commit_id = 20
    available_commit: int | None = None
    while len(transactions) < count:
        kind = rng.choice(
            ("tick", "tick", "tick", "route_flush", "snapshot", "mod", "weight", "clear", "reset")
        )
        learn_enable = rng.random() < 0.8
        if kind == "tick":
            transactions.append(
                TileTransaction(
                    kind,
                    mask=rng.randrange(16),
                    learn_enable=learn_enable,
                    busy_noise=rng.choice(("", "", "tick", "clear", "snapshot", "mod", "weight")),
                )
            )
        elif kind == "route_flush":
            transactions.append(
                TileTransaction(
                    kind,
                    learn_enable=learn_enable,
                    busy_noise=rng.choice(("", "tick", "clear", "snapshot", "mod", "weight")),
                )
            )
        elif kind == "snapshot":
            use_valid = learn_enable and available_commit is None and rng.random() < 0.8
            commit_id = next_commit_id if use_valid else rng.randrange(max(1, next_commit_id + 2))
            transactions.append(
                TileTransaction(
                    kind,
                    learn_enable=learn_enable,
                    commit_id=commit_id,
                    episode_id=rng.randrange(1 << 12),
                    busy_noise=rng.choice(("", "tick", "clear")),
                )
            )
            if use_valid:
                available_commit = commit_id
                next_commit_id += 1
        elif kind == "mod":
            use_valid = learn_enable and available_commit is not None and rng.random() < 0.8
            commit_id = available_commit if use_valid else rng.randrange(max(1, next_commit_id + 2))
            transactions.append(
                TileTransaction(
                    kind,
                    learn_enable=learn_enable,
                    commit_id=commit_id,
                    modulators=tuple(rng.choice((-1, 0, 1)) for _ in range(4)),
                    busy_noise=rng.choice(("", "tick", "weight")),
                )
            )
            if use_valid:
                available_commit = None
        elif kind == "weight":
            transactions.append(
                TileTransaction(
                    kind,
                    learn_enable=learn_enable,
                    neuron_addr=rng.randrange(4),
                    weight_addr=rng.randrange(4),
                    weight_wdata=rng.randint(-12, 12),
                )
            )
        elif kind == "clear":
            transactions.append(TileTransaction(kind, busy_noise=rng.choice(("", "tick", "mod"))))
        else:
            transactions.append(TileTransaction(kind))
            available_commit = None
            next_commit_id = 20
    return tuple(transactions)


def mod_bits(value: int) -> str:
    if value < 0:
        return "2'b11"
    if value > 0:
        return "2'b01"
    return "2'b00"


def clear_command_lines() -> list[str]:
    return [
        "state_clear=1'b0; tick_valid=1'b0; route_flush_valid=1'b0; input_spikes='0; learn_enable=1'b1;",
        "snapshot_we=1'b0; snapshot_commit_id='0; snapshot_episode_id='0;",
        "mod_valid=1'b0; mod_commit_id='0; hidden0_modulator='0; hidden1_modulator='0;",
        "output0_modulator='0; output1_modulator='0; weight_we=1'b0;",
        "neuron_addr='0; weight_addr='0; weight_wdata='0;",
    ]


def transaction_assignments(transaction: TileTransaction) -> list[str]:
    lines = [f"learn_enable=1'b{int(transaction.learn_enable)};"]
    if transaction.kind == "tick":
        lines.extend(["tick_valid=1'b1;", f"input_spikes=4'b{transaction.mask:04b};"])
    elif transaction.kind == "route_flush":
        lines.append("route_flush_valid=1'b1;")
    elif transaction.kind == "clear":
        lines.append("state_clear=1'b1;")
    elif transaction.kind == "snapshot":
        lines.extend(
            [
                "snapshot_we=1'b1;",
                f"snapshot_commit_id={transaction.commit_id};",
                f"snapshot_episode_id={transaction.episode_id};",
            ]
        )
    elif transaction.kind == "mod":
        m0, m1, m2, m3 = transaction.modulators
        lines.extend(
            [
                "mod_valid=1'b1;",
                f"mod_commit_id={transaction.commit_id};",
                f"hidden0_modulator={mod_bits(m0)};",
                f"hidden1_modulator={mod_bits(m1)};",
                f"output0_modulator={mod_bits(m2)};",
                f"output1_modulator={mod_bits(m3)};",
            ]
        )
    elif transaction.kind == "weight":
        lines.extend(
            [
                "weight_we=1'b1;",
                f"neuron_addr={transaction.neuron_addr};",
                f"weight_addr={transaction.weight_addr};",
                f"weight_wdata={transaction.weight_wdata};",
            ]
        )
    else:
        raise ValueError(f"未知事务类型: {transaction.kind}")
    return lines


def noise_assignments(kind: str) -> list[str]:
    if kind == "tick":
        return ["tick_valid=1'b1;", "input_spikes=4'b1111;"]
    if kind == "route_flush":
        return ["route_flush_valid=1'b1;"]
    if kind == "clear":
        return ["state_clear=1'b1;"]
    if kind == "snapshot":
        return ["snapshot_we=1'b1;", "snapshot_commit_id=16'hfffe;"]
    if kind == "mod":
        return ["mod_valid=1'b1;", "mod_commit_id=16'hfffe;", "hidden0_modulator=2'b01;"]
    if kind == "weight":
        return ["weight_we=1'b1;", "neuron_addr=0;", "weight_addr=0;", "weight_wdata=-7;"]
    return []


def core_state_writes(instance: str, n_inputs: int) -> list[str]:
    lines = [
        f"      $write(\" %0d %0d %0d %0d %0d\", $signed({instance}.current_reg), $signed({instance}.membrane_reg), {instance}.refractory, {instance}.threshold_reg, {instance}.post_trace);"
    ]
    for index in range(n_inputs):
        lines.append(f"      $write(\" %0d\", $signed({instance}.weights[{index}]));")
    for index in range(n_inputs):
        lines.append(f"      $write(\" %0d\", {instance}.pre_trace[{index}]);")
    for index in range(n_inputs):
        lines.append(f"      $write(\" %0d\", $signed({instance}.eligibility[{index}]));")
    lines.append(f"      $write(\" %0d\", {instance}.snapshot_valid);")
    for index in range(n_inputs):
        lines.append(
            f"      $write(\" %0d\", $signed({instance}.eligibility_snapshot[{index}]));"
        )
    return lines


def make_testbench(transactions: tuple[TileTransaction, ...]) -> str:
    lines = [
        "module tb;",
        "  logic clk=1'b0; always #5 clk=~clk;",
        "  logic rst, state_clear, tick_valid, route_flush_valid, learn_enable, snapshot_we, mod_valid, weight_we;",
        "  logic [3:0] input_spikes;",
        "  logic [15:0] snapshot_commit_id, snapshot_episode_id, mod_commit_id;",
        "  logic signed [1:0] hidden0_modulator, hidden1_modulator, output0_modulator, output1_modulator;",
        "  logic [1:0] neuron_addr, weight_addr;",
        "  logic signed [7:0] weight_wdata, weight_rdata;",
        "  logic ready, busy, done, protocol_error;",
        "  logic [1:0] hidden_spikes, output_spikes, pending_hidden_state;",
        "  logic snapshot_valid_state;",
        "  logic [15:0] pending_commit_id_state, pending_episode_id_state;",
        "  logic last_commit_valid_state; logic [15:0] last_commit_id_state;",
        "  logic [31:0] weight_epoch_state;",
        "  logic [1:0] saved_pending_hidden; logic saved_snapshot_valid;",
        "  logic [15:0] saved_commit_id, saved_episode_id; logic [31:0] saved_weight_epoch;",
        "  integer latency;",
        "  digital_snn_tile_4x2x2 dut (.*);",
        "  task clear_commands; begin",
    ]
    lines.extend(f"      {line}" for line in clear_command_lines())
    lines.extend(
        [
            "    end endtask",
            "  task capture_external_state; begin",
            "      saved_pending_hidden=dut.pending_hidden; saved_snapshot_valid=dut.snapshot_valid;",
            "      saved_commit_id=dut.pending_commit_id; saved_episode_id=dut.pending_episode_id;",
            "      saved_weight_epoch=dut.weight_epoch;",
            "    end endtask",
            "  task assert_external_state_stable; begin",
            "      if ((dut.pending_hidden !== saved_pending_hidden) ||",
            "          (dut.snapshot_valid !== saved_snapshot_valid) ||",
            "          (dut.pending_commit_id !== saved_commit_id) ||",
            "          (dut.pending_episode_id !== saved_episode_id) ||",
            "          (dut.weight_epoch !== saved_weight_epoch))",
            "        $fatal(1, \"tile state changed before done\");",
            "      if (ready || !busy || done || protocol_error || hidden_spikes || output_spikes)",
            "        $fatal(1, \"busy output contract failed\");",
            "      if (weight_rdata !== 0) $fatal(1, \"weight read visible while busy\");",
            "    end endtask",
            "  task show_state(input integer transaction_id); begin",
            "      $write(\"STATE %0d %0d %0d %0d %0d %0d %0d %0d %0d\", transaction_id, dut.pending_hidden, dut.snapshot_valid, dut.pending_commit_id, dut.pending_episode_id, dut.weight_epoch, hidden_spikes, output_spikes, protocol_error);",
        ]
    )
    lines.extend(core_state_writes("dut.hidden0", 4))
    lines.extend(core_state_writes("dut.hidden1", 4))
    lines.extend(core_state_writes("dut.output0", 2))
    lines.extend(core_state_writes("dut.output1", 2))
    lines.extend(
        [
            "      $write(\" %0d %0d %0d %0d %0d\\n\", dut.last_commit_valid, dut.last_commit_id, ready, done, latency);",
            "    end endtask",
            "  always @(negedge clk) begin",
            "    if (!rst) begin",
            "      if (ready !== !busy) $fatal(1, \"ready/busy contract failed\");",
            "      if ((hidden_spikes || output_spikes) && !done) $fatal(1, \"spike escaped done\");",
            "    end",
            "  end",
            "  initial begin",
            "    clear_commands(); rst=1'b1; repeat(2) @(posedge clk); #1 rst=1'b0;",
        ]
    )

    for transaction_id, transaction in enumerate(transactions):
        if transaction.kind == "reset":
            lines.extend(
                [
                    "    @(negedge clk); clear_commands(); latency=0; rst=1'b1;",
                    "    @(posedge clk); #1; rst=1'b0;",
                    f"    show_state({transaction_id});",
                    "    @(posedge clk); #1; if (done) $fatal(1, \"done must be low after reset\");",
                ]
            )
            continue

        lines.append("    @(negedge clk); clear_commands(); capture_external_state(); latency=0;")
        lines.extend(f"    {line}" for line in transaction_assignments(transaction))
        lines.extend(["    @(posedge clk); #1;", "    clear_commands();"])
        if transaction.busy_noise:
            lines.extend(
                [
                    "    if (!done) begin",
                    "      assert_external_state_stable();",
                    "      @(negedge clk); clear_commands();",
                ]
            )
            lines.extend(f"      {line}" for line in noise_assignments(transaction.busy_noise))
            lines.extend(
                [
                    "      @(posedge clk); #1; latency=latency+1; clear_commands();",
                    "      if (!done) assert_external_state_stable();",
                    "    end",
                ]
            )
        lines.extend(
            [
                "    while (!done) begin",
                "      @(posedge clk); #1; latency=latency+1;",
                "      if (!done) assert_external_state_stable();",
                "      if (latency > 40) $fatal(1, \"tile transaction timeout\");",
                "    end",
                f"    show_state({transaction_id});",
                "    @(posedge clk); #1; if (done) $fatal(1, \"done wider than one cycle\");",
            ]
        )

    lines.extend(["    $finish;", "  end", "endmodule"])
    return "\n".join(lines) + "\n"


def flatten_core(state: RtlState) -> tuple[int, ...]:
    return (
        state.current,
        state.membrane,
        state.refractory,
        state.threshold,
        state.post_trace,
        *state.weights,
        *state.pre_trace,
        *state.eligibility,
        state.snapshot_valid,
        *state.eligibility_snapshot,
    )


def idle_state(neuron: RtlReferenceNeuron, tick: int) -> RtlState:
    return neuron.tick((), tick=tick, tick_valid=False)


def apply_transaction(
    oracle: TileOracle,
    transaction: TileTransaction,
    transaction_id: int,
) -> tuple[int, ...]:
    hidden_mask = 0
    output_mask = 0
    protocol_error = 0
    latency = 0

    if transaction.kind == "reset":
        oracle = TileOracle.create()
        states = [idle_state(neuron, transaction_id) for neuron in oracle.neurons]
        return (
            transaction_id,
            oracle.pending_hidden,
            int(oracle.snapshot_valid),
            oracle.pending_commit_id,
            oracle.pending_episode_id,
            oracle.weight_epoch,
            0,
            0,
            0,
            *(field for state in states for field in flatten_core(state)),
            int(oracle.last_commit_valid),
            oracle.last_commit_id,
            1,
            0,
            0,
        ), oracle

    if transaction.kind == "tick":
        output_active = tuple(index for index in range(2) if oracle.pending_hidden & (1 << index))
        input_active = tuple(index for index in range(4) if transaction.mask & (1 << index))
        output_states = [
            neuron.tick(output_active, learn_enable=transaction.learn_enable, tick=transaction_id)
            for neuron in oracle.output
        ]
        hidden_states = [
            neuron.tick(input_active, learn_enable=transaction.learn_enable, tick=transaction_id)
            for neuron in oracle.hidden
        ]
        for index, state in enumerate(hidden_states):
            hidden_mask |= state.spike << index
        for index, state in enumerate(output_states):
            output_mask |= state.spike << index
        oracle.pending_hidden = hidden_mask
        states = hidden_states + output_states
        core_latencies = []
        for state in hidden_states:
            core_latencies.append(12 + (4 if transaction.learn_enable and state.spike else 0))
        for state in output_states:
            core_latencies.append(8 + (2 if transaction.learn_enable and state.spike else 0))
        latency = max(core_latencies) + 1
    elif transaction.kind == "route_flush":
        output_active = tuple(index for index in range(2) if oracle.pending_hidden & (1 << index))
        hidden_states = [idle_state(neuron, transaction_id) for neuron in oracle.hidden]
        output_states = [
            neuron.tick(output_active, learn_enable=transaction.learn_enable, tick=transaction_id)
            for neuron in oracle.output
        ]
        for index, state in enumerate(output_states):
            output_mask |= state.spike << index
        oracle.pending_hidden = 0
        states = hidden_states + output_states
        latency = max(
            8 + (2 if transaction.learn_enable and state.spike else 0)
            for state in output_states
        ) + 1
    elif transaction.kind == "clear":
        states = [
            neuron.tick((), tick=transaction_id, tick_valid=False, state_clear=True)
            for neuron in oracle.neurons
        ]
        oracle.pending_hidden = 0
        latency = 1
    elif transaction.kind == "snapshot":
        allowed = (
            transaction.learn_enable
            and not oracle.snapshot_valid
            and (not oracle.last_commit_valid or transaction.commit_id > oracle.last_commit_id)
        )
        if allowed:
            states = [
                neuron.tick((), tick=transaction_id, tick_valid=False, snapshot_we=True)
                for neuron in oracle.neurons
            ]
            oracle.snapshot_valid = True
            oracle.pending_commit_id = transaction.commit_id
            oracle.pending_episode_id = transaction.episode_id
            oracle.last_commit_id = transaction.commit_id
            oracle.last_commit_valid = True
            latency = 6
        else:
            states = [idle_state(neuron, transaction_id) for neuron in oracle.neurons]
            protocol_error = 1
    elif transaction.kind == "mod":
        allowed = (
            transaction.learn_enable
            and oracle.snapshot_valid
            and transaction.commit_id == oracle.pending_commit_id
        )
        if allowed:
            states = [
                neuron.tick(
                    (),
                    learn_enable=True,
                    mod_valid=True,
                    modulator=modulator,
                    tick=transaction_id,
                    tick_valid=False,
                )
                for neuron, modulator in zip(oracle.neurons, transaction.modulators)
            ]
            oracle.snapshot_valid = False
            oracle.weight_epoch += 1
            hidden_nonzero = any(transaction.modulators[index] for index in (0, 1))
            output_nonzero = any(transaction.modulators[index] for index in (2, 3))
            latency = 6 if hidden_nonzero else 4 if output_nonzero else 1
        else:
            states = [idle_state(neuron, transaction_id) for neuron in oracle.neurons]
            protocol_error = 1
    elif transaction.kind == "weight":
        address_valid = transaction.neuron_addr < 2 or transaction.weight_addr < 2
        allowed = transaction.learn_enable and address_valid
        states = []
        for neuron_id, neuron in enumerate(oracle.neurons):
            states.append(
                neuron.tick(
                    (),
                    learn_enable=transaction.learn_enable,
                    tick=transaction_id,
                    tick_valid=False,
                    weight_we=allowed and neuron_id == transaction.neuron_addr,
                    weight_addr=transaction.weight_addr if neuron_id < 2 else transaction.weight_addr & 1,
                    weight_wdata=transaction.weight_wdata,
                )
            )
        if allowed:
            latency = 1
        else:
            protocol_error = 1
    else:
        raise ValueError(f"未知事务类型: {transaction.kind}")

    return (
        transaction_id,
        oracle.pending_hidden,
        int(oracle.snapshot_valid),
        oracle.pending_commit_id,
        oracle.pending_episode_id,
        oracle.weight_epoch,
        hidden_mask,
        output_mask,
        protocol_error,
        *(field for state in states for field in flatten_core(state)),
        int(oracle.last_commit_valid),
        oracle.last_commit_id,
        1,
        1,
        latency,
    ), oracle


def expected_states(transactions: tuple[TileTransaction, ...]) -> list[tuple[int, ...]]:
    oracle = TileOracle.create()
    expected: list[tuple[int, ...]] = []
    for transaction_id, transaction in enumerate(transactions):
        state, oracle = apply_transaction(oracle, transaction, transaction_id)
        expected.append(state)
    return expected


def parse_states(output: str) -> list[tuple[int, ...]]:
    return [
        tuple(int(value) for value in line.split()[1:])
        for line in output.splitlines()
        if line.startswith("STATE ")
    ]


def run(seed: int, transaction_count: int) -> None:
    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")

    transactions = make_transactions(seed, transaction_count)
    with tempfile.TemporaryDirectory(prefix="eneuron_tile_") as temp_dir:
        temp = Path(temp_dir)
        tb_path = temp / "tb.sv"
        sim_path = temp / "tb.vvp"
        tb_path.write_text(make_testbench(transactions), encoding="utf-8")
        compile_result = subprocess.run(
            [
                str(iverilog),
                "-g2012",
                "-s",
                "tb",
                "-o",
                str(sim_path),
                str(ROOT / "digital_lif_engine.sv"),
                str(ROOT / "digital_snn_tile_4x2x2.sv"),
                str(tb_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if compile_result.returncode != 0:
            raise RuntimeError(f"iverilog failed:\n{compile_result.stdout}\n{compile_result.stderr}")

        env = os.environ.copy()
        env["PATH"] = f"{vvp.parent}{os.pathsep}{env.get('PATH', '')}"
        sim_result = subprocess.run(
            [str(vvp), str(sim_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if sim_result.returncode != 0:
            raise RuntimeError(f"vvp failed:\n{sim_result.stdout}\n{sim_result.stderr}")

    actual = parse_states(sim_result.stdout)
    expected = expected_states(transactions)
    if actual != expected:
        for index, (actual_state, expected_state) in enumerate(zip(actual, expected)):
            if actual_state != expected_state:
                raise AssertionError(
                    f"tile RTL 在事务 {index} 不一致: {transactions[index]}\n"
                    f"actual={actual_state}\nexpected={expected_state}"
                )
        raise AssertionError(f"状态数量不一致: actual={len(actual)} expected={len(expected)}")

    LOGGER.info("tile cosim 通过: seed=%d transactions=%d", seed, transaction_count)


def run_priority_conflict_regression() -> None:
    """验证非法高优先级命令不会把低优先级请求派发给子核。"""
    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")

    testbench = """
module tb;
  logic clk=1'b0; always #5 clk=~clk;
  logic rst, state_clear, tick_valid, route_flush_valid, learn_enable, snapshot_we, mod_valid, weight_we;
  logic [3:0] input_spikes;
  logic [15:0] snapshot_commit_id, snapshot_episode_id, mod_commit_id;
  logic signed [1:0] hidden0_modulator, hidden1_modulator, output0_modulator, output1_modulator;
  logic [1:0] neuron_addr, weight_addr;
  logic signed [7:0] weight_wdata, weight_rdata;
  logic ready, busy, done, protocol_error;
  logic [1:0] hidden_spikes, output_spikes, pending_hidden_state;
  logic snapshot_valid_state;
  logic [15:0] pending_commit_id_state, pending_episode_id_state;
  logic last_commit_valid_state; logic [15:0] last_commit_id_state;
  logic [31:0] weight_epoch_state;
  digital_snn_tile_4x2x2 dut (.*);

  task clear_commands; begin
    state_clear=0; tick_valid=0; route_flush_valid=0; input_spikes=0; learn_enable=1;
    snapshot_we=0; snapshot_commit_id=0; snapshot_episode_id=0;
    mod_valid=0; mod_commit_id=0; hidden0_modulator=0; hidden1_modulator=0;
    output0_modulator=0; output1_modulator=0; weight_we=0;
    neuron_addr=0; weight_addr=0; weight_wdata=0;
  end endtask

  initial begin
    clear_commands(); rst=1; repeat(2) @(posedge clk); #1 rst=0;

    // 先建立 pending snapshot，使下一次 SNAPSHOT 成为非法高优先级命令。
    @(negedge clk); snapshot_we=1; snapshot_commit_id=10; snapshot_episode_id=3;
    @(posedge clk); #1 clear_commands();
    while (!done) begin @(posedge clk); #1; end
    if (!snapshot_valid_state) $fatal(1, "snapshot setup failed");

    // 非法 SNAPSHOT + 合法 WEIGHT：不得向任何子核写权重。
    @(negedge clk); clear_commands(); snapshot_we=1; snapshot_commit_id=11;
    weight_we=1; neuron_addr=0; weight_addr=0; weight_wdata=7; #1;
    if (dut.core_weight_we != 0) $fatal(1, "illegal snapshot leaked weight request");
    if (dut.core_mod_valid != 0 || dut.core_tick_valid != 0)
      $fatal(1, "illegal snapshot leaked lower-priority request");
    @(posedge clk); #1;
    if (!done || !protocol_error) $fatal(1, "illegal snapshot must finish with error");

    // 非法 WEIGHT + 合法 TICK：不得启动 TICK。
    @(negedge clk); clear_commands(); weight_we=1; neuron_addr=2; weight_addr=3;
    tick_valid=1; input_spikes=4'b1111; #1;
    if (dut.core_tick_valid != 0) $fatal(1, "illegal weight leaked tick request");
    if (dut.core_weight_we != 0) $fatal(1, "illegal weight reached core");
    @(posedge clk); #1;
    if (!done || !protocol_error) $fatal(1, "illegal weight must finish with error");

    // 非法 MOD + 合法 TICK：不得启动 TICK。
    @(negedge clk); clear_commands(); mod_valid=1; mod_commit_id=16'hffff;
    route_flush_valid=1; tick_valid=1; input_spikes=4'b0011; #1;
    if (dut.core_tick_valid != 0) $fatal(1, "illegal mod leaked tick request");
    if (dut.core_mod_valid != 0) $fatal(1, "illegal mod reached core");
    @(posedge clk); #1;
    if (!done || !protocol_error) $fatal(1, "illegal mod must finish with error");

    $display("PRIORITY_CONFLICT_PASS");
    $finish;
  end
endmodule
"""

    with tempfile.TemporaryDirectory(prefix="eneuron_priority_") as temp_dir:
        temp = Path(temp_dir)
        tb_path = temp / "tb.sv"
        sim_path = temp / "tb.vvp"
        tb_path.write_text(testbench, encoding="utf-8")
        compile_result = subprocess.run(
            [
                str(iverilog),
                "-g2012",
                "-s",
                "tb",
                "-o",
                str(sim_path),
                str(ROOT / "digital_lif_engine.sv"),
                str(ROOT / "digital_snn_tile_4x2x2.sv"),
                str(tb_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if compile_result.returncode != 0:
            raise RuntimeError(
                f"priority regression compile failed:\n{compile_result.stdout}\n{compile_result.stderr}"
            )

        env = os.environ.copy()
        env["PATH"] = f"{vvp.parent}{os.pathsep}{env.get('PATH', '')}"
        sim_result = subprocess.run(
            [str(vvp), str(sim_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if sim_result.returncode != 0:
            raise AssertionError(
                f"priority conflict regression failed:\n{sim_result.stdout}\n{sim_result.stderr}"
            )
        if "PRIORITY_CONFLICT_PASS" not in sim_result.stdout:
            raise AssertionError("priority conflict regression 未输出 PASS")

    LOGGER.info("tile 非法高优先级命令隔离回归通过")


def run_route_flush_regression() -> None:
    """验证 ROUTE_FLUSH 只推进输出层，并冻结 clear/commit 保留合同。"""
    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")

    testbench = r"""
module tb;
  logic clk=1'b0; always #5 clk=~clk;
  logic rst, state_clear, tick_valid, route_flush_valid, learn_enable, snapshot_we, mod_valid, weight_we;
  logic [3:0] input_spikes;
  logic [15:0] snapshot_commit_id, snapshot_episode_id, mod_commit_id;
  logic signed [1:0] hidden0_modulator, hidden1_modulator, output0_modulator, output1_modulator;
  logic [1:0] neuron_addr, weight_addr;
  logic signed [7:0] weight_wdata, weight_rdata;
  logic ready, busy, done, protocol_error;
  logic [1:0] hidden_spikes, output_spikes, pending_hidden_state;
  logic snapshot_valid_state, last_commit_valid_state;
  logic [15:0] pending_commit_id_state, pending_episode_id_state, last_commit_id_state;
  logic [31:0] weight_epoch_state;
  logic signed [15:0] h_current [0:1], h_membrane [0:1];
  logic [3:0] h_refractory [0:1];
  logic [7:0] h_threshold [0:1], h_post [0:1];
  logic signed [7:0] h_weight [0:1][0:3];
  logic [7:0] h_pre [0:1][0:3];
  logic signed [11:0] h_elig [0:1][0:3], h_snapshot [0:1][0:3];
  logic h_snapshot_valid [0:1];
  logic signed [7:0] saved_weights [0:3][0:3];
  logic signed [11:0] saved_snapshots [0:3][0:3];
  integer latency, n, s;

  digital_snn_tile_4x2x2 dut (.*);

  task clear_commands; begin
    state_clear=0; tick_valid=0; route_flush_valid=0; input_spikes=0; learn_enable=1;
    snapshot_we=0; snapshot_commit_id=0; snapshot_episode_id=0;
    mod_valid=0; mod_commit_id=0; hidden0_modulator=0; hidden1_modulator=0;
    output0_modulator=0; output1_modulator=0; weight_we=0;
    neuron_addr=0; weight_addr=0; weight_wdata=0;
  end endtask

  task wait_done; begin
    latency=0;
    while (!done) begin
      @(posedge clk); #1; latency=latency+1;
      if (latency > 20) $fatal(1, "transaction timeout");
    end
  end endtask

  task save_hidden; begin
    h_current[0]=dut.hidden0.current_reg; h_current[1]=dut.hidden1.current_reg;
    h_membrane[0]=dut.hidden0.membrane_reg; h_membrane[1]=dut.hidden1.membrane_reg;
    h_refractory[0]=dut.hidden0.refractory; h_refractory[1]=dut.hidden1.refractory;
    h_threshold[0]=dut.hidden0.threshold_reg; h_threshold[1]=dut.hidden1.threshold_reg;
    h_post[0]=dut.hidden0.post_trace; h_post[1]=dut.hidden1.post_trace;
    h_snapshot_valid[0]=dut.hidden0.snapshot_valid; h_snapshot_valid[1]=dut.hidden1.snapshot_valid;
    for (s=0; s<4; s=s+1) begin
      h_weight[0][s]=dut.hidden0.weights[s]; h_weight[1][s]=dut.hidden1.weights[s];
      h_pre[0][s]=dut.hidden0.pre_trace[s]; h_pre[1][s]=dut.hidden1.pre_trace[s];
      h_elig[0][s]=dut.hidden0.eligibility[s]; h_elig[1][s]=dut.hidden1.eligibility[s];
      h_snapshot[0][s]=dut.hidden0.eligibility_snapshot[s];
      h_snapshot[1][s]=dut.hidden1.eligibility_snapshot[s];
    end
  end endtask

  task assert_hidden_unchanged; begin
    if (dut.hidden0.current_reg!==h_current[0] || dut.hidden1.current_reg!==h_current[1] ||
        dut.hidden0.membrane_reg!==h_membrane[0] || dut.hidden1.membrane_reg!==h_membrane[1] ||
        dut.hidden0.refractory!==h_refractory[0] || dut.hidden1.refractory!==h_refractory[1] ||
        dut.hidden0.threshold_reg!==h_threshold[0] || dut.hidden1.threshold_reg!==h_threshold[1] ||
        dut.hidden0.post_trace!==h_post[0] || dut.hidden1.post_trace!==h_post[1] ||
        dut.hidden0.snapshot_valid!==h_snapshot_valid[0] || dut.hidden1.snapshot_valid!==h_snapshot_valid[1])
      $fatal(1, "route flush changed hidden scalar state");
    for (s=0; s<4; s=s+1) begin
      if (dut.hidden0.weights[s]!==h_weight[0][s] || dut.hidden1.weights[s]!==h_weight[1][s] ||
          dut.hidden0.pre_trace[s]!==h_pre[0][s] || dut.hidden1.pre_trace[s]!==h_pre[1][s] ||
          dut.hidden0.eligibility[s]!==h_elig[0][s] || dut.hidden1.eligibility[s]!==h_elig[1][s] ||
          dut.hidden0.eligibility_snapshot[s]!==h_snapshot[0][s] ||
          dut.hidden1.eligibility_snapshot[s]!==h_snapshot[1][s])
        $fatal(1, "route flush changed hidden array state at %0d", s);
    end
  end endtask

  initial begin
    clear_commands(); rst=1; repeat(2) @(posedge clk); #1 rst=0;

    // 一个训练 TICK 让两个 hidden 发放并建立 pending_hidden=2'b11。
    @(negedge clk); tick_valid=1; input_spikes=4'b0011; learn_enable=1;
    @(posedge clk); #1; clear_commands(); wait_done();
    if (pending_hidden_state!==2'b11) $fatal(1, "tick did not create pending hidden spikes");
    save_hidden();

    // TRAIN flush 应只推进输出层，并在 C0+11 返回两个输出脉冲。
    @(negedge clk); route_flush_valid=1; tick_valid=1; input_spikes=4'b1111; learn_enable=1; #1;
    if (dut.core_tick_valid!==4'b1100) $fatal(1, "route flush priority/mask failed");
    @(posedge clk); #1; clear_commands(); wait_done();
    if (latency!=11) $fatal(1, "train flush latency %0d != 11", latency);
    if (hidden_spikes!==0 || output_spikes!==2'b11 || pending_hidden_state!==0)
      $fatal(1, "train flush output contract failed");
    assert_hidden_unchanged();

    // 即使 pending=0，INFER flush 也必须执行一次 output-only tick，延迟 C0+9。
    save_hidden();
    @(negedge clk); route_flush_valid=1; learn_enable=0;
    @(posedge clk); #1; clear_commands(); wait_done();
    if (latency!=9) $fatal(1, "infer flush latency %0d != 9", latency);
    if (hidden_spikes!==0 || pending_hidden_state!==0) $fatal(1, "infer flush contract failed");
    assert_hidden_unchanged();

    // 建立 snapshot，检查导出的 last_commit 状态。
    @(negedge clk); snapshot_we=1; snapshot_commit_id=16'd10; snapshot_episode_id=16'd3; learn_enable=1;
    @(posedge clk); #1; clear_commands(); wait_done();
    if (!snapshot_valid_state || !last_commit_valid_state || last_commit_id_state!=16'd10 ||
        pending_commit_id_state!=16'd10 || pending_episode_id_state!=16'd3)
      $fatal(1, "snapshot metadata export failed");
    for (s=0; s<4; s=s+1) begin
      saved_weights[0][s]=dut.hidden0.weights[s]; saved_weights[1][s]=dut.hidden1.weights[s];
      saved_snapshots[0][s]=dut.hidden0.eligibility_snapshot[s];
      saved_snapshots[1][s]=dut.hidden1.eligibility_snapshot[s];
      if (s<2) begin
        saved_weights[2][s]=dut.output0.weights[s]; saved_weights[3][s]=dut.output1.weights[s];
        saved_snapshots[2][s]=dut.output0.eligibility_snapshot[s];
        saved_snapshots[3][s]=dut.output1.eligibility_snapshot[s];
      end
    end

    // STATE_CLEAR 清动态状态和 pending route，但保留模型和 delayed commit。
    @(negedge clk); state_clear=1; learn_enable=0;
    @(posedge clk); #1; clear_commands(); wait_done();
    if (latency!=1 || !snapshot_valid_state || !last_commit_valid_state ||
        last_commit_id_state!=16'd10 || pending_commit_id_state!=16'd10 ||
        pending_episode_id_state!=16'd3 || weight_epoch_state!=0)
      $fatal(1, "state clear changed commit metadata");
    for (s=0; s<4; s=s+1) begin
      if (dut.hidden0.weights[s]!==saved_weights[0][s] || dut.hidden1.weights[s]!==saved_weights[1][s] ||
          dut.hidden0.eligibility_snapshot[s]!==saved_snapshots[0][s] ||
          dut.hidden1.eligibility_snapshot[s]!==saved_snapshots[1][s])
        $fatal(1, "state clear changed hidden model/snapshot at %0d", s);
      if (s<2 && (dut.output0.weights[s]!==saved_weights[2][s] || dut.output1.weights[s]!==saved_weights[3][s] ||
          dut.output0.eligibility_snapshot[s]!==saved_snapshots[2][s] ||
          dut.output1.eligibility_snapshot[s]!==saved_snapshots[3][s]))
        $fatal(1, "state clear changed output model/snapshot at %0d", s);
    end

    // 消费 snapshot 后 last_commit 仍表示最近捕获 ID。
    @(negedge clk); mod_valid=1; mod_commit_id=16'd10; learn_enable=1;
    @(posedge clk); #1; clear_commands(); wait_done();
    if (snapshot_valid_state || !last_commit_valid_state || last_commit_id_state!=16'd10 ||
        weight_epoch_state!=1)
      $fatal(1, "mod changed last commit lifecycle");

    $display("ROUTE_FLUSH_PASS");
    $finish;
  end
endmodule
"""

    with tempfile.TemporaryDirectory(prefix="eneuron_route_flush_") as temp_dir:
        temp = Path(temp_dir)
        tb_path = temp / "tb.sv"
        sim_path = temp / "tb.vvp"
        tb_path.write_text(testbench, encoding="utf-8")
        compile_result = subprocess.run(
            [
                str(iverilog),
                "-g2012",
                "-s",
                "tb",
                "-o",
                str(sim_path),
                str(ROOT / "digital_lif_engine.sv"),
                str(ROOT / "digital_snn_tile_4x2x2.sv"),
                str(tb_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if compile_result.returncode != 0:
            raise RuntimeError(
                f"route flush regression compile failed:\n{compile_result.stdout}\n{compile_result.stderr}"
            )

        env = os.environ.copy()
        env["PATH"] = f"{vvp.parent}{os.pathsep}{env.get('PATH', '')}"
        sim_result = subprocess.run(
            [str(vvp), str(sim_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if sim_result.returncode != 0:
            raise AssertionError(
                f"route flush regression failed:\n{sim_result.stdout}\n{sim_result.stderr}"
            )
        if "ROUTE_FLUSH_PASS" not in sim_result.stdout:
            raise AssertionError("route flush regression 未输出 PASS")

    LOGGER.info("tile ROUTE_FLUSH 与 commit 保留回归通过")


def main() -> None:
    parser = argparse.ArgumentParser(description="4->2->2 tile 事务级协同仿真")
    parser.add_argument("--seed", type=int, default=19)
    parser.add_argument("--transactions", type=int, default=128)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    run(args.seed, args.transactions)


if __name__ == "__main__":
    main()

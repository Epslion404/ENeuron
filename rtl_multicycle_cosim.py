"""digital_lif_engine.sv 的事务级 Icarus/Python 协同仿真。

测试只在事务完成时比较架构状态，不复制 RTL 的内部 FSM 周期。
busy 期间会注入额外请求，以验证当前事务不会被第二条命令污染。
"""

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


LOGGER = logging.getLogger("rtl_multicycle_cosim")
ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Transaction:
    """一个在 ready 周期提交的单核命令。"""

    kind: str
    mask: int = 0
    learn_enable: bool = True
    modulator: int = 0
    weight_addr: int = 0
    weight_wdata: int = 0
    busy_noise: str = ""


def find_tool(name: str) -> Path | None:
    """优先使用 PATH，再兼容本机 MSYS2 UCRT64 安装。"""
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


def make_transactions(seed: int, count: int, n_inputs: int) -> tuple[Transaction, ...]:
    """生成带定向前缀的随机事务，确保关键协议路径不会依赖随机命中。"""
    if count < 12:
        raise ValueError("count 必须至少为 12")
    full_mask = (1 << n_inputs) - 1
    last_addr = n_inputs - 1
    transactions = [
        Transaction("weight", weight_addr=0, weight_wdata=7),
        Transaction("weight", weight_addr=last_addr, weight_wdata=-3),
        Transaction("tick", mask=full_mask, busy_noise="clear"),
        Transaction("snapshot", busy_noise="weight"),
        Transaction("clear"),
        Transaction("mod", modulator=1, busy_noise="tick"),
        Transaction("tick", mask=full_mask),
        Transaction("snapshot", busy_noise="mod"),
        Transaction("mod", modulator=0),
        Transaction("weight", learn_enable=False, weight_addr=0, weight_wdata=-7),
        Transaction("mod", learn_enable=False, modulator=-1),
        Transaction("tick", mask=full_mask, learn_enable=False, busy_noise="snapshot"),
    ]

    rng = random.Random(seed)
    kinds = ("tick", "tick", "tick", "snapshot", "mod", "weight", "clear", "reset")
    noises = ("", "", "", "clear", "snapshot", "mod", "weight", "tick")
    while len(transactions) < count:
        kind = rng.choice(kinds)
        learn_enable = rng.random() < 0.75
        if kind == "tick":
            mask = sum(1 << index for index in range(n_inputs) if rng.random() < 0.35)
            transactions.append(
                Transaction(
                    kind,
                    mask=mask,
                    learn_enable=learn_enable,
                    busy_noise=rng.choice(noises),
                )
            )
        elif kind == "mod":
            modulator = rng.choice((-1, 0, 0, 1))
            noise = rng.choice(noises) if learn_enable and modulator else ""
            transactions.append(
                Transaction(
                    kind,
                    learn_enable=learn_enable,
                    modulator=modulator,
                    busy_noise=noise,
                )
            )
        elif kind == "weight":
            transactions.append(
                Transaction(
                    kind,
                    learn_enable=learn_enable,
                    weight_addr=rng.randrange(n_inputs),
                    weight_wdata=rng.randint(-12, 12),
                )
            )
        elif kind == "snapshot":
            transactions.append(Transaction(kind, busy_noise=rng.choice(noises)))
        else:
            transactions.append(Transaction(kind))
    return tuple(transactions)


def mod_bits(value: int) -> str:
    if value < 0:
        return "2'b11"
    if value > 0:
        return "2'b01"
    return "2'b00"


def command_assignments(transaction: Transaction, n_inputs: int) -> list[str]:
    """生成一个主事务的 testbench 端口赋值。"""
    assignments = [f"learn_enable=1'b{int(transaction.learn_enable)};"]
    if transaction.kind == "tick":
        assignments.extend(
            [
                "tick_valid=1'b1;",
                f"input_spikes={n_inputs}'b{transaction.mask:0{n_inputs}b};",
            ]
        )
    elif transaction.kind == "snapshot":
        assignments.append("snapshot_we=1'b1;")
    elif transaction.kind == "mod":
        assignments.extend(["mod_valid=1'b1;", f"modulator={mod_bits(transaction.modulator)};"])
    elif transaction.kind == "weight":
        assignments.extend(
            [
                "weight_we=1'b1;",
                f"weight_addr={transaction.weight_addr};",
                f"weight_wdata={transaction.weight_wdata};",
            ]
        )
    elif transaction.kind == "clear":
        assignments.append("state_clear=1'b1;")
    else:
        raise ValueError(f"未知事务类型: {transaction.kind}")
    return assignments


def noise_assignments(kind: str, n_inputs: int) -> list[str]:
    """busy 期间的请求只用于检查隔离，不应进入黄金模型。"""
    if kind == "clear":
        return ["state_clear=1'b1;"]
    if kind == "snapshot":
        return ["snapshot_we=1'b1;"]
    if kind == "mod":
        return ["learn_enable=1'b1;", "mod_valid=1'b1;", "modulator=2'b01;"]
    if kind == "weight":
        return ["learn_enable=1'b1;", "weight_we=1'b1;", "weight_addr='0;", "weight_wdata=-7;"]
    if kind == "tick":
        return ["learn_enable=1'b1;", "tick_valid=1'b1;", f"input_spikes={n_inputs}'b1;"]
    return []


def make_testbench(transactions: tuple[Transaction, ...], n_inputs: int) -> str:
    addr_bits = max(1, (n_inputs - 1).bit_length())
    lines = [
        "module tb;",
        f"  localparam integer N_INPUTS = {n_inputs};",
        f"  localparam integer ADDR_BITS = {addr_bits};",
        "  logic clk = 1'b0;",
        "  always #5 clk = ~clk;",
        "  logic rst, state_clear, tick_valid, learn_enable, snapshot_we, mod_valid, weight_we;",
        "  logic [N_INPUTS-1:0] input_spikes;",
        "  logic signed [1:0] modulator;",
        "  logic [ADDR_BITS-1:0] weight_addr;",
        "  logic signed [7:0] weight_wdata, weight_rdata;",
        "  logic ready, done, spike;",
        "  logic signed [15:0] membrane;",
        "  logic [7:0] threshold_state;",
        "  logic snapshot_valid_state;",
        "  logic signed [15:0] saved_current, saved_membrane;",
        "  logic [3:0] saved_refractory;",
        "  logic [7:0] saved_threshold, saved_post;",
        "  logic saved_snapshot_valid;",
        "  logic signed [7:0] saved_weights [0:N_INPUTS-1];",
        "  logic [7:0] saved_pre [0:N_INPUTS-1];",
        "  logic signed [11:0] saved_eligibility [0:N_INPUTS-1];",
        "  logic signed [11:0] saved_snapshot [0:N_INPUTS-1];",
        "  integer latency;",
        "  digital_lif_engine #(.N_INPUTS(N_INPUTS)) dut (.*);",
        "  task clear_commands;",
        "    begin",
        "      state_clear=1'b0; tick_valid=1'b0; input_spikes='0; learn_enable=1'b1;",
        "      snapshot_we=1'b0; mod_valid=1'b0; modulator=2'b00; weight_we=1'b0;",
        "      weight_addr='0; weight_wdata='0;",
        "    end",
        "  endtask",
        "  task capture_architecture;",
        "    integer index;",
        "    begin",
        "      saved_current=dut.current_reg; saved_membrane=dut.membrane_reg;",
        "      saved_refractory=dut.refractory; saved_threshold=dut.threshold_reg;",
        "      saved_post=dut.post_trace; saved_snapshot_valid=dut.snapshot_valid;",
        "      for (index=0; index<N_INPUTS; index=index+1) begin",
        "        saved_weights[index]=dut.weights[index]; saved_pre[index]=dut.pre_trace[index];",
        "        saved_eligibility[index]=dut.eligibility[index];",
        "        saved_snapshot[index]=dut.eligibility_snapshot[index];",
        "      end",
        "    end",
        "  endtask",
        "  task assert_architecture_stable;",
        "    integer index;",
        "    begin",
        "      if ((dut.current_reg !== saved_current) || (dut.membrane_reg !== saved_membrane) ||",
        "          (dut.refractory !== saved_refractory) || (dut.threshold_reg !== saved_threshold) ||",
        "          (dut.post_trace !== saved_post) || (dut.snapshot_valid !== saved_snapshot_valid))",
        "        $fatal(1, \"scalar architecture changed before done\");",
        "      for (index=0; index<N_INPUTS; index=index+1) begin",
        "        if ((dut.weights[index] !== saved_weights[index]) ||",
        "            (dut.pre_trace[index] !== saved_pre[index]) ||",
        "            (dut.eligibility[index] !== saved_eligibility[index]) ||",
        "            (dut.eligibility_snapshot[index] !== saved_snapshot[index]))",
        "          $fatal(1, \"array architecture changed before done at %0d\", index);",
        "      end",
        "    end",
        "  endtask",
        "  task show_state(input integer transaction_id);",
        "    begin",
        "      $write(\"STATE %0d %0d %0d %0d %0d %0d %0d\", transaction_id, $signed(dut.current_reg), $signed(dut.membrane_reg), spike, dut.refractory, dut.threshold_reg, dut.post_trace);",
    ]
    for index in range(n_inputs):
        lines.append(f"      $write(\" %0d\", $signed(dut.weights[{index}]));")
    for index in range(n_inputs):
        lines.append(f"      $write(\" %0d\", dut.pre_trace[{index}]);")
    for index in range(n_inputs):
        lines.append(f"      $write(\" %0d\", $signed(dut.eligibility[{index}]));")
    lines.append("      $write(\" %0d\", dut.snapshot_valid);")
    for index in range(n_inputs):
        lines.append(f"      $write(\" %0d\", $signed(dut.eligibility_snapshot[{index}]));")
    lines.extend(
        [
            "      $write(\" %0d %0d %0d\\n\", ready, done, latency);",
            "    end",
            "  endtask",
            "  always @(negedge clk) begin",
            "    if (!rst) begin",
            "      if (ready !== (dut.state == 0)) $fatal(1, \"ready/state contract failed\");",
            "      if (spike && !done) $fatal(1, \"spike escaped done cycle\");",
            "    end",
            "  end",
            "  initial begin",
            "    clear_commands(); rst=1'b1;",
            "    repeat (2) @(posedge clk);",
            "    #1 rst=1'b0;",
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

        lines.append("    @(negedge clk); clear_commands(); capture_architecture(); latency=0;")
        lines.extend(f"    {assignment}" for assignment in command_assignments(transaction, n_inputs))
        lines.extend(
            [
                "    @(posedge clk); #1;",
                "    if (!done) assert_architecture_stable();",
                "    clear_commands();",
            ]
        )

        supports_busy_noise = transaction.kind in {"tick", "snapshot"} or (
            transaction.kind == "mod" and transaction.learn_enable and transaction.modulator != 0
        )
        if transaction.busy_noise and supports_busy_noise:
            lines.append("    if (!done) begin")
            lines.append("      @(negedge clk); clear_commands();")
            lines.extend(f"      {assignment}" for assignment in noise_assignments(transaction.busy_noise, n_inputs))
            lines.extend(
                [
                    "      @(posedge clk); #1; clear_commands();",
                    "      latency=latency+1; if (!done) assert_architecture_stable();",
                    "    end",
                ]
            )
        lines.extend(
            [
                "    while (!done) begin",
                "      @(posedge clk); #1; latency=latency+1;",
                "      if (!done) assert_architecture_stable();",
                "      if (latency > (4*N_INPUTS+16)) $fatal(1, \"transaction timeout\");",
                "    end",
                f"    show_state({transaction_id});",
                "    @(posedge clk); #1; if (done) $fatal(1, \"done wider than one cycle\");",
            ]
        )

    lines.extend(["    $finish;", "  end", "endmodule"])
    return "\n".join(lines) + "\n"


def state_tuple(
    transaction_id: int,
    state: RtlState,
    done: int,
    latency: int,
) -> tuple[int, ...]:
    return (
        transaction_id,
        state.current,
        state.membrane,
        state.spike,
        state.refractory,
        state.threshold,
        state.post_trace,
        *state.weights,
        *state.pre_trace,
        *state.eligibility,
        state.snapshot_valid,
        *state.eligibility_snapshot,
        1,
        done,
        latency,
    )


def expected_states(
    transactions: tuple[Transaction, ...], n_inputs: int
) -> list[tuple[int, ...]]:
    neuron = RtlReferenceNeuron(n_inputs=n_inputs)
    states: list[tuple[int, ...]] = []
    for transaction_id, transaction in enumerate(transactions):
        if transaction.kind == "reset":
            neuron = RtlReferenceNeuron(n_inputs=n_inputs)
            state = neuron.tick((), tick=transaction_id, tick_valid=False)
            states.append(state_tuple(transaction_id, state, done=0, latency=0))
            continue

        active = tuple(index for index in range(n_inputs) if transaction.mask & (1 << index))
        state = neuron.tick(
            active,
            learn_enable=transaction.learn_enable,
            mod_valid=transaction.kind == "mod",
            modulator=transaction.modulator,
            tick=transaction_id,
            tick_valid=transaction.kind == "tick",
            state_clear=transaction.kind == "clear",
            snapshot_we=transaction.kind == "snapshot",
            weight_we=transaction.kind == "weight",
            weight_addr=transaction.weight_addr,
            weight_wdata=transaction.weight_wdata,
        )
        if transaction.kind == "tick":
            latency = 2 * n_inputs + 4
            if transaction.learn_enable and state.spike:
                latency += n_inputs
        elif transaction.kind == "snapshot":
            latency = n_inputs + 1
        elif transaction.kind == "mod" and transaction.learn_enable and transaction.modulator:
            latency = n_inputs + 1
        else:
            latency = 0
        states.append(state_tuple(transaction_id, state, done=1, latency=latency))
    return states


def parse_states(output: str) -> list[tuple[int, ...]]:
    states: list[tuple[int, ...]] = []
    for line in output.splitlines():
        if line.startswith("STATE "):
            states.append(tuple(int(value) for value in line.split()[1:]))
    return states


def run(seed: int, transaction_count: int, n_inputs: int = 4) -> None:
    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp；可通过 PATH 或 C:/msys64/ucrt64/bin 提供")

    transactions = make_transactions(seed, transaction_count, n_inputs)
    with tempfile.TemporaryDirectory(prefix="eneuron_multicycle_") as temp_dir:
        temp = Path(temp_dir)
        tb_path = temp / "tb.sv"
        sim_path = temp / "tb.vvp"
        tb_path.write_text(make_testbench(transactions, n_inputs), encoding="utf-8")
        compile_result = subprocess.run(
            [
                str(iverilog),
                "-g2012",
                "-s",
                "tb",
                "-o",
                str(sim_path),
                str(ROOT / "digital_lif_engine.sv"),
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
    expected = expected_states(transactions, n_inputs)
    if actual != expected:
        for index, (actual_state, expected_state) in enumerate(zip(actual, expected)):
            if actual_state != expected_state:
                transaction = transactions[index]
                raise AssertionError(
                    f"多周期 RTL 在事务 {index} 不一致: {transaction}\n"
                    f"actual={actual_state}\nexpected={expected_state}"
                )
        raise AssertionError(f"状态数量不一致: actual={len(actual)} expected={len(expected)}")

    LOGGER.info(
        "多周期 RTL cosim 通过: seed=%d transactions=%d n_inputs=%d",
        seed,
        transaction_count,
        n_inputs,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="多周期数字 LIF 引擎事务级协同仿真")
    parser.add_argument("--seed", type=int, default=19)
    parser.add_argument("--transactions", type=int, default=128)
    parser.add_argument("--n-inputs", type=int, default=4)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    run(args.seed, args.transactions, args.n_inputs)


if __name__ == "__main__":
    main()

"""用 Icarus Verilog 对 digital_lif_core.sv 做逐周期状态对照。"""

from __future__ import annotations

import argparse
import logging
import os
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from rtl_reference import RtlReferenceNeuron


LOGGER = logging.getLogger("rtl_cosim")
ROOT = Path(__file__).resolve().parent


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


def make_vectors(seed: int, ticks: int) -> tuple[tuple[int, tuple[int, ...], int], ...]:
    rng = random.Random(seed)
    vectors: list[tuple[int, tuple[int, ...], int]] = []
    for _ in range(ticks):
        mask = sum((1 << index) for index in range(4) if rng.random() < 0.3)
        active = tuple(index for index in range(4) if mask & (1 << index))
        modulator = rng.choice((-1, 0, 0, 0, 1))
        vectors.append((mask, active, modulator))
    return tuple(vectors)


def mod_bits(value: int) -> str:
    if value < 0:
        return "2'b11"
    if value > 0:
        return "2'b01"
    return "2'b00"


def make_testbench(vectors: tuple[tuple[int, tuple[int, ...], int], ...]) -> str:
    lines = [
        "module tb;",
        "  logic clk = 1'b0;",
        "  always #5 clk = ~clk;",
        "  logic rst, state_clear, tick_valid, learn_enable, mod_valid, snapshot_we, weight_we;",
        "  logic [3:0] input_spikes;",
        "  logic signed [1:0] modulator;",
        "  logic [1:0] weight_addr;",
        "  logic signed [7:0] weight_wdata;",
        "  logic signed [7:0] weight_rdata;",
        "  logic spike, ready;",
        "  logic signed [15:0] membrane;",
        "  logic [7:0] threshold_state;",
        "  digital_lif_core dut (.*);",
        "  task show_state(input integer tick);",
        "    begin",
        "      $write(\"STATE %0d %0d %0d %0d %0d %0d %0d\", tick, $signed(dut.current_reg), $signed(dut.membrane_reg), spike, dut.refractory, dut.threshold_reg, dut.post_trace);",
        "      $write(\" %0d %0d %0d %0d\", $signed(dut.weights[0]), $signed(dut.weights[1]), $signed(dut.weights[2]), $signed(dut.weights[3]));",
        "      $write(\" %0d %0d %0d %0d\", dut.pre_trace[0], dut.pre_trace[1], dut.pre_trace[2], dut.pre_trace[3]);",
        "      $write(\" %0d %0d %0d %0d\", $signed(dut.eligibility[0]), $signed(dut.eligibility[1]), $signed(dut.eligibility[2]), $signed(dut.eligibility[3]));",
        "      $write(\" %0d %0d %0d %0d %0d\\n\", dut.snapshot_valid, $signed(dut.eligibility_snapshot[0]), $signed(dut.eligibility_snapshot[1]), $signed(dut.eligibility_snapshot[2]), $signed(dut.eligibility_snapshot[3]));",
        "    end",
        "  endtask",
        "  initial begin",
        "    rst=1'b1; state_clear=1'b0; tick_valid=1'b0; input_spikes='0; learn_enable=1'b1; mod_valid=1'b0; modulator=2'b00; snapshot_we=1'b0; weight_we=1'b0; weight_addr='0; weight_wdata='0;",
        "    repeat (2) @(posedge clk);",
        "    #1 rst=1'b0;",
    ]
    for tick, (mask, _active, modulator_value) in enumerate(vectors):
        lines.extend(
            [
                f"    input_spikes=4'b{mask:04b}; state_clear=1'b0; tick_valid=1'b1; learn_enable=1'b1; mod_valid={'1\'b1' if modulator_value else '1\'b0'}; modulator={mod_bits(modulator_value)}; snapshot_we=1'b0; weight_we=1'b0;",
                f"    @(posedge clk); #1 show_state({tick});",
            ]
        )
    lines.extend(
        [
            "    state_clear=1'b0; tick_valid=1'b0; input_spikes='0; learn_enable=1'b1; mod_valid=1'b1; modulator=2'b01; snapshot_we=1'b0; weight_we=1'b0;",
            f"    @(posedge clk); #1 show_state({len(vectors)});",
            "    state_clear=1'b0; tick_valid=1'b0; input_spikes='0; learn_enable=1'b1; mod_valid=1'b0; modulator=2'b00; snapshot_we=1'b0; weight_we=1'b1; weight_addr=2'b10; weight_wdata=8'b11111001;",
            f"    @(posedge clk); #1 show_state({len(vectors) + 1});",
            "    state_clear=1'b0; tick_valid=1'b1; input_spikes=4'b0011; learn_enable=1'b0; mod_valid=1'b1; modulator=2'b01; snapshot_we=1'b0; weight_we=1'b1; weight_addr=2'b01; weight_wdata=8'b00000111;",
            f"    @(posedge clk); #1 show_state({len(vectors) + 2});",
            "    state_clear=1'b0; tick_valid=1'b0; input_spikes='0; learn_enable=1'b1; mod_valid=1'b0; modulator=2'b00; snapshot_we=1'b1; weight_we=1'b0;",
            f"    @(posedge clk); #1 show_state({len(vectors) + 3});",
            "    state_clear=1'b1; tick_valid=1'b0; input_spikes='0; learn_enable=1'b1; mod_valid=1'b0; snapshot_we=1'b0; weight_we=1'b0;",
            f"    @(posedge clk); #1 show_state({len(vectors) + 4});",
            "    state_clear=1'b0; tick_valid=1'b0; input_spikes='0; learn_enable=1'b1; mod_valid=1'b1; modulator=2'b01; snapshot_we=1'b0; weight_we=1'b0;",
            f"    @(posedge clk); #1 show_state({len(vectors) + 5});",
            "    $finish;",
            "  end",
            "endmodule",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_states(output: str) -> list[tuple[int, ...]]:
    states: list[tuple[int, ...]] = []
    for line in output.splitlines():
        if not line.startswith("STATE "):
            continue
        fields = line.split()
        if len(fields) != 25:
            raise AssertionError(f"unexpected state field count: {line}")
        states.append(tuple(int(value) for value in fields[1:]))
    return states


def expected_states(vectors: tuple[tuple[int, tuple[int, ...], int], ...]) -> list[tuple[int, ...]]:
    neuron = RtlReferenceNeuron()
    states: list[tuple[int, ...]] = []
    for tick, (_mask, active, modulator_value) in enumerate(vectors):
        state = neuron.tick(
            active,
            learn_enable=True,
            mod_valid=modulator_value != 0,
            modulator=modulator_value,
            tick=tick,
        )
        states.append(
            (
                state.tick,
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
            )
        )
    # mod-only 周期只提交当前 eligibility，不推进神经动力学。
    state = neuron.tick(
        (),
        learn_enable=True,
        mod_valid=True,
        modulator=1,
        tick=len(vectors),
        tick_valid=False,
    )
    states.append(
        (
            state.tick,
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
        )
    )
    state = neuron.tick(
        (),
        learn_enable=True,
        tick=len(vectors) + 1,
        tick_valid=False,
        weight_we=True,
        weight_addr=2,
        weight_wdata=-7,
    )
    states.append(
        (
            state.tick,
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
        )
    )
    # learn_enable=0 must hold all learning state and ignore simultaneous writes.
    state = neuron.tick(
        (0, 1),
        learn_enable=False,
        mod_valid=True,
        modulator=1,
        tick=len(vectors) + 2,
        tick_valid=True,
        weight_we=True,
        weight_addr=1,
        weight_wdata=7,
    )
    states.append(
        (
            state.tick,
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
        )
    )
    state = neuron.tick(
        (),
        learn_enable=True,
        tick=len(vectors) + 3,
        tick_valid=False,
        snapshot_we=True,
    )
    states.append(
        (
            state.tick,
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
        )
    )
    state = neuron.tick(
        (),
        learn_enable=True,
        tick=len(vectors) + 4,
        tick_valid=False,
        state_clear=True,
    )
    states.append(
        (
            state.tick,
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
        )
    )
    state = neuron.tick(
        (),
        learn_enable=True,
        mod_valid=True,
        modulator=1,
        tick=len(vectors) + 5,
        tick_valid=False,
    )
    states.append(
        (
            state.tick,
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
        )
    )
    return states


def run(seed: int, ticks: int) -> None:
    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp；可通过 PATH 或 C:/msys64/ucrt64/bin 提供")

    vectors = make_vectors(seed, ticks)
    with tempfile.TemporaryDirectory(prefix="eneuron_rtl_") as temp_dir:
        temp = Path(temp_dir)
        tb_path = temp / "tb.sv"
        sim_path = temp / "tb.vvp"
        tb_path.write_text(make_testbench(vectors), encoding="utf-8")
        compile_result = subprocess.run(
            [str(iverilog), "-g2012", "-s", "tb", "-o", str(sim_path), str(ROOT / "digital_lif_core.sv"), str(tb_path)],
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
    expected = expected_states(vectors)
    if actual != expected:
        for index, (actual_state, expected_state) in enumerate(zip(actual, expected)):
            if actual_state != expected_state:
                raise AssertionError(
                    f"RTL mismatch at state index {index}:\n"
                    f"actual={actual_state}\nexpected={expected_state}"
                )
        raise AssertionError(f"RTL state count mismatch: actual={len(actual)} expected={len(expected)}")
    LOGGER.info("RTL cosim passed: seed=%d ticks=%d states=%d", seed, ticks, len(actual))
    print(f"RTL cosim passed: seed={seed} ticks={ticks} states={len(actual)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Icarus 与 Python 黄金模型逐周期对照")
    parser.add_argument("--seed", type=int, default=19)
    parser.add_argument("--ticks", type=int, default=128)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    run(args.seed, args.ticks)


if __name__ == "__main__":
    main()

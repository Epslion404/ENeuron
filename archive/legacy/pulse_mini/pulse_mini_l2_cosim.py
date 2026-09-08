"""Pulse-Mini-L2 Python/Icarus 逐事务协同仿真。"""

from __future__ import annotations

import random
import re
import subprocess
import tempfile
from pathlib import Path

from pulse_mini_l2_reference import PulseMiniL2Reference
from pulse_mini_reference import Command, Mode, Opcode
from rtl_tile_cosim import find_tool

ROOT = Path(__file__).resolve().parent
ROW_RE = re.compile(
    r"^R\s+(\d+)\s+(-?\d+)\s+(-?\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+"
    r"(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(\d+)\s+(\d+)\s+"
    r"(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(\d+)"
)


def make_commands(seed: int, count: int) -> list[tuple[int, int, int]]:
    rng = random.Random(seed)
    commands: list[tuple[int, int, int]] = [(0, 1, 0), (1, 0, 0)]
    for index in range(count - 2):
        phase = index % 19
        if phase == 0:
            commands.append((0, 1, 0))
        elif phase == 1:
            commands.append((1, 0, 0))
        elif phase in (2, 3, 4, 5, 6, 7, 8):
            commands.append((2, rng.randrange(16), rng.randrange(2)))
        elif phase == 9:
            commands.append((3, 0, 0))
        elif phase == 10:
            commands.append((4, rng.choice((0, 1, 3)), 0))
        elif phase == 11:
            commands.append((5, rng.randrange(4), rng.choice(tuple(range(16)))))
        elif phase == 12:
            commands.append((6, rng.randrange(4), 0))
        elif phase == 13:
            commands.append((4, 2, 0))
        elif phase == 14:
            commands.append((5, 4, 0))
        elif phase == 15:
            commands.append((6, 0, 1))
        elif phase == 16:
            commands.append((7, 0, 0))
        elif phase == 17:
            commands.append((2, rng.randrange(16), 0))
        else:
            commands.append((1, 0, 0))
    return commands


def pack_captured(values: list[int]) -> int:
    return sum((value & 0x7) << (3 * index) for index, value in enumerate(values))


def expected_rows(commands: list[tuple[int, int, int]]) -> list[tuple[int, ...]]:
    model = PulseMiniL2Reference()
    rows: list[tuple[int, ...]] = []
    for op, a0, a1 in commands:
        response = model.execute(Command(op, a0, a1))
        state = model.state
        rows.append((
            response.status.value,
            response.data,
            response.spike,
            int(state.mode),
            int(state.pending_valid),
            int(response.status.value != "ok"),
            *state.weights,
            state.soma,
            state.refractory,
            state.leak_timer,
            sum(age << (4 * index) for index, age in enumerate(state.pre_age)),
            state.post_age,
            sum(value << (2 * index) for index, value in enumerate(state.positive_evidence)),
            sum(value << (2 * index) for index, value in enumerate(state.negative_evidence)),
            pack_captured(list(state.captured_direction)),
        ))
    return rows


def run(seed: int, count: int = 1000) -> None:
    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")
    commands = make_commands(seed, count)
    expected = expected_rows(commands)
    with tempfile.TemporaryDirectory(prefix="pulse_mini_l2_cosim_") as temp:
        temp_path = Path(temp)
        command_path = temp_path / "commands.txt"
        sim_path = temp_path / "pulse_mini_l2.vvp"
        command_path.write_text(
            "".join(f"{op} {a0} {a1}\n" for op, a0, a1 in commands), encoding="ascii"
        )
        compile_result = subprocess.run(
            [str(iverilog), "-g2012", "-Wall", "-s", "tb_pulse_mini_l2_cosim", "-o", str(sim_path),
             str(ROOT / "pulse_mini_l2_core.sv"), str(ROOT / "tb_pulse_mini_l2_cosim.sv")],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        if compile_result.returncode:
            raise RuntimeError(compile_result.stdout + compile_result.stderr)
        result = subprocess.run(
            [str(vvp), str(sim_path), f"+CMDFILE={command_path}"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        actual: list[tuple[int, ...]] = []
        status_codes = {"ok": 0, "bad_opcode": 1, "bad_arg": 2, "bad_mode": 3,
                        "busy_pending": 4, "no_pending": 5}
        for line in result.stdout.splitlines():
            match = ROW_RE.match(line)
            if not match:
                continue
            values = [int(value) for value in match.groups()]
            status = values[1]
            actual.append((
                next(name for name, code in status_codes.items() if code == status),
                values[2], values[3], values[4], values[5], values[6],
                *values[7:18], values[18] & 0xFFF,
            ))
        if len(actual) != len(expected):
            raise AssertionError(f"响应数量不符 actual={len(actual)} expected={len(expected)}\n{result.stdout[-2000:]}")
        for index, (got, want) in enumerate(zip(actual, expected)):
            if got != want:
                raise AssertionError(f"seed={seed} transaction={index} got={got} want={want}")


def main() -> None:
    for seed in range(20):
        run(seed, 1000)
    print("PULSE_MINI_L2_COSIM_PASS seeds=20 transactions=20000")


if __name__ == "__main__":
    main()

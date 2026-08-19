"""固定 4->2->2 Pulse-Mini 网络 RTL 训练/推理回归。"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from rtl_tile_cosim import find_tool

ROOT = Path(__file__).resolve().parent
ROW_RE = re.compile(r"^R\s+(\d+)\s+(-?\d+)\s+(-?\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$")


def commands() -> list[tuple[int, int, int]]:
    result: list[tuple[int, int, int]] = []
    result.append((0, 1, 0))
    for neuron, feature, post_bit in ((0, 1, 0), (1, 2, 1)):
        for _ in range(6):
            result += [(1, 0, 0), (2, feature, 0), (2, 0, 1 << post_bit)]
            result += [(2, 0, 0)] * 5
            result += [(3, neuron << 6, 0), (4, neuron << 6, 1)]
    for neuron, feature, post_bit in ((2, 1, 2), (3, 2, 3)):
        for _ in range(6):
            result.append((1, 0, 0))
            for tick in range(8):
                result.append((2, feature if tick < 6 else 0, 1 << post_bit if tick == 6 else 0))
            result += [(3, neuron << 6, 0), (4, neuron << 6, 1)]
    # 推理保持与 Python 黄金模型一致：连续输入 8 tick，输出层权重为 +3，
    # 因而需要累计多次隐藏脉冲后才产生输出脉冲。
    result += [(0, 2, 0), (1, 0, 0)]
    result += [(2, 1, 0)] * 8
    result += [(1, 0, 0)]
    result += [(2, 2, 0)] * 8
    return result


def run() -> None:
    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")
    tx = commands()
    with tempfile.TemporaryDirectory(prefix="pulse_mini_network_") as temp:
        temp_path = Path(temp)
        cmdfile = temp_path / "commands.txt"
        sim = temp_path / "network.vvp"
        cmdfile.write_text("".join(f"{op} {a0} {a1}\n" for op, a0, a1 in tx), encoding="ascii")
        compile_result = subprocess.run(
            [str(iverilog), "-g2012", "-Wall", "-s", "tb_pulse_mini_network_file", "-o", str(sim),
             str(ROOT / "pulse_mini_core.sv"), str(ROOT / "pulse_mini_network_4x2x2.sv"),
             str(ROOT / "tb_pulse_mini_network_file.sv")],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        if compile_result.returncode:
            raise RuntimeError(compile_result.stdout + compile_result.stderr)
        result = subprocess.run([str(vvp), str(sim), f"+CMDFILE={cmdfile}"],
                                cwd=ROOT, capture_output=True, text=True, check=False)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        rows = [tuple(int(value) for value in match.groups())
                for line in result.stdout.splitlines() if (match := ROW_RE.match(line))]
        if len(rows) != len(tx):
            raise AssertionError(f"network response count {len(rows)} != {len(tx)}")
        if any(row[1] != 0 for row in rows):
            raise AssertionError("network training produced a protocol error")
        infer_start = max(index for index, (opcode, arg0, _arg1) in enumerate(tx)
                          if opcode == 0 and arg0 == 2)
        positive = rows[infer_start + 2:infer_start + 10]
        negative_clear = infer_start + 10
        negative = rows[negative_clear + 1:negative_clear + 9]
        if len(positive) != 8 or len(negative) != 8:
            raise AssertionError("inference response section has an unexpected length")
        if positive[0][3] != 1 or positive[0][4] != 0 or positive[0][5] != 1:
            raise AssertionError(f"positive hidden route mismatch: {positive[0]}")
        if not any(row[4] & 1 for row in positive):
            raise AssertionError(f"positive class produced no output spike: {positive}")
        if not any(row[4] & 2 for row in negative):
            raise AssertionError(f"negative class produced no output spike: {negative}")
        if any(row[4] & 2 for row in positive) or any(row[4] & 1 for row in negative):
            raise AssertionError("inference output classes are not separated")
        print(f"PULSE_MINI_NETWORK_RTL_COSIM_PASS commands={len(tx)} one_tick_route=1 positive=1 negative=2")


if __name__ == "__main__":
    run()

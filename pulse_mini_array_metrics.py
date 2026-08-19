"""测量广播阵列的逻辑 tick 延迟、输出拥塞和反馈带宽。"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from rtl_tile_cosim import find_tool


ROOT = Path(__file__).resolve().parent
METRIC_RE = re.compile(r"^METRIC N=(\d+) TICK_LATENCY=(\d+) SPIKES=(\d+)$")
TOTAL_RE = re.compile(r"^METRIC N=(\d+) TICK_TOTAL=(\d+) FEEDBACK_LATENCY=(\d+)$")
BURST_RE = re.compile(r"^METRIC N=(\d+) BURST_CYCLES=(\d+) BURST_ACCEPTS=(\d+)$")


def measure(n_cores: int) -> dict[str, int]:
    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")
    with tempfile.TemporaryDirectory(prefix=f"pulse_mini_array_metrics_{n_cores}_") as temp:
        sim = Path(temp) / "metrics.vvp"
        compile_result = subprocess.run(
            [str(iverilog), "-g2012", "-Wall", "-s", "tb_pulse_mini_array_metrics",
             "-P", f"tb_pulse_mini_array_metrics.N_CORES={n_cores}", "-o", str(sim),
             str(ROOT / "pulse_mini_core.sv"), str(ROOT / "pulse_mini_array.sv"),
             str(ROOT / "tb_pulse_mini_array_metrics.sv")],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        if compile_result.returncode:
            raise RuntimeError(compile_result.stdout + compile_result.stderr)
        result = subprocess.run([str(vvp), str(sim)], cwd=ROOT,
                                capture_output=True, text=True, check=False)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        metric = next((METRIC_RE.match(line) for line in result.stdout.splitlines()
                       if METRIC_RE.match(line)), None)
        total = next((TOTAL_RE.match(line) for line in result.stdout.splitlines()
                      if TOTAL_RE.match(line)), None)
        burst = next((BURST_RE.match(line) for line in result.stdout.splitlines()
                      if BURST_RE.match(line)), None)
        if metric is None or total is None or burst is None:
            raise AssertionError(result.stdout)
        return {
            "N_CORES": int(metric.group(1)),
            "TICK_LATENCY": int(metric.group(2)),
            "SPIKES": int(metric.group(3)),
            "TICK_TOTAL": int(total.group(2)),
            "FEEDBACK_LATENCY": int(total.group(3)),
            "BURST_CYCLES": int(burst.group(2)),
            "BURST_ACCEPTS": int(burst.group(3)),
        }


def main() -> None:
    rows = [measure(n) for n in (32, 64, 128)]
    for row in rows:
        if row["SPIKES"] != row["N_CORES"]:
            raise AssertionError(f"broadcast output count mismatch: {row}")
        if row["TICK_LATENCY"] != 1 or row["FEEDBACK_LATENCY"] != 1:
            raise AssertionError(f"unexpected protocol latency: {row}")
        if row["BURST_ACCEPTS"] != row["BURST_CYCLES"] // 2:
            raise AssertionError(f"unexpected sustained command throughput: {row}")
        print("PULSE_MINI_ARRAY_METRIC", " ".join(f"{key}={value}" for key, value in row.items()))
    print("PULSE_MINI_ARRAY_METRICS_PASS tick_latency=1 protocol_gap=2 sustained_rate=0.5 broadcast_spikes=all")


if __name__ == "__main__":
    main()

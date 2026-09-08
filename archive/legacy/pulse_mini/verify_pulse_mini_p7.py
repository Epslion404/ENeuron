"""P7 阵列资源、协议吞吐和共享 lane 架构对比签核。"""

from __future__ import annotations

import json
from pathlib import Path

from pulse_mini_array_metrics import measure
from pulse_mini_lane_model import compare


ROOT = Path(__file__).resolve().parent


def parse_summary(path: Path) -> dict[str, str]:
    return {
        key: value
        for key, value in (line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line)
    }


def main() -> None:
    resources: list[dict[str, object]] = []
    metrics: list[dict[str, int]] = []
    for n_cores in (32, 64, 128):
        summary = parse_summary(ROOT / "vivado_pulse_mini_array_reports" / f"n{n_cores}" / "summary.txt")
        row = {
            "N_CORES": int(summary["N_CORES"]),
            "LUT": int(summary["LUT"]),
            "FF": int(summary["FF"]),
            "BRAM": int(summary["BRAM"]),
            "DSP": int(summary["DSP"]),
            "WNS_NS": float(summary["WNS_NS"]),
            "TNS_NS": float(summary["TNS_NS"]),
            "CLOCK_MHZ": float(summary["CLOCK_MHZ"]),
        }
        resources.append(row)
        metrics.append(measure(n_cores))

    lane_points = [compare(128, lanes).__dict__ for lanes in (1, 2, 4, 8, 128)]
    timing_pass = all(row["WNS_NS"] >= 0 and row["TNS_NS"] == 0 for row in resources)
    largest_parallel_pass = max(
        row["N_CORES"] for row in resources if row["WNS_NS"] >= 0 and row["TNS_NS"] == 0
    )
    for row in metrics:
        assert row["SPIKES"] == row["N_CORES"]
        assert row["TICK_LATENCY"] == 1
        assert row["FEEDBACK_LATENCY"] == 1
        assert row["BURST_ACCEPTS"] * 2 == row["BURST_CYCLES"]
    result = {
        "schema": "pulse_mini_p7_signoff_v1",
        "resource_rows": resources,
        "protocol_metrics": metrics,
        "lane_model": lane_points,
        "timing_all_pass": timing_pass,
        "largest_parallel_100mhz_proven": largest_parallel_pass,
        "capacity_claim": "NOT_PROVEN" if not timing_pass else "PROVEN",
        "parallel_architecture_note": "32 parallel cores pass; 64/128 fail the 100 MHz setup gate in simple broadcast architecture.",
        "shared_lane_note": "Lane rows are cycle-model results, not routed physical capacity claims.",
    }
    output = ROOT / "pulse_mini_p7_signoff_summary.json"
    output.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="ascii")
    print(
        "PULSE_MINI_P7_SIGNOFF_PASS "
        f"largest_parallel_100mhz_proven={largest_parallel_pass} "
        f"capacity_claim={result['capacity_claim']}"
    )


if __name__ == "__main__":
    main()

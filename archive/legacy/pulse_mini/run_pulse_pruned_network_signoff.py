"""运行 NP4B4 Pulse-L/L2 正式网络矩阵并保存独立机器摘要。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pulse_mini_pruned_network_random_cosim import run_matrix


ROOT = Path(__file__).resolve().parent


def _run(*, l2: bool, seeds: tuple[int, ...], output_name: str) -> dict[str, int | str | list[int]]:
    summary = run_matrix(seeds=seeds, transaction_count=1000, l2=l2)
    summary.update({
        "date": "2026-08-29",
        "seed_values": list(seeds),
        "evidence_scope": "logical_functional_cosim_only",
        "physical_speedup_proven": 0,
        "bram_skip_proven": 0,
        "power_reduction_proven": 0,
    })
    output = ROOT / output_name
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{summary['status']} {json.dumps(summary, sort_keys=True)}")
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _run(
        l2=False,
        seeds=tuple(range(201, 221)),
        output_name="pulse_mini_l_np4b4_summary.json",
    )
    _run(
        l2=True,
        seeds=tuple(range(301, 321)),
        output_name="pulse_mini_l2_np4b4_summary.json",
    )


if __name__ == "__main__":
    main()

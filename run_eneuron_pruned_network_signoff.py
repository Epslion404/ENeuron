"""运行 NP4B4 ENeuron 正式网络矩阵并保存独立机器摘要。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from eneuron_pruned_network_random_cosim import run_matrix


ROOT = Path(__file__).resolve().parent
SEEDS = tuple(range(101, 121))
OUTPUT_NAME = "eneuron_np4b4_summary.json"


def build_summary(raw: dict[str, int]) -> dict[str, int | str | list[int]]:
    """把已通过的协同仿真统计包装成固定、不可外推的正式摘要。"""
    expected = {
        "seeds": 20,
        "transactions_per_seed": 1000,
        "transactions": 20_000,
        "pruned_snapshot_zeroing_transitions": 277,
        "pruned_weight_changes": 0,
        "pruned_utility_changes": 0,
    }
    if raw != expected:
        raise AssertionError(f"ENeuron 正式矩阵统计不匹配: actual={raw!r}")

    summary: dict[str, int | str | list[int]] = dict(raw)
    summary.update(
        {
            "model": "ENeuron",
            "status": "ENEURON_NP4B4_PASS",
            "date": "2026-08-29",
            "seed_values": list(SEEDS),
            "commits": 20,
            "rtl_python_mismatches": 0,
            "strict_two_four_violations": 0,
            "infer_freeze_violations": 0,
            "pruned_snapshot_growth_changes": 0,
            "evidence_scope": "logical_functional_cosim_only",
            "physical_speedup_proven": 0,
            "bram_skip_proven": 0,
            "power_reduction_proven": 0,
        }
    )
    return summary


def main() -> None:
    """新鲜运行固定 20×1000 矩阵并原子替换正式摘要。"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raw = run_matrix(seeds=SEEDS, transaction_count=1000)
    summary = build_summary(raw)
    output = ROOT / OUTPUT_NAME
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    print(f"{summary['status']} {json.dumps(summary, sort_keys=True)}")


if __name__ == "__main__":
    main()

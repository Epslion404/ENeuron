"""Fail-closed 校验 NP4B4 ENeuron 独立机器摘要。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SUMMARY_NAME = "eneuron_np4b4_summary.json"
EXPECTED_SEEDS = list(range(101, 121))


def verify_summary(data: dict[str, Any]) -> None:
    """严格检查固定 seed、精确统计、冻结性质和声明边界。"""
    required = {
        "model": "ENeuron",
        "status": "ENEURON_NP4B4_PASS",
        "date": "2026-08-29",
        "seed_values": EXPECTED_SEEDS,
        "seeds": 20,
        "transactions_per_seed": 1000,
        "transactions": 20_000,
        "commits": 20,
        "pruned_snapshot_zeroing_transitions": 277,
        "pruned_snapshot_growth_changes": 0,
        "pruned_weight_changes": 0,
        "pruned_utility_changes": 0,
        "rtl_python_mismatches": 0,
        "strict_two_four_violations": 0,
        "infer_freeze_violations": 0,
        "evidence_scope": "logical_functional_cosim_only",
        "physical_speedup_proven": 0,
        "bram_skip_proven": 0,
        "power_reduction_proven": 0,
    }
    if set(data) != set(required):
        missing = sorted(set(required) - set(data))
        extra = sorted(set(data) - set(required))
        raise AssertionError(f"{SUMMARY_NAME}: keys missing={missing} extra={extra}")
    for key, value in required.items():
        if data[key] != value:
            raise AssertionError(
                f"{SUMMARY_NAME}: {key}={data[key]!r}, expected={value!r}"
            )


def main() -> None:
    """读取正式文件并输出唯一通过标记。"""
    path = ROOT / SUMMARY_NAME
    if not path.is_file() or path.stat().st_size == 0:
        raise AssertionError(f"缺少非空正式摘要: {SUMMARY_NAME}")
    verify_summary(json.loads(path.read_text(encoding="utf-8")))
    print("ENEURON_NP4B4_SUMMARY_VERIFY_PASS transactions=20000 seeds=101..120")


if __name__ == "__main__":
    main()

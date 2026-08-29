"""校验 NP4B4 Pulse-L/L2 机器摘要的独立模型边界和硬门。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _verify(name: str, expected_model: str, expected_status: str) -> None:
    data = json.loads((ROOT / name).read_text(encoding="utf-8"))
    required = {
        "model": expected_model,
        "status": expected_status,
        "seeds": 20,
        "transactions_per_seed": 1000,
        "transactions": 20_000,
        "commits": 20,
        "pruned_weight_changes": 0,
        "pruned_evidence_changes": 0,
        "pruned_utility_changes": 0,
        "evidence_scope": "logical_functional_cosim_only",
        "physical_speedup_proven": 0,
        "bram_skip_proven": 0,
        "power_reduction_proven": 0,
    }
    for key, value in required.items():
        if data.get(key) != value:
            raise AssertionError(f"{name}: {key}={data.get(key)!r}, expected={value!r}")
    if len(data.get("seed_values", [])) != 20 or len(set(data["seed_values"])) != 20:
        raise AssertionError(f"{name}: seed_values 必须包含 20 个独立 seed")
    if data.get("exact_two_checks", 0) <= 0 or data.get("pruned_lane_checks", 0) <= 0:
        raise AssertionError(f"{name}: 缺少严格 2:4 或被剪 lane 检查")
    if data.get("issue_mask_acceptance_checks", 0) <= 0:
        raise AssertionError(f"{name}: 缺少接受沿 issue_mask 检查")


def main() -> None:
    _verify(
        "pulse_mini_l_np4b4_summary.json",
        "Pulse-Mini-L",
        "PULSE_L_NP4B4_PASS",
    )
    _verify(
        "pulse_mini_l2_np4b4_summary.json",
        "Pulse-Mini-L2",
        "PULSE_L2_NP4B4_PASS",
    )
    print("PULSE_NP4B4_SUMMARY_VERIFY_PASS models=2 transactions=40000")


if __name__ == "__main__":
    main()

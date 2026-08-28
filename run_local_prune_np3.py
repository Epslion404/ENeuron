"""生成三模型 NP3 剪枝闭环的机器可读结果。"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
from pathlib import Path

from local_prune_np3 import run_np3_experiment


LOGGER = logging.getLogger("run_local_prune_np3")
ROOT = Path(__file__).resolve().parent
SOURCE_FILES = (
    "local_prune_reference.py",
    "local_prune_b1.py",
    "local_prune_b2.py",
    "local_prune_np3.py",
    "run_local_prune_np3.py",
    "neuron_sim.py",
    "pulse_mini_reference.py",
    "pulse_mini_l2_reference.py",
)


def _sha256(path: Path) -> str:
    """返回源码原始字节的 SHA-256。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_revision() -> str:
    """读取 HEAD，不修改全局 Git 安全配置。"""
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _decide_model(model: dict[str, object]) -> dict[str, object]:
    """检查闭环、负对照和结构账本，并按 KISS 选择一次剪枝。"""
    branches = model["branches"]
    one_shot = branches["S2_one_shot"]
    progressive = branches["S2_progressive"]
    wrong_sign = branches["S2_wrong_sign"]
    audit_fields = (
        "mask_stable_during_fine_tune",
        "pruned_weights_unchanged",
        "pruned_history_zero",
        "infer_freeze_pass",
    )
    audit_pass = all(
        branch["mask_write_count"] == 0
        and branch["prune_commit_counts"] == [1] * 8
        and all(branch[field] for field in audit_fields)
        for branch in branches.values()
    )
    parent_pass = len({branch["parent_checkpoint_sha256"] for branch in branches.values()}) == 1
    budget_pass = all(
        branch["fine_tune_observations_per_detector"] == 2
        for branch in branches.values()
    )
    task_pass = all(
        branch["after_fine_tune"]["balanced_accuracy"] >= 0.98
        and branch["after_fine_tune"]["coverage"] >= 0.98
        for branch in (one_shot, progressive)
    )
    negative_pass = (
        wrong_sign["after_fine_tune"]["balanced_accuracy"] <= 0.5
        and wrong_sign["after_fine_tune"]["coverage"] <= 0.5
    )
    flow_match = one_shot["final_masks"] == progressive["final_masks"]
    np3_pass = audit_pass and parent_pass and budget_pass and task_pass and negative_pass and flow_match
    return {
        "np3_pass": np3_pass,
        "shared_parent_pass": parent_pass,
        "equal_budget_pass": budget_pass,
        "task_gate_pass": task_pass,
        "wrong_sign_negative_control_pass": negative_pass,
        "ledger_and_freeze_pass": audit_pass,
        "one_shot_matches_progressive": flow_match,
        "recommended_flow": "S2_one_shot" if np3_pass else None,
        "rtl_go": False,
        "reason": (
            "NP3 passes; B2.1 system work gate remains pending"
            if np3_pass
            else "NP3 closure failed"
        ),
    }


def build_results() -> dict[str, object]:
    """运行确定性 NP3 并补齐逐模型决定与来源绑定。"""
    result = run_np3_experiment()
    decisions = {
        model_id: _decide_model(model)
        for model_id, model in result["models"].items()
    }
    return {
        **result,
        "generated_date": "2026-08-28",
        "git_commit": _git_revision(),
        "source_sha256": {name: _sha256(ROOT / name) for name in SOURCE_FILES},
        "decisions": decisions,
    }


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "local_prune_np3_results.json")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = build_results()
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("NP3 三模型闭环结果已写入 %s", args.output)


if __name__ == "__main__":
    main()

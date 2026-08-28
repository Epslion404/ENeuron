"""运行三种神经元的 10-seed B2 冗余 detector 剪枝实验。"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Sequence

from local_prune_b2 import run_b2_matrix


LOGGER = logging.getLogger("run_local_prune_b2")
ROOT = Path(__file__).resolve().parent
SOURCE_FILES = (
    "local_prune_reference.py",
    "local_prune_b2.py",
    "run_local_prune_b2.py",
    "neuron_sim.py",
    "pulse_mini_reference.py",
    "pulse_mini_l2_reference.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_revision() -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def decide_model(
    summary: dict[str, Any],
    *,
    full_network_reduction: float,
) -> dict[str, object]:
    """按预注册精度门和系统工作量门生成逐模型决定。"""
    dense = summary["dense"]["median_balanced_accuracy"]
    s2 = summary["S2"]["median_balanced_accuracy"]
    gates = summary["gates"]
    algorithm_gate = (
        dense - s2 <= 0.02
        and gates["s2_minus_random_median_pp"] >= 5.0
        and gates["s2_not_below_random_seeds"] >= 8
    )
    system_gate = full_network_reduction >= 0.45
    s3_extra = 100 * (
        summary["S3"]["median_balanced_accuracy"]
        - summary["S2"]["median_balanced_accuracy"]
    )
    return {
        "algorithm_gate_pass": algorithm_gate,
        "system_work_gate_pass": system_gate,
        "rtl_go": algorithm_gate and system_gate,
        "recommended_score": "S2" if algorithm_gate else None,
        "s3_minus_s2_median_pp": s3_extra,
        "reason": (
            "S2 passes accuracy but full-network work reduction is below 45%; test output-layer sparsity"
            if algorithm_gate and not system_gate
            else "local evidence does not pass the B2 algorithm gate"
            if not algorithm_gate
            else "algorithm and work gates pass"
        ),
    }


def build_results(*, seeds: Sequence[int] = tuple(range(10))) -> dict[str, object]:
    matrix = run_b2_matrix(seeds=seeds)
    decisions: dict[str, object] = {}
    for model_id, summary in matrix["summary"].items():
        first_seed = matrix["per_seed"][0]["models"][model_id]
        dense_reads = first_seed["dense"]["work"]["network_weight_reads_issued"]
        s2_reads = first_seed["S2"]["work"]["network_weight_reads_issued"]
        reduction = (dense_reads - s2_reads) / dense_reads
        decisions[model_id] = {
            **decide_model(summary, full_network_reduction=reduction),
            "dense_network_reads": dense_reads,
            "s2_network_reads": s2_reads,
            "full_network_reduction": reduction,
        }
    return {
        **matrix,
        "generated_date": "2026-08-28",
        "git_commit": _git_revision(),
        "source_sha256": {name: _sha256(ROOT / name) for name in SOURCE_FILES},
        "task": {
            "task_id": "redundant_detector_4x8x2_b2_v1",
            "topology": "4->8->2",
            "all_neurons_four_input": True,
            "output_requires_detectors": 3,
            "evaluation_samples": 20,
            "random_mask_seed_rule": "seed+2003",
            "decoder_id": "strict_single_active_v1",
        },
        "decisions": decisions,
        "claim_boundary": {
            "synthetic_pressure_task": True,
            "shared_lane_rtl_proven": False,
            "vivado_timing_proven": False,
            "power_savings_proven": False,
            "image_pruning_proven": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "local_prune_b2_results.json")
    parser.add_argument("--seeds", type=int, default=10)
    args = parser.parse_args()
    if args.seeds < 10:
        raise ValueError("B2 requires at least ten seeds")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = build_results(seeds=tuple(range(args.seeds)))
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("B2 %d-seed 结果已写入 %s", args.seeds, args.output)


if __name__ == "__main__":
    main()

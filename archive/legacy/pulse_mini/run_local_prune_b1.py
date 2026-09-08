"""运行三种神经元的固定 B1 局部 2:4 剪枝实验。"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from compare_simulation import (
    make_shared_network_evaluation_data,
    make_shared_network_training_data,
)
from local_prune_b1 import run_eneuron_b1, run_pulse_b1
from pulse_mini_l2_reference import PulseMiniL2Reference
from pulse_mini_reference import PulseMiniReference


LOGGER = logging.getLogger("run_local_prune_b1")
ROOT = Path(__file__).resolve().parent
SOURCE_FILES = (
    "local_prune_reference.py",
    "local_prune_b1.py",
    "eneuron_prune_adapter.py",
    "pulse_prune_adapter.py",
    "pulse_mini_network.py",
    "run_local_prune_b1.py",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(name: str) -> str:
    return _sha256_bytes((ROOT / name).read_bytes())


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(encoded)


def _git_revision() -> str:
    """读取当前提交；只为 provenance 使用，不修改全局 safe.directory。"""
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "rev-parse",
            "HEAD",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build_results(
    *,
    seed: int = 7,
    eneuron_warmup_epochs: int = 30,
    eneuron_fine_tune_epochs: int = 5,
    pulse_warmup_repetitions: int = 6,
    pulse_fine_tune_repetitions: int = 2,
) -> dict[str, Any]:
    """构造可重复的三模型 B1 结果，不写文件。"""
    training = make_shared_network_training_data()
    evaluation = make_shared_network_evaluation_data()
    models = {
        "eneuron": run_eneuron_b1(
            seed=seed,
            warmup_epochs=eneuron_warmup_epochs,
            fine_tune_epochs=eneuron_fine_tune_epochs,
        ),
        "pulse_mini_l": run_pulse_b1(
            model_id="pulse_mini_l",
            core_type=PulseMiniReference,
            seed=seed,
            warmup_repetitions=pulse_warmup_repetitions,
            fine_tune_repetitions=pulse_fine_tune_repetitions,
        ),
        "pulse_mini_l2": run_pulse_b1(
            model_id="pulse_mini_l2",
            core_type=PulseMiniL2Reference,
            seed=seed,
            warmup_repetitions=pulse_warmup_repetitions,
            fine_tune_repetitions=pulse_fine_tune_repetitions,
        ),
    }
    return {
        "schema": "eneuron.local_prune_b1_matrix.v1",
        "generated_date": "2026-08-28",
        "git_commit": _git_revision(),
        "source_sha256": {name: _sha256_file(name) for name in SOURCE_FILES},
        "task": {
            "task_id": "shared_4x2x2_b1_v1",
            "topology": "4->2->2",
            "route_latency_ticks": 1,
            "mask_scope": "hidden_only",
            "training_samples": len(training),
            "evaluation_samples": len(evaluation),
            "training_dataset_sha256": _canonical_sha256(training),
            "evaluation_dataset_sha256": _canonical_sha256(evaluation),
            "decoder_id": "strict_single_active_v1",
            "random_mask_seed": seed + 1009,
        },
        "config": {
            "seed": seed,
            "eneuron_warmup_epochs": eneuron_warmup_epochs,
            "eneuron_fine_tune_epochs": eneuron_fine_tune_epochs,
            "pulse_warmup_repetitions": pulse_warmup_repetitions,
            "pulse_fine_tune_repetitions": pulse_fine_tune_repetitions,
        },
        "models": models,
        "claim_boundary": {
            "b1_only": True,
            "distinguishes_score_methods": False,
            "rtl_skip_proven": False,
            "power_savings_proven": False,
            "image_pruning_proven": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/results/local_prune_b1_results.json",
    )
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    result = build_results(seed=args.seed)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("B1 三模型结果已写入 %s", args.output)


if __name__ == "__main__":
    main()

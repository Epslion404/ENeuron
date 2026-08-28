"""生成三模型 NP2 固定量化扫描的机器可读结果。"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Sequence

from local_prune_np2 import run_np2_scan


LOGGER = logging.getLogger("run_local_prune_np2")
ROOT = Path(__file__).resolve().parent
SOURCE_FILES = (
    "local_prune_reference.py",
    "local_prune_b1.py",
    "local_prune_b2.py",
    "local_prune_np2.py",
    "run_local_prune_np2.py",
    "neuron_sim.py",
    "pulse_mini_reference.py",
    "pulse_mini_l2_reference.py",
)


def _sha256(path: Path) -> str:
    """返回文件原始字节的 SHA-256。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_revision() -> str:
    """读取当前提交，且不修改用户的全局 safe.directory。"""
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build_results(*, seeds: Sequence[int] = tuple(range(10))) -> dict[str, object]:
    """运行扫描并补齐可复现来源、声明边界和固定日期。"""
    result = run_np2_scan(seeds=seeds)
    return {
        **result,
        "generated_date": "2026-08-28",
        "git_commit": _git_revision(),
        "source_sha256": {name: _sha256(ROOT / name) for name in SOURCE_FILES},
        "claim_boundary": {
            **result["claim_boundary"],
            "image_pruning_proven": False,
            "power_savings_proven": False,
            "vivado_timing_proven": False,
        },
    }


def main() -> None:
    """命令行入口；默认运行冻结的十个验收 seed。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "local_prune_np2_results.json")
    parser.add_argument("--seeds", type=int, default=10)
    args = parser.parse_args()
    if args.seeds < 10:
        raise ValueError("NP2 requires at least ten seeds")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = build_results(seeds=tuple(range(args.seeds)))
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("NP2 %d-seed 量化扫描已写入 %s", args.seeds, args.output)


if __name__ == "__main__":
    main()

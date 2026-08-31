"""生成三模型 B2.1 结果并联合 NP2/NP3 判断是否允许启动 NP4。"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Sequence

from local_prune_b21 import run_b21_experiment


LOGGER = logging.getLogger("run_local_prune_b21")
ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "artifacts" / "results"
SOURCE_FILES = (
    "local_prune_reference.py",
    "local_prune_b1.py",
    "local_prune_b2.py",
    "local_prune_np2.py",
    "local_prune_b21.py",
    "run_local_prune_b21.py",
    "neuron_sim.py",
    "pulse_mini_reference.py",
    "pulse_mini_l2_reference.py",
)
PREREQUISITE_FILES = (
    "artifacts/results/local_prune_np2_results.json",
    "artifacts/results/local_prune_np3_results.json",
)


def _sha256(path: Path) -> str:
    """返回文件原始字节的 SHA-256。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_revision() -> str:
    """读取 HEAD，不修改用户的全局 Git 配置。"""
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _load_result(name: str) -> dict[str, Any]:
    """读取前置机器结果并验证其记录的源码仍与当前工作树一致。"""
    result = json.loads((ROOT / name).read_text(encoding="utf-8"))
    for source_name, expected_hash in result["source_sha256"].items():
        actual_hash = _sha256(ROOT / source_name)
        if actual_hash != expected_hash:
            raise RuntimeError(f"stale prerequisite {name}: {source_name} changed")
    return result


def build_results(*, seeds: Sequence[int] = tuple(range(10))) -> dict[str, object]:
    """联合三道软件门，但只放行 NP4 实现，不宣称 RTL 已证明。"""
    b21 = run_b21_experiment(seeds=seeds)
    np2 = _load_result("artifacts/results/local_prune_np2_results.json")
    np3 = _load_result("artifacts/results/local_prune_np3_results.json")
    decisions: dict[str, object] = {}
    for model_id, model in b21["models"].items():
        recommended = model["recommended_candidate"]
        candidate = model["candidates"][recommended] if recommended is not None else None
        np2_pass = bool(np2["models"][model_id]["algorithm_gate_pass"])
        np3_pass = bool(np3["decisions"][model_id]["np3_pass"])
        b21_pass = bool(candidate and candidate["joint_gate_pass"])
        np4_go = np2_pass and np3_pass and b21_pass and recommended == "output_2of4"
        dense_reads = int(model["baseline"]["dense_network_weight_reads"])
        sparse_reads = int(candidate["learned"]["work"]["network_weight_reads_issued"]) if candidate else dense_reads
        decisions[model_id] = {
            "np2_pass": np2_pass,
            "np3_pass": np3_pass,
            "b21_joint_gate_pass": b21_pass,
            "recommended_candidate": recommended,
            "dense_network_reads": dense_reads,
            "recommended_network_reads": sparse_reads,
            "full_network_reduction": (dense_reads - sparse_reads) / dense_reads,
            "np4_implementation_go": np4_go,
            "rtl_proven": False,
            "reason": (
                "software gates pass; freeze output-2:4 interface and start NP4"
                if np4_go
                else "one or more software gates failed"
            ),
        }
    return {
        **b21,
        "generated_date": "2026-08-28",
        "git_commit": _git_revision(),
        "source_sha256": {name: _sha256(ROOT / name) for name in SOURCE_FILES},
        "prerequisite_sha256": {name: _sha256(ROOT / name) for name in PREREQUISITE_FILES},
        "decisions": decisions,
        "overall_decision": {
            "np4_implementation_go": all(
                decision["np4_implementation_go"]
                for decision in decisions.values()
            ),
            "frozen_candidate": "output_2of4",
            "rtl_proven": False,
        },
    }


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_DIR / "local_prune_b21_results.json",
    )
    parser.add_argument("--seeds", type=int, default=10)
    args = parser.parse_args()
    if args.seeds < 10:
        raise ValueError("B2.1 requires at least ten seeds")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = build_results(seeds=tuple(range(args.seeds)))
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("B2.1 三模型联合门结果已写入 %s", args.output)


if __name__ == "__main__":
    main()

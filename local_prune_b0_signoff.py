"""生成 NP1/B0 固定向量的可复核机器摘要。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from local_prune_reference import LocalPrune2of4, PruneMode, ScoreMethod


ROOT = Path(__file__).resolve().parent
VECTOR_PATH = ROOT / "local_prune_b0_vectors.json"
HASHED_SOURCES = (
    "local_prune_reference.py",
    "test_local_prune_reference.py",
    "local_prune_b0_vectors.json",
    "local_prune_b0_signoff.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_signoff_summary() -> dict[str, object]:
    """执行固定向量并返回确定性摘要；任何不一致立即失败。"""
    vectors = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
    score_results: list[dict[str, object]] = []
    for vector in vectors["score_vectors"]:
        method = ScoreMethod[vector["method"]]
        controller = LocalPrune2of4(score_method=method)
        controller.set_mode(PruneMode.TRAIN)
        for observation_id, evidence in enumerate(vector["observations"]):
            controller.observe(
                weights=vector["weights"],
                evidence_levels=evidence,
                modulator=1,
                observation_id=observation_id,
            )
        result = controller.prune_commit(weights=vector["weights"], commit_id=1)
        if result.mask != vector["expected_mask"]:
            raise AssertionError(f"{method.name} golden mask mismatch")
        score_results.append({
            "method": method.name,
            "utility": list(controller.utility),
            "mask": result.mask,
            "selected": list(result.selected),
            "reason": result.reason,
        })

    output_mask_results: dict[str, int] = {}
    for expected_mask, weights in vectors["all_output_masks"].items():
        controller = LocalPrune2of4(score_method=ScoreMethod.S0)
        controller.set_mode(PruneMode.TRAIN)
        result = controller.prune_commit(weights=weights, commit_id=1)
        if result.mask != int(expected_mask):
            raise AssertionError(f"output mask {expected_mask} mismatch")
        output_mask_results[expected_mask] = result.mask

    issue_vector = vectors["issue_vector"]
    gate = LocalPrune2of4(score_method=ScoreMethod.S0)
    gate.mask_write(issue_vector["structural_mask"])
    issue_masks = [gate.issue(mask).issue_mask for mask in issue_vector["activity_masks"]]
    expected_issue_masks = issue_vector["expected_issue_masks"]
    if issue_masks != expected_issue_masks:
        raise AssertionError("activity/structural intersection mismatch")
    issue_totals = {
        "dense_reads": gate.dense_weight_reads_requested,
        "issued_reads": gate.weight_reads_issued,
        "saved_reads": gate.reads_saved_by_structure,
        "inactive_groups": gate.inactive_groups,
        "structurally_skipped_groups": gate.groups_skipped,
    }
    expected_totals = {
        "dense_reads": issue_vector["expected_dense_reads"],
        "issued_reads": issue_vector["expected_issued_reads"],
        "saved_reads": issue_vector["expected_saved_reads"],
        "inactive_groups": issue_vector["expected_inactive_groups"],
        "structurally_skipped_groups": issue_vector["expected_structurally_skipped_groups"],
    }
    if issue_totals != expected_totals:
        raise AssertionError("issue counter totals mismatch")

    return {
        "schema": "eneuron.local_prune_b0_signoff.v1",
        "source_sha256": {
            name: _sha256(ROOT / name)
            for name in HASHED_SOURCES
        },
        "score_results": score_results,
        "all_output_masks": output_mask_results,
        "issue_masks": issue_masks,
        "issue_totals": issue_totals,
    }


def main() -> None:
    """将稳定 JSON 写到标准输出，便于 CI 或人工保存。"""
    print(json.dumps(build_signoff_summary(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

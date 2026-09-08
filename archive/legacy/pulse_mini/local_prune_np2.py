"""NP2：三模型固定证据量化扫描与剪枝统计。

扫描只改变适配器输出的二位证据等级，不改变神经元状态、utility 位宽或
控制器更新方程。每个模型从同一 checkpoint 选择一个全局 gain，禁止按 seed
或 detector 单独调参。
"""

from __future__ import annotations

import logging
import statistics
from collections import Counter
from dataclasses import replace
from typing import Any, Sequence

from local_prune_b1 import exact_two_random_masks
from local_prune_b2 import (
    B2Checkpoint,
    _evaluate_branch,
    build_eneuron_b2_checkpoint,
    build_pulse_b2_checkpoint,
)
from local_prune_reference import LocalPrune2of4, PruneMode, ScoreMethod
from pulse_mini_l2_reference import PulseMiniL2Reference
from pulse_mini_reference import PulseMiniReference


LOGGER = logging.getLogger("local_prune_np2")
EVIDENCE_GAINS = (1, 2, 3)


def scale_checkpoint_evidence(checkpoint: B2Checkpoint, *, gain: int) -> B2Checkpoint:
    """把整个模型的非负证据统一放大并饱和到控制器的 0..3 接口。"""
    if not isinstance(gain, int) or isinstance(gain, bool):
        raise TypeError("gain must be an integer")
    if gain not in EVIDENCE_GAINS:
        raise ValueError(f"gain must be one of {EVIDENCE_GAINS}")
    ledgers = tuple(
        tuple(
            replace(
                entry,
                evidence_levels=tuple(min(3, gain * value) for value in entry.evidence_levels),
            )
            for entry in ledger
        )
        for ledger in checkpoint.ledgers
    )
    return replace(checkpoint, ledgers=ledgers)


def _preview_s2_mask(utility: Sequence[int]) -> int:
    """复现 S2 的 utility、输入编号破同分规则，但不改变控制器状态。"""
    ranked = sorted(range(4), key=lambda index: (utility[index], -index), reverse=True)
    return (1 << ranked[0]) | (1 << ranked[1])


def _audit_group(checkpoint: B2Checkpoint, group_index: int) -> dict[str, object]:
    """重放一个四连接组，并记录真实裁剪、边界同分和前缀稳定性。"""
    core = checkpoint.cores[group_index]
    ledger = checkpoint.ledgers[group_index]
    controller = LocalPrune2of4(score_method=ScoreMethod.S2)
    controller.set_mode(PruneMode.TRAIN)
    clip_events = 0
    update_opportunities = 0
    stable_previews: list[int] = []
    pre_mislead_mask: int | None = None

    for observation_id, entry in enumerate(ledger):
        if entry.phase == "mislead" and pre_mislead_mask is None:
            pre_mislead_mask = _preview_s2_mask(controller.utility)
        if entry.modulator != 0:
            for old_value, level in zip(controller.utility, entry.evidence_levels):
                raw_value = max(0, old_value - 1) + level
                clip_events += raw_value > controller.UTILITY_MAX
                update_opportunities += 1
        controller.observe(
            weights=entry.weights_before,
            evidence_levels=entry.evidence_levels,
            modulator=entry.modulator,
            observation_id=observation_id,
        )
        if entry.phase == "stable":
            stable_previews.append(_preview_s2_mask(controller.utility))

    utility = tuple(controller.utility)
    ranked = sorted(range(4), key=lambda index: (utility[index], -index), reverse=True)
    boundary_tie = utility[ranked[1]] == utility[ranked[2]]
    result = controller.prune_commit(weights=core.weights, commit_id=1)
    final_window = stable_previews[-3:]
    return {
        "mask": result.mask,
        "utility": list(utility),
        "boundary_tie": boundary_tie,
        "index_tiebreak": boundary_tie,
        "clip_events": clip_events,
        "update_opportunities": update_opportunities,
        "saturated_lanes": sum(value == controller.UTILITY_MAX for value in utility),
        "final_window_matches": sum(mask == result.mask for mask in final_window),
        "final_window_samples": len(final_window),
        "pre_mislead_match": pre_mislead_mask == result.mask,
    }


def audit_s2_checkpoint(checkpoint: B2Checkpoint) -> dict[str, object]:
    """汇总八个 detector 组的可签核统计和最终 mask。"""
    groups = [_audit_group(checkpoint, index) for index in range(len(checkpoint.cores))]
    masks = [int(group["mask"]) for group in groups]
    total_updates = sum(int(group["update_opportunities"]) for group in groups)
    total_final_samples = sum(int(group["final_window_samples"]) for group in groups)
    distribution = Counter(f"0x{mask:x}" for mask in masks)
    return {
        "masks": masks,
        "mask_distribution": dict(sorted(distribution.items())),
        "unique_masks": len(distribution),
        "boundary_tie_rate": sum(bool(group["boundary_tie"]) for group in groups) / len(groups),
        "index_tiebreak_rate": sum(bool(group["index_tiebreak"]) for group in groups) / len(groups),
        "clip_event_rate": (
            sum(int(group["clip_events"]) for group in groups) / total_updates
            if total_updates
            else 0.0
        ),
        "lane_saturation_rate": (
            sum(int(group["saturated_lanes"]) for group in groups) / (4 * len(groups))
        ),
        "final_window_stability": (
            sum(int(group["final_window_matches"]) for group in groups) / total_final_samples
            if total_final_samples
            else 0.0
        ),
        "pre_mislead_match_rate": (
            sum(bool(group["pre_mislead_match"]) for group in groups) / len(groups)
        ),
        "groups": groups,
    }


def _algorithm_gate(
    *,
    dense: dict[str, object],
    sparse: dict[str, object],
    random_values: Sequence[float],
) -> dict[str, object]:
    """复用 B2 的精度、coverage、随机优势和逐 seed 配对门。"""
    sparse_bacc = float(sparse["balanced_accuracy"])
    random_median = statistics.median(random_values)
    not_below_random = sum(sparse_bacc >= value for value in random_values)
    pass_gate = (
        float(dense["balanced_accuracy"]) - sparse_bacc <= 0.02
        and float(dense["coverage"]) - float(sparse["coverage"]) <= 0.02
        and 100 * (sparse_bacc - random_median) >= 5.0
        and not_below_random >= 8
    )
    return {
        "algorithm_gate_pass": pass_gate,
        "s2_minus_random_median_pp": 100 * (sparse_bacc - random_median),
        "s2_not_below_random_seeds": not_below_random,
    }


def _scan_model(checkpoint: B2Checkpoint, *, seeds: Sequence[int]) -> dict[str, object]:
    """对一个模型运行共享随机对照和三个固定 gain。"""
    dense = _evaluate_branch(checkpoint, (0b1111,) * len(checkpoint.cores))
    random_values = [
        float(
            _evaluate_branch(
                checkpoint,
                exact_two_random_masks(seed=seed + 2003, count=len(checkpoint.cores)),
            )["balanced_accuracy"]
        )
        for seed in seeds
    ]
    gains: dict[str, object] = {}
    selected_gain: int | None = None
    for gain in EVIDENCE_GAINS:
        scaled = scale_checkpoint_evidence(checkpoint, gain=gain)
        audit = audit_s2_checkpoint(scaled)
        sparse = _evaluate_branch(scaled, audit["masks"])
        gate = _algorithm_gate(dense=dense, sparse=sparse, random_values=random_values)
        gains[str(gain)] = {
            "balanced_accuracy": sparse["balanced_accuracy"],
            "coverage": sparse["coverage"],
            "network_weight_reads_issued": sparse["work"]["network_weight_reads_issued"],
            "network_synapse_ops_issued": sparse["work"]["network_synapse_ops_issued"],
            "audit": audit,
            **gate,
        }
        if selected_gain is None and gate["algorithm_gate_pass"]:
            selected_gain = gain

    LOGGER.info("NP2 model=%s selected_gain=%s", checkpoint.model_id, selected_gain)
    return {
        "dense_balanced_accuracy": dense["balanced_accuracy"],
        "dense_coverage": dense["coverage"],
        "dense_network_weight_reads_issued": dense["work"]["network_weight_reads_issued"],
        "random_balanced_accuracy_values": random_values,
        "random_median_balanced_accuracy": statistics.median(random_values),
        "gains": gains,
        "selected_gain": selected_gain,
        "algorithm_gate_pass": selected_gain is not None,
    }


def run_np2_scan(*, seeds: Sequence[int]) -> dict[str, object]:
    """三模型共享 seed，一次性选择每个适配器的最小固定 evidence gain。"""
    if len(seeds) < 10 or len(set(seeds)) != len(seeds):
        raise ValueError("NP2 requires at least ten distinct seeds")
    checkpoints = (
        build_eneuron_b2_checkpoint(),
        build_pulse_b2_checkpoint(PulseMiniReference),
        build_pulse_b2_checkpoint(PulseMiniL2Reference),
    )
    return {
        "schema": "eneuron.local_prune_np2.v1",
        "seeds": list(seeds),
        "evidence_gains": list(EVIDENCE_GAINS),
        "selection_rule": "smallest_global_gain_passing_b2_algorithm_gate",
        "models": {
            checkpoint.model_id: _scan_model(checkpoint, seeds=seeds)
            for checkpoint in checkpoints
        },
        "claim_boundary": {
            "adapter_quantization_only": True,
            "per_seed_tuning": False,
            "rtl_proven": False,
            "system_work_gate_proven": False,
        },
    }


__all__ = [
    "EVIDENCE_GAINS",
    "audit_s2_checkpoint",
    "run_np2_scan",
    "scale_checkpoint_evidence",
]

"""B2.1：三模型输出层 2:4 与整 detector 通道门控软件实验。

隐藏层固定使用 NP2/NP3 已签核的 S2 与 gain=1/2/1。三种候选只改变
输出连接或 detector enable；所有门控都在权重读取和计算发射前生效。
"""

from __future__ import annotations

import copy
import logging
import random
from dataclasses import dataclass, replace
from typing import Any, Sequence

from local_prune_b1 import exact_two_random_masks, score_binary_outputs
from local_prune_b2 import (
    B2Checkpoint,
    _evaluate_branch,
    _indices,
    _pulse_execute,
    _train_eneuron_observation,
    _train_pulse_observation,
    build_b2_dataset,
    build_eneuron_b2_checkpoint,
    build_pulse_b2_checkpoint,
)
from local_prune_np2 import audit_s2_checkpoint, scale_checkpoint_evidence
from local_prune_reference import LocalPrune2of4, PruneMode, ScoreMethod
from neuron_sim import ThreeFactorNeuron
from pulse_mini_l2_reference import PulseMiniL2Reference
from pulse_mini_reference import Command, Mode, Opcode, PulseMiniReference, Status


LOGGER = logging.getLogger("local_prune_b21")
MODEL_GAINS = {
    "eneuron": 1,
    "pulse_mini_l": 2,
    "pulse_mini_l2": 1,
}
CANDIDATE_ORDER = ("output_2of4", "detector_3of4", "detector_2of4")


@dataclass(frozen=True)
class GateConfig:
    """一个候选的永久 detector enable 和两组输出结构 mask。"""

    channel_enable: int
    output_masks: tuple[int, int]


def _global_channel_enable(class_masks: Sequence[int]) -> int:
    """把两个四位类内 mask 合并为八位 detector enable。"""
    if len(class_masks) != 2 or any(not 0 <= mask <= 0xF for mask in class_masks):
        raise ValueError("class masks must contain two four-bit values")
    return class_masks[0] | (class_masks[1] << 4)


def _top_class_masks(group_audit: Sequence[dict[str, object]], count: int) -> tuple[int, int]:
    """按每个 detector 的四路 utility 总和选择类内 top-k。"""
    masks: list[int] = []
    for class_index in range(2):
        group_slice = group_audit[class_index * 4:(class_index + 1) * 4]
        scores = [sum(int(value) for value in group["utility"]) for group in group_slice]
        ranked = sorted(range(4), key=lambda index: (scores[index], -index), reverse=True)
        masks.append(sum(1 << index for index in ranked[:count]))
    return masks[0], masks[1]


def _learned_output_masks() -> tuple[tuple[int, int], dict[str, object]]:
    """用本地等价 detector 证据训练两个输出 S2 控制器。"""
    masks: list[int] = []
    utilities: list[list[int]] = []
    boundary_ties: list[bool] = []
    for _ in range(2):
        controller = LocalPrune2of4(score_method=ScoreMethod.S2)
        controller.set_mode(PruneMode.TRAIN)
        for observation_id in range(6):
            controller.observe(
                weights=(2, 2, 2, 2),
                evidence_levels=(2, 2, 2, 2),
                modulator=1,
                observation_id=observation_id,
            )
        utility = list(controller.utility)
        ranked = sorted(range(4), key=lambda index: (utility[index], -index), reverse=True)
        boundary_ties.append(utility[ranked[1]] == utility[ranked[2]])
        masks.append(controller.prune_commit(weights=(2, 2, 2, 2), commit_id=1).mask)
        utilities.append(utility)
    return (masks[0], masks[1]), {
        "utilities": utilities,
        "boundary_ties": boundary_ties,
        "score_superiority_proven": False,
        "reason": "four redundant detectors have equal local utility; input index resolves the tie",
    }


def _learned_config(candidate: str, hidden_audit: dict[str, object]) -> tuple[GateConfig, dict[str, object]]:
    """从隐藏 utility 或输出本地 utility 形成确定性候选。"""
    if candidate == "output_2of4":
        output_masks, audit = _learned_output_masks()
        return GateConfig(0xFF, output_masks), audit
    count = 3 if candidate == "detector_3of4" else 2
    class_masks = _top_class_masks(hidden_audit["groups"], count)
    return GateConfig(_global_channel_enable(class_masks), class_masks), {
        "class_masks": list(class_masks),
        "score_superiority_proven": False,
        "reason": "detectors are deliberately redundant and tie on local utility",
    }


def _random_config(candidate: str, seed: int) -> GateConfig:
    """生成跨模型共享的同稀疏率随机对照。"""
    if candidate == "output_2of4":
        masks = exact_two_random_masks(seed=seed + 3001, count=2)
        return GateConfig(0xFF, (masks[0], masks[1]))
    if candidate == "detector_2of4":
        masks = exact_two_random_masks(seed=seed + 4001, count=2)
        return GateConfig(_global_channel_enable(masks), (masks[0], masks[1]))
    rng = random.Random(seed + 5003)
    masks = tuple(0xF ^ (1 << rng.randrange(4)) for _ in range(2))
    return GateConfig(_global_channel_enable(masks), (masks[0], masks[1]))


def _new_output_cores(checkpoint: B2Checkpoint) -> list[Any]:
    """构造与隐藏核心同类型的两个固定四输入输出神经元。"""
    if checkpoint.model_id == "eneuron":
        outputs = [ThreeFactorNeuron(4), ThreeFactorNeuron(4)]
        for output in outputs:
            output.weights = [2, 2, 2, 2]
        return outputs
    core_type = type(checkpoint.cores[0])
    outputs = [core_type(initial_weights=(2, 2, 2, 2)) for _ in range(2)]
    for output in outputs:
        _pulse_execute(output, Command(Opcode.MODE_SET, int(Mode.TRAIN)))
    return outputs


def _train_output_cores(
    checkpoint: B2Checkpoint,
    output_masks: Sequence[int],
) -> tuple[tuple[Any, Any], dict[str, object]]:
    """只用正常训练事务适配稀疏输出，不直接写权重或阈值。"""
    outputs = _new_output_cores(checkpoint)
    parent_weights = [tuple(output.weights) for output in outputs]
    ledger: list[dict[str, object]] = []
    for output_index, (output, mask) in enumerate(zip(outputs, output_masks)):
        for observation in range(2):
            weights_before = tuple(output.weights)
            if checkpoint.model_id == "eneuron":
                evidence = _train_eneuron_observation(
                    output,
                    input_mask=mask,
                    modulator=1,
                    strong=True,
                    phase="output_sparse_fine_tune",
                )
            else:
                evidence = _train_pulse_observation(
                    output,
                    input_mask=mask,
                    modulator=1,
                    strong=True,
                    phase="output_sparse_fine_tune",
                )
            ledger.append({
                "output": output_index,
                "observation": observation,
                "input_mask": mask,
                "weights_before": list(weights_before),
                "weights_after": list(output.weights),
                "evidence_levels": list(evidence.evidence_levels),
            })
    pruned_unchanged = all(
        output.weights[index] == parent_weights[output_index][index]
        for output_index, (output, mask) in enumerate(zip(outputs, output_masks))
        for index in range(4)
        if not mask & (1 << index)
    )
    return (outputs[0], outputs[1]), {
        "direct_weight_writes": 0,
        "threshold_writes": 0,
        "observations_per_output": 2,
        "pruned_output_weights_unchanged": pruned_unchanged,
        "final_weights": [list(output.weights) for output in outputs],
        "ledger": ledger,
    }


def _prepare_pulse_infer(core: PulseMiniReference) -> None:
    """把 Pulse 输出或 detector 核切换到冻结推理。"""
    _pulse_execute(core, Command(Opcode.MODE_SET, int(Mode.INFER)))
    _pulse_execute(core, Command(Opcode.STATE_CLEAR))


def _infer_eneuron_sample(
    checkpoint: B2Checkpoint,
    *,
    hidden_masks: Sequence[int],
    config: GateConfig,
    output_templates: Sequence[ThreeFactorNeuron],
    sample: Any,
) -> tuple[tuple[int, int], dict[str, int]]:
    """运行一个 ENeuron 样本并统计门控前后的实际请求。"""
    detectors = copy.deepcopy(checkpoint.cores)
    outputs = copy.deepcopy(output_templates)
    for core in (*detectors, *outputs):
        core.reset_episode()
    pending = ((), ())
    counts = [0, 0]
    work = {"hidden_dense_active": 0, "hidden_after_structure": 0, "hidden_actual": 0, "output_pre_mask": 0, "output_actual": 0}
    for tick, input_mask in enumerate((sample.input_mask, 0, 0)):
        for label, output in enumerate(outputs):
            work["output_pre_mask"] += len(pending[label])
            active = tuple(index for index in pending[label] if config.output_masks[label] & (1 << index))
            work["output_actual"] += len(active)
            counts[label] += output.step(active, tick, learn_enable=False)
        fired_by_class = [[], []]
        for index, (core, structural_mask) in enumerate(zip(detectors, hidden_masks)):
            work["hidden_dense_active"] += input_mask.bit_count()
            structural = input_mask & structural_mask
            work["hidden_after_structure"] += structural.bit_count()
            if not config.channel_enable & (1 << index):
                continue
            work["hidden_actual"] += structural.bit_count()
            if core.step(_indices(structural), tick, learn_enable=False):
                fired_by_class[index // 4].append(index % 4)
        pending = tuple(tuple(values) for values in fired_by_class)  # type: ignore[assignment]
    for label, output in enumerate(outputs):
        work["output_pre_mask"] += len(pending[label])
        active = tuple(index for index in pending[label] if config.output_masks[label] & (1 << index))
        work["output_actual"] += len(active)
        counts[label] += output.step(active, 3, learn_enable=False)
    return (counts[0], counts[1]), work


def _infer_pulse_sample(
    checkpoint: B2Checkpoint,
    *,
    hidden_masks: Sequence[int],
    config: GateConfig,
    output_templates: Sequence[PulseMiniReference],
    sample: Any,
) -> tuple[tuple[int, int], dict[str, int]]:
    """运行一个 Pulse 样本并统计门控前后的实际请求。"""
    detectors = copy.deepcopy(checkpoint.cores)
    outputs = copy.deepcopy(output_templates)
    for core in (*detectors, *outputs):
        _prepare_pulse_infer(core)
    pending = (0, 0)
    counts = [0, 0]
    work = {"hidden_dense_active": 0, "hidden_after_structure": 0, "hidden_actual": 0, "output_pre_mask": 0, "output_actual": 0}
    for input_mask in (sample.input_mask, 0, 0):
        for label, output in enumerate(outputs):
            work["output_pre_mask"] += pending[label].bit_count()
            active = pending[label] & config.output_masks[label]
            work["output_actual"] += active.bit_count()
            response = output.execute(Command(Opcode.TICK, active, 0))
            if response.status is not Status.OK:
                raise RuntimeError("Pulse B2.1 output tick failed")
            counts[label] += response.spike
        next_pending = [0, 0]
        for index, (core, structural_mask) in enumerate(zip(detectors, hidden_masks)):
            work["hidden_dense_active"] += input_mask.bit_count()
            structural = input_mask & structural_mask
            work["hidden_after_structure"] += structural.bit_count()
            if not config.channel_enable & (1 << index):
                continue
            work["hidden_actual"] += structural.bit_count()
            response = core.execute(Command(Opcode.TICK, structural, 0))
            if response.status is not Status.OK:
                raise RuntimeError("Pulse B2.1 detector tick failed")
            if response.spike:
                next_pending[index // 4] |= 1 << (index % 4)
        pending = next_pending[0], next_pending[1]
    for label, output in enumerate(outputs):
        work["output_pre_mask"] += pending[label].bit_count()
        active = pending[label] & config.output_masks[label]
        work["output_actual"] += active.bit_count()
        response = output.execute(Command(Opcode.TICK, active, 0))
        if response.status is not Status.OK:
            raise RuntimeError("Pulse B2.1 route flush failed")
        counts[label] += response.spike
    return (counts[0], counts[1]), work


def _evaluate_config(
    checkpoint: B2Checkpoint,
    *,
    hidden_masks: Sequence[int],
    config: GateConfig,
    dense_hidden_reads: int,
    hidden_s2_reads: int,
    hidden_s2_output_reads: int,
) -> dict[str, object]:
    """训练稀疏输出并在固定数据集上汇总不重叠的工作量。"""
    output_templates, training_audit = _train_output_cores(checkpoint, config.output_masks)
    infer = _infer_eneuron_sample if checkpoint.model_id == "eneuron" else _infer_pulse_sample
    rows = [
        infer(
            checkpoint,
            hidden_masks=hidden_masks,
            config=config,
            output_templates=output_templates,
            sample=sample,
        )
        for sample in build_b2_dataset()
    ]
    metrics = score_binary_outputs(
        labels=tuple(sample.label for sample in build_b2_dataset()),
        scores=tuple(row[0] for row in rows),
    )
    totals = {
        key: sum(row[1][key] for row in rows)
        for key in rows[0][1]
    }
    actual_reads = totals["hidden_actual"] + totals["output_actual"]
    dense_network_reads = dense_hidden_reads + hidden_s2_output_reads
    work = {
        "scope": "full_4x8x2_hidden_2of4_output_or_channel_gate",
        "dense_network_weight_reads": dense_network_reads,
        "hidden_dense_active_reads": dense_hidden_reads,
        "hidden_after_structure_reads": totals["hidden_after_structure"],
        "hidden_weight_reads_issued": totals["hidden_actual"],
        "output_pre_mask_reads": totals["output_pre_mask"],
        "output_weight_reads_issued": totals["output_actual"],
        "hidden_reads_saved_by_structure": dense_hidden_reads - hidden_s2_reads,
        "hidden_reads_saved_by_channel": hidden_s2_reads - totals["hidden_actual"],
        "output_reads_saved_by_channel": hidden_s2_output_reads - totals["output_pre_mask"],
        "output_reads_saved_by_structure": totals["output_pre_mask"] - totals["output_actual"],
        "network_weight_reads_issued": actual_reads,
        "network_synapse_ops_issued": actual_reads,
        "natural_zero_activity_is_not_counted_as_saving": True,
    }
    return {
        "balanced_accuracy": metrics.balanced_accuracy,
        "coverage": metrics.coverage,
        "correct": metrics.correct,
        "covered": metrics.covered,
        "total": metrics.total,
        "channel_enable": config.channel_enable,
        "output_masks": list(config.output_masks),
        "work": work,
        "output_training_audit": training_audit,
    }


def _run_model(checkpoint: B2Checkpoint, *, seeds: Sequence[int]) -> dict[str, object]:
    """运行一个模型的三个 learned 分支及共享随机对照。"""
    gain = MODEL_GAINS[checkpoint.model_id]
    scaled = scale_checkpoint_evidence(checkpoint, gain=gain)
    hidden_audit = audit_s2_checkpoint(scaled)
    hidden_masks = tuple(int(mask) for mask in hidden_audit["masks"])
    dense = _evaluate_branch(scaled, (0xF,) * 8)
    hidden_s2 = _evaluate_branch(scaled, hidden_masks)
    dense_hidden_reads = int(dense["work"]["hidden_weight_reads_issued"])
    hidden_s2_reads = int(hidden_s2["work"]["hidden_weight_reads_issued"])
    hidden_s2_output_reads = int(hidden_s2["work"]["output_weight_reads_issued"])
    candidates: dict[str, object] = {}
    for candidate in CANDIDATE_ORDER:
        learned_config, selection_audit = _learned_config(candidate, hidden_audit)
        learned = _evaluate_config(
            scaled,
            hidden_masks=hidden_masks,
            config=learned_config,
            dense_hidden_reads=dense_hidden_reads,
            hidden_s2_reads=hidden_s2_reads,
            hidden_s2_output_reads=hidden_s2_output_reads,
        )
        random_results = [
            _evaluate_config(
                scaled,
                hidden_masks=hidden_masks,
                config=_random_config(candidate, seed),
                dense_hidden_reads=dense_hidden_reads,
                hidden_s2_reads=hidden_s2_reads,
                hidden_s2_output_reads=hidden_s2_output_reads,
            )
            for seed in seeds
        ]
        not_below_random = sum(
            float(learned["balanced_accuracy"]) >= float(result["balanced_accuracy"])
            for result in random_results
        )
        audit = learned["output_training_audit"]
        joint_gate = (
            float(learned["balanced_accuracy"]) >= 0.98
            and float(learned["coverage"]) >= 0.98
            and int(learned["work"]["network_weight_reads_issued"]) <= 132
            and int(learned["work"]["network_synapse_ops_issued"]) <= 132
            and not_below_random >= 8
            and audit["direct_weight_writes"] == 0
            and audit["threshold_writes"] == 0
            and audit["pruned_output_weights_unchanged"]
        )
        candidates[candidate] = {
            "learned": learned,
            "random": random_results,
            "random_balanced_accuracy_values": [result["balanced_accuracy"] for result in random_results],
            "not_below_random_seeds": not_below_random,
            "selection_audit": selection_audit,
            "joint_gate_pass": joint_gate,
        }
        LOGGER.info(
            "B2.1 model=%s candidate=%s bacc=%.2f reads=%d pass=%s",
            checkpoint.model_id,
            candidate,
            learned["balanced_accuracy"],
            learned["work"]["network_weight_reads_issued"],
            joint_gate,
        )
    recommended = next(
        (candidate for candidate in CANDIDATE_ORDER if candidates[candidate]["joint_gate_pass"]),
        None,
    )
    return {
        "evidence_gain": gain,
        "hidden_masks": list(hidden_masks),
        "baseline": {
            "dense_network_weight_reads": dense["work"]["network_weight_reads_issued"],
            "hidden_s2_network_weight_reads": hidden_s2["work"]["network_weight_reads_issued"],
            "hidden_s2_balanced_accuracy": hidden_s2["balanced_accuracy"],
            "hidden_s2_coverage": hidden_s2["coverage"],
        },
        "candidates": candidates,
        "recommended_candidate": recommended,
        "selection_claim": (
            "redundancy_elimination_not_score_superiority"
            if recommended is not None
            else "no_candidate_passed"
        ),
    }


def run_b21_experiment(*, seeds: Sequence[int]) -> dict[str, object]:
    """运行三模型 B2.1；随机 mask seed 在模型之间完全共享。"""
    if len(seeds) < 10 or len(set(seeds)) != len(seeds):
        raise ValueError("B2.1 requires at least ten distinct seeds")
    checkpoints = (
        build_eneuron_b2_checkpoint(),
        build_pulse_b2_checkpoint(PulseMiniReference),
        build_pulse_b2_checkpoint(PulseMiniL2Reference),
    )
    models = {
        checkpoint.model_id: _run_model(checkpoint, seeds=seeds)
        for checkpoint in checkpoints
    }
    return {
        "schema": "eneuron.local_prune_b21.v1",
        "seeds": list(seeds),
        "models": models,
        "decision": {
            "all_models_joint_gate_pass": all(
                model["recommended_candidate"] is not None
                for model in models.values()
            ),
            "recommended_candidate": "output_2of4",
            "rtl_interface_freeze_allowed": all(
                model["recommended_candidate"] == "output_2of4"
                for model in models.values()
            ),
        },
        "claim_boundary": {
            "synthetic_redundancy_task": True,
            "score_superiority_proven": False,
            "python_issue_counts_only": True,
            "rtl_proven": False,
            "vivado_timing_proven": False,
            "power_savings_proven": False,
            "image_pruning_proven": False,
        },
    }


__all__ = ["CANDIDATE_ORDER", "GateConfig", "run_b21_experiment"]

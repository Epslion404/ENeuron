"""NP3：三模型剪枝—微调闭环、渐进对照和错误符号负对照。

所有分支共享同一个稠密 B2 checkpoint。渐进分支的中间 3:4 只是一张软件
训练 mask；最终仍只调用一次真实 2:4 PRUNE_COMMIT，不放宽 V1 控制器语义。
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from dataclasses import asdict, replace
from typing import Any, Sequence

from local_prune_b2 import (
    CLASS_MASKS,
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
from local_prune_reference import LocalPrune2of4, PruneMode, ScoreMethod
from neuron_sim import ThreeFactorNeuron
from pulse_mini_l2_reference import PulseMiniL2Reference
from pulse_mini_reference import Command, Mode, Opcode, PulseMiniReference


LOGGER = logging.getLogger("local_prune_np3")
MODEL_GAINS = {
    "eneuron": 1,
    "pulse_mini_l": 2,
    "pulse_mini_l2": 1,
}


def _checkpoint_sha256(checkpoint: B2Checkpoint) -> str:
    """绑定父 checkpoint 的权重与完整训练证据账本。"""
    payload = {
        "model_id": checkpoint.model_id,
        "weights": [list(core.weights) for core in checkpoint.cores],
        "ledgers": [
            [asdict(entry) for entry in ledger]
            for ledger in checkpoint.ledgers
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _scale_levels(levels: Sequence[int], gain: int) -> tuple[int, int, int, int]:
    """复用 NP2 冻结的二位饱和编码。"""
    return tuple(min(3, gain * value) for value in levels)  # type: ignore[return-value]


def _replay_controller(checkpoint: B2Checkpoint, group_index: int) -> LocalPrune2of4:
    """从父账本重建一个尚未提交的 S2 控制器。"""
    controller = LocalPrune2of4(score_method=ScoreMethod.S2)
    controller.set_mode(PruneMode.TRAIN)
    for observation_id, entry in enumerate(checkpoint.ledgers[group_index]):
        controller.observe(
            weights=entry.weights_before,
            evidence_levels=entry.evidence_levels,
            modulator=entry.modulator,
            observation_id=observation_id,
        )
    return controller


def _top_mask(utility: Sequence[int], count: int) -> int:
    """按 S2 的 utility、输入编号规则形成软件 top-k mask。"""
    if count not in (2, 3):
        raise ValueError("count must be two or three")
    ranked = sorted(range(4), key=lambda index: (utility[index], -index), reverse=True)
    return sum(1 << index for index in ranked[:count])


def _train_observation(
    *,
    model_id: str,
    core: Any,
    input_mask: int,
    applied_modulator: int,
    stage: str,
):
    """通过真实神经元训练事务产生一次强证据观察。"""
    if model_id == "eneuron":
        return _train_eneuron_observation(
            core,
            input_mask=input_mask,
            modulator=applied_modulator,
            strong=True,
            phase=stage,
        )
    return _train_pulse_observation(
        core,
        input_mask=input_mask,
        modulator=applied_modulator,
        strong=True,
        phase=stage,
    )


def _learning_state(core: Any, model_id: str) -> tuple[object, ...]:
    """返回推理期间必须冻结的核心学习状态。"""
    if model_id == "eneuron":
        return (
            tuple(core.weights),
            tuple(core.pre_trace),
            core.post_trace,
            tuple(core.eligibility),
            core.threshold,
        )
    return (
        tuple(core.weights),
        tuple(core.pre_age),
        core.post_age,
        tuple(core.positive_evidence),
        tuple(core.negative_evidence),
        tuple(core.captured_direction),
        core.pending_valid,
    )


def _prepare_infer_core(core: Any, model_id: str) -> None:
    """清除动态 trial 状态并切换到冻结推理。"""
    if model_id == "eneuron":
        core.reset_episode()
        return
    _pulse_execute(core, Command(Opcode.MODE_SET, int(Mode.INFER)))
    _pulse_execute(core, Command(Opcode.STATE_CLEAR))


def _infer_freeze_probe(
    *,
    model_id: str,
    cores: Sequence[Any],
    controllers: Sequence[LocalPrune2of4],
    masks: Sequence[int],
) -> bool:
    """在同一批活动核心上运行数据集，证明学习与结构指纹不变。"""
    for core in cores:
        _prepare_infer_core(core, model_id)
    before = (
        tuple(_learning_state(core, model_id) for core in cores),
        tuple((tuple(controller.utility), controller.mask_read(log_event=False), controller.mask_valid) for controller in controllers),
    )
    for sample in build_b2_dataset():
        for core in cores:
            _prepare_infer_core(core, model_id)
        for tick, input_mask in enumerate((sample.input_mask, 0, 0)):
            for core, mask in zip(cores, masks):
                active_mask = input_mask & mask
                if model_id == "eneuron":
                    core.step(_indices(active_mask), tick, learn_enable=False)
                else:
                    _pulse_execute(core, Command(Opcode.TICK, active_mask, 0))
    after = (
        tuple(_learning_state(core, model_id) for core in cores),
        tuple((tuple(controller.utility), controller.mask_read(log_event=False), controller.mask_valid) for controller in controllers),
    )
    return before == after


def _pruned_history_is_zero(core: Any, model_id: str, mask: int) -> bool:
    """确认最终关闭的输入没有残留可继续学习的局部历史。"""
    pruned = [index for index in range(4) if not mask & (1 << index)]
    if model_id == "eneuron":
        return all(core.pre_trace[index] == 0 and core.eligibility[index] == 0 for index in pruned)
    return all(
        core.positive_evidence[index] == 0
        and core.negative_evidence[index] == 0
        and core.captured_direction[index] == 0
        for index in pruned
    )


def _metric_summary(checkpoint: B2Checkpoint, masks: Sequence[int]) -> dict[str, object]:
    """只保留 NP3 决策所需的精度、coverage 和工作量。"""
    result = _evaluate_branch(checkpoint, masks)
    return {
        "balanced_accuracy": result["balanced_accuracy"],
        "coverage": result["coverage"],
        "network_weight_reads_issued": result["work"]["network_weight_reads_issued"],
        "network_synapse_ops_issued": result["work"]["network_synapse_ops_issued"],
    }


def _run_branch(
    checkpoint: B2Checkpoint,
    *,
    gain: int,
    branch_name: str,
) -> dict[str, object]:
    """运行一个公平的两次微调分支并输出逐事务账本。"""
    if branch_name not in ("S2_one_shot", "S2_progressive", "S2_wrong_sign"):
        raise ValueError("unknown NP3 branch")
    parent_hash = _checkpoint_sha256(checkpoint)
    cores = list(copy.deepcopy(checkpoint.cores))
    controllers = [_replay_controller(checkpoint, index) for index in range(8)]
    stage1_masks: list[int] = []
    final_masks: list[int] = []
    ledger: list[dict[str, object]] = []
    parent_weights = [tuple(core.weights) for core in checkpoint.cores]

    if branch_name == "S2_progressive":
        stage1_masks = [_top_mask(controller.utility, 3) for controller in controllers]
    else:
        for core, controller in zip(cores, controllers):
            final_masks.append(controller.prune_commit(weights=core.weights, commit_id=1).mask)

    immediate_checkpoint = replace(checkpoint, cores=tuple(copy.deepcopy(cores)))
    immediate_masks = stage1_masks if branch_name == "S2_progressive" else final_masks
    immediate = _metric_summary(immediate_checkpoint, immediate_masks)
    stage1_after_fine_tune: dict[str, object] | None = None

    for fine_step in range(2):
        progressive_stage1 = branch_name == "S2_progressive" and fine_step == 0
        training_masks = stage1_masks if progressive_stage1 else final_masks
        if not training_masks:
            raise AssertionError("final 2:4 mask must exist before final fine-tune")
        for index, (core, controller, training_mask) in enumerate(zip(cores, controllers, training_masks)):
            expected_modulator = 1
            applied_modulator = -1 if branch_name == "S2_wrong_sign" else 1
            input_mask = CLASS_MASKS[index // 4] & training_mask
            weights_before = tuple(core.weights)
            utility_before = tuple(controller.utility)
            mask_before = controller.mask_read(log_event=False)
            mask_valid_before = controller.mask_valid
            evidence = _train_observation(
                model_id=checkpoint.model_id,
                core=core,
                input_mask=input_mask,
                applied_modulator=applied_modulator,
                stage="progressive_3of4" if progressive_stage1 else "sparse_fine_tune",
            )
            evidence_levels = _scale_levels(evidence.evidence_levels, gain)
            controller.observe(
                weights=evidence.weights_before,
                evidence_levels=evidence_levels,
                modulator=applied_modulator,
                observation_id=len(checkpoint.ledgers[index]) + fine_step,
            )
            ledger.append({
                "model_id": checkpoint.model_id,
                "branch": branch_name,
                "stage": "progressive_3of4" if progressive_stage1 else "sparse_fine_tune",
                "detector": index,
                "observation_id": len(checkpoint.ledgers[index]) + fine_step,
                "input_mask": input_mask,
                "training_mask": training_mask,
                "expected_modulator": expected_modulator,
                "applied_modulator": applied_modulator,
                "evidence_levels": list(evidence_levels),
                "weights_before": list(weights_before),
                "weights_after": list(core.weights),
                "utility_before": list(utility_before),
                "utility_after": list(controller.utility),
                "mask_before": mask_before,
                "mask_after": controller.mask_read(log_event=False),
                "mask_valid_before": mask_valid_before,
                "mask_valid_after": controller.mask_valid,
            })

        if progressive_stage1:
            stage1_checkpoint = replace(checkpoint, cores=tuple(copy.deepcopy(cores)))
            stage1_after_fine_tune = _metric_summary(stage1_checkpoint, stage1_masks)
            for core, controller in zip(cores, controllers):
                final_masks.append(controller.prune_commit(weights=core.weights, commit_id=1).mask)

    branch_checkpoint = replace(checkpoint, cores=tuple(cores))
    after_fine_tune = _metric_summary(branch_checkpoint, final_masks)
    pruned_weights_unchanged = all(
        core.weights[index] == parent_weights[group][index]
        for group, (core, mask) in enumerate(zip(cores, final_masks))
        for index in range(4)
        if not mask & (1 << index)
    )
    mask_stable = all(
        entry["mask_before"] == entry["mask_after"]
        for entry in ledger
        if entry["mask_valid_before"]
    )
    history_zero = all(
        _pruned_history_is_zero(core, checkpoint.model_id, mask)
        for core, mask in zip(cores, final_masks)
    )
    infer_freeze = _infer_freeze_probe(
        model_id=checkpoint.model_id,
        cores=cores,
        controllers=controllers,
        masks=final_masks,
    )
    LOGGER.info(
        "NP3 model=%s branch=%s bacc=%.2f",
        checkpoint.model_id,
        branch_name,
        after_fine_tune["balanced_accuracy"],
    )
    return {
        "parent_checkpoint_sha256": parent_hash,
        "stage1_kind": "software_3of4_training_mask" if stage1_masks else None,
        "stage1_masks": stage1_masks,
        "final_masks": final_masks,
        "fine_tune_observations_per_detector": 2,
        "immediate": immediate,
        "stage1_after_fine_tune": stage1_after_fine_tune,
        "after_fine_tune": after_fine_tune,
        "training_ledger": ledger,
        "mask_write_count": 0,
        "prune_commit_counts": [controller.mask_commits for controller in controllers],
        "mask_stable_during_fine_tune": mask_stable,
        "pruned_weights_unchanged": pruned_weights_unchanged,
        "pruned_history_zero": history_zero,
        "infer_freeze_pass": infer_freeze,
    }


def run_np3_experiment() -> dict[str, object]:
    """运行三模型、三分支的确定性 NP3 软件闭环。"""
    checkpoints = (
        build_eneuron_b2_checkpoint(),
        build_pulse_b2_checkpoint(PulseMiniReference),
        build_pulse_b2_checkpoint(PulseMiniL2Reference),
    )
    models: dict[str, object] = {}
    for raw_checkpoint in checkpoints:
        gain = MODEL_GAINS[raw_checkpoint.model_id]
        scaled_ledgers = tuple(
            tuple(replace(entry, evidence_levels=_scale_levels(entry.evidence_levels, gain)) for entry in ledger)
            for ledger in raw_checkpoint.ledgers
        )
        checkpoint = replace(raw_checkpoint, ledgers=scaled_ledgers)
        models[checkpoint.model_id] = {
            "evidence_gain": gain,
            "parent_checkpoint_sha256": _checkpoint_sha256(checkpoint),
            "branches": {
                branch_name: _run_branch(checkpoint, gain=gain, branch_name=branch_name)
                for branch_name in ("S2_one_shot", "S2_progressive", "S2_wrong_sign")
            },
        }
    return {
        "schema": "eneuron.local_prune_np3.v1",
        "models": models,
        "branch_contract": {
            "shared_parent_checkpoint": True,
            "fine_tune_observations_per_detector": 2,
            "progressive_stage1_is_software_only": True,
            "real_prune_commits_per_detector": 1,
            "host_mask_writes": 0,
        },
        "claim_boundary": {
            "software_training_closure": True,
            "rtl_proven": False,
            "system_work_gate_proven": False,
            "image_pruning_proven": False,
        },
    }


__all__ = ["MODEL_GAINS", "run_np3_experiment"]

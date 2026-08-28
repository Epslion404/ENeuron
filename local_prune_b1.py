"""三种神经元 B1 剪枝实验共用的最小公平性工具。"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Sequence


class B1Variant(Enum):
    DENSE = "dense"
    RANDOM = "random"
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"


@dataclass(frozen=True)
class BinaryMetrics:
    correct: int
    covered: int
    total: int
    accuracy: float
    coverage: float
    balanced_accuracy: float


def strict_single_active(scores: Sequence[int]) -> int | None:
    """只有一个输出曾发放时才解码；零输出和多输出均弃权。"""
    if len(scores) != 2:
        raise ValueError("B1 decoder requires exactly two output counts")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in scores):
        raise ValueError("output counts must be non-negative integers")
    active = [index for index, value in enumerate(scores) if value > 0]
    return active[0] if len(active) == 1 else None


def score_binary_outputs(
    *,
    labels: Sequence[int],
    scores: Sequence[Sequence[int]],
) -> BinaryMetrics:
    """按固定二分类标签计算准确率、覆盖率和 balanced accuracy。"""
    if len(labels) != len(scores) or not labels:
        raise ValueError("labels and scores must have the same non-zero length")
    if any(label not in (0, 1) for label in labels):
        raise ValueError("B1 labels must be 0 or 1")
    predictions = [strict_single_active(value) for value in scores]
    correct = sum(int(prediction == label) for prediction, label in zip(predictions, labels))
    covered = sum(prediction is not None for prediction in predictions)
    recalls: list[float] = []
    for label in (0, 1):
        positions = [index for index, value in enumerate(labels) if value == label]
        if not positions:
            raise ValueError("both B1 labels must be present")
        recalls.append(sum(predictions[index] == label for index in positions) / len(positions))
    total = len(labels)
    return BinaryMetrics(
        correct=correct,
        covered=covered,
        total=total,
        accuracy=correct / total,
        coverage=covered / total,
        balanced_accuracy=sum(recalls) / 2,
    )


def exact_two_random_masks(*, seed: int, count: int) -> tuple[int, ...]:
    """产生确定性的神经元本地随机 2:4 负对照掩码。"""
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise TypeError("seed must be an integer")
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError("count must be a positive integer")
    legal_masks = (0b0011, 0b0101, 0b1001, 0b0110, 0b1010, 0b1100)
    rng = random.Random(seed)
    return tuple(rng.choice(legal_masks) for _ in range(count))


def _evaluate_pulse_adapter(adapter: Any) -> tuple[BinaryMetrics, bool]:
    """用公共 20 样本和统一严格解码评价一个 Pulse 分支。"""
    from compare_simulation import make_shared_network_evaluation_data

    samples = make_shared_network_evaluation_data()
    labels = tuple(label for _, label, _, _ in samples)
    before = adapter.learning_fingerprint()
    scores = tuple(adapter.infer_counts(events) for events, _, _, _ in samples)
    frozen = before == adapter.learning_fingerprint()
    return score_binary_outputs(labels=labels, scores=scores), frozen


def _counter_delta(after: dict[str, Any], before: dict[str, Any]) -> dict[str, Any]:
    """对同一 scope 的整数工作量计数做阶段差分。"""
    if after["scope"] != before["scope"]:
        raise AssertionError("work counter scope changed within one branch")
    return {
        "scope": after["scope"],
        **{
            key: after[key] - before[key]
            for key in after
            if key != "scope"
        },
    }


def run_pulse_b1(
    *,
    model_id: str,
    core_type: type[Any],
    seed: int,
    warmup_repetitions: int = 6,
    fine_tune_repetitions: int = 2,
) -> dict[str, object]:
    """从一个稠密检查点公平分支 Pulse-L/L2 的六种 B1 对照。"""
    from local_prune_reference import ScoreMethod
    from pulse_prune_adapter import PulsePruneAdapter

    warmup = PulsePruneAdapter(core_type=core_type)
    warmup.train_p8(repetitions=warmup_repetitions, phase="warmup")
    parent_checkpoint = warmup.checkpoint_sha256()
    score_methods = {
        B1Variant.S0: ScoreMethod.S0,
        B1Variant.S1: ScoreMethod.S1,
        B1Variant.S2: ScoreMethod.S2,
        B1Variant.S3: ScoreMethod.S3,
    }
    branches: dict[str, dict[str, object]] = {}
    for variant in B1Variant:
        method = score_methods.get(variant, ScoreMethod.S0)
        adapter = warmup.branch(score_method=method)
        if adapter.parent_checkpoint_sha256 != parent_checkpoint:
            raise AssertionError("Pulse B1 branches do not share one warm-up checkpoint")

        if variant is B1Variant.RANDOM:
            masks = adapter.install_random_masks(exact_two_random_masks(seed=seed + 1009, count=2))
            mask_source = "random_config_control"
        elif variant in score_methods:
            masks = adapter.prune_score(commit_id=1)
            mask_source = method.name
        else:
            masks = (0b1111, 0b1111)
            mask_source = "dense"

        work_start = adapter.work_counters()
        immediate_metrics, immediate_frozen = _evaluate_pulse_adapter(adapter)
        work_after_immediate = adapter.work_counters()
        adapter.train_p8(repetitions=fine_tune_repetitions, phase="finetune")
        work_after_finetune = adapter.work_counters()
        final_metrics, final_frozen = _evaluate_pulse_adapter(adapter)
        work_final = adapter.work_counters()
        snapshot = adapter.snapshot()
        branches[variant.value] = {
            "variant": variant.value,
            "score_method": None if variant in (B1Variant.DENSE, B1Variant.RANDOM) else method.name,
            "mask_source": mask_source,
            "masks": list(masks),
            "parent_checkpoint_sha256": adapter.parent_checkpoint_sha256,
            "immediate_metrics": asdict(immediate_metrics),
            "final_metrics": asdict(final_metrics),
            "inference_learning_state_frozen": immediate_frozen and final_frozen,
            "work_by_stage": {
                "immediate_infer": _counter_delta(work_after_immediate, work_start),
                "fine_tune": _counter_delta(work_after_finetune, work_after_immediate),
                "final_infer": _counter_delta(work_final, work_after_finetune),
                "total": _counter_delta(work_final, work_start),
            },
            "snapshot": snapshot,
        }

    return {
        "schema": "eneuron.local_prune_b1.v1",
        "model_id": model_id,
        "core_type": core_type.__name__,
        "seed": seed,
        "warmup_repetitions": warmup_repetitions,
        "fine_tune_repetitions": fine_tune_repetitions,
        "evaluation_samples": 20,
        "decoder_id": "strict_single_active_v1",
        "training_schedule_id": "pulse_p8_hidden_then_output_v1",
        "quantizer_id": (
            "pulse_l2_abs_captured_direction_0_2_v1"
            if core_type.__name__ == "PulseMiniL2Reference"
            else "pulse_l_abs_captured_direction_0_1_v1"
        ),
        "parent_checkpoint_sha256": parent_checkpoint,
        "branches": branches,
    }


def _train_eneuron_adapter(
    adapter: Any,
    *,
    epochs: int,
    seed: int,
    start_commit_id: int,
) -> int:
    """按固定共同数据和确定性顺序推进 ENeuron teacher 事务。"""
    from compare_simulation import make_shared_network_training_data
    from network_sim import HostTrainingController

    if epochs < 0:
        raise ValueError("epochs must not be negative")
    dataset = make_shared_network_training_data()
    rng = random.Random(seed)
    commit_id = start_commit_id
    for _ in range(epochs):
        order = list(range(len(dataset)))
        rng.shuffle(order)
        for index in order:
            events, label = dataset[index]
            hidden_modulator, output_modulator = HostTrainingController.teacher_modulator(label)
            adapter.train_sample(
                events,
                label=label,
                hidden_modulator=hidden_modulator,
                output_modulator=output_modulator,
                commit_id=commit_id,
            )
            commit_id += 1
    return commit_id


def _evaluate_eneuron_adapter(adapter: Any) -> tuple[BinaryMetrics, bool]:
    from compare_simulation import make_shared_network_evaluation_data

    samples = make_shared_network_evaluation_data()
    labels = tuple(label for _, label, _, _ in samples)
    before = adapter.learning_fingerprint()
    scores = tuple(
        adapter.run_sample(events, label=label, train=False).episode.output_spikes
        for events, label, _, _ in samples
    )
    frozen = before == adapter.learning_fingerprint()
    return score_binary_outputs(labels=labels, scores=scores), frozen


def run_eneuron_b1(
    *,
    seed: int,
    warmup_epochs: int = 30,
    fine_tune_epochs: int = 5,
) -> dict[str, object]:
    """从一个 ENeuron 稠密检查点公平分支六种 B1 对照。"""
    from eneuron_prune_adapter import ENeuronB1PruneAdapter
    from local_prune_reference import ScoreMethod

    warmup = ENeuronB1PruneAdapter(score_method=ScoreMethod.S0, init_seed=seed)
    next_commit_id = _train_eneuron_adapter(
        warmup,
        epochs=warmup_epochs,
        seed=seed,
        start_commit_id=0,
    )
    parent_checkpoint = warmup.checkpoint_sha256()
    score_methods = {
        B1Variant.S0: ScoreMethod.S0,
        B1Variant.S1: ScoreMethod.S1,
        B1Variant.S2: ScoreMethod.S2,
        B1Variant.S3: ScoreMethod.S3,
    }
    random_masks = exact_two_random_masks(seed=seed + 1009, count=2)
    branches: dict[str, dict[str, object]] = {}
    for variant in B1Variant:
        method = score_methods.get(variant, ScoreMethod.S0)
        if variant is B1Variant.RANDOM:
            adapter = warmup.mask_branch(random_masks)
            masks = random_masks
            mask_source = "random_config_control"
        else:
            adapter = warmup.branch_for_score(method)
            if variant in score_methods:
                masks = tuple(result.mask for result in adapter.prune_hidden(commit_id=1))
                mask_source = method.name
            else:
                masks = (0b1111, 0b1111)
                mask_source = "dense"

        work_start = adapter.work_counters()
        immediate_metrics, immediate_frozen = _evaluate_eneuron_adapter(adapter)
        work_after_immediate = adapter.work_counters()
        _train_eneuron_adapter(
            adapter,
            epochs=fine_tune_epochs,
            seed=seed + 1,
            start_commit_id=next_commit_id,
        )
        work_after_finetune = adapter.work_counters()
        final_metrics, final_frozen = _evaluate_eneuron_adapter(adapter)
        work_final = adapter.work_counters()
        branches[variant.value] = {
            "variant": variant.value,
            "score_method": None if variant in (B1Variant.DENSE, B1Variant.RANDOM) else method.name,
            "mask_source": mask_source,
            "masks": list(masks),
            "parent_checkpoint_sha256": parent_checkpoint,
            "immediate_metrics": asdict(immediate_metrics),
            "final_metrics": asdict(final_metrics),
            "inference_learning_state_frozen": immediate_frozen and final_frozen,
            "work_by_stage": {
                "immediate_infer": _counter_delta(work_after_immediate, work_start),
                "fine_tune": _counter_delta(work_after_finetune, work_after_immediate),
                "final_infer": _counter_delta(work_final, work_after_finetune),
                "total": _counter_delta(work_final, work_start),
            },
            "snapshot": adapter.snapshot(),
        }

    return {
        "schema": "eneuron.local_prune_b1.v1",
        "model_id": "eneuron",
        "seed": seed,
        "warmup_epochs": warmup_epochs,
        "fine_tune_epochs": fine_tune_epochs,
        "evaluation_samples": 20,
        "decoder_id": "strict_single_active_v1",
        "quantizer_id": "eneuron_abs_eligibility_ceil16_sat3_v1",
        "training_schedule_id": "eneuron_teacher_all_neurons_per_sample_v1",
        "parent_checkpoint_sha256": parent_checkpoint,
        "branches": branches,
    }


__all__ = [
    "B1Variant",
    "BinaryMetrics",
    "exact_two_random_masks",
    "run_eneuron_b1",
    "run_pulse_b1",
    "score_binary_outputs",
    "strict_single_active",
]

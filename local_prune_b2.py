"""B2：能区分局部评分策略的 4→8→2 冗余 detector 压力任务。"""

from __future__ import annotations

import copy
import random
import statistics
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from local_prune_b1 import exact_two_random_masks, score_binary_outputs
from local_prune_reference import LocalPrune2of4, PruneMode, ScoreMethod
from neuron_sim import ThreeFactorNeuron
from pulse_mini_reference import Command, Mode, Opcode, PulseMiniReference, Status


CLASS_MASKS = (0b0101, 0b1010)
N_DETECTORS_PER_CLASS = 4


@dataclass(frozen=True)
class B2Sample:
    sample_id: str
    label: int
    input_mask: int


@dataclass(frozen=True)
class B2Evidence:
    phase: str
    weights_before: tuple[int, int, int, int]
    evidence_levels: tuple[int, int, int, int]
    modulator: int


@dataclass(frozen=True)
class B2Checkpoint:
    model_id: str
    cores: tuple[Any, ...]
    ledgers: tuple[tuple[B2Evidence, ...], ...]


def build_b2_dataset() -> tuple[B2Sample, ...]:
    """两个类别各十个样本，交替只保留互补信息对中的一个通道。"""
    samples: list[B2Sample] = []
    for label, channels in ((0, (0, 2)), (1, (1, 3))):
        for index in range(10):
            channel = channels[index % 2]
            samples.append(B2Sample(f"c{label}_{index:02d}", label, 1 << channel))
    return tuple(samples)


def _indices(mask: int) -> tuple[int, ...]:
    return tuple(index for index in range(4) if mask & (1 << index))


def _quantize_eneuron(values: Sequence[int]) -> tuple[int, int, int, int]:
    return tuple(min(3, (abs(value) + 15) // 16) for value in values)  # type: ignore[return-value]


def _train_eneuron_observation(
    core: ThreeFactorNeuron,
    *,
    input_mask: int,
    modulator: int,
    strong: bool,
    phase: str,
) -> B2Evidence:
    core.reset_episode()
    active = _indices(input_mask)
    schedule = (active, (), active, (), active) if strong else (active,)
    for tick, tick_active in enumerate(schedule):
        core.step(tick_active, tick, learn_enable=True)
    eligibility = tuple(core.eligibility)
    weights_before = tuple(core.weights)
    levels = _quantize_eneuron(eligibility)
    core.apply_modulator_from_eligibility(eligibility, modulator)
    return B2Evidence(phase, weights_before, levels, modulator)


def build_eneuron_b2_checkpoint() -> B2Checkpoint:
    """构造八个实际 ENeuron detector，并保留完整本地观察账本。"""
    cores: list[ThreeFactorNeuron] = []
    ledgers: list[tuple[B2Evidence, ...]] = []
    for detector_index in range(8):
        label = detector_index // N_DETECTORS_PER_CLASS
        informative = CLASS_MASKS[label]
        distractor = CLASS_MASKS[1 - label]
        core = ThreeFactorNeuron(4)
        core.weights = [0, 0, 0, 0]
        entries: list[B2Evidence] = []
        for channel in range(4):
            sign = 1 if informative & (1 << channel) else -1
            for _ in range(4):
                entries.append(_train_eneuron_observation(
                    core,
                    input_mask=1 << channel,
                    modulator=sign,
                    strong=False,
                    phase="saturate",
                ))
        for _ in range(6):
            entries.append(_train_eneuron_observation(
                core,
                input_mask=informative,
                modulator=1,
                strong=True,
                phase="stable",
            ))
        entries.append(_train_eneuron_observation(
            core,
            input_mask=distractor,
            modulator=-1,
            strong=False,
            phase="mislead",
        ))
        cores.append(core)
        ledgers.append(tuple(entries))
    return B2Checkpoint("eneuron", tuple(cores), tuple(ledgers))


def _pulse_execute(core: PulseMiniReference, command: Command) -> None:
    response = core.execute(command)
    if response.status is not Status.OK:
        raise RuntimeError(f"Pulse B2 command {command.opcode} failed: {response.status.name}")


def _train_pulse_observation(
    core: PulseMiniReference,
    *,
    input_mask: int,
    modulator: int,
    strong: bool,
    phase: str,
) -> B2Evidence:
    _pulse_execute(core, Command(Opcode.STATE_CLEAR))
    _pulse_execute(core, Command(Opcode.TICK, input_mask, 0))
    _pulse_execute(core, Command(Opcode.TICK, 0, 1))
    if strong:
        for _ in range(3):
            _pulse_execute(core, Command(Opcode.TICK, 0, 0))
        _pulse_execute(core, Command(Opcode.TICK, input_mask, 0))
        _pulse_execute(core, Command(Opcode.TICK, 0, 1))
    _pulse_execute(core, Command(Opcode.CAPTURE))
    raw = tuple(core.captured_direction)
    weights_before = tuple(core.weights)
    feedback_code = 1 if modulator > 0 else 3
    _pulse_execute(core, Command(Opcode.FEEDBACK, feedback_code))
    return B2Evidence(
        phase,
        weights_before,  # type: ignore[arg-type]
        tuple(abs(value) for value in raw),  # type: ignore[arg-type]
        modulator,
    )


def build_pulse_b2_checkpoint(
    core_type: type[PulseMiniReference],
) -> B2Checkpoint:
    """用相同训练事务构造 Pulse-Mini-L 或 L2 detector bank。"""
    cores: list[PulseMiniReference] = []
    ledgers: list[tuple[B2Evidence, ...]] = []
    for detector_index in range(8):
        label = detector_index // N_DETECTORS_PER_CLASS
        informative = CLASS_MASKS[label]
        distractor = CLASS_MASKS[1 - label]
        core = core_type()
        _pulse_execute(core, Command(Opcode.MODE_SET, int(Mode.TRAIN)))
        entries: list[B2Evidence] = []
        for channel in range(4):
            sign = 1 if informative & (1 << channel) else -1
            for _ in range(7):
                entries.append(_train_pulse_observation(
                    core,
                    input_mask=1 << channel,
                    modulator=sign,
                    strong=False,
                    phase="saturate",
                ))
        for _ in range(6):
            entries.append(_train_pulse_observation(
                core,
                input_mask=informative,
                modulator=1,
                strong=True,
                phase="stable",
            ))
        entries.append(_train_pulse_observation(
            core,
            input_mask=distractor,
            modulator=-1,
            strong=False,
            phase="mislead",
        ))
        cores.append(core)
        ledgers.append(tuple(entries))
    model_id = "pulse_mini_l2" if core_type.__name__ == "PulseMiniL2Reference" else "pulse_mini_l"
    return B2Checkpoint(model_id, tuple(cores), tuple(ledgers))


def _score_masks(
    checkpoint: B2Checkpoint,
    method: ScoreMethod,
    *,
    phases: set[str] | None = None,
    shuffle_seed: int | None = None,
) -> tuple[int, ...]:
    masks: list[int] = []
    for detector_index, (core, ledger) in enumerate(zip(checkpoint.cores, checkpoint.ledgers)):
        controller = LocalPrune2of4(score_method=method)
        controller.set_mode(PruneMode.TRAIN)
        selected_ledger = [entry for entry in ledger if phases is None or entry.phase in phases]
        for observation_id, entry in enumerate(selected_ledger):
            evidence_levels = entry.evidence_levels
            if shuffle_seed is not None:
                rng = random.Random(shuffle_seed * 1009 + detector_index * 131 + observation_id)
                order = list(range(4))
                rng.shuffle(order)
                evidence_levels = tuple(entry.evidence_levels[index] for index in order)  # type: ignore[assignment]
            controller.observe(
                weights=entry.weights_before,
                evidence_levels=evidence_levels,
                modulator=entry.modulator,
                observation_id=observation_id,
            )
        masks.append(controller.prune_commit(weights=core.weights, commit_id=1).mask)
    return tuple(masks)


def _infer_eneuron(
    checkpoint: B2Checkpoint,
    masks: Sequence[int],
    sample: B2Sample,
) -> tuple[tuple[int, int], int, int]:
    detectors = copy.deepcopy(checkpoint.cores)
    outputs = [ThreeFactorNeuron(4), ThreeFactorNeuron(4)]
    for output in outputs:
        # 每个 detector 贡献 2，阈值 6，因此至少需要 3/4 冗余路径同时响应。
        output.weights = [2, 2, 2, 2]
    for core in (*detectors, *outputs):
        core.reset_episode()
    pending = ((), ())
    counts = [0, 0]
    hidden_reads = 0
    output_reads = 0
    for tick, input_mask in enumerate((sample.input_mask, 0, 0)):
        for label, output in enumerate(outputs):
            output_reads += len(pending[label])
            counts[label] += output.step(pending[label], tick, learn_enable=False)
        fired_by_class = [[], []]
        for index, (core, structural_mask) in enumerate(zip(detectors, masks)):
            active = _indices(input_mask & structural_mask)
            hidden_reads += len(active)
            fired = core.step(active, tick, learn_enable=False)
            if fired:
                label = index // N_DETECTORS_PER_CLASS
                fired_by_class[label].append(index % N_DETECTORS_PER_CLASS)
        pending = tuple(tuple(values) for values in fired_by_class)  # type: ignore[assignment]
    for label, output in enumerate(outputs):
        output_reads += len(pending[label])
        counts[label] += output.step(pending[label], 3, learn_enable=False)
    return (counts[0], counts[1]), hidden_reads, output_reads


def _infer_pulse(
    checkpoint: B2Checkpoint,
    masks: Sequence[int],
    sample: B2Sample,
) -> tuple[tuple[int, int], int, int]:
    detectors = copy.deepcopy(checkpoint.cores)
    core_type = type(detectors[0])
    outputs = [core_type(initial_weights=(2, 2, 2, 2)), core_type(initial_weights=(2, 2, 2, 2))]
    for core in (*detectors, *outputs):
        if core.pending_valid:
            raise AssertionError("checkpoint contains pending Pulse evidence")
        _pulse_execute(core, Command(Opcode.MODE_SET, int(Mode.INFER)))
        _pulse_execute(core, Command(Opcode.STATE_CLEAR))
    pending = (0, 0)
    counts = [0, 0]
    hidden_reads = 0
    output_reads = 0
    for input_mask in (sample.input_mask, 0, 0):
        for label, output in enumerate(outputs):
            output_reads += pending[label].bit_count()
            response = output.execute(Command(Opcode.TICK, pending[label], 0))
            if response.status is not Status.OK:
                raise RuntimeError("Pulse B2 output tick failed")
            counts[label] += response.spike
        next_pending = [0, 0]
        for index, (core, structural_mask) in enumerate(zip(detectors, masks)):
            hidden_reads += (input_mask & structural_mask).bit_count()
            response = core.execute(Command(Opcode.TICK, input_mask & structural_mask, 0))
            if response.status is not Status.OK:
                raise RuntimeError("Pulse B2 detector tick failed")
            if response.spike:
                label = index // N_DETECTORS_PER_CLASS
                next_pending[label] |= 1 << (index % N_DETECTORS_PER_CLASS)
        pending = next_pending[0], next_pending[1]
    for label, output in enumerate(outputs):
        output_reads += pending[label].bit_count()
        response = output.execute(Command(Opcode.TICK, pending[label], 0))
        if response.status is not Status.OK:
            raise RuntimeError("Pulse B2 route flush failed")
        counts[label] += response.spike
    return (counts[0], counts[1]), hidden_reads, output_reads


def _evaluate_branch(
    checkpoint: B2Checkpoint,
    masks: Sequence[int],
) -> dict[str, object]:
    samples = build_b2_dataset()
    infer = _infer_eneuron if checkpoint.model_id == "eneuron" else _infer_pulse
    inference = tuple(infer(checkpoint, masks, sample) for sample in samples)
    scores = tuple(value[0] for value in inference)
    metrics = score_binary_outputs(
        labels=tuple(sample.label for sample in samples),
        scores=scores,
    )
    return {
        **asdict(metrics),
        "masks": list(masks),
        "work": {
            "scope": "full_4x8x2_hidden_structural_output_dense",
            "hidden_weight_reads_issued": sum(value[1] for value in inference),
            "output_weight_reads_issued": sum(value[2] for value in inference),
            "network_weight_reads_issued": sum(value[1] + value[2] for value in inference),
            "network_synapse_ops_issued": sum(value[1] + value[2] for value in inference),
        },
    }


def _run_checkpoint(
    checkpoint: B2Checkpoint,
    *,
    random_masks: Sequence[int],
    control_seed: int,
) -> dict[str, dict[str, object]]:
    branches: dict[str, dict[str, object]] = {
        "dense": _evaluate_branch(checkpoint, (0b1111,) * 8),
        "random": _evaluate_branch(checkpoint, random_masks),
    }
    for method in ScoreMethod:
        branches[method.name] = _evaluate_branch(checkpoint, _score_masks(checkpoint, method))
    branches["S2_early"] = _evaluate_branch(
        checkpoint,
        _score_masks(checkpoint, ScoreMethod.S2, phases={"saturate"}),
    )
    branches["S2_shuffled"] = _evaluate_branch(
        checkpoint,
        _score_masks(checkpoint, ScoreMethod.S2, shuffle_seed=control_seed),
    )
    return branches


def _checkpoints() -> tuple[B2Checkpoint, ...]:
    from pulse_mini_l2_reference import PulseMiniL2Reference

    return (
        build_eneuron_b2_checkpoint(),
        build_pulse_b2_checkpoint(PulseMiniReference),
        build_pulse_b2_checkpoint(PulseMiniL2Reference),
    )


def run_b2_seed(*, seed: int) -> dict[str, dict[str, dict[str, object]]]:
    """三模型使用同一组随机 mask，评分分支完全确定。"""
    random_masks = exact_two_random_masks(seed=seed + 2003, count=8)
    checkpoints = _checkpoints()
    return {
        checkpoint.model_id: _run_checkpoint(
            checkpoint,
            random_masks=random_masks,
            control_seed=seed,
        )
        for checkpoint in checkpoints
    }


def run_b2_matrix(*, seeds: Sequence[int]) -> dict[str, object]:
    """复用三模型 checkpoint 运行至少十个随机/打乱对照 seed。"""
    if len(seeds) < 10 or len(set(seeds)) != len(seeds):
        raise ValueError("B2 requires at least ten distinct seeds")
    checkpoints = _checkpoints()
    per_seed: list[dict[str, object]] = []
    for seed in seeds:
        random_masks = exact_two_random_masks(seed=seed + 2003, count=8)
        per_seed.append({
            "seed": seed,
            "models": {
                checkpoint.model_id: _run_checkpoint(
                    checkpoint,
                    random_masks=random_masks,
                    control_seed=seed,
                )
                for checkpoint in checkpoints
            },
        })

    branch_names = ("dense", "random", "S0", "S1", "S2", "S3", "S2_early", "S2_shuffled")
    summary: dict[str, dict[str, object]] = {}
    for checkpoint in checkpoints:
        model_summary: dict[str, object] = {}
        for branch in branch_names:
            accuracies = [
                row["models"][checkpoint.model_id][branch]["balanced_accuracy"]  # type: ignore[index]
                for row in per_seed
            ]
            coverages = [
                row["models"][checkpoint.model_id][branch]["coverage"]  # type: ignore[index]
                for row in per_seed
            ]
            model_summary[branch] = {
                "median_balanced_accuracy": statistics.median(accuracies),
                "min_balanced_accuracy": min(accuracies),
                "max_balanced_accuracy": max(accuracies),
                "values": accuracies,
                "median_coverage": statistics.median(coverages),
                "min_coverage": min(coverages),
                "max_coverage": max(coverages),
                "coverage_values": coverages,
            }
        s2_values = model_summary["S2"]["values"]  # type: ignore[index]
        random_values = model_summary["random"]["values"]  # type: ignore[index]
        s0_values = model_summary["S0"]["values"]  # type: ignore[index]
        model_summary["gates"] = {
            "s2_minus_random_median_pp": 100 * (
                model_summary["S2"]["median_balanced_accuracy"]  # type: ignore[index]
                - model_summary["random"]["median_balanced_accuracy"]  # type: ignore[index]
            ),
            "s2_not_below_random_seeds": sum(a >= b for a, b in zip(s2_values, random_values)),
            "s2_minus_s0_median_pp": 100 * (
                model_summary["S2"]["median_balanced_accuracy"]  # type: ignore[index]
                - model_summary["S0"]["median_balanced_accuracy"]  # type: ignore[index]
            ),
        }
        summary[checkpoint.model_id] = model_summary
    return {
        "schema": "eneuron.local_prune_b2_matrix.v2",
        "seeds": list(seeds),
        "per_seed": per_seed,
        "summary": summary,
    }


__all__ = [
    "B2Checkpoint",
    "B2Evidence",
    "B2Sample",
    "build_b2_dataset",
    "build_eneuron_b2_checkpoint",
    "build_pulse_b2_checkpoint",
    "run_b2_matrix",
    "run_b2_seed",
]

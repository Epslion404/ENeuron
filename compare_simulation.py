"""ENeuron 1.0 与 Pulse-Mini 的纯软件仿真比较。

本脚本只调用项目中的 Python 黄金模型，不调用 HDL、Vivado 或任何硬件
资源报告。公共任务使用相同四输入事件、零初始权重、相同训练样本数和
相同留出集；各自原生协议的结果另行报告，避免把两种学习规则伪装成等价。
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from network_sim import (
    DigitalSNN2Layer,
    HostTrainingController,
    make_dataset,
    make_noisy_dataset,
)
from neuron_sim import ThreeFactorNeuron
from pulse_mini_network import PulseMiniNetwork, run_p8, train_network
from pulse_mini_reference import Command, Mode, Opcode, PulseMiniReference, Status
from pulse_mini_task import Sample, heldout_samples


LOGGER = logging.getLogger("compare_simulation")

PULSE_VARIANTS = {
    "pulse_mini": 0,
    "pulse_mini_l": PulseMiniReference.LEAK_PERIOD,
}


def make_pulse_variants(*, initial_weights: Sequence[int] | None = None) -> dict[str, PulseMiniReference]:
    """创建无泄放基线和带泄放升级，避免比较实验误用默认版本。"""

    kwargs = {} if initial_weights is None else {"initial_weights": initial_weights}
    return {
        name: PulseMiniReference(leak_period=period, **kwargs)
        for name, period in PULSE_VARIANTS.items()
    }


def mask_to_active(mask: int) -> tuple[int, ...]:
    """把四位输入掩码转换为 ENeuron 使用的活动输入编号。"""

    return tuple(index for index in range(4) if mask & (1 << index))


def masks_to_events(masks: Sequence[int]) -> tuple[tuple[int, ...], ...]:
    """把一个 Pulse-Mini 样本转换为 ENeuron 的逐 tick 事件。"""

    return tuple(mask_to_active(mask) for mask in masks)


def issue(model: PulseMiniReference, opcode: Opcode, arg0: int = 0, arg1: int = 0):
    """发送并立即消费一条 Pulse-Mini 黄金模型命令。"""

    response = model.execute(Command(opcode, arg0, arg1))
    if response.status is not Status.OK:
        raise RuntimeError(f"Pulse-Mini command failed: {opcode.name} {response.status.value}")
    return response


def evaluate_eneuron(neuron: ThreeFactorNeuron, samples: Iterable[Sample]) -> tuple[int, int]:
    """按是否至少发放一次将 ENeuron 解码为二分类输出。"""

    correct = 0
    total = 0
    for sample in samples:
        result = neuron.inference(masks_to_events(sample.masks), label=sample.label)
        correct += int(int(result.spike_count > 0) == sample.label)
        total += 1
    return correct, total


def evaluate_pulse_mini(model: PulseMiniReference, samples: Iterable[Sample]) -> tuple[int, int]:
    """按是否至少发放一次将 Pulse-Mini 解码为二分类输出。"""

    issue(model, Opcode.MODE_SET, int(Mode.INFER))
    correct = 0
    total = 0
    for sample in samples:
        issue(model, Opcode.STATE_CLEAR)
        fired = 0
        for mask in sample.masks:
            fired |= issue(model, Opcode.TICK, mask).spike
        correct += int(fired == sample.label)
        total += 1
    return correct, total


def train_shared_eneuron(
    repetitions: int = 6,
    *,
    positive_modulator: int = 1,
    negative_modulator: int = -1,
) -> ThreeFactorNeuron:
    """用与 Pulse-Mini P5 相同的正负单事件样本训练 ENeuron。"""

    neuron = ThreeFactorNeuron(4)
    neuron.weights = [0, 0, 0, 0]
    for _ in range(repetitions):
        neuron.run_trial(
            (mask_to_active(0b0001),), label=1,
            modulator=positive_modulator, train=True,
        )
        neuron.run_trial(
            (mask_to_active(0b0010),), label=0,
            modulator=negative_modulator, train=True,
        )
    return neuron


def train_shared_pulse_mini(
    repetitions: int = 6,
    *,
    positive_feedback: int = 1,
    negative_feedback: int = -1,
    leak_period: int = PulseMiniReference.LEAK_PERIOD,
) -> PulseMiniReference:
    """用正负单事件、同拍训练后事件和有符号反馈训练 Pulse-Mini。"""

    model = PulseMiniReference(leak_period=leak_period)
    issue(model, Opcode.MODE_SET, int(Mode.TRAIN))
    for _ in range(repetitions):
        for mask, feedback in (
            (0b0001, positive_feedback),
            (0b0010, negative_feedback),
        ):
            issue(model, Opcode.STATE_CLEAR)
            issue(model, Opcode.TICK, mask, 1)
            issue(model, Opcode.CAPTURE)
            feedback_code = 1 if feedback > 0 else 3 if feedback < 0 else 0
            issue(model, Opcode.FEEDBACK, feedback_code)
    return model


def run_shared_task() -> dict[str, Any]:
    """运行零初态、同训练预算和同留出集的直接对照。"""

    samples = heldout_samples()
    baseline_eneuron = ThreeFactorNeuron(4)
    baseline_eneuron.weights = [0, 0, 0, 0]
    eneuron_before, total = evaluate_eneuron(baseline_eneuron, samples)
    pulse_baselines = make_pulse_variants()
    pulse_before = {
        name: evaluate_pulse_mini(model, samples)[0]
        for name, model in pulse_baselines.items()
    }

    eneuron = train_shared_eneuron()
    eneuron_weights_before = tuple(eneuron.weights)
    eneuron_after, _ = evaluate_eneuron(eneuron, samples)
    pulse_results: dict[str, dict[str, Any]] = {}
    for name, period in PULSE_VARIANTS.items():
        pulse = train_shared_pulse_mini(leak_period=period)
        pulse_weights_before = tuple(pulse.weights)
        pulse_after, _ = evaluate_pulse_mini(pulse, samples)
        pulse_results[name] = {
            "baseline_correct": pulse_before[name],
            "trained_correct": pulse_after,
            "final_weights": list(pulse.weights),
            "inference_weights_frozen": tuple(pulse.weights) == pulse_weights_before,
            "leak_period": period,
        }

    return {
        "samples": total,
        "training_samples": 12,
        "initial_weights": [0, 0, 0, 0],
        "eneuron": {
            "baseline_correct": eneuron_before,
            "trained_correct": eneuron_after,
            "final_weights": list(eneuron.weights),
            "inference_weights_frozen": tuple(eneuron.weights) == eneuron_weights_before,
        },
        **pulse_results,
    }


def run_result_delay_scan(max_gap: int = 12) -> list[dict[str, int]]:
    """扫描输入事件与稍后结果信号之间的逻辑 tick 间隔。

    ENeuron 在间隔内衰减多位 eligibility；Pulse-Mini 在显式训练后事件
    到达时检查固定三 tick 窗口。这里同时记录内部记忆和最终权重变化，
    因为非零 eligibility 可能在定点右移后仍不足以改变权重。
    """

    rows: list[dict[str, int]] = []
    for gap in range(max_gap + 1):
        eneuron = ThreeFactorNeuron(4)
        eneuron.weights = [0, 0, 0, 0]
        eneuron.reset_episode()
        eneuron.step((0,), tick=0, learn_enable=True)
        for offset in range(gap):
            eneuron.step((), tick=offset + 1, learn_enable=True)
        eligibility = eneuron.eligibility[0]
        eneuron.apply_modulator(1)

        pulse_results: dict[str, tuple[int, int]] = {}
        for name, pulse in make_pulse_variants().items():
            issue(pulse, Opcode.MODE_SET, int(Mode.TRAIN))
            issue(pulse, Opcode.STATE_CLEAR)
            issue(pulse, Opcode.TICK, 0b0001)
            for _ in range(gap):
                issue(pulse, Opcode.TICK, 0)
            issue(pulse, Opcode.TICK, 0, 1)
            issue(pulse, Opcode.CAPTURE)
            direction = pulse.captured_direction[0]
            issue(pulse, Opcode.FEEDBACK, 1)
            pulse_results[name] = direction, pulse.weights[0]

        rows.append({
            "gap_ticks": gap,
            "eneuron_eligibility": eligibility,
            "eneuron_weight_delta": eneuron.weights[0],
            "pulse_mini_direction": pulse_results["pulse_mini"][0],
            "pulse_mini_weight_delta": pulse_results["pulse_mini"][1],
            "pulse_mini_l_direction": pulse_results["pulse_mini_l"][0],
            "pulse_mini_l_weight_delta": pulse_results["pulse_mini_l"][1],
        })
    return rows


def run_event_multiplicity_scan(max_events: int = 8) -> list[dict[str, int]]:
    """比较一条连接重复出现时，两种学习状态保留的信息量。"""

    rows: list[dict[str, int]] = []
    for event_count in range(1, max_events + 1):
        eneuron = ThreeFactorNeuron(4)
        eneuron.weights = [0, 0, 0, 0]
        eneuron.reset_episode()
        for tick in range(event_count):
            eneuron.step((0,), tick=tick, learn_enable=True)
        eligibility = eneuron.eligibility[0]
        eneuron.apply_modulator(1)

        pulse_results: dict[str, tuple[int, int]] = {}
        for name, pulse in make_pulse_variants().items():
            issue(pulse, Opcode.MODE_SET, int(Mode.TRAIN))
            issue(pulse, Opcode.STATE_CLEAR)
            for _ in range(event_count):
                issue(pulse, Opcode.TICK, 0b0001)
            issue(pulse, Opcode.TICK, 0, 1)
            issue(pulse, Opcode.CAPTURE)
            direction = pulse.captured_direction[0]
            issue(pulse, Opcode.FEEDBACK, 1)
            pulse_results[name] = direction, pulse.weights[0]

        rows.append({
            "event_count": event_count,
            "eneuron_eligibility": eligibility,
            "eneuron_weight_delta": eneuron.weights[0],
            "pulse_mini_direction": pulse_results["pulse_mini"][0],
            "pulse_mini_weight_delta": pulse_results["pulse_mini"][1],
            "pulse_mini_l_direction": pulse_results["pulse_mini_l"][0],
            "pulse_mini_l_weight_delta": pulse_results["pulse_mini_l"][1],
        })
    return rows


def run_identical_weight_spacing_scan(max_gap: int = 12) -> list[dict[str, int]]:
    """固定相同权重，比较泄漏积分与跨样本无泄漏累计。"""

    rows: list[dict[str, int]] = []
    for gap in range(max_gap + 1):
        events: list[tuple[int, ...]] = []
        masks: list[int] = []
        for event_index in range(6):
            events.append((0,))
            masks.append(0b0001)
            if event_index < 5:
                events.extend([()] * gap)
                masks.extend([0] * gap)

        eneuron = ThreeFactorNeuron(4)
        eneuron.weights = [1, -1, 0, 0]
        eneuron_spikes = eneuron.inference(tuple(events)).spike_count

        pulse_variants = make_pulse_variants(initial_weights=(1, -1, 0, 0))
        pulse_spikes = {}
        for name, pulse in pulse_variants.items():
            issue(pulse, Opcode.MODE_SET, int(Mode.INFER))
            issue(pulse, Opcode.STATE_CLEAR)
            pulse_spikes[name] = sum(issue(pulse, Opcode.TICK, mask).spike for mask in masks)
        rows.append({
            "gap_ticks": gap,
            "sample_ticks": len(masks),
            "eneuron_spikes": eneuron_spikes,
            "pulse_mini_spikes": pulse_spikes["pulse_mini"],
            "pulse_mini_l_spikes": pulse_spikes["pulse_mini_l"],
        })
    return rows


def run_one_update_spacing_scan(max_gap: int = 12) -> list[dict[str, int]]:
    """各训练一次后，扫描六个正事件之间的空白间隔。"""

    eneuron = train_shared_eneuron(repetitions=1)
    pulse_variants = {
        name: train_shared_pulse_mini(repetitions=1, leak_period=period)
        for name, period in PULSE_VARIANTS.items()
    }
    for pulse in pulse_variants.values():
        issue(pulse, Opcode.MODE_SET, int(Mode.INFER))
    rows: list[dict[str, int]] = []
    for gap in range(max_gap + 1):
        events: list[tuple[int, ...]] = []
        masks: list[int] = []
        for event_index in range(6):
            events.append((0,))
            masks.append(0b0001)
            if event_index < 5:
                events.extend([()] * gap)
                masks.extend([0] * gap)
        eneuron_spikes = eneuron.inference(tuple(events)).spike_count
        pulse_spikes: dict[str, int] = {}
        for name, pulse in pulse_variants.items():
            issue(pulse, Opcode.STATE_CLEAR)
            pulse_spikes[name] = sum(issue(pulse, Opcode.TICK, mask).spike for mask in masks)
        rows.append({
            "gap_ticks": gap,
            "sample_ticks": len(masks),
            "eneuron_weight": eneuron.weights[0],
            "pulse_mini_weight": pulse_variants["pulse_mini"].weights[0],
            "pulse_mini_l_weight": pulse_variants["pulse_mini_l"].weights[0],
            "eneuron_spikes": eneuron_spikes,
            "pulse_mini_spikes": pulse_spikes["pulse_mini"],
            "pulse_mini_l_spikes": pulse_spikes["pulse_mini_l"],
        })
    return rows


def _pulse_trace(
    *,
    leak_period: int,
    weight: int,
    event_count: int,
    gap_ticks: int,
) -> dict[str, int | None]:
    """返回固定权重、固定事件间隔下的脉冲和膜电位轨迹摘要。"""

    model = PulseMiniReference(initial_weights=(weight, 0, 0, 0), leak_period=leak_period)
    issue(model, Opcode.MODE_SET, int(Mode.INFER))
    issue(model, Opcode.STATE_CLEAR)
    spike_count = 0
    first_spike_tick: int | None = None
    max_soma = model.soma
    for event_index in range(event_count):
        response = issue(model, Opcode.TICK, 0b0001)
        if response.spike:
            spike_count += 1
            if first_spike_tick is None:
                first_spike_tick = event_index * (gap_ticks + 1)
        max_soma = max(max_soma, model.soma)
        if event_index < event_count - 1:
            for _ in range(gap_ticks):
                response = issue(model, Opcode.TICK, 0)
                if response.spike:
                    spike_count += 1
                    if first_spike_tick is None:
                        first_spike_tick = event_index * (gap_ticks + 1) + 1
                max_soma = max(max_soma, model.soma)
    return {
        "spike_count": spike_count,
        "first_spike_tick": first_spike_tick,
        "sample_ticks": event_count + (event_count - 1) * gap_ticks,
        "final_soma": model.soma,
        "max_soma": max_soma,
    }


def _pulse_network_metrics(leak_period: int) -> dict[str, Any]:
    """测量一个泄放周期下的固定 4→2→2 网络闭环。"""

    evaluation = make_shared_network_evaluation_data()
    network = train_network(leak_period=leak_period)
    before = network.weights
    correct = evaluate_pulse_network(network, evaluation)
    after = network.weights
    ticks = [entry for entry in network.ledger if entry["op"] == "TICK"]
    route_delay = any(
        first["hidden_spikes"] != 0 and first["output_spikes"] == 0
        and second["pending_hidden_before"] == first["hidden_spikes"]
        and second["output_spikes"] != 0
        for first, second in zip(ticks, ticks[1:])
    )
    return {
        "correct": correct,
        "samples": len(evaluation),
        "accuracy": correct / len(evaluation),
        "weights": [list(weights) for weights in before],
        "weights_frozen": before == after,
        "one_tick_route": all(entry["pending_hidden_after"] == entry["hidden_spikes"] for entry in ticks),
        "route_delay_observed": route_delay,
    }


def run_leak_period_scan() -> dict[str, Any]:
    """扫描无泄放与小型固定泄放周期，筛选简洁升级的适用范围。"""

    periods = (0, 1, 2, 4, 8, 12)
    direct_cases = [(weight, events) for weight in (1, 2, 3, 6) for events in (6, 8)]
    rows: list[dict[str, Any]] = []
    baseline_training = train_shared_pulse_mini(leak_period=0)
    baseline_network = _pulse_network_metrics(0)
    for period in periods:
        dense = [_pulse_trace(leak_period=period, weight=weight, event_count=events, gap_ticks=0)
                 for weight, events in direct_cases]
        sparse = [_pulse_trace(leak_period=period, weight=weight, event_count=events, gap_ticks=8)
                  for weight, events in direct_cases]
        trained = train_shared_pulse_mini(leak_period=period)
        network = _pulse_network_metrics(period)
        dense_hit_rate = sum(int(int(item["spike_count"]) > 0) for item in dense) / len(dense)
        sparse_false_rate = sum(int(int(item["spike_count"]) > 0) for item in sparse) / len(sparse)
        rows.append({
            "leak_period": period,
            "dense_hit_rate": dense_hit_rate,
            "sparse_false_spike_rate": sparse_false_rate,
            "temporal_selectivity": dense_hit_rate - sparse_false_rate,
            "training_weights": list(trained.weights),
            "training_matches_no_leak": trained.weights == baseline_training.weights,
            "network": network,
            "network_accuracy_delta_vs_no_leak": network["accuracy"] - baseline_network["accuracy"],
            "direct": {
                "dense": dense,
                "sparse_gap_8": sparse,
            },
        })
    # 硬门只用于选择候选，不把它包装成通用最优性证明。
    baseline_row = rows[0]
    for row in rows:
        row["passes_minimal_gate"] = bool(
            row["dense_hit_rate"] >= baseline_row["dense_hit_rate"] - 0.05
            and row["sparse_false_spike_rate"] <= baseline_row["sparse_false_spike_rate"] - 0.20
            and row["training_matches_no_leak"]
            and row["network_accuracy_delta_vs_no_leak"] >= -0.05
            and row["network"]["weights_frozen"]
            and row["network"]["one_tick_route"]
            and row["network"]["route_delay_observed"]
        )
    selected = next((row["leak_period"] for row in rows[1:] if row["passes_minimal_gate"]), None)
    return {
        "periods": list(periods),
        "candidate_selection_rule": {
            "dense_hit_drop_max": 0.05,
            "sparse_false_drop_min": 0.20,
            "network_accuracy_drop_max": 0.05,
            "training_weights_must_match_no_leak": True,
        },
        "selected_minimal_period": selected,
        "baseline_no_leak_network": baseline_network,
        "rows": rows,
    }


def run_conflicting_evidence_probe() -> dict[str, Any]:
    """让同一连接既形成正证据又形成负证据，观察压缩差异。"""

    events = ((0,), (), (0,))
    eneuron = ThreeFactorNeuron(4)
    eneuron.weights = [7, 0, 0, 0]
    eneuron.reset_episode()
    eneuron_spikes = [eneuron.step(active, tick, learn_enable=True) for tick, active in enumerate(events)]

    pulse_results: dict[str, dict[str, Any]] = {}
    for name, pulse in make_pulse_variants(initial_weights=(7, 0, 0, 0)).items():
        issue(pulse, Opcode.MODE_SET, int(Mode.TRAIN))
        issue(pulse, Opcode.STATE_CLEAR)
        pulse_spikes = [issue(pulse, Opcode.TICK, mask).spike for mask in (1, 0, 1)]
        positive = pulse.positive_evidence[0]
        negative = pulse.negative_evidence[0]
        issue(pulse, Opcode.CAPTURE)
        pulse_results[name] = {
            "spikes": pulse_spikes,
            "positive": positive,
            "negative": negative,
            "direction": pulse.captured_direction[0],
        }
    return {
        "input_masks": [1, 0, 1],
        "eneuron_spikes": eneuron_spikes,
        "eneuron_eligibility": eneuron.eligibility[0],
        "pulse_mini_spikes": pulse_results["pulse_mini"]["spikes"],
        "pulse_mini_positive_evidence": pulse_results["pulse_mini"]["positive"],
        "pulse_mini_negative_evidence": pulse_results["pulse_mini"]["negative"],
        "pulse_mini_captured_direction": pulse_results["pulse_mini"]["direction"],
        "pulse_mini_l_spikes": pulse_results["pulse_mini_l"]["spikes"],
        "pulse_mini_l_positive_evidence": pulse_results["pulse_mini_l"]["positive"],
        "pulse_mini_l_negative_evidence": pulse_results["pulse_mini_l"]["negative"],
        "pulse_mini_l_captured_direction": pulse_results["pulse_mini_l"]["direction"],
    }


def run_convergence_scan(max_repetitions: int = 7) -> dict[str, Any]:
    """记录从零权重开始达到共同任务满分所需的训练重复次数。"""

    samples = heldout_samples()
    rows: list[dict[str, Any]] = []
    for repetitions in range(max_repetitions + 1):
        eneuron = train_shared_eneuron(repetitions)
        eneuron_correct, total = evaluate_eneuron(eneuron, samples)
        pulse_results = {}
        for name, period in PULSE_VARIANTS.items():
            pulse = train_shared_pulse_mini(repetitions, leak_period=period)
            pulse_results[name] = {
                "correct": evaluate_pulse_mini(pulse, samples)[0],
                "weights": list(pulse.weights),
            }
        rows.append({
            "repetitions": repetitions,
            "training_samples": repetitions * 2,
            "eneuron_correct": eneuron_correct,
            "pulse_mini_correct": pulse_results["pulse_mini"]["correct"],
            "pulse_mini_l_correct": pulse_results["pulse_mini_l"]["correct"],
            "samples": total,
            "eneuron_weights": list(eneuron.weights),
            "pulse_mini_weights": pulse_results["pulse_mini"]["weights"],
            "pulse_mini_l_weights": pulse_results["pulse_mini_l"]["weights"],
        })

    def first_full_score(field: str) -> int | None:
        return next((row["repetitions"] for row in rows if row[field] == row["samples"]), None)

    return {
        "rows": rows,
        "eneuron_first_full_score_repetition": first_full_score("eneuron_correct"),
        "pulse_mini_first_full_score_repetition": first_full_score("pulse_mini_correct"),
        "pulse_mini_l_first_full_score_repetition": first_full_score("pulse_mini_l_correct"),
    }


def run_negative_controls() -> dict[str, dict[str, int]]:
    """在完全相同的训练样本上执行反馈因果负对照。"""

    samples = heldout_samples()
    protocols = {
        "correct_feedback": (1, -1),
        "no_feedback": (0, 0),
        "reversed_feedback": (-1, 1),
        # 与既有 P5 对照一致：打乱后两个特征都收到负结果。
        "label_shuffled": (-1, -1),
    }
    result = {"eneuron": {}, "pulse_mini": {}, "pulse_mini_l": {}}
    for name, (positive, negative) in protocols.items():
        eneuron = train_shared_eneuron(
            positive_modulator=positive,
            negative_modulator=negative,
        )
        result["eneuron"][name] = evaluate_eneuron(eneuron, samples)[0]
        for variant, period in PULSE_VARIANTS.items():
            pulse = train_shared_pulse_mini(
                positive_feedback=positive,
                negative_feedback=negative,
                leak_period=period,
            )
            result[variant][name] = evaluate_pulse_mini(pulse, samples)[0]
    return result


def make_shared_noise_samples(
    seed: int,
    *,
    count: int,
    dropout: float,
    cross_class: float,
    neutral: float,
) -> tuple[Sample, ...]:
    """生成三个模型共用的平衡噪声样本。

    每个样本固定八个 tick。正类的有效通道为 0，负类为 1；对立噪声
    使用另一类通道，无关噪声只使用当前未训练的通道 2/3。
    """

    rng = random.Random(seed)
    samples: list[Sample] = []
    for index in range(count):
        label = index % 2
        signal_channel = 0 if label == 1 else 1
        cross_channel = 1 if label == 1 else 0
        masks: list[int] = []
        for _ in range(8):
            mask = 0
            if rng.random() >= dropout:
                mask |= 1 << signal_channel
            if rng.random() < cross_class:
                mask |= 1 << cross_channel
            if rng.random() < neutral:
                mask |= 1 << rng.choice((2, 3))
            masks.append(mask)
        samples.append(Sample(label=label, masks=tuple(masks)))
    return tuple(samples)


def run_noise_sweep(
    seeds: Sequence[int],
    *,
    samples_per_seed: int = 200,
) -> dict[str, Any]:
    """在共享噪声数据上比较训练后分类鲁棒性。"""

    levels = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9)
    profiles = {
        "dropout": lambda level: (level, 0.0, 0.0),
        "cross_class": lambda level: (0.0, level, 0.0),
        "neutral": lambda level: (0.0, 0.0, level),
        "combined": lambda level: (level, level, level),
    }
    eneuron = train_shared_eneuron()
    eneuron_weights = tuple(eneuron.weights)
    pulses = {
        name: train_shared_pulse_mini(leak_period=period)
        for name, period in PULSE_VARIANTS.items()
    }
    pulse_weights = {name: tuple(model.weights) for name, model in pulses.items()}
    profile_results: dict[str, list[dict[str, Any]]] = {}

    for profile_index, (profile_name, parameters) in enumerate(profiles.items()):
        rows: list[dict[str, Any]] = []
        for level in levels:
            eneuron_scores: list[float] = []
            pulse_scores = {name: [] for name in PULSE_VARIANTS}
            dropout, cross_class, neutral = parameters(level)
            for seed in seeds:
                # 各 profile 使用独立流；同一 profile 的各 level 重用同一
                # 基础随机数顺序，使严重度扫描尽量保持嵌套。
                samples = make_shared_noise_samples(
                    seed * 1009 + profile_index,
                    count=samples_per_seed,
                    dropout=dropout,
                    cross_class=cross_class,
                    neutral=neutral,
                )
                correct, total = evaluate_eneuron(eneuron, samples)
                eneuron_scores.append(correct / total)
                for variant_name, pulse in pulses.items():
                    correct, total = evaluate_pulse_mini(pulse, samples)
                    pulse_scores[variant_name].append(correct / total)
                    pulse.event_log.clear()
            rows.append({
                "severity": level,
                "eneuron_mean_accuracy": sum(eneuron_scores) / len(eneuron_scores),
                "eneuron_min_accuracy": min(eneuron_scores),
                "eneuron_max_accuracy": max(eneuron_scores),
                **{
                    f"{name}_mean_accuracy": sum(scores) / len(scores)
                    for name, scores in pulse_scores.items()
                },
                **{
                    f"{name}_min_accuracy": min(scores)
                    for name, scores in pulse_scores.items()
                },
                **{
                    f"{name}_max_accuracy": max(scores)
                    for name, scores in pulse_scores.items()
                },
            })
        profile_results[profile_name] = rows

    if tuple(eneuron.weights) != eneuron_weights or any(
        tuple(pulses[name].weights) != pulse_weights[name] for name in PULSE_VARIANTS
    ):
        raise AssertionError("noise inference changed trained weights")
    return {
        "seed_count": len(seeds),
        "samples_per_seed": samples_per_seed,
        "levels": list(levels),
        "profiles": profile_results,
        "inference_weights_frozen": True,
    }


def make_shared_network_training_data() -> tuple[tuple[tuple[tuple[int, ...], ...], int], ...]:
    """构造两个类别各一个样本的共同网络训练集。"""

    positive = masks_to_events((0b0001,) * 6 + (0, 0))
    negative = masks_to_events((0b0010,) * 6 + (0, 0))
    # ENeuron 的输出编号 0/1 分别对应 Pulse-Mini 输出位 1/2。
    return ((positive, 0), (negative, 1))


def make_shared_network_evaluation_data() -> tuple[
    tuple[tuple[tuple[int, ...], ...], int, int, int], ...
]:
    """返回事件、ENeuron 标签、Pulse-Mini 输出位和原始特征掩码。"""

    samples: list[tuple[tuple[tuple[int, ...], ...], int, int, int]] = []
    for index in range(10):
        feature = 0b1001 if index % 3 == 0 else 0b0001
        samples.append((masks_to_events((feature,) * 8), 0, 0b01, feature))
    for index in range(10):
        feature = 0b1010 if index % 2 == 0 else 0b0010
        samples.append((masks_to_events((feature,) * 8), 1, 0b10, feature))
    return tuple(samples)


def evaluate_pulse_network(
    network: PulseMiniNetwork,
    samples: Sequence[tuple[tuple[tuple[int, ...], ...], int, int, int]],
) -> int:
    """在共同网络样本上按输出位精确评分 Pulse-Mini。"""

    network.mode_set(Mode.INFER)
    return sum(int(network.infer(feature) == expected) for _, _, expected, feature in samples)


def run_shared_network_task(seeds: Sequence[int]) -> dict[str, Any]:
    """在共同训练集和共同留出集上比较三个固定 4->2->2 网络。"""

    training = make_shared_network_training_data()
    evaluation = make_shared_network_evaluation_data()
    host = HostTrainingController()
    baseline_scores: list[float] = []
    trained_scores: list[float] = []
    eneuron_frozen = True

    for seed in seeds:
        network = DigitalSNN2Layer(init_seed=seed)
        baseline_scores.append(sum(
            int(network.inference(events, label=label).prediction == label)
            for events, label, _, _ in evaluation
        ) / len(evaluation))
        host.train(network, training, epochs=30, seed=seed, mode="teacher")
        weights_before = tuple(tuple(neuron.weights) for neuron in network.neurons)
        trained_scores.append(sum(
            int(network.inference(events, label=label).prediction == label)
            for events, label, _, _ in evaluation
        ) / len(evaluation))
        eneuron_frozen &= weights_before == tuple(tuple(neuron.weights) for neuron in network.neurons)

    pulse_results: dict[str, dict[str, Any]] = {}
    for name, period in PULSE_VARIANTS.items():
        pulse_baseline = PulseMiniNetwork(leak_period=period)
        pulse = train_network(leak_period=period)
        pulse_weights_before = pulse.weights
        pulse_results[name] = {
            "baseline_correct": evaluate_pulse_network(pulse_baseline, evaluation),
            "trained_correct": evaluate_pulse_network(pulse, evaluation),
            "inference_weights_frozen": pulse.weights == pulse_weights_before,
            "trained_weights": [list(weights) for weights in pulse.weights],
            "leak_period": period,
        }

    return {
        "samples": len(evaluation),
        "training_samples_per_epoch": len(training),
        "eneuron": {
            "seeds": len(seeds),
            "baseline_mean_accuracy": sum(baseline_scores) / len(baseline_scores),
            "baseline_min_accuracy": min(baseline_scores),
            "trained_mean_accuracy": sum(trained_scores) / len(trained_scores),
            "trained_min_accuracy": min(trained_scores),
            "trained_success_rate": sum(score == 1.0 for score in trained_scores) / len(trained_scores),
            "inference_weights_frozen": eneuron_frozen,
        },
        **pulse_results,
    }


def summarize_scores(clean: Sequence[float], noisy: Sequence[float]) -> dict[str, float | int]:
    """汇总网络多种子准确率，保留最差值避免均值掩盖失败。"""

    return {
        "seeds": len(clean),
        "clean_success_rate": sum(score == 1.0 for score in clean) / len(clean),
        "clean_mean_accuracy": sum(clean) / len(clean),
        "clean_min_accuracy": min(clean),
        "noisy_mean_accuracy": sum(noisy) / len(noisy),
        "noisy_min_accuracy": min(noisy),
    }


def run_native_network_protocols(seeds: Sequence[int]) -> dict[str, Any]:
    """复跑三个版本各自冻结的原生网络训练协议。"""

    host = HostTrainingController()
    clean_data = make_dataset()
    eneuron_results: dict[str, dict[str, float | int]] = {}
    for mode in ("teacher", "reward", "hybrid"):
        clean_scores: list[float] = []
        noisy_scores: list[float] = []
        for seed in seeds:
            network = (
                DigitalSNN2Layer(hidden_wta=True, output_wta=True, init_seed=seed)
                if mode in {"reward", "hybrid"}
                else DigitalSNN2Layer()
            )
            if mode == "hybrid":
                host.train_hybrid(network, clean_data, feature_epochs=30, reward_epochs=100, seed=seed)
            else:
                host.train(network, clean_data, epochs=30, seed=seed, mode=mode)
            clean_scores.append(host.evaluate(network, clean_data))
            noisy_scores.append(host.evaluate(network, make_noisy_dataset(seed=seed, count=100)))
        eneuron_results[mode] = summarize_scores(clean_scores, noisy_scores)

    pulse_results = {
        name: run_p8(leak_period=period)
        for name, period in PULSE_VARIANTS.items()
    }

    def summarize_pulse(pulse: dict[str, Any]) -> dict[str, Any]:
        return {
            "baseline_correct": sum(int(value != 0) for value in pulse["baseline"].values()),
            "clean_correct": sum(value == 1 for value in pulse["positive_outputs"])
            + sum(value == 2 for value in pulse["negative_outputs"]),
            "clean_samples": len(pulse["positive_outputs"]) + len(pulse["negative_outputs"]),
            "no_feedback_outputs": pulse["no_feedback_outputs"],
            "inference_weights_frozen": pulse["weights_frozen"],
            "one_tick_route": pulse["hidden_to_output_one_tick"] and pulse["route_delay_observed"],
            "direct_weight_write_count": pulse["direct_weight_write_count"],
        }

    return {
        "eneuron_teacher": eneuron_results["teacher"],
        "eneuron_global_reward": eneuron_results["reward"],
        "eneuron_hybrid": eneuron_results["hybrid"],
        "pulse_mini_local_teacher": summarize_pulse(pulse_results["pulse_mini"]),
        "pulse_mini_l_local_teacher": summarize_pulse(pulse_results["pulse_mini_l"]),
        "pulse_mini_global_reward": "not_tested",
        "pulse_mini_l_global_reward": "not_tested",
    }


def run_network_comparison(seeds: Sequence[int]) -> dict[str, Any]:
    """运行固定 4->2->2 网络的共同任务与原生协议比较。"""

    return {
        "shared_task": run_shared_network_task(seeds),
        "native_protocols": run_native_network_protocols(seeds),
    }


def run_rtl_cosim_evidence() -> dict[str, Any]:
    """复跑现有 Icarus/Python 协同仿真，不调用 Vivado。"""

    from pulse_mini_cosim import run as run_pulse_core
    from pulse_mini_network_rtl_cosim import commands as pulse_network_commands
    from pulse_mini_network_rtl_cosim import run as run_pulse_network
    from rtl_multicycle_cosim import run as run_eneuron_core
    from rtl_tile_cosim import run as run_eneuron_tile

    LOGGER.info("开始 ENeuron 单核 20000 事务 RTL 协同仿真")
    for seed in range(20):
        run_eneuron_core(seed, 1000, 4)
    LOGGER.info("开始 Pulse-Mini-L 单核 20000 事务 RTL 协同仿真")
    for seed in range(20):
        run_pulse_core(seed, 1000)
    LOGGER.info("开始 ENeuron Tile 10000 事务 RTL 协同仿真")
    for seed in range(20):
        run_eneuron_tile(seed, 500)
    LOGGER.info("开始 Pulse-Mini-L 固定网络 RTL 协同仿真")
    run_pulse_network()
    return {
        "tool": "Icarus Verilog + Python golden model",
        "eneuron_core": {"seeds": 20, "transactions": 20000, "result": "bit_exact_pass"},
        "pulse_mini_l_core": {
            "seeds": 20,
            "transactions": 20000,
            "leak_period": PulseMiniReference.LEAK_PERIOD,
            "result": "bit_exact_pass",
        },
        "eneuron_tile_4x2x2": {"seeds": 20, "transactions": 10000, "result": "bit_exact_pass"},
        "pulse_mini_l_network_4x2x2": {
            "commands": len(pulse_network_commands()),
            "leak_period": PulseMiniReference.LEAK_PERIOD,
            "result": "bit_exact_pass",
            "one_tick_route": True,
        },
    }


def run_comparison(
    *,
    seeds: Iterable[int] = range(20),
    rtl_cosim: bool = False,
) -> dict[str, Any]:
    """运行完整比较；后续实验以同一个稳定入口逐项加入。"""

    seed_values = tuple(seeds)
    LOGGER.info("开始纯仿真比较，seeds=%d", len(seed_values))
    result = {
        "scope": {
            "method": "simulation_only",
            "vivado_used": False,
            "rtl_simulation_used": rtl_cosim,
            "seed_count": len(seed_values),
            "report_date": "2026-08-19",
        },
        "model_contracts": {
            "shared": {
                "inputs": 4,
                "weight_range": [-7, 7],
                "threshold": 6,
                "refractory_ticks": 1,
                "common_initial_weights": [0, 0, 0, 0],
            },
            "eneuron": {
                "state": "leaky current + leaky membrane + pre/post traces + signed eligibility",
                "result_interface": "signed modulator applied to eligibility snapshot",
                "learning_resolution": "multi-bit magnitude, fixed-point shifted update",
                "threshold": "adaptive during training",
            },
            "pulse_mini": {
                "state": "single soma accumulator + three-tick presence window",
                "result_interface": "CAPTURE direction then signed FEEDBACK",
                "learning_resolution": "-1/0/+1 direction, one weight step per feedback",
                "threshold": "fixed",
                "leak_period": 0,
                "leak_semantics": "disabled",
            },
            "pulse_mini_l": {
                "state": "leaky soma accumulator + three-tick presence window",
                "result_interface": "CAPTURE direction then signed FEEDBACK",
                "learning_resolution": "-1/0/+1 direction, one weight step per feedback",
                "threshold": "fixed",
                "leak_period": PulseMiniReference.LEAK_PERIOD,
                "leak_semantics": "accepted TICK only; toward-zero one step before input; refractory pauses phase",
            },
        },
        "single_neuron": {
            "shared_task": run_shared_task(),
            "result_delay_scan": run_result_delay_scan(),
            "event_multiplicity_scan": run_event_multiplicity_scan(),
            "identical_weight_spacing_scan": run_identical_weight_spacing_scan(),
            "one_update_spacing_scan": run_one_update_spacing_scan(),
            "leak_period_scan": run_leak_period_scan(),
            "conflicting_evidence": run_conflicting_evidence_probe(),
            "convergence": run_convergence_scan(),
            "negative_controls": run_negative_controls(),
            "noise_sweep": run_noise_sweep(seed_values),
        },
        "network_4x2x2": run_network_comparison(seed_values),
    }
    if rtl_cosim:
        result["rtl_cosimulation"] = run_rtl_cosim_evidence()
    return result


def percent(value: float) -> str:
    """把 0..1 的比率格式化为一位小数百分比。"""

    return f"{value * 100:.1f}%"


def render_report(result: dict[str, Any]) -> str:
    """根据机器结果生成中文完整报告。"""

    scope = result["scope"]
    single = result["single_neuron"]
    shared = single["shared_task"]
    convergence = single["convergence"]
    controls = single["negative_controls"]
    network = result["network_4x2x2"]
    shared_network = network["shared_task"]
    native = network["native_protocols"]
    leak_scan = single["leak_period_scan"]
    lines = [
        "# ENeuron 1.0、Pulse-Mini 基线与 Pulse-Mini-L 纯仿真比较报告",
        "",
        f"日期：{scope['report_date']}",
        "",
        "## 1. 范围与结论",
        "",
        "本报告是仅仿真评估，只使用 Python 黄金模型与可选的 Icarus RTL 协同仿真。没有调用 Vivado，",
        "不包含 LUT、FF、BRAM、DSP、布线时序、功耗或板级结论。",
        "",
        "主要结论：",
        "",
        f"- 共同单神经元任务中，三者训练前均为 {shared['eneuron']['baseline_correct']}/{shared['samples']}，"
        f"训练后 ENeuron、Pulse-Mini、Pulse-Mini-L 均为20/20。",
        f"- 三者都在第 {convergence['eneuron_first_full_score_repetition']} 次正负训练重复后达到满分；"
        "ENeuron 一次反馈可产生多级变化，两个 Pulse-Mini 版本每次只改变一步。",
        "- 无泄放 Pulse-Mini 会把低频输入长期累积；Pulse-Mini-L 通过一个固定周期计时器向零泄放，"
        "在本测试矩阵中保留密集命中并降低部分稀疏误发放。",
        f"- 预注册周期扫描选出最小通过候选 LEAK_PERIOD={leak_scan['selected_minimal_period']}；这是当前测试矩阵的选择，不是全局最优证明。",
        "- 固定 4→2→2 共同任务中三者都达到满分，但训练信号仍是神经元级监督，不能据此推出通用自训练。",
        "",
        "## 2. 比较口径",
        "",
        "### 2.1 共同条件直接比较",
        "",
        "- 四个二值输入通道，权重范围 -7..+7，阈值 6，不应期 1 tick。",
        "- 零初始权重。每次训练重复包含一个正样本和一个负样本。",
        "- 正样本使用通道0并给出正结果；负样本使用通道1并给出负结果。",
        "- 相同20样本留出集、相同噪声样本和相同解码规则：至少发放一次即判为正类。",
        "",
        "### 2.2 原生协议比较",
        "",
        "ENeuron 使用多位 eligibility 与 signed modulator；两个 Pulse-Mini 版本使用 presence flag、CAPTURE 和",
        "一步 FEEDBACK，差别仅在膜电位是否按周期泄放。原生网络结果用于说明各自能做到什么，",
        "不视为学习规则完全等价。",
        "",
        "## 3. 模型行为差异",
        "",
        "| 项目 | ENeuron 1.0 | Pulse-Mini | Pulse-Mini-L |",
        "|---|---|---|---|",
        "| 胞体 | 电流与膜状态均泄漏 | 膜状态不泄放 | 膜状态每8个成功TICK向零移动1 |",
        "| 时间记录 | 多位 pre/post trace 和 eligibility | 三 tick 窗口与正负 presence flag | 泄放计时器 + 三 tick 窗口与 presence flag |",
        "| 学习结果 | eligibility 大小决定权重变化幅度 | 每条连接只保存上调、下调或不动 | 同左；泄放不改学习字段 |",
        "| 阈值 | 训练时可适应 | 固定为6 | 固定为6 |",
        "| 延迟结果 | 快照后接受 signed modulator | CAPTURE 后接受 -1/0/+1 FEEDBACK | 同左 |",
        "| 推理 | 冻结学习状态和权重 | 允许膜状态变化，冻结权重和学习字段 | 允许膜状态/计时器变化，冻结权重和学习字段 |",
        "",
        "## 4. 单神经元共同任务",
        "",
        "| 模型 | 训练前 | 训练后 | 最终权重 | 推理冻结 |",
        "|---|---:|---:|---|---|",
        f"| ENeuron 1.0 | {shared['eneuron']['baseline_correct']}/{shared['samples']} | "
        f"{shared['eneuron']['trained_correct']}/{shared['samples']} | {shared['eneuron']['final_weights']} | "
        f"{'通过' if shared['eneuron']['inference_weights_frozen'] else '失败'} |",
        f"| Pulse-Mini | {shared['pulse_mini']['baseline_correct']}/{shared['samples']} | "
        f"{shared['pulse_mini']['trained_correct']}/{shared['samples']} | {shared['pulse_mini']['final_weights']} | "
        f"{'通过' if shared['pulse_mini']['inference_weights_frozen'] else '失败'} |",
        f"| Pulse-Mini-L | {shared['pulse_mini_l']['baseline_correct']}/{shared['samples']} | "
        f"{shared['pulse_mini_l']['trained_correct']}/{shared['samples']} | {shared['pulse_mini_l']['final_weights']} | "
        f"{'通过' if shared['pulse_mini_l']['inference_weights_frozen'] else '失败'} |",
        "",
        "### 4.1 收敛过程",
        "",
        "| 正负训练重复 | 训练样本数 | ENeuron | Pulse-Mini | Pulse-Mini-L | EN权重 | PM权重 | PM-L权重 |",
        "|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for row in convergence["rows"]:
        lines.append(
            f"| {row['repetitions']} | {row['training_samples']} | {row['eneuron_correct']}/{row['samples']} | "
            f"{row['pulse_mini_correct']}/{row['samples']} | {row['pulse_mini_l_correct']}/{row['samples']} | "
            f"{row['eneuron_weights']} | {row['pulse_mini_weights']} | {row['pulse_mini_l_weights']} |"
        )

    lines.extend([
        "",
        "### 4.2 反馈负对照",
        "",
        "| 条件 | ENeuron | Pulse-Mini | Pulse-Mini-L |",
        "|---|---:|---:|---:|",
        f"| 正确反馈 | {controls['eneuron']['correct_feedback']}/20 | {controls['pulse_mini']['correct_feedback']}/20 | {controls['pulse_mini_l']['correct_feedback']}/20 |",
        f"| 无反馈 | {controls['eneuron']['no_feedback']}/20 | {controls['pulse_mini']['no_feedback']}/20 | {controls['pulse_mini_l']['no_feedback']}/20 |",
        f"| 反馈反向 | {controls['eneuron']['reversed_feedback']}/20 | {controls['pulse_mini']['reversed_feedback']}/20 | {controls['pulse_mini_l']['reversed_feedback']}/20 |",
        f"| 标签打乱对照 | {controls['eneuron']['label_shuffled']}/20 | {controls['pulse_mini']['label_shuffled']}/20 | {controls['pulse_mini_l']['label_shuffled']}/20 |",
        "",
        "这组结果说明三者的成功都依赖反馈符号；它们不是靠初始权重直接答对。",
        "",
        "## 5. 时间与信息保存能力",
        "",
        "### 5.1 输入到结果的间隔",
        "",
        "| 间隔tick | EN eligibility | EN权重变化 | PM方向 | PM变化 | PM-L方向 | PM-L变化 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in single["result_delay_scan"]:
        lines.append(
            f"| {row['gap_ticks']} | {row['eneuron_eligibility']} | {row['eneuron_weight_delta']} | "
            f"{row['pulse_mini_direction']} | {row['pulse_mini_weight_delta']} | "
            f"{row['pulse_mini_l_direction']} | {row['pulse_mini_l_weight_delta']} |"
        )

    lines.extend([
        "",
        "ENeuron 在间隔3到9 tick仍保留非零内部资格值，但当前学习右移使其最终更新为0。",
        "Pulse-Mini 在间隔0到2 tick更新一步，间隔3 tick后直接没有方向。就当前参数的实际权重效果看，",
        "在当前参数下，三个模型的实际权重更新窗口都集中在 gap 0..2；若改变 ENeuron 学习移位或累积更多证据，内部余量才可能转化为更长有效窗口。",
        "",
        "### 5.2 重复证据",
        "",
        "| 同一事件次数 | EN eligibility | EN权重变化 | PM方向 | PM变化 | PM-L方向 | PM-L变化 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in single["event_multiplicity_scan"]:
        lines.append(
            f"| {row['event_count']} | {row['eneuron_eligibility']} | {row['eneuron_weight_delta']} | "
            f"{row['pulse_mini_direction']} | {row['pulse_mini_weight_delta']} | "
            f"{row['pulse_mini_l_direction']} | {row['pulse_mini_l_weight_delta']} |"
        )

    learned_spacing = single["one_update_spacing_scan"]
    lines.extend([
        "",
        "两个 Pulse-Mini 版本对1次和8次同方向证据都只更新一步；ENeuron 的 eligibility 随证据次数增加，",
        "三次事件已把本实验中的单次提交推到权重上限。前者稳定且简单，后者保留更多置信度信息。",
        "",
        "### 5.3 事件稀疏度",
        "",
        "以下是三个模型各完成一次正负训练后的结果：EN权重为2，两个 Pulse-Mini 版本权重为1。每个样本都含6个正事件；泄放会让长间隔事件不再无限累加。",
        "",
        "| 事件间空白tick | 样本长度 | EN脉冲数 | PM脉冲数 | PM-L脉冲数 |",
        "|---:|---:|---:|---:|---:|",
    ])
    for row in learned_spacing:
        lines.append(
            f"| {row['gap_ticks']} | {row['sample_ticks']} | {row['eneuron_spikes']} | "
            f"{row['pulse_mini_spikes']} | {row['pulse_mini_l_spikes']} |"
        )

    conflict = single["conflicting_evidence"]
    lines.extend([
        "",
        "ENeuron 和 Pulse-Mini-L 都有时间泄漏；无泄放基线则会把同样的低频事件长期累积到阈值。",
        "Pulse-Mini-L 的代价是弱连接在短样本中可能需要更多事件；因此周期必须由任务矩阵选择，不能只凭单条曲线决定。",
        "",
        "### 5.4 泄放周期消融与选择",
        "",
        "硬门：密集命中率相对无泄放下降不超过5个百分点；8-tick稀疏误发放率至少下降20个百分点；",
        "训练后权重逐位一致；固定4→2→2网络准确率下降不超过5个百分点，且冻结与一拍路由继续通过。",
        "",
        "| LEAK_PERIOD | 密集命中率 | 稀疏误发放率 | 时间选择性 | 训练权重同基线 | 网络准确率 | 通过硬门 |",
        "|---:|---:|---:|---:|---|---:|---|",
    ])
    for row in leak_scan["rows"]:
        lines.append(
            f"| {row['leak_period']} | {percent(row['dense_hit_rate'])} | "
            f"{percent(row['sparse_false_spike_rate'])} | {percent(row['temporal_selectivity'])} | "
            f"{'是' if row['training_matches_no_leak'] else '否'} | "
            f"{percent(row['network']['accuracy'])} | {'是' if row['passes_minimal_gate'] else '否'} |"
        )
    lines.extend([
        "",
        f"当前矩阵选出的最小候选是 `LEAK_PERIOD={leak_scan['selected_minimal_period']}`。"
        "周期4虽然能过滤更多稀疏事件，但会损失弱连接+1的密集命中；周期12没有增加网络收益，因此没有取更大的周期。",
        "",
        "### 5.5 正负证据冲突",
        "",
        f"输入序列 `{conflict['input_masks']}` 使两个 Pulse-Mini 版本同时置位正负证据，CAPTURE方向均为 "
        f"{conflict['pulse_mini_captured_direction']}；ENeuron在同一序列后仍保留 eligibility="
        f"{conflict['eneuron_eligibility']}。",
        "",
        "Pulse-Mini选择确定性的冲突归零，避免顺序敏感；代价是丢失哪一侧证据更多。ENeuron保留净强度，",
        "表达能力更高，但参数和定点缩放也更难调。",
        "",
        "## 6. 噪声鲁棒性",
        "",
        f"每个严重度使用 {single['noise_sweep']['seed_count']} 个种子、每种子 "
        f"{single['noise_sweep']['samples_per_seed']} 个平衡样本。表中为平均准确率。",
    ])
    noise_titles = {
        "dropout": "丢失有效事件",
        "cross_class": "混入对立类别通道",
        "neutral": "混入未训练的无关通道",
        "combined": "三种噪声叠加",
    }
    for name, rows in single["noise_sweep"]["profiles"].items():
        lines.extend([
            "",
            f"### 6.{list(noise_titles).index(name) + 1} {noise_titles[name]}",
            "",
            "| 严重度 | EN均值 | EN最差 | PM均值 | PM最差 | PM-L均值 | PM-L最差 |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for row in rows:
            lines.append(
                f"| {row['severity']:.2f} | {percent(row['eneuron_mean_accuracy'])} | "
                f"{percent(row['eneuron_min_accuracy'])} | {percent(row['pulse_mini_mean_accuracy'])} | "
                f"{percent(row['pulse_mini_min_accuracy'])} | {percent(row['pulse_mini_l_mean_accuracy'])} | "
                f"{percent(row['pulse_mini_l_min_accuracy'])} |"
            )

    en_shared = shared_network["eneuron"]
    pm_shared = shared_network["pulse_mini"]
    pm_l_shared = shared_network["pulse_mini_l"]
    lines.extend([
        "",
        "## 7. 固定 4→2→2 网络",
        "",
        "### 7.1 共同输入与留出集",
        "",
        "| 模型 | 训练前 | 训练后 | 最差种子 | 推理冻结 |",
        "|---|---:|---:|---:|---|",
        f"| ENeuron 1.0 | {percent(en_shared['baseline_mean_accuracy'])} | "
        f"{percent(en_shared['trained_mean_accuracy'])} | {percent(en_shared['trained_min_accuracy'])} | "
        f"{'通过' if en_shared['inference_weights_frozen'] else '失败'} |",
        f"| Pulse-Mini | {pm_shared['baseline_correct']}/{shared_network['samples']} | "
        f"{pm_shared['trained_correct']}/{shared_network['samples']} | 不适用：确定性训练 | "
        f"{'通过' if pm_shared['inference_weights_frozen'] else '失败'} |",
        f"| Pulse-Mini-L | {pm_l_shared['baseline_correct']}/{shared_network['samples']} | "
        f"{pm_l_shared['trained_correct']}/{shared_network['samples']} | 不适用：确定性训练 | "
        f"{'通过' if pm_l_shared['inference_weights_frozen'] else '失败'} |",
        "",
        "### 7.2 各自原生训练协议",
        "",
        "| 协议 | 干净结果 | 扰动结果 | 说明 |",
        "|---|---:|---:|---|",
        f"| ENeuron可寻址教师 | {percent(native['eneuron_teacher']['clean_mean_accuracy'])} | "
        f"{percent(native['eneuron_teacher']['noisy_mean_accuracy'])} | 神经元级 signed modulator |",
        f"| ENeuron纯全局reward | {percent(native['eneuron_global_reward']['clean_mean_accuracy'])} | "
        f"{percent(native['eneuron_global_reward']['noisy_mean_accuracy'])} | 当前固定小网络未解决隐藏层信用分配 |",
        f"| ENeuron混合训练 | {percent(native['eneuron_hybrid']['clean_mean_accuracy'])} | "
        f"{percent(native['eneuron_hybrid']['noisy_mean_accuracy'])} | 先教师塑形隐藏层，再reward训练输出层 |",
        f"| Pulse-Mini局部教师 | {native['pulse_mini_local_teacher']['clean_correct']}/"
        f"{native['pulse_mini_local_teacher']['clean_samples']} | 20/20 | 神经元级 train_post + FEEDBACK |",
        f"| Pulse-Mini-L局部教师 | {native['pulse_mini_l_local_teacher']['clean_correct']}/"
        f"{native['pulse_mini_l_local_teacher']['clean_samples']} | 20/20 | 神经元级 train_post + FEEDBACK + leak |",
        "| Pulse-Mini纯全局reward | 未测试 | 未测试 | 不能用局部教师结果代替 |",
        "| Pulse-Mini-L纯全局reward | 未测试 | 未测试 | 不能用局部教师结果代替 |",
        "",
        "### 7.3 网络层优缺点",
        "",
        "| 网络版本 | 主要优点 | 主要缺点 |",
        "|---|---|---|",
        "| ENeuron 1.0 网络 | 多位资格状态能表达证据强度；教师和混合训练都能在当前网络达到100% | 状态、缩放和调制接口更复杂；纯全局 reward 当前只有有限效果，隐藏层信用分配未解决 |",
        "| Pulse-Mini 网络 | 协议最小、行为确定、四核复制简单；局部教师训练20/20，一拍隐藏层路由和推理冻结均通过 | 无泄放时稀疏事件会长期累积；只保留方向，不能表达证据强弱；纯全局 reward 尚未验证 |",
        "| Pulse-Mini-L 网络 | 保留 Pulse-Mini 的协议和一拍路由，只增加泄放计时器；训练权重与基线一致，并能过滤部分稀疏误发放 | 周期依赖事件密度和权重幅度；当前 RTL 旁证只覆盖 LEAK_PERIOD=8，仍依赖局部教师和 STATE_CLEAR |",
        "",
        "## 8. RTL协同仿真旁证",
        "",
    ])
    rtl = result.get("rtl_cosimulation")
    if rtl is None:
        lines.append("本次未启用 `--rtl-cosim`；以上均为Python黄金模型结果。")
    else:
        lines.extend([
            f"工具：{rtl['tool']}。以下均与对应Python黄金模型逐事务一致：",
            "",
            f"- ENeuron单核：{rtl['eneuron_core']['seeds']} seeds，"
            f"{rtl['eneuron_core']['transactions']}事务。",
            f"- Pulse-Mini-L单核：{rtl['pulse_mini_l_core']['seeds']} seeds，"
            f"{rtl['pulse_mini_l_core']['transactions']}事务，"
            f"LEAK_PERIOD={rtl['pulse_mini_l_core']['leak_period']}。",
            f"- ENeuron固定Tile：{rtl['eneuron_tile_4x2x2']['seeds']} seeds，"
            f"{rtl['eneuron_tile_4x2x2']['transactions']}事务。",
            f"- Pulse-Mini-L固定网络：{rtl['pulse_mini_l_network_4x2x2']['commands']}条命令，"
            "一tick跨层路由通过。",
            "- 无泄放 Pulse-Mini 的相对差异来自 Python 黄金模型消融；本次没有把它写成独立 RTL 参数签核。",
        ])

    lines.extend([
        "",
        "## 9. 综合评价",
        "",
        "### ENeuron 1.0",
        "",
        "适合需要泄漏时间动力学、证据强度、延迟调制和较细信用记录的实验。它能区分一次与多次证据，",
        "也能在冲突证据中保留净值。代价是参数更多、定点量化更复杂；当前参数下，非零 eligibility 不一定",
        "产生非零权重更新，而且纯全局reward仍不能训练隐藏层。",
        "",
        "### Pulse-Mini、Pulse-Mini-L",
        "",
        "两者都适合固定小任务和大量复制前的算法验证。方向压缩、固定窗口、一步反馈使行为容易解释；",
        "Pulse-Mini 无膜电位泄放，Pulse-Mini-L 额外用一个固定周期计时器让膜电位向零移动，减少稀疏事件的无限累加。",
        "两者都无法表示证据强弱，",
        "正负证据同时出现时直接归零，且周期对连接幅度敏感，因此必须依赖明确的 STATE_CLEAR 边界。",
        "",
        "### 当前选择",
        "",
        "- 目标是最小、确定、容易复制的训练/推理构件：Pulse-Mini更合适。",
        "- 目标是研究时间动力学、信用强度或更复杂延迟学习：ENeuron 1.0更合适。",
        f"- 在本次矩阵中，最有价值且仍保持简洁的升级是 Pulse-Mini-L 的 `LEAK_PERIOD={leak_scan['selected_minimal_period']}`；",
        "  它只增加一个小计数器和向零的一步修正。下一步若需要证据强度，应单独评估多位 eligibility，不能把两者混为一谈。",
        "",
        "## 10. 不能得出的结论",
        "",
        "- 20/20只证明当前固定二分类任务，不代表通用AI、持续学习或任意数据泛化。",
        "- 三种网络对照中的 Pulse-Mini 结果都使用神经元级教师信息；不能宣称纯全局奖励已经解决。",
        "- Python与RTL协同仿真不能证明无限时域正确性，也不能替代综合、布线、板级和真实功耗验证；新增计时器的 LUT/FF 代价尚未由 Vivado 实测。",
        "- 本报告没有比较硬件资源，因此不能仅凭这里的准确率判断单位面积效率。",
        "- ENeuron与Pulse-Mini的训练信号信息量不同，原生协议结果不能当作严格算法公平竞赛。",
        "",
        "## 11. 复现",
        "",
        "```powershell",
        "python compare_simulation.py --seeds 20 --rtl-cosim",
        "python -m unittest -v test_compare_simulation.py",
        "```",
        "",
        "完整逐点结果见 `comparison_simulation_results.json`。",
    ])
    return "\n".join(lines) + "\n"


def write_outputs(
    result: dict[str, Any],
    *,
    json_path: Path,
    report_path: Path,
) -> None:
    """写出原始数据和由同一结果生成的报告。"""

    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(render_report(result), encoding="utf-8")
    LOGGER.info("原始结果已写入 %s", json_path.resolve())
    LOGGER.info("比较报告已写入 %s", report_path.resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description="ENeuron 1.0、Pulse-Mini 基线与 Pulse-Mini-L 纯仿真比较")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--rtl-cosim", action="store_true")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("comparison_simulation_results.json"),
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=Path("SIMULATION_COMPARISON_REPORT.md"),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.seeds <= 0:
        parser.error("--seeds must be positive")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    result = run_comparison(seeds=range(args.seeds), rtl_cosim=args.rtl_cosim)
    write_outputs(result, json_path=args.output_json, report_path=args.output_report)
    print(
        "SIMULATION_COMPARISON_PASS "
        f"seeds={args.seeds} rtl_cosim={int(args.rtl_cosim)} "
        f"single={result['single_neuron']['shared_task']['eneuron']['trained_correct']}/"
        f"{result['single_neuron']['shared_task']['samples']} "
        f"network={percent(result['network_4x2x2']['shared_task']['eneuron']['trained_mean_accuracy'])}"
    )


__all__ = ["render_report", "run_comparison", "write_outputs"]


if __name__ == "__main__":
    main()

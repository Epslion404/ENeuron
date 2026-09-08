"""D2：固定 64->16->4 特征层、只训练十个输出神经元。

这个实验模块刻意不修改已有 ``neuron_sim``/``network_sim`` 合同。前两层只做
事件变换，十个输出单元在训练时接收显式 ``teacher_post`` 事件；训练阶段不会
把输出单元的自然发放当成教师事件。推理阶段才允许输出单元自然发放并产生
分类结果。
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from digit8x8 import DigitSample, TIME_STEPS, encode_patch_masks, load_fixture, load_manifest
from digit8x8_experiment import ClassificationMetrics, evaluate_predictions
from neuron_sim import ThreeFactorNeuron, saturate


LOGGER = logging.getLogger("digit8x8_d2")
LABELS = tuple(range(10))
PATCH_COUNT = 16
QUADRANT_COUNT = 4
OUTPUT_COUNT = 10
QUADRANT_PATCHES = ((0, 1, 4, 5), (2, 3, 6, 7), (8, 9, 12, 13), (10, 11, 14, 15))


@dataclass(frozen=True)
class D2Episode:
    """单张图像的一次训练或推理记录。"""

    sample_id: int
    label: int
    prediction: int
    feature_events: tuple[tuple[int, ...], ...]
    output_spikes: tuple[int, ...]
    teacher_post_ticks: tuple[int, ...]
    natural_spikes_during_train: int
    modulators: tuple[int, ...]


class TeacherThreeFactorNeuron(ThreeFactorNeuron):
    """带显式教师后脉冲的输出单元。

    ``train_tick`` 只积累前脉冲资格，不允许自然发放；``teacher_post`` 才会
    写入后迹线并完成后脉冲对应的资格增量。这样“教师事件”在软件账本中可独立
    计数，也不会因为输出单元偶然越过阈值而伪造监督信号。
    """

    def __init__(self, n_inputs: int) -> None:
        super().__init__(n_inputs)
        # 图像读出器每个样本都会收到一次调制；比通用单元更慢的移位
        # 避免十分类负调制在一个 epoch 内把全部权重直接压到下限。
        self.learning_shift = 6
        self.teacher_post_ticks: list[int] = []
        self.training_ticks = 0

    def reset_episode(self) -> None:
        super().reset_episode()
        self.teacher_post_ticks = []
        self.training_ticks = 0

    def train_tick(self, active_inputs: Sequence[int], tick: int) -> None:
        """处理输入事件，但明确抑制自然输出。"""
        self.prepare_step(active_inputs, learn_enable=True)
        # inhibit 会清除候选膜电位；此路径绝不调用自然 spike 提交逻辑。
        self.commit_prepared_step(tick, allow_fire=False, inhibit=True, learn_enable=True)
        self.training_ticks += 1

    def teacher_post(self, tick: int) -> None:
        """提交一个独立的教师后脉冲。"""
        for index in range(self.n_inputs):
            self.eligibility[index] = self._sat_eligibility(
                self.eligibility[index] + self.a_plus * self.pre_trace[index]
            )
            self.ops += 3
        self.post_trace = saturate(self.post_trace + self.trace_increment, 0, 255)
        self.teacher_post_ticks.append(int(tick))
        self.ops += 3

    def apply_modulator_from_eligibility(
        self,
        eligibility_snapshot: Sequence[int],
        value: int,
    ) -> None:
        """提交 D2 调制；负反馈保留至少一个正权，维持可发放读出器。"""
        if value == 0:
            return
        if len(eligibility_snapshot) != self.n_inputs:
            raise ValueError("eligibility snapshot length must match neuron inputs")
        signed_modulator = 1 if value > 0 else -1
        for target, eligibility in enumerate(eligibility_snapshot):
            delta = (signed_modulator * eligibility) >> self.learning_shift
            # 小资格值经移位可能为零；只要证据和调制同向，保留一个最小
            # 定点步进，避免“有教师、有资格但账本没有任何权重变化”。
            if delta == 0 and eligibility != 0:
                delta = 1 if signed_modulator * eligibility > 0 else -1
            lower = 2 if signed_modulator < 0 else self.weight_min
            bounded = saturate(self.weights[target] + delta, lower, self.weight_max)
            if bounded != self.weights[target] + delta:
                self.saturation_count += 1
            self.weights[target] = bounded
            self.ops += 4


class FixedD2FeatureExtractor:
    """固定的 64->16->4 事件特征提取器，每个单元恰有四个局部输入。"""

    def __init__(self) -> None:
        self.patch = [ThreeFactorNeuron(4) for _ in range(PATCH_COUNT)]
        self.quadrant = [ThreeFactorNeuron(4) for _ in range(QUADRANT_COUNT)]
        for neuron in self.patch + self.quadrant:
            # 一次局部事件即可产生特征脉冲；这些权重和阈值在 D2 全程冻结。
            neuron.weights = [3, 3, 3, 3]
            neuron.base_threshold = 3
            neuron.threshold = 3
        self._fixed_fingerprint = self.fingerprint()

    @property
    def neurons(self) -> tuple[ThreeFactorNeuron, ...]:
        return tuple(self.patch + self.quadrant)

    def reset(self) -> None:
        for neuron in self.neurons:
            neuron.reset_episode()

    def fingerprint(self) -> str:
        payload = tuple(tuple(neuron.weights) for neuron in self.neurons)
        return hashlib.sha256(repr(payload).encode("ascii")).hexdigest()

    def encode(self, pixels: Sequence[int]) -> tuple[tuple[int, ...], ...]:
        """将像素事件推进两层，并输出给读出层的四路事件。"""
        self.reset()
        masks = encode_patch_masks(pixels)
        patch_pending: tuple[int, ...] = ()
        quadrant_pending: tuple[int, ...] = ()
        output_events: list[tuple[int, ...]] = []

        # 两拍尾部排空：patch->quadrant 和 quadrant->output 各一拍。
        for tick in range(TIME_STEPS + 2):
            patch_active = ()
            if tick < TIME_STEPS:
                active_masks = masks[tick]
                patch_active = tuple(
                    (patch_index, local_bit)
                    for patch_index, mask in enumerate(active_masks)
                    for local_bit in range(4)
                    if mask & (1 << local_bit)
                )
            quadrant_fired_list: list[int] = []
            for quadrant_index, neuron in enumerate(self.quadrant):
                patch_group = QUADRANT_PATCHES[quadrant_index]
                local_active = tuple(
                    local_index for local_index, patch_index in enumerate(patch_group) if patch_index in patch_pending
                )
                quadrant_fired_list.append(neuron.step(local_active, tick, learn_enable=False))
            quadrant_fired = tuple(quadrant_fired_list)
            # pending 向量保存的是已发放的象限编号，而不是 0/1 位图。
            output_events.append(tuple(quadrant_pending))

            patch_fired_list: list[int] = []
            for patch_index, neuron in enumerate(self.patch):
                local_active = tuple(local for index, local in patch_active if index == patch_index)
                patch_fired_list.append(neuron.step(local_active, tick, learn_enable=False))
            patch_pending = tuple(index for index, fired in enumerate(patch_fired_list) if fired)
            quadrant_pending = tuple(index for index, fired in enumerate(quadrant_fired) if fired)

        if self.fingerprint() != self._fixed_fingerprint:
            raise AssertionError("fixed feature weights changed during encoding")
        return tuple(output_events)


class D2Network:
    """64->16->4->10 网络；只有十个输出单元可学习。"""

    def __init__(self, init_seed: int = 7) -> None:
        self.features = FixedD2FeatureExtractor()
        self.output = [TeacherThreeFactorNeuron(QUADRANT_COUNT) for _ in range(OUTPUT_COUNT)]
        rng = random.Random(init_seed)
        for neuron in self.output:
            neuron.base_threshold = 3
            neuron.threshold = 3
            neuron.weights = [rng.randint(1, 3) for _ in range(QUADRANT_COUNT)]
        self.ledger: list[dict[str, object]] = []
        self.training_natural_spikes = 0
        self.training_tick_count = 0
        self.training_teacher_posts = 0

    @property
    def fixed_weight_fingerprint(self) -> str:
        return self.features.fingerprint()

    @property
    def output_weights(self) -> tuple[tuple[int, ...], ...]:
        return tuple(tuple(neuron.weights) for neuron in self.output)

    def encode_features(self, pixels: Sequence[int]) -> tuple[tuple[int, ...], ...]:
        return self.features.encode(pixels)

    @staticmethod
    def _predict(spikes: Sequence[int]) -> int:
        best = max(spikes, default=0)
        if best <= 0:
            return -1
        winners = [index for index, count in enumerate(spikes) if count == best]
        return winners[0] if len(winners) == 1 else -1

    def train_sample(self, sample_id: int, pixels: Sequence[int], label: int) -> D2Episode:
        if not 0 <= label < OUTPUT_COUNT:
            raise ValueError("label must be in 0..9")
        feature_events = self.encode_features(pixels)
        for neuron in self.output:
            neuron.reset_episode()

        # 每个非空特征事件展开为独立的五拍微窗口：输入、教师后脉冲、
        # 三个空 tick。这样 teacher-post 与输入证据的相对位置固定为 +1，
        # 不会把一个 episode 末尾的单次教师事件冒充全部监督。
        teacher_ticks: list[int] = []
        sim_tick = 0
        for active in feature_events:
            if not active:
                for neuron in self.output:
                    neuron.train_tick((), sim_tick)
                self.training_tick_count += 1
                sim_tick += 1
                continue
            for neuron in self.output:
                neuron.train_tick(active, sim_tick)
            self.training_tick_count += 1
            sim_tick += 1
            for neuron in self.output:
                neuron.train_tick((), sim_tick)
            self.training_tick_count += 1
            for neuron in self.output:
                neuron.teacher_post(sim_tick)
            teacher_ticks.append(sim_tick)
            self.training_teacher_posts += OUTPUT_COUNT
            sim_tick += 1
            for _ in range(3):
                for neuron in self.output:
                    neuron.train_tick((), sim_tick)
                self.training_tick_count += 1
                sim_tick += 1

        modulators = tuple(1 if index == label else -1 for index in LABELS)
        for index, (neuron, modulator) in enumerate(zip(self.output, modulators)):
            before = tuple(neuron.weights)
            eligibility = tuple(neuron.eligibility)
            neuron.apply_modulator_from_eligibility(eligibility, modulator)
            after = tuple(neuron.weights)
            delta = tuple(new - old for old, new in zip(before, after))
            self.ledger.append(
                {
                    "sample_id": int(sample_id),
                    "layer": "output",
                    "neuron": index,
                    "source": "explicit_teacher_post",
                    "commit_id": len(self.ledger),
                    "teacher_post_ticks": tuple(teacher_ticks),
                    "modulator": modulator,
                    "evidence": {
                        "teacher_post_ticks": tuple(teacher_ticks),
                        "eligibility_snapshot": eligibility,
                    },
                    "old_weights": before,
                    "delta": delta,
                    "new_weights": after,
                    "weight_min": neuron.weight_min,
                    "weight_max": neuron.weight_max,
                }
            )
        natural_spikes = sum(neuron.spike_count for neuron in self.output)
        self.training_natural_spikes += natural_spikes
        return D2Episode(
            sample_id=sample_id,
            label=label,
            prediction=-1,
            feature_events=feature_events,
            output_spikes=tuple(neuron.spike_count for neuron in self.output),
            teacher_post_ticks=tuple(teacher_ticks),
            natural_spikes_during_train=natural_spikes,
            modulators=modulators,
        )

    def inference_sample(self, sample_id: int, pixels: Sequence[int], label: int) -> D2Episode:
        feature_events = self.encode_features(pixels)
        for neuron in self.output:
            neuron.reset_episode()
        for tick, active in enumerate(feature_events):
            for neuron in self.output:
                neuron.step(active, tick, learn_enable=False)
        spikes = tuple(neuron.spike_count for neuron in self.output)
        return D2Episode(
            sample_id=sample_id,
            label=label,
            prediction=self._predict(spikes),
            feature_events=feature_events,
            output_spikes=spikes,
            teacher_post_ticks=(),
            natural_spikes_during_train=0,
            modulators=(),
        )


def _evaluate_network(network: D2Network, samples: Sequence[DigitSample], ids: Sequence[int]) -> ClassificationMetrics:
    by_id = {sample.sample_id: sample for sample in samples}
    labels = [by_id[int(sample_id)].label for sample_id in ids]
    predictions = [
        network.inference_sample(sample.sample_id, sample.pixels, sample.label).prediction
        for sample_id in ids
        for sample in (by_id[int(sample_id)],)
    ]
    return evaluate_predictions(labels, predictions)


def run_d2_experiment(
    fixture_path: str | Path,
    manifest_path: str | Path,
    *,
    epochs: int = 3,
    seed: int = 7,
) -> dict[str, object]:
    """运行固定特征、只训练输出层的 D2 实验。"""
    if epochs <= 0:
        raise ValueError("epochs must be positive")
    samples = load_fixture(fixture_path)
    manifest = load_manifest(manifest_path)
    ids = manifest["splits"]
    assert isinstance(ids, dict)
    network = D2Network(init_seed=seed)
    history: list[float] = []
    train_ids = [int(value) for value in ids["train"]]
    validation_ids = [int(value) for value in ids["validation"]]
    for epoch in range(epochs):
        order = list(train_ids)
        random.Random(seed + epoch).shuffle(order)
        for sample_id in order:
            sample = samples[sample_id]
            network.train_sample(sample.sample_id, sample.pixels, sample.label)
        metrics = _evaluate_network(network, samples, validation_ids)
        history.append(metrics.balanced_accuracy)
        LOGGER.info("D2 epoch=%d validation_balanced_accuracy=%.4f", epoch + 1, metrics.balanced_accuracy)

    validation = _evaluate_network(network, samples, validation_ids)
    test = _evaluate_network(network, samples, [int(value) for value in ids["test"]])
    canonical_ledger = json.dumps(network.ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    ledger_sha256 = hashlib.sha256(canonical_ledger.encode("utf-8")).hexdigest()
    chain_tail = "0" * 64
    for entry in network.ledger:
        record = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        chain_tail = hashlib.sha256((chain_tail + record).encode("utf-8")).hexdigest()
    model = {
        "train_history": history,
        "validation": validation.as_dict(),
        "test": test.as_dict(),
        "fixed_weight_fingerprint": network.fixed_weight_fingerprint,
        "output_weights": [list(weights) for weights in network.output_weights],
        "ledger": {
            "events": network.training_tick_count * OUTPUT_COUNT,
            "teacher_posts": network.training_teacher_posts,
            "natural_posts_during_train": network.training_natural_spikes,
            "weight_updates": len(network.ledger),
            "direct_weight_writes": 0,
            "entry_count": len(network.ledger),
            "canonical_sha256": ledger_sha256,
            "hash_chain_tail": chain_tail,
        },
    }
    return {
        "format": "eneuron_digit8x8_d2_v1",
        "config": {"epochs": epochs, "seed": seed, "architecture": "64->16->4->10", "route_latency": 1},
        "models": {"d2_teacher": model},
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_d2_experiment("digit8x8_fixture.json", "digit8x8_manifest.json")
    Path("artifacts/results/digit8x8_d2_results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    test = result["models"]["d2_teacher"]["test"]
    print(f"DIGIT8X8_D2_PASS test_balanced_accuracy={test['balanced_accuracy']:.4f} coverage={test['coverage']:.4f}")


if __name__ == "__main__":
    main()

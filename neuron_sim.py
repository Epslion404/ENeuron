"""硬件友好的单脉冲神经元候选比较器。

脚本只使用 Python 标准库，模拟三种候选：
1. 原始无泄漏计数器 IF 基线；
2. 有符号 LIF + 二因子 STDP；
3. 有符号 LIF + 资格迹线 + 有符号调制端口（推荐候选）。

输出包含训练/推理结果、权重变化和状态位数/事件操作数代理指标。
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


LOGGER = logging.getLogger("neuron_sim")


def saturate(value: int, low: int, high: int) -> int:
    """有界定点运算，禁止权重和状态回绕。"""
    return max(low, min(high, value))


def decay_toward_zero(value: int, shift: int) -> int:
    """用移位近似漏电；对小数值保留至少一个单位的衰减。"""
    if value == 0 or shift < 0:
        return value
    magnitude = abs(value)
    decrement = max(1, magnitude >> shift)
    next_magnitude = max(0, magnitude - decrement)
    return next_magnitude if value >= 0 else -next_magnitude


TickEvents = tuple[int, ...]
TrialEvents = tuple[TickEvents, ...]


@dataclass(frozen=True)
class TrialResult:
    label: int
    spike_count: int
    spike_ticks: tuple[int, ...]


class BaseNeuron:
    """所有候选共用的事件驱动接口。"""

    name = "base"

    def __init__(
        self,
        n_inputs: int,
        threshold: int = 6,
        reset_value: int = 0,
        refractory_length: int = 1,
        weight_min: int = -7,
        weight_max: int = 7,
        initial_weight: int = 2,
        state_limit: int = 32767,
    ) -> None:
        self.n_inputs = n_inputs
        self.base_threshold = threshold
        self.threshold = threshold
        self.reset_value = reset_value
        self.refractory_length = refractory_length
        self.weight_min = weight_min
        self.weight_max = weight_max
        self.state_limit = state_limit
        self.weights = [saturate(initial_weight, weight_min, weight_max) for _ in range(n_inputs)]
        self.v = reset_value
        self.current = 0
        self.refractory = 0
        self.spike_count = 0
        self.spike_ticks: list[int] = []
        self.ops = 0
        self.saturation_count = 0

    def reset_episode(self) -> None:
        """清除动态状态但保留权重，便于按 trial 训练或评估。"""
        self.v = self.reset_value
        self.current = 0
        self.refractory = 0
        self.spike_count = 0
        self.spike_ticks = []
        self._reset_learning_state()

    def _reset_learning_state(self) -> None:
        pass

    def _sat_state(self, value: int) -> int:
        bounded = saturate(value, -self.state_limit - 1, self.state_limit)
        if bounded != value:
            self.saturation_count += 1
        return bounded

    def _sat_weight(self, index: int, value: int) -> None:
        bounded = saturate(value, self.weight_min, self.weight_max)
        if bounded != value:
            self.saturation_count += 1
        self.weights[index] = bounded

    def step(self, active_inputs: Iterable[int], tick: int, learn_enable: bool = True) -> int:
        raise NotImplementedError

    def run_trial(
        self,
        events: TrialEvents,
        label: int,
        modulator: int = 0,
        train: bool = False,
        learn_enable: bool | None = None,
    ) -> TrialResult:
        if learn_enable is None:
            learn_enable = train
        self.reset_episode()
        for tick, active in enumerate(events):
            self.step(active, tick, learn_enable=learn_enable)
        self.apply_modulator(modulator if train else 0)
        return TrialResult(label, self.spike_count, tuple(self.spike_ticks))

    def apply_modulator(self, value: int) -> None:
        del value

    def inference(self, events: TrialEvents, label: int = 0) -> TrialResult:
        return self.run_trial(events, label=label, train=False, learn_enable=False)

    def complexity(self) -> dict[str, int | str]:
        raise NotImplementedError


class CounterIFNeuron(BaseNeuron):
    """原始方案的抽象基线：无符号、无漏电、无学习。"""

    name = "counter_if"

    def __init__(self, n_inputs: int) -> None:
        super().__init__(
            n_inputs=n_inputs,
            threshold=6,
            refractory_length=1,
            weight_min=0,
            weight_max=7,
            initial_weight=2,
        )

    def step(self, active_inputs: Iterable[int], tick: int, learn_enable: bool = True) -> int:
        del learn_enable
        if self.refractory > 0:
            self.refractory -= 1
            self.v = self.reset_value
            return 0
        for index in active_inputs:
            if 0 <= index < self.n_inputs:
                self.v = self._sat_state(self.v + self.weights[index])
                self.ops += 2  # 加法 + 饱和比较
        if self.v >= self.threshold:
            self.spike_count += 1
            self.spike_ticks.append(tick)
            self.v = self.reset_value
            self.refractory = self.refractory_length
            self.ops += 2  # 阈值比较 + 发放状态机
            return 1
        self.ops += 1
        return 0

    def complexity(self) -> dict[str, int | str]:
        # counter1 + divider1 的状态位作为原始方案代理，不等价于综合后的 LUT 数。
        bits = self.n_inputs * (8 + 8) + 16 + 4
        return {
            "name": self.name,
            "state_bits": bits,
            "event_ops": 3,
            "learning_ops": 0,
        }


class PairSTDPNeuron(BaseNeuron):
    """有符号 LIF 和局部二因子 STDP。"""

    name = "pair_stdp_lif"

    def __init__(self, n_inputs: int) -> None:
        super().__init__(n_inputs=n_inputs, threshold=6, refractory_length=1)
        self.leak_shift = 2
        self.current_leak_shift = 2
        self.trace_shift = 2
        self.trace_increment = 8
        self.a_plus = 2
        self.a_minus = 2
        self.learning_shift = 3
        self.pre_trace = [0 for _ in range(n_inputs)]
        self.post_trace = 0

    def _reset_learning_state(self) -> None:
        self.pre_trace = [0 for _ in range(self.n_inputs)]
        self.post_trace = 0

    def _decay_traces(self) -> None:
        self.pre_trace = [decay_toward_zero(value, self.trace_shift) for value in self.pre_trace]
        self.post_trace = decay_toward_zero(self.post_trace, self.trace_shift)
        self.ops += self.n_inputs + 1

    def step(self, active_inputs: Iterable[int], tick: int, learn_enable: bool = True) -> int:
        if learn_enable:
            self._decay_traces()
        active = tuple(sorted(set(active_inputs)))
        effective_active = () if self.refractory > 0 else active
        if learn_enable:
            for index in effective_active:
                if 0 <= index < self.n_inputs:
                    self.pre_trace[index] = saturate(self.pre_trace[index] + self.trace_increment, 0, 255)
                    delta = (self.a_minus * self.post_trace) >> self.learning_shift
                    self._sat_weight(index, self.weights[index] - delta)
                    self.ops += 4

        self.current = self._sat_state(decay_toward_zero(self.current, self.current_leak_shift))
        for index in effective_active:
            self.current = self._sat_state(self.current + self.weights[index])
            self.ops += 2
        self.v = self._sat_state(decay_toward_zero(self.v, self.leak_shift) + self.current)
        self.ops += 2

        fired = 0
        if self.refractory > 0:
            self.refractory -= 1
            self.v = self.reset_value
        elif self.v >= self.threshold:
            fired = 1
            self.spike_count += 1
            self.spike_ticks.append(tick)
            self.v = self.reset_value
            self.refractory = self.refractory_length
            if learn_enable:
                for index in range(self.n_inputs):
                    delta = (self.a_plus * self.pre_trace[index]) >> self.learning_shift
                    self._sat_weight(index, self.weights[index] + delta)
                    self.ops += 2
                self.post_trace = saturate(self.post_trace + self.trace_increment, 0, 255)
                self.ops += 3
        return fired

    def complexity(self) -> dict[str, int | str]:
        bits = self.n_inputs * (8 + 8) + 8 + 16 + 16 + 4
        return {
            "name": self.name,
            "state_bits": bits,
            "event_ops": 9,
            "learning_ops": 4,
        }


class ThreeFactorNeuron(PairSTDPNeuron):
    """推荐候选：LIF + STDP 资格迹线 + 有符号第三因子。"""

    name = "three_factor_lif"

    def __init__(self, n_inputs: int) -> None:
        super().__init__(n_inputs=n_inputs)
        self.eligibility = [0 for _ in range(n_inputs)]
        self.eligibility_shift = 2
        self.silent_credit_gain = 2
        self.eligibility_limit = 2047
        self.learning_shift = 3
        self.homeostasis_increment = 1
        self.homeostasis_shift = 4
        self.prepared_refractory = False
        self.prepared_learn_enable = True

    def _reset_learning_state(self) -> None:
        super()._reset_learning_state()
        self.eligibility = [0 for _ in range(self.n_inputs)]
        self.threshold = self.base_threshold

    def _decay_traces(self) -> None:
        super()._decay_traces()
        self.eligibility = [decay_toward_zero(value, self.eligibility_shift) for value in self.eligibility]
        self.ops += self.n_inputs

    def _sat_eligibility(self, value: int) -> int:
        bounded = saturate(value, -self.eligibility_limit - 1, self.eligibility_limit)
        if bounded != value:
            self.saturation_count += 1
        return bounded

    def prepare_step(self, active_inputs: Iterable[int], learn_enable: bool = True) -> int:
        """完成衰减和积分，但把阈值发放留给层级 WTA 仲裁器。"""
        if learn_enable:
            self._decay_traces()
        active = tuple(sorted(set(active_inputs)))
        if any(index < 0 or index >= self.n_inputs for index in active):
            raise ValueError("input spike index out of range")
        self.prepared_refractory = self.refractory > 0
        self.prepared_learn_enable = learn_enable
        effective_active = () if self.prepared_refractory else active
        if learn_enable:
            for index in effective_active:
                if 0 <= index < self.n_inputs:
                    self.pre_trace[index] = saturate(self.pre_trace[index] + self.trace_increment, 0, 255)
                    # silent_credit_gain 是显式的可选第三因子资格项，不伪装成 A_plus。
                    self.eligibility[index] = self._sat_eligibility(
                        self.eligibility[index]
                        + self.pre_trace[index] * self.silent_credit_gain
                        - self.a_minus * self.post_trace
                    )
                    self.ops += 7

        self.current = self._sat_state(
            decay_toward_zero(self.current, self.current_leak_shift)
            + sum(self.weights[index] for index in effective_active)
        )
        self.ops += 2 * len(effective_active)
        self.v = self._sat_state(decay_toward_zero(self.v, self.leak_shift) + self.current)
        self.ops += 2

        if self.prepared_refractory:
            self.refractory -= 1
            self.v = self.reset_value
        return self.v

    def commit_prepared_step(
        self,
        tick: int,
        allow_fire: bool = True,
        inhibit: bool = False,
        learn_enable: bool | None = None,
    ) -> int:
        """提交阈值结果；WTA 可禁止或抑制本神经元的候选 spike。"""
        if learn_enable is None:
            learn_enable = self.prepared_learn_enable
        fired = 0
        if inhibit and not self.prepared_refractory:
            self.v = self.reset_value
            self.current = 0
        elif not self.prepared_refractory and allow_fire and self.v >= self.threshold:
            fired = 1
            self.spike_count += 1
            self.spike_ticks.append(tick)
            self.v = self.reset_value
            self.refractory = self.refractory_length
            if learn_enable:
                for index in range(self.n_inputs):
                    self.eligibility[index] = self._sat_eligibility(
                        self.eligibility[index] + self.a_plus * self.pre_trace[index]
                    )
                    self.ops += 3
                self.post_trace = saturate(self.post_trace + self.trace_increment, 0, 255)
                self.threshold = min(self.threshold + self.homeostasis_increment, 31)
                self.ops += 5

        # 阈值在安静时缓慢回落，避免永久抬高。
        if learn_enable and not fired and self.threshold > self.base_threshold:
            self.threshold -= max(1, (self.threshold - self.base_threshold) >> self.homeostasis_shift)
        self.prepared_refractory = False
        return fired

    def step(self, active_inputs: Iterable[int], tick: int, learn_enable: bool = True) -> int:
        self.prepare_step(active_inputs, learn_enable=learn_enable)
        return self.commit_prepared_step(tick, learn_enable=learn_enable)

    def apply_modulator(self, value: int) -> None:
        if value == 0:
            return
        self.apply_modulator_from_eligibility(tuple(self.eligibility), value)

    def apply_modulator_from_eligibility(
        self,
        eligibility_snapshot: Sequence[int],
        value: int,
    ) -> None:
        """从 episode 快照提交调制，模拟片外总线延迟期间的 pending buffer。"""
        if value == 0:
            return
        signed_modulator = 1 if value > 0 else -1
        if len(eligibility_snapshot) != self.n_inputs:
            raise ValueError("eligibility snapshot length must match neuron inputs")
        for target, eligibility in enumerate(eligibility_snapshot):
            delta = (signed_modulator * eligibility) >> self.learning_shift
            self._sat_weight(target, self.weights[target] + delta)
            self.ops += 4

    def complexity(self) -> dict[str, int | str]:
        bits = self.n_inputs * (8 + 8 + 12) + 8 + 16 + 16 + 4 + 8 + 5
        return {
            "name": self.name,
            "state_bits": bits,
            "event_ops": 16,
            "learning_ops": 4,
        }


def make_trial(label: int, length: int = 12) -> TrialEvents:
    """两个事件数相同但通道不同的模式，避免计数器基线凭总脉冲数取巧。"""
    events: list[list[int]] = [[] for _ in range(length)]
    if label == 1:
        sequence = ((1, (0,)), (3, (1,)), (5, (0,)), (7, (1,)), (9, (0, 1)))
    else:
        sequence = ((1, (2,)), (3, (3,)), (5, (2,)), (7, (3,)), (9, (2, 3)))
    for tick, channels in sequence:
        events[tick].extend(channels)
    return tuple(tuple(sorted(tick_events)) for tick_events in events)


def train_and_evaluate(seed: int, epochs: int) -> dict[str, object]:
    rng = random.Random(seed)
    positive = make_trial(1)
    negative = make_trial(0)
    candidates: list[BaseNeuron] = [
        CounterIFNeuron(4),
        PairSTDPNeuron(4),
        ThreeFactorNeuron(4),
    ]
    report: dict[str, object] = {}

    for neuron in candidates:
        initial_weights = list(neuron.weights)
        for epoch in range(epochs):
            order = [1, 0]
            rng.shuffle(order)
            for label in order:
                events = positive if label == 1 else negative
                # 有符号调制代表局部奖励/惩罚；基线和二因子模型会忽略它。
                modulator = 1 if label == 1 else -1
                neuron.run_trial(events, label=label, modulator=modulator, train=True)

        positive_result = neuron.inference(positive, label=1)
        negative_result = neuron.inference(negative, label=0)
        report[neuron.name] = {
            "initial_weights": initial_weights,
            "final_weights": list(neuron.weights),
            "positive_spikes": positive_result.spike_count,
            "negative_spikes": negative_result.spike_count,
            "separated": positive_result.spike_count > negative_result.spike_count,
            "complexity": neuron.complexity(),
            "saturation_count": neuron.saturation_count,
        }

    return {
        "seed": seed,
        "epochs": epochs,
        "task": "equal-count channel discrimination",
        "candidates": report,
    }


def print_report(result: dict[str, object]) -> None:
    print("单神经元候选模拟结果")
    print(f"任务: {result['task']}; epochs={result['epochs']}; seed={result['seed']}")
    print("候选                 正样本脉冲  负样本脉冲  区分  状态位  事件操作  最终权重")
    print("-" * 92)
    candidates = result["candidates"]
    assert isinstance(candidates, dict)
    for name, item in candidates.items():
        assert isinstance(item, dict)
        complexity = item["complexity"]
        assert isinstance(complexity, dict)
        print(
            f"{name:<20} {item['positive_spikes']:>10}  {item['negative_spikes']:>10}  "
            f"{str(item['separated']):>4}  {complexity['state_bits']:>6}  "
            f"{complexity['event_ops']:>8}  {item['final_weights']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="比较硬件友好的单神经元候选")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/results/simulation_results.json"),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    result = train_and_evaluate(seed=args.seed, epochs=args.epochs)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.info("结果已写入 %s", args.output.resolve())
    print_report(result)


if __name__ == "__main__":
    main()

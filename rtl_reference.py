"""digital_lif_core.sv 的独立逐周期 Python 黄金模型。

该模型不复用 neuron_sim.py 的类层次，只复现冻结后的硬件状态方程：
固定宽度、有符号饱和、向零衰减、同 tick 的 pre/post 合并以及调制提交。
它是 RTL 仿真的参考，不是 HDL 编译器或综合器。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class RtlState:
    tick: int
    current: int
    membrane: int
    spike: int
    refractory: int
    threshold: int
    post_trace: int
    weights: tuple[int, ...]
    pre_trace: tuple[int, ...]
    eligibility: tuple[int, ...]
    snapshot_valid: int
    eligibility_snapshot: tuple[int, ...]


def saturate(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def decay_toward_zero(value: int, shift: int) -> int:
    """用移位近似漏电；正负值都向零收敛，最小衰减为一个单位。"""
    if value == 0 or shift < 0:
        return value
    magnitude = abs(value)
    decrement = max(1, magnitude >> shift)
    next_magnitude = max(0, magnitude - decrement)
    return next_magnitude if value > 0 else -next_magnitude


class RtlReferenceNeuron:
    """与 digital_lif_core.sv 参数对应的固定宽度状态机。"""

    def __init__(
        self,
        n_inputs: int = 4,
        threshold: int = 6,
        reset_value: int = 0,
        init_weight: int = 2,
        current_leak_shift: int = 2,
        membrane_leak_shift: int = 2,
        trace_decay_shift: int = 2,
        eligibility_decay_shift: int = 2,
        learning_shift: int = 3,
        trace_increment: int = 8,
        a_plus: int = 2,
        a_minus: int = 2,
        silent_credit_gain: int = 2,
        refractory_length: int = 1,
        threshold_increment: int = 1,
        threshold_relax_shift: int = 4,
        threshold_max: int = 31,
        weight_min: int = -7,
        weight_max: int = 7,
        state_min: int = -32768,
        state_max: int = 32767,
        trace_max: int = 255,
        elig_min: int = -2048,
        elig_max: int = 2047,
    ) -> None:
        self.n_inputs = n_inputs
        self.base_threshold = threshold
        self.threshold = threshold
        self.reset_value = reset_value
        self.current_leak_shift = current_leak_shift
        self.membrane_leak_shift = membrane_leak_shift
        self.trace_decay_shift = trace_decay_shift
        self.eligibility_decay_shift = eligibility_decay_shift
        self.learning_shift = learning_shift
        self.trace_increment = trace_increment
        self.a_plus = a_plus
        self.a_minus = a_minus
        self.silent_credit_gain = silent_credit_gain
        self.refractory_length = refractory_length
        self.threshold_increment = threshold_increment
        self.threshold_relax_shift = threshold_relax_shift
        self.threshold_max = threshold_max
        self.weight_min = weight_min
        self.weight_max = weight_max
        self.state_min = state_min
        self.state_max = state_max
        self.trace_max = trace_max
        self.elig_min = elig_min
        self.elig_max = elig_max
        self.current = reset_value
        self.membrane = reset_value
        self.refractory = 0
        self.post_trace = 0
        self.weights = [saturate(init_weight, weight_min, weight_max) for _ in range(n_inputs)]
        self.pre_trace = [0 for _ in range(n_inputs)]
        self.eligibility = [0 for _ in range(n_inputs)]
        self.snapshot_valid = False
        self.eligibility_snapshot = [0 for _ in range(n_inputs)]

    def _sat_state(self, value: int) -> int:
        return saturate(value, self.state_min, self.state_max)

    def _sat_trace(self, value: int) -> int:
        return saturate(value, 0, self.trace_max)

    def _sat_eligibility(self, value: int) -> int:
        return saturate(value, self.elig_min, self.elig_max)

    def _sat_weight(self, value: int) -> int:
        return saturate(value, self.weight_min, self.weight_max)

    def _decay_state(self, value: int, shift: int) -> int:
        return self._sat_state(decay_toward_zero(value, shift))

    def _decay_trace(self, value: int) -> int:
        return self._sat_trace(decay_toward_zero(value, self.trace_decay_shift))

    def _decay_eligibility(self, value: int) -> int:
        return self._sat_eligibility(decay_toward_zero(value, self.eligibility_decay_shift))

    def _relax_threshold(self, value: int) -> int:
        if value <= self.base_threshold:
            return value
        decrement = max(1, (value - self.base_threshold) >> self.threshold_relax_shift)
        return max(self.base_threshold, value - decrement)

    def tick(
        self,
        input_spikes: Iterable[int],
        learn_enable: bool = True,
        mod_valid: bool = False,
        modulator: int = 0,
        tick: int = 0,
        tick_valid: bool = True,
        state_clear: bool = False,
        snapshot_we: bool = False,
        weight_we: bool = False,
        weight_addr: int = 0,
        weight_wdata: int = 0,
    ) -> RtlState:
        """模拟一个 tick_valid 周期，所有 next 值只读取 tick 开始的旧状态。"""
        active = set(input_spikes)
        invalid = [index for index in active if index < 0 or index >= self.n_inputs]
        if invalid:
            raise ValueError("input spike index out of range")
        if weight_we and (weight_addr < 0 or weight_addr >= self.n_inputs):
            raise ValueError("weight address out of range")

        was_refractory = self.refractory != 0
        effective_active = () if was_refractory else tuple(sorted(active))
        next_current = self.current
        next_membrane_candidate = self.membrane
        next_refractory = self.refractory
        next_membrane = self.membrane
        spike = 0

        if tick_valid:
            next_current = self._sat_state(
                self._decay_state(self.current, self.current_leak_shift)
                + sum(self.weights[index] for index in effective_active)
            )
            next_membrane_candidate = self._sat_state(
                self._decay_state(self.membrane, self.membrane_leak_shift) + next_current
            )
            next_membrane = next_membrane_candidate

            if was_refractory:
                next_refractory = self.refractory - 1
                next_membrane = self.reset_value
            elif next_membrane_candidate >= self.threshold:
                spike = 1
                next_membrane = self.reset_value
                next_refractory = self.refractory_length

        next_pre_trace = list(self.pre_trace)
        next_post_trace = self.post_trace
        next_eligibility = list(self.eligibility)
        next_threshold = self.threshold

        if tick_valid and learn_enable:
            next_pre_trace = [self._decay_trace(value) for value in self.pre_trace]
            next_post_trace = self._decay_trace(self.post_trace)
            next_eligibility = [self._decay_eligibility(value) for value in self.eligibility]

            for index in effective_active:
                next_pre_trace[index] = self._sat_trace(
                    next_pre_trace[index] + self.trace_increment
                )
                next_eligibility[index] = self._sat_eligibility(
                    next_eligibility[index]
                    + next_pre_trace[index] * self.silent_credit_gain
                    - self.a_minus * next_post_trace
                )

            if spike:
                for index in range(self.n_inputs):
                    next_eligibility[index] = self._sat_eligibility(
                        next_eligibility[index] + self.a_plus * next_pre_trace[index]
                    )
                next_post_trace = self._sat_trace(next_post_trace + self.trace_increment)
                next_threshold = min(
                    self.threshold + self.threshold_increment,
                    self.threshold_max,
                )
            else:
                next_threshold = self._relax_threshold(next_threshold)

        next_snapshot_valid = self.snapshot_valid
        next_eligibility_snapshot = list(self.eligibility_snapshot)
        if snapshot_we:
            next_snapshot_valid = True
            next_eligibility_snapshot = list(next_eligibility)

        # MOD_COMMIT 优先读取 pending snapshot；没有 snapshot 时读取本周期 next eligibility。
        if mod_valid and learn_enable and not state_clear:
            signed_modulator = 1 if modulator > 0 else -1 if modulator < 0 else 0
            if signed_modulator:
                source = next_eligibility_snapshot if next_snapshot_valid else next_eligibility
                for index, eligibility in enumerate(source):
                    delta = (signed_modulator * eligibility) >> self.learning_shift
                    self.weights[index] = self._sat_weight(self.weights[index] + delta)
                next_snapshot_valid = False

        if weight_we and learn_enable and not state_clear:
            self.weights[weight_addr] = self._sat_weight(weight_wdata)

        if state_clear:
            self.current = self.reset_value
            self.membrane = self.reset_value
            self.refractory = 0
            self.threshold = self.base_threshold
            self.post_trace = 0
            self.pre_trace = [0 for _ in range(self.n_inputs)]
            self.eligibility = [0 for _ in range(self.n_inputs)]
        else:
            self.current = next_current
            self.membrane = next_membrane
            self.refractory = next_refractory
            self.threshold = next_threshold
            self.post_trace = next_post_trace
            self.pre_trace = next_pre_trace
            self.eligibility = next_eligibility
        if not state_clear:
            self.snapshot_valid = next_snapshot_valid
            self.eligibility_snapshot = next_eligibility_snapshot
        return RtlState(
            tick=tick,
            current=self.current,
            membrane=self.membrane,
            spike=spike,
            refractory=self.refractory,
            threshold=self.threshold,
            post_trace=self.post_trace,
            weights=tuple(self.weights),
            pre_trace=tuple(self.pre_trace),
            eligibility=tuple(self.eligibility),
            snapshot_valid=int(self.snapshot_valid),
            eligibility_snapshot=tuple(self.eligibility_snapshot),
        )


def generate_trace(
    events: Sequence[Sequence[int]],
    learn_enable: bool = True,
) -> tuple[RtlState, ...]:
    neuron = RtlReferenceNeuron(n_inputs=4)
    return tuple(
        neuron.tick(active, learn_enable=learn_enable, tick=tick)
        for tick, active in enumerate(events)
    )

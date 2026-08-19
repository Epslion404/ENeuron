"""Pulse-Mini-L2 黄金模型。

L2 保留 Pulse-Mini-L 的命令、膜电位泄放和窗口合同，只把每条连接的
正/负 presence flag 升级为两个 2 位饱和证据计数器。CAPTURE 时使用
``positive_count - negative_count``，并将结果限制在 -2..+2；因此重复的
同方向事件能产生更大的本地更新，正负事件的先后顺序也不会改变结果。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from pulse_mini_reference import (
    Command,
    Mode,
    Opcode,
    PulseMiniReference,
    Response,
    Status,
    decode_weight,
    saturate,
)


@dataclass(frozen=True)
class L2StateView:
    mode: Mode
    weights: tuple[int, ...]
    soma: int
    refractory: int
    leak_timer: int
    pre_age: tuple[int, ...]
    post_age: int
    positive_evidence: tuple[int, ...]
    negative_evidence: tuple[int, ...]
    captured_direction: tuple[int, ...]
    pending_valid: bool
    last_spike: int


class PulseMiniL2Reference(PulseMiniReference):
    """Pulse-Mini-L2：四输入、有符号连接、粗粒度证据强度学习单元。"""

    EVIDENCE_MAX = 2

    def __init__(
        self,
        *,
        initial_weights: Sequence[int] | None = None,
        init_weight: int = 0,
        leak_period: int = PulseMiniReference.LEAK_PERIOD,
    ) -> None:
        super().__init__(
            initial_weights=initial_weights,
            init_weight=init_weight,
            leak_period=leak_period,
        )
        self.positive_evidence = [0] * self.N_INPUTS
        self.negative_evidence = [0] * self.N_INPUTS
        self.captured_direction = [0] * self.N_INPUTS

    @property
    def state(self) -> L2StateView:
        return L2StateView(
            mode=self.mode,
            weights=tuple(self.weights),
            soma=self.soma,
            refractory=self.refractory,
            leak_timer=self.leak_timer,
            pre_age=tuple(self.pre_age),
            post_age=self.post_age,
            positive_evidence=tuple(self.positive_evidence),
            negative_evidence=tuple(self.negative_evidence),
            captured_direction=tuple(self.captured_direction),
            pending_valid=self.pending_valid,
            last_spike=self.last_spike,
        )

    def reset(self) -> None:
        super().reset()
        self.positive_evidence = [0] * self.N_INPUTS
        self.negative_evidence = [0] * self.N_INPUTS
        self.captured_direction = [0] * self.N_INPUTS

    def state_digest(self) -> dict[str, Any]:
        value = self.state
        return {
            "model": "Pulse-Mini-L2",
            "mode": value.mode.name,
            "weights": list(value.weights),
            "soma": value.soma,
            "refractory": value.refractory,
            "leak_timer": value.leak_timer,
            "pre_age": list(value.pre_age),
            "post_age": value.post_age,
            "positive_evidence": list(value.positive_evidence),
            "negative_evidence": list(value.negative_evidence),
            "captured_direction": list(value.captured_direction),
            "pending_valid": value.pending_valid,
            "last_spike": value.last_spike,
        }

    def _state_clear(self, arg0: int, arg1: int) -> tuple[Status, dict[str, Any]]:
        status, details = super()._state_clear(arg0, arg1)
        if status is Status.OK:
            self.positive_evidence = [0] * self.N_INPUTS
            self.negative_evidence = [0] * self.N_INPUTS
            self.captured_direction = [0] * self.N_INPUTS
        return status, details

    def _tick(self, input_mask: int, train_post: bool, *, learning: bool) -> tuple[int, dict[str, Any]]:
        old_pre = tuple(self.pre_age)
        old_post = self.post_age
        old_soma = self.soma
        old_leak_timer = self.leak_timer
        was_refractory = self.refractory > 0
        active = tuple(index for index in range(self.N_INPUTS) if input_mask & (1 << index))
        natural_spike = False
        total = 0
        candidate = self.soma

        if was_refractory:
            self.soma = 0
            self.refractory = max(0, self.refractory - 1)
            self.leak_timer = old_leak_timer
        else:
            leak_due = self.leak_period > 0 and old_leak_timer == self.leak_period - 1
            if leak_due:
                if self.soma > 0:
                    self.soma -= 1
                elif self.soma < 0:
                    self.soma += 1
                self.leak_timer = 0
            elif self.leak_period > 0:
                self.leak_timer = old_leak_timer + 1
            else:
                self.leak_timer = 0
            total = sum(self.weights[index] for index in active)
            candidate = saturate(self.soma + total, self.SOMA_MIN, self.SOMA_MAX)
            if candidate >= self.THRESHOLD:
                natural_spike = True
                self.soma = 0
                self.refractory = self.REFRACTORY_LENGTH
                self.leak_timer = 0
            else:
                self.soma = candidate

        post_event = natural_spike or train_post
        if learning:
            # 同一 tick 对同一连接最多记一次正证据，避免“当前输入”和
            # 尚未过期的 pre 窗口重复计数；这也与 RTL 的单次非阻塞写一致。
            for index in range(self.N_INPUTS):
                positive_hit = bool(post_event and (
                    (not was_refractory and index in active) or old_pre[index] > 0
                ))
                negative_hit = bool(
                    not was_refractory and index in active and old_post > 0
                )
                if positive_hit:
                    self.positive_evidence[index] = min(
                        self.EVIDENCE_MAX, self.positive_evidence[index] + 1
                    )
                if negative_hit:
                    self.negative_evidence[index] = min(
                        self.EVIDENCE_MAX, self.negative_evidence[index] + 1
                    )

            if not was_refractory:
                self.pre_age = [
                    self.WINDOW if index in active else max(0, old_pre[index] - 1)
                    for index in range(self.N_INPUTS)
                ]
            if post_event:
                self.post_age = self.WINDOW
            else:
                self.post_age = max(0, old_post - 1)

        if natural_spike:
            self.spike_count += 1
        self.last_spike = int(natural_spike)
        return int(natural_spike), {
            "input_mask": input_mask,
            "active_inputs": list(active),
            "train_post": int(train_post),
            "was_refractory": was_refractory,
            "old_pre_age": list(old_pre),
            "old_post_age": old_post,
            "old_soma": old_soma,
            "old_leak_timer": old_leak_timer,
            "leak_period": self.leak_period,
            "leak_due": int(not was_refractory and self.leak_period > 0
                             and old_leak_timer == self.leak_period - 1),
            "leak_timer": self.leak_timer,
            "contribution": total,
            "candidate": candidate,
            "post_event": int(post_event),
            "natural_spike": int(natural_spike),
            "positive_evidence": list(self.positive_evidence),
            "negative_evidence": list(self.negative_evidence),
        }

    def _capture(self, arg0: int, arg1: int) -> tuple[Status, dict[str, Any]]:
        self._unused_zero(arg0, arg1)
        if self.mode is not Mode.TRAIN:
            return Status.BAD_MODE, {"reason": "CAPTURE requires TRAIN"}
        if self.pending_valid:
            return Status.BUSY_PENDING, {"reason": "only one capture may be pending"}
        directions = [
            saturate(positive - negative, -self.EVIDENCE_MAX, self.EVIDENCE_MAX)
            for positive, negative in zip(self.positive_evidence, self.negative_evidence)
        ]
        self.captured_direction = directions
        self.pending_valid = True
        return Status.OK, {
            "captured_direction": list(directions),
            "positive_evidence": list(self.positive_evidence),
            "negative_evidence": list(self.negative_evidence),
        }

    def _feedback(self, feedback_code: int, arg1: int) -> tuple[Status, dict[str, Any]]:
        if arg1 != 0:
            return Status.BAD_ARG, {"reason": "arg1 must be zero"}
        if feedback_code not in (0, 1, 3):
            return Status.BAD_ARG, {"reason": "feedback 10 is reserved"}
        if self.mode is not Mode.TRAIN:
            return Status.BAD_MODE, {"reason": "FEEDBACK requires TRAIN"}
        if not self.pending_valid:
            return Status.NO_PENDING, {"reason": "no captured direction"}
        feedback = 0 if feedback_code == 0 else 1 if feedback_code == 1 else -1
        old_weights = list(self.weights)
        deltas = [feedback * direction for direction in self.captured_direction]
        self.weights = [
            saturate(weight + delta, self.WEIGHT_MIN, self.WEIGHT_MAX)
            for weight, delta in zip(self.weights, deltas)
        ]
        self.positive_evidence = [0] * self.N_INPUTS
        self.negative_evidence = [0] * self.N_INPUTS
        self.captured_direction = [0] * self.N_INPUTS
        self.pending_valid = False
        return Status.OK, {
            "feedback": feedback,
            "old_weights": old_weights,
            "deltas": deltas,
            "new_weights": list(self.weights),
        }


__all__ = ["L2StateView", "PulseMiniL2Reference"]

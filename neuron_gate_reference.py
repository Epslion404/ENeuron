"""NeuronGate V1：NPU 连接门控器的 Python 黄金模型。

这个模块刻意比 ENeuron/Pulse-Mini 更轻：它不保存膜电位、不应期、可塑权重或
逐突触资格迹，而是为一个“四连接组”保存重要性分数、保留掩码和冷却计数。
训练阶段只观察输入/输出事件与局部任务反馈；每个 IMAGE_END 形成候选掩码，
每个 EPOCH_END 才安全提交。NPU 在推理阶段根据 keep_mask 跳过被关闭的连接，
因此神经门控与 NPU 的乘加资源在 FPGA 上错开使用。

默认合同：
  * 4 条连接一组，结构化上限为 2:4；
  * 每条连接一个 8 位分数，初值 128；
  * 低阈值 16，高阈值 48，冷却长度 4；
  * 每 8 个逻辑 tick 对空闲连接衰减 1。

该模型只做标准库整数运算，便于独立审计和后续 RTL 对拍。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


N_INPUTS = 4
SCORE_MIN = 0
SCORE_MAX = 255

TRAIN_MODE = "TRAIN"
INFER_MODE = "INFER"


def clamp_score(value: int) -> int:
    """分数饱和到 0..255。"""

    return max(SCORE_MIN, min(SCORE_MAX, value))


def bit_count(value: int) -> int:
    """四位掩码中置位的个数。"""

    return (value & 1) + ((value >> 1) & 1) + ((value >> 2) & 1) + ((value >> 3) & 1)


@dataclass(frozen=True)
class GateState:
    mode: str
    tick_count: int
    scores: tuple[int, int, int, int]
    keep_mask: int
    cooldowns: tuple[int, int, int, int]
    candidate_mask: int
    candidate_valid: bool


class NeuronGateV1:
    """固定四连接组的轻量神经元门控模型。

    ``observe`` 只允许在 TRAIN 模式调用。``image_end`` 生成候选掩码，但不会
    立即改变 keep_mask；``epoch_end`` 才提交候选并递减冷却计数。INFER 模式冻结
    全部学习与候选状态，只暴露 ``keep_mask``。
    """

    def __init__(
        self,
        *,
        initial_mask: int = 0xF,
        initial_scores: Sequence[int] | None = None,
        prune_lo: int = 16,
        regrow_hi: int = 48,
        cooldown_length: int = 4,
        decay_interval: int = 8,
        max_keep: int = 2,
        activity_inc: int = 1,
        coincidence_inc: int = 3,
        correct_inc: int = 4,
        incorrect_dec: int = 2,
    ) -> None:
        if initial_mask < 0 or initial_mask > 0xF:
            raise ValueError("initial_mask must be four bits")
        if prune_lo < 0 or regrow_hi < 0 or prune_lo >= regrow_hi:
            raise ValueError("thresholds must satisfy 0 <= prune_lo < regrow_hi")
        if cooldown_length < 0:
            raise ValueError("cooldown_length must be non-negative")
        if decay_interval <= 0:
            raise ValueError("decay_interval must be positive")
        if max_keep < 0 or max_keep > N_INPUTS:
            raise ValueError("max_keep must be in 0..4")

        self.prune_lo = prune_lo
        self.regrow_hi = regrow_hi
        self.cooldown_length = cooldown_length
        self.decay_interval = decay_interval
        self.max_keep = max_keep
        self.activity_inc = activity_inc
        self.coincidence_inc = coincidence_inc
        self.correct_inc = correct_inc
        self.incorrect_dec = incorrect_dec

        if initial_scores is None:
            initial_scores = (128, 128, 128, 128)
        if len(initial_scores) != N_INPUTS:
            raise ValueError("initial_scores must have four entries")
        self._initial_scores = tuple(clamp_score(int(value)) for value in initial_scores)
        self._initial_mask = initial_mask
        self.reset()

    def reset(self) -> None:
        """恢复初始分数、全掩码、冷却和候选状态。"""

        self.mode = TRAIN_MODE
        self.tick_count = 0
        self.scores = list(self._initial_scores)
        self.keep_mask_value = self._initial_mask
        self.cooldowns = [0] * N_INPUTS
        self.candidate_mask_value = self._initial_mask
        self.candidate_valid = False

    @property
    def keep_mask(self) -> int:
        return self.keep_mask_value

    @property
    def candidate_mask(self) -> int:
        return self.candidate_mask_value

    @property
    def state(self) -> GateState:
        return GateState(
            mode=self.mode,
            tick_count=self.tick_count,
            scores=(self.scores[0], self.scores[1], self.scores[2], self.scores[3]),
            keep_mask=self.keep_mask_value,
            cooldowns=(
                self.cooldowns[0],
                self.cooldowns[1],
                self.cooldowns[2],
                self.cooldowns[3],
            ),
            candidate_mask=self.candidate_mask_value,
            candidate_valid=self.candidate_valid,
        )

    def set_mode(self, mode: str) -> None:
        if mode not in (TRAIN_MODE, INFER_MODE):
            raise ValueError("mode must be TRAIN or INFER")
        self.mode = mode

    def _require_train(self) -> None:
        if self.mode != TRAIN_MODE:
            raise RuntimeError("operation requires TRAIN mode")

    def observe(
        self,
        pre_mask: int,
        *,
        post_event: bool = False,
        feedback_valid: bool = False,
        feedback_correct: bool = False,
    ) -> tuple[int, int, int, int]:
        """处理一个逻辑 tick，返回更新后的四条分数。"""

        self._require_train()
        if pre_mask < 0 or pre_mask > 0xF:
            raise ValueError("pre_mask must be four bits")
        if feedback_valid and not isinstance(feedback_correct, bool):
            raise TypeError("feedback_correct must be bool")

        decay_due = self.tick_count == self.decay_interval - 1
        next_tick_count = (self.tick_count + 1) % self.decay_interval

        for index in range(N_INPUTS):
            active = bool(pre_mask & (1 << index))
            score = self.scores[index]
            if active:
                score += self.activity_inc
                if post_event:
                    score += self.coincidence_inc
                if feedback_valid:
                    score += self.correct_inc if feedback_correct else -self.incorrect_dec
            elif decay_due:
                score -= 1
            self.scores[index] = clamp_score(score)

        self.tick_count = next_tick_count
        return self.scores[0], self.scores[1], self.scores[2], self.scores[3]

    def image_end(self) -> int:
        """按分数和滞回规则生成候选掩码，不立即提交。"""

        self._require_train()
        raw_mask = self.keep_mask_value
        for index in range(N_INPUTS):
            score = self.scores[index]
            bit = 1 << index
            if not (raw_mask & bit) and self.cooldowns[index] == 0 and score > self.regrow_hi:
                raw_mask |= bit
            elif (raw_mask & bit) and self.cooldowns[index] == 0 and score < self.prune_lo:
                raw_mask &= ~bit & 0xF
                self.cooldowns[index] = self.cooldown_length

        if self.max_keep > 0 and bit_count(raw_mask) > self.max_keep:
            order = sorted(
                range(N_INPUTS),
                key=lambda index: (-self.scores[index], index),
            )
            selected = order[: self.max_keep]
            raw_mask = sum(1 << index for index in selected)

        self.candidate_mask_value = raw_mask
        self.candidate_valid = True
        return raw_mask

    def epoch_end(self) -> int:
        """提交候选掩码，并推进所有连接的冷却计数。"""

        self._require_train()
        if self.candidate_valid:
            self.keep_mask_value = self.candidate_mask_value
            self.candidate_valid = False
        for index in range(N_INPUTS):
            self.cooldowns[index] = max(0, self.cooldowns[index] - 1)
        return self.keep_mask_value


__all__ = [
    "GateState",
    "NeuronGateV1",
    "INFER_MODE",
    "N_INPUTS",
    "SCORE_MAX",
    "SCORE_MIN",
    "TRAIN_MODE",
    "bit_count",
    "clamp_score",
]

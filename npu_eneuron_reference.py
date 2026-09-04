"""传统 INT8 NPU 与 ENeuron 局部门控的可复现参考模型。"""

import logging
from dataclasses import dataclass
from typing import Sequence


LOGGER = logging.getLogger(__name__)


def validate_uint4_input(value: object) -> int:
    """验证核心输入是严格的 4 bit 无符号整数。"""
    if type(value) is not int or not 0 <= value <= 15:
        LOGGER.debug("reject non-uint4 core input value=%r", value)
        raise ValueError("core input must be a uint4 integer")
    return value


def saturate_hidden(value: int) -> int:
    """隐藏层 ReLU 后饱和到 0..127。"""
    return max(0, min(127, int(value)))


@dataclass(frozen=True)
class NpuConfig:
    input_size: int = 64
    hidden_size: int = 32
    output_size: int = 10
    group_size: int = 4


@dataclass(frozen=True)
class InferenceResult:
    logits: list[int]
    prediction: int | None
    abstain: bool
    group_reads: int
    mac_count: int


class NpuReference:
    """最小确定性 NPU；门控只影响组是否发出乘加，不改变数值规则。"""

    def __init__(self, config: NpuConfig | None = None) -> None:
        self.config = config or NpuConfig()
        self._weights0: list[list[int]] | None = None
        self._bias0: list[int] | None = None
        self._weights1: list[list[int]] | None = None
        self._bias1: list[int] | None = None

    def load_weights(
        self,
        weights0: Sequence[Sequence[int]],
        bias0: Sequence[int],
        weights1: Sequence[Sequence[int]],
        bias1: Sequence[int],
    ) -> None:
        """载入固定形状权重，并在配置窗口执行 INT8/INT32 边界归一化。"""
        c = self.config
        if len(weights0) != c.hidden_size or any(len(row) != c.input_size for row in weights0):
            raise ValueError("weights0 shape mismatch")
        if len(weights1) != c.output_size or any(len(row) != c.hidden_size for row in weights1):
            raise ValueError("weights1 shape mismatch")
        if len(bias0) != c.hidden_size or len(bias1) != c.output_size:
            raise ValueError("bias shape mismatch")
        self._weights0 = [[max(-128, min(127, int(v))) for v in row] for row in weights0]
        self._bias0 = [int(v) for v in bias0]
        self._weights1 = [[max(-128, min(127, int(v))) for v in row] for row in weights1]
        self._bias1 = [int(v) for v in bias1]

    def infer(
        self,
        image: Sequence[int],
        *,
        mode: str = "bypass",
        group_mask0: Sequence[bool] | None = None,
        group_mask1: Sequence[bool] | None = None,
    ) -> InferenceResult:
        """执行一次冻结推理；同一输入只读取已提交的门控版本。"""
        if self._weights0 is None or self._bias0 is None or self._weights1 is None or self._bias1 is None:
            raise RuntimeError("weights are not loaded")
        c = self.config
        if len(image) != c.input_size:
            raise ValueError("image shape mismatch")
        if mode not in {"bypass", "gated"}:
            raise ValueError("mode must be bypass or gated")
        activations = [validate_uint4_input(value) for value in image]
        mask0 = self._validate_mask(group_mask0, c.hidden_size * (c.input_size // c.group_size), mode)
        hidden: list[int] = []
        reads = 0
        macs = 0
        for output_index, row in enumerate(self._weights0):
            acc = self._bias0[output_index]
            for group, start in enumerate(range(0, c.input_size, c.group_size)):
                if not mask0[output_index * (c.input_size // c.group_size) + group]:
                    continue
                reads += 1
                for offset in range(c.group_size):
                    acc += activations[start + offset] * row[start + offset]
                    macs += 1
            hidden.append(saturate_hidden(acc))
        mask1 = self._validate_mask(group_mask1, c.output_size * (c.hidden_size // c.group_size), mode)
        logits: list[int] = []
        for output_index, row in enumerate(self._weights1):
            acc = self._bias1[output_index]
            for group, start in enumerate(range(0, c.hidden_size, c.group_size)):
                if not mask1[output_index * (c.hidden_size // c.group_size) + group]:
                    continue
                reads += 1
                for offset in range(c.group_size):
                    acc += hidden[start + offset] * row[start + offset]
                    macs += 1
            logits.append(acc)
        best = max(logits)
        winners = [index for index, value in enumerate(logits) if value == best]
        prediction = winners[0] if len(winners) == 1 else None
        LOGGER.debug("infer mode=%s group_reads=%d mac_count=%d prediction=%s", mode, reads, macs, prediction)
        return InferenceResult(logits, prediction, prediction is None, reads, macs)

    def _validate_mask(self, mask: Sequence[bool] | None, size: int, mode: str) -> list[bool]:
        if mode == "bypass":
            return [True] * size
        if mask is None or len(mask) != size:
            raise ValueError("gated mode requires a complete committed mask")
        return [bool(value) for value in mask]

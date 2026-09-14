"""传统 INT8 NPU 与 ENeuron 局部门控的可复现参考模型。"""

import logging
from dataclasses import dataclass
from typing import Sequence


LOGGER = logging.getLogger(__name__)

INT8_MIN = -128
INT8_MAX = 127
BIAS0_MIN = -2147360768
BIAS0_MAX = 2147361727
BIAS1_MIN = -2146963456
BIAS1_MAX = 2146967519


def validate_uint4_input(value: object) -> int:
    """验证核心输入是严格的 4 bit 无符号整数。"""
    if type(value) is not int or not 0 <= value <= 15:
        LOGGER.debug("reject non-uint4 core input value=%r", value)
        raise ValueError("core input must be a uint4 integer")
    return value


def _validate_integer_range(value: object, *, minimum: int, maximum: int, label: str) -> int:
    """验证配置值是指定闭区间内的真正整数。"""
    if type(value) is not int or not minimum <= value <= maximum:
        LOGGER.debug("reject invalid %s value=%r range=[%d,%d]", label, value, minimum, maximum)
        raise ValueError(f"{label} must be an integer in [{minimum}, {maximum}]")
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

    def __post_init__(self) -> None:
        values = (self.input_size, self.hidden_size, self.output_size, self.group_size)
        if any(type(value) is not int for value in values) or values != (64, 32, 10, 4):
            LOGGER.debug("reject noncanonical V1 config values=%r", values)
            raise ValueError("V1 config must be 64 inputs, 32 hidden, 10 outputs, group 4")


@dataclass(frozen=True)
class InferenceResult:
    logits: tuple[int, ...]
    prediction: int | None
    abstain: bool
    group_reads: int
    mac_count: int


class NpuReference:
    """最小确定性 NPU；组门控或 lane 门控只改变实际乘加，不改变数值规则。"""

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
        """完整验证固定形状模型后，一次提交四块参数。"""
        c = self.config
        if len(weights0) != c.hidden_size or any(len(row) != c.input_size for row in weights0):
            raise ValueError("weights0 shape mismatch")
        if len(weights1) != c.output_size or any(len(row) != c.hidden_size for row in weights1):
            raise ValueError("weights1 shape mismatch")
        if len(bias0) != c.hidden_size or len(bias1) != c.output_size:
            raise ValueError("bias shape mismatch")
        new_weights0 = [
            [_validate_integer_range(value, minimum=INT8_MIN, maximum=INT8_MAX, label="INT8 weight") for value in row]
            for row in weights0
        ]
        new_bias0 = [
            _validate_integer_range(value, minimum=BIAS0_MIN, maximum=BIAS0_MAX, label="layer0 bias")
            for value in bias0
        ]
        new_weights1 = [
            [_validate_integer_range(value, minimum=INT8_MIN, maximum=INT8_MAX, label="INT8 weight") for value in row]
            for row in weights1
        ]
        new_bias1 = [
            _validate_integer_range(value, minimum=BIAS1_MIN, maximum=BIAS1_MAX, label="layer1 bias")
            for value in bias1
        ]
        self._weights0, self._bias0, self._weights1, self._bias1 = new_weights0, new_bias0, new_weights1, new_bias1
        LOGGER.debug("loaded validated V1 model parameters")

    def infer(
        self,
        image: Sequence[int],
        *,
        mode: str = "bypass",
        group_mask0: Sequence[bool] | None = None,
        group_mask1: Sequence[bool] | None = None,
        lane_mask0: Sequence[int] | None = None,
        lane_mask1: Sequence[int] | None = None,
    ) -> InferenceResult:
        """执行一次冻结推理；同一输入只读取已提交的门控版本。

        group_mask 是组级开关（一位关四权重）。lane_mask 是每组 4-bit
        连接开关：nibble 非 0 仍计一次 group_read，只对置位 lane 做 MAC。
        两者不能混用。lane_mask 允许 0000/1111，严格 2:4 合法性在编码层检查。
        """
        if self._weights0 is None or self._bias0 is None or self._weights1 is None or self._bias1 is None:
            raise RuntimeError("weights are not loaded")
        c = self.config
        if len(image) != c.input_size:
            raise ValueError("image shape mismatch")
        if mode not in {"bypass", "gated"}:
            raise ValueError("mode must be bypass or gated")
        if (lane_mask0 is not None or lane_mask1 is not None) and (
            group_mask0 is not None or group_mask1 is not None
        ):
            raise ValueError("lane masks and group masks cannot be combined")
        activations = [validate_uint4_input(value) for value in image]
        l0_groups = c.hidden_size * (c.input_size // c.group_size)
        l1_groups = c.output_size * (c.hidden_size // c.group_size)
        use_lanes = lane_mask0 is not None or lane_mask1 is not None
        if use_lanes:
            if mode != "gated":
                raise ValueError("lane masks require gated mode")
            lanes0 = self._validate_lane_mask(lane_mask0, l0_groups)
            lanes1 = self._validate_lane_mask(lane_mask1, l1_groups)
        else:
            mask0 = self._validate_mask(group_mask0, l0_groups, mode)
            mask1 = self._validate_mask(group_mask1, l1_groups, mode)
        hidden: list[int] = []
        reads = 0
        macs = 0
        for output_index, row in enumerate(self._weights0):
            acc = self._bias0[output_index]
            for group, start in enumerate(range(0, c.input_size, c.group_size)):
                index = output_index * (c.input_size // c.group_size) + group
                nibble = lanes0[index] if use_lanes else (0xF if mask0[index] else 0)
                if nibble == 0:
                    continue
                reads += 1
                for offset in range(c.group_size):
                    if (nibble >> offset) & 1:
                        acc += activations[start + offset] * row[start + offset]
                        macs += 1
            hidden.append(saturate_hidden(acc))
        logits: list[int] = []
        for output_index, row in enumerate(self._weights1):
            acc = self._bias1[output_index]
            for group, start in enumerate(range(0, c.hidden_size, c.group_size)):
                index = output_index * (c.hidden_size // c.group_size) + group
                nibble = lanes1[index] if use_lanes else (0xF if mask1[index] else 0)
                if nibble == 0:
                    continue
                reads += 1
                for offset in range(c.group_size):
                    if (nibble >> offset) & 1:
                        acc += hidden[start + offset] * row[start + offset]
                        macs += 1
            logits.append(acc)
        best = max(logits)
        winners = [index for index, value in enumerate(logits) if value == best]
        prediction = winners[0] if len(winners) == 1 else None
        LOGGER.debug(
            "infer mode=%s lane_gated=%s group_reads=%d mac_count=%d prediction=%s",
            mode, use_lanes, reads, macs, prediction,
        )
        return InferenceResult(tuple(logits), prediction, prediction is None, reads, macs)

    def _validate_mask(self, mask: Sequence[bool] | None, size: int, mode: str) -> list[bool]:
        if mode == "bypass":
            return [True] * size
        if mask is None or len(mask) != size:
            raise ValueError("gated mode requires a complete committed mask")
        return [bool(value) for value in mask]

    def _validate_lane_mask(self, mask: Sequence[int] | None, size: int) -> list[int]:
        """校验每组 4-bit nibble；0000/1111 合法，供 group_4way 展开。"""
        if mask is None or len(mask) != size:
            raise ValueError("gated lane mode requires a complete 4-bit mask per group")
        lanes: list[int] = []
        for value in mask:
            if type(value) is not int or not 0 <= value <= 0xF:
                LOGGER.debug("reject non-nibble lane mask value=%r", value)
                raise ValueError("lane mask must be a 4-bit integer")
            lanes.append(value)
        return lanes

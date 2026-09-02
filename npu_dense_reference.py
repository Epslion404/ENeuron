"""64->32->10 signed INT8 稠密 NPU 黄金模型。

本模块只描述 N1 的数据平面和可审计工作量，不实现神经元、剪枝或 RTL。
周期合同保持简单且确定：一个 lane 每拍处理一个四连接组；同一输出神经元
的组按输入编号递增处理，输出神经元按编号递增处理。稠密存储中每组四个
INT8 权重占两个 20-bit 逻辑字，因此 ``weight_reads = groups * 2``；每组
固定发出四次乘加。lane 数只改变组批次周期，不改变数值结果或读取总量。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


INPUT_DIM = 64
HIDDEN_DIM = 32
OUTPUT_DIM = 10
GROUP_WIDTH = 4
WEIGHT_BITS = 8
ACC_BITS = 24
WEIGHT_MIN = -(1 << (WEIGHT_BITS - 1))
WEIGHT_MAX = (1 << (WEIGHT_BITS - 1)) - 1
ACC_MIN = -(1 << (ACC_BITS - 1))
ACC_MAX = (1 << (ACC_BITS - 1)) - 1
LANE_COUNTS = (1, 2, 4, 8)
DENSE_WORDS_PER_GROUP = 2


def _check_int(value: int, name: str, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if not low <= value <= high:
        raise ValueError(f"{name} must be within {low}..{high}")
    return value


def check_int8(value: int, name: str = "value") -> int:
    """检查 signed INT8 数值。"""
    return _check_int(value, name, WEIGHT_MIN, WEIGHT_MAX)


def sat_acc(value: int) -> int:
    """将整数钳位到 signed INT24 累加器范围。"""
    return max(ACC_MIN, min(ACC_MAX, value))


def _validate_vector(values: Sequence[int], length: int, name: str,
                     low: int, high: int) -> tuple[int, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{name} must be an integer sequence")
    if len(values) != length:
        raise ValueError(f"{name} must contain exactly {length} values")
    return tuple(_check_int(value, f"{name}[{index}]", low, high)
                 for index, value in enumerate(values))


@dataclass(frozen=True)
class LayerLedger:
    """单层稠密执行账本。

    ``cycles`` 是该层所有输出神经元顺序执行时的逻辑周期；它不含 DMA、
    跨时钟域、启动/排空和下游背压。``weight_reads`` 是逻辑字读取请求，
    ``synapse_ops`` 是实际乘加发射次数。
    """

    name: str
    input_features: int
    output_features: int
    groups_per_output: int
    lane_count: int
    weight_reads: int
    synapse_ops: int
    cycles: int

    @property
    def groups_total(self) -> int:
        return self.output_features * self.groups_per_output


@dataclass(frozen=True)
class InferenceResult:
    """一次完整 MLP 推理的数值结果和工作量。"""

    hidden: tuple[int, ...]
    logits: tuple[int, ...]
    prediction: int | None
    one_hot: tuple[int, ...]
    abstain: bool
    layers: tuple[LayerLedger, LayerLedger]

    @property
    def total_weight_reads(self) -> int:
        return sum(layer.weight_reads for layer in self.layers)

    @property
    def total_synapse_ops(self) -> int:
        return sum(layer.synapse_ops for layer in self.layers)

    @property
    def total_cycles(self) -> int:
        return sum(layer.cycles for layer in self.layers)


class DenseInt8Layer:
    """固定输入/输出尺寸的 INT8 稠密层。"""

    def __init__(self, weights: Sequence[Sequence[int]],
                 biases: Sequence[int], *, name: str) -> None:
        if isinstance(weights, (str, bytes)) or not isinstance(weights, Sequence):
            raise TypeError("weights must be a matrix")
        if not weights:
            raise ValueError("weights must not be empty")
        self.output_features = len(weights)
        first_row = weights[0]
        if isinstance(first_row, (str, bytes)) or not isinstance(first_row, Sequence):
            raise TypeError("weights rows must be sequences")
        self.input_features = len(first_row)
        if self.input_features == 0 or self.input_features % GROUP_WIDTH:
            raise ValueError("input_features must be a positive multiple of four")
        self.weights = tuple(
            _validate_vector(row, self.input_features, f"weights[{row_index}]",
                             WEIGHT_MIN, WEIGHT_MAX)
            for row_index, row in enumerate(weights)
        )
        self.biases = _validate_vector(biases, self.output_features, "biases",
                                       ACC_MIN, ACC_MAX)
        self.name = name

    @property
    def groups_per_output(self) -> int:
        return self.input_features // GROUP_WIDTH

    def _ledger(self, lane_count: int) -> LayerLedger:
        if lane_count not in LANE_COUNTS:
            raise ValueError(f"lane_count must be one of {LANE_COUNTS}")
        groups_total = self.output_features * self.groups_per_output
        cycles = self.output_features * (
            (self.groups_per_output + lane_count - 1) // lane_count
        )
        return LayerLedger(
            name=self.name,
            input_features=self.input_features,
            output_features=self.output_features,
            groups_per_output=self.groups_per_output,
            lane_count=lane_count,
            weight_reads=groups_total * DENSE_WORDS_PER_GROUP,
            synapse_ops=groups_total * GROUP_WIDTH,
            cycles=cycles,
        )

    def run(self, activations: Sequence[int], *, lane_count: int,
            relu: bool = False) -> tuple[tuple[int, ...], LayerLedger]:
        """执行一层并返回输出和账本。

        累加器从 bias 开始，每次乘积都先加入并做 INT24 饱和；隐藏层随后
        使用 ReLU 并饱和到 signed INT8，输出层保留 INT24 logits。
        """
        values = _validate_vector(activations, self.input_features, "activations",
                                  WEIGHT_MIN, WEIGHT_MAX)
        ledger = self._ledger(lane_count)
        outputs: list[int] = []
        for row, bias in zip(self.weights, self.biases):
            acc = sat_acc(bias)
            for weight, activation in zip(row, values):
                acc = sat_acc(acc + weight * activation)
            if relu:
                acc = max(0, acc)
                acc = min(WEIGHT_MAX, acc)
            outputs.append(acc)
        return tuple(outputs), ledger


class DenseInt8MLP64x32x10:
    """N1 固定拓扑的两层稠密 INT8 MLP。"""

    def __init__(self, hidden_weights: Sequence[Sequence[int]],
                 hidden_biases: Sequence[int], output_weights: Sequence[Sequence[int]],
                 output_biases: Sequence[int]) -> None:
        self.hidden = DenseInt8Layer(hidden_weights, hidden_biases, name="hidden")
        self.output = DenseInt8Layer(output_weights, output_biases, name="output")
        if (self.hidden.input_features, self.hidden.output_features,
                self.output.input_features, self.output.output_features) != (
                    INPUT_DIM, HIDDEN_DIM, HIDDEN_DIM, OUTPUT_DIM):
            raise ValueError("MLP topology must be exactly 64->32->10")

    @classmethod
    def zeros(cls) -> "DenseInt8MLP64x32x10":
        """构造全零权重的确定性测试网络。"""
        return cls(
            [[0] * INPUT_DIM for _ in range(HIDDEN_DIM)], [0] * HIDDEN_DIM,
            [[0] * HIDDEN_DIM for _ in range(OUTPUT_DIM)], [0] * OUTPUT_DIM,
        )

    def infer(self, inputs: Sequence[int], *, lane_count: int,
              abstain_margin: int | None = None) -> InferenceResult:
        """完成一次推理，默认不 abstain；margin>0 可启用低置信度 abstain。"""
        if abstain_margin is not None:
            _check_int(abstain_margin, "abstain_margin", 0, ACC_MAX)
        hidden, hidden_ledger = self.hidden.run(inputs, lane_count=lane_count, relu=True)
        logits, output_ledger = self.output.run(hidden, lane_count=lane_count, relu=False)
        ranked = sorted(range(OUTPUT_DIM), key=lambda index: (-logits[index], index))
        top = ranked[0]
        second = logits[ranked[1]]
        abstain = abstain_margin is not None and logits[top] - second < abstain_margin
        prediction = None if abstain else top
        one_hot = tuple(0 if abstain or index != top else 1
                        for index in range(OUTPUT_DIM))
        return InferenceResult(
            hidden=hidden,
            logits=logits,
            prediction=prediction,
            one_hot=one_hot,
            abstain=abstain,
            layers=(hidden_ledger, output_ledger),
        )

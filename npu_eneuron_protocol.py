"""NPU + ENeuron 门控版本和单槽结果的最小事务参考模型。"""

from dataclasses import dataclass
import logging
from typing import Sequence

from npu_eneuron_reference import InferenceResult, NpuConfig, NpuReference


LOGGER = logging.getLogger(__name__)

MODEL_WORD_COUNT = 634


@dataclass(frozen=True)
class DecodedModel:
    """由固定 634-word 镜像解码出的不可变模型参数。"""

    weights0: tuple[tuple[int, ...], ...]
    bias0: tuple[int, ...]
    weights1: tuple[tuple[int, ...], ...]
    bias1: tuple[int, ...]


def _validate_model_word(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        LOGGER.debug("reject non-uint32 model word value=%r", value)
        raise ValueError("model word must be a uint32 integer")
    return value


def _signed(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return value - (1 << bits) if value & sign else value


def _decode_int8_word(word: int) -> tuple[int, int, int, int]:
    return tuple(_signed((word >> (8 * byte)) & 0xFF, 8) for byte in range(4))


def decode_model_words(words: Sequence[object]) -> DecodedModel:
    """按 V1 的 512/32/80/10 段表和低字节优先规则解码模型镜像。"""
    snapshot = tuple(words)
    if len(snapshot) != MODEL_WORD_COUNT:
        raise ValueError("model image must contain exactly 634 words")
    image = tuple(_validate_model_word(word) for word in snapshot)

    weights0 = tuple(
        tuple(value for group in range(16) for value in _decode_int8_word(image[16 * hidden + group]))
        for hidden in range(32)
    )
    bias0 = tuple(_signed(image[512 + hidden], 32) for hidden in range(32))
    weights1 = tuple(
        tuple(value for group in range(8) for value in _decode_int8_word(image[544 + 8 * output + group]))
        for output in range(10)
    )
    bias1 = tuple(_signed(image[624 + output], 32) for output in range(10))
    return DecodedModel(weights0, bias0, weights1, bias1)


def load_model_words(model: NpuReference, words: Sequence[object]) -> None:
    """完整解码并验证镜像后，复用参考模型的原子参数提交。"""
    decoded = decode_model_words(words)
    model.load_weights(decoded.weights0, decoded.bias0, decoded.weights1, decoded.bias1)
    LOGGER.debug("loaded validated 634-word model image")


@dataclass(frozen=True)
class _PendingMasks:
    epoch: int
    mask0: tuple[bool, ...]
    mask1: tuple[bool, ...]


@dataclass(frozen=True)
class RuntimeResult:
    """与输出数据一起锁存的门控版本。"""

    epoch: int
    inference: InferenceResult


class NpuEpochRuntime:
    """用双版本门控和一个结果槽表达样本边界与背压合同。"""

    def __init__(self, model: NpuReference, config: NpuConfig | None = None) -> None:
        self.model = model
        self.config = config or model.config
        self.active_epoch = 0
        self._active_mask0 = self._all_open_mask(self.config.hidden_size * (self.config.input_size // self.config.group_size))
        self._active_mask1 = self._all_open_mask(self.config.output_size * (self.config.hidden_size // self.config.group_size))
        self._pending: _PendingMasks | None = None
        self._frozen = False
        self._inflight: RuntimeResult | None = None
        self._result: RuntimeResult | None = None
        self.clear_count = 0

    @staticmethod
    def _all_open_mask(size: int) -> tuple[bool, ...]:
        return (True,) * size

    @property
    def result(self) -> RuntimeResult | None:
        """当前结果槽；未被接受时对象和内容都保持稳定。"""
        return self._result

    @property
    def running(self) -> bool:
        return self._inflight is not None

    def set_infer_freeze(self, frozen: bool) -> None:
        if self.running:
            raise RuntimeError("cannot change infer freeze while sample is running")
        self._frozen = bool(frozen)

    def stage_masks(self, epoch: int, mask0: Sequence[bool], mask1: Sequence[bool]) -> None:
        """把候选版本写入单槽 pending 区，不影响当前 active 版本。"""
        if self._frozen:
            raise RuntimeError("infer freeze rejects mask update")
        if self._pending is not None:
            raise RuntimeError("pending mask slot is full")
        if epoch <= self.active_epoch:
            raise ValueError("epoch must increase monotonically")
        expected0 = self.config.hidden_size * (self.config.input_size // self.config.group_size)
        expected1 = self.config.output_size * (self.config.hidden_size // self.config.group_size)
        if len(mask0) != expected0 or len(mask1) != expected1:
            raise ValueError("complete masks are required")
        self._pending = _PendingMasks(epoch, tuple(bool(value) for value in mask0), tuple(bool(value) for value in mask1))
        LOGGER.debug("staged mask epoch=%d", epoch)

    def begin_sample(self, image: Sequence[int]) -> RuntimeResult:
        """原子接受样本及下一门控版本；非法输入不改变任何状态。"""
        if self.running:
            raise RuntimeError("sample already running")
        if self._result is not None:
            raise RuntimeError("result backpressure blocks next sample")
        if self._pending is None:
            epoch = self.active_epoch
            mask0 = self._active_mask0
            mask1 = self._active_mask1
        else:
            epoch = self._pending.epoch
            mask0 = self._pending.mask0
            mask1 = self._pending.mask1
        inference = self.model.infer(image, mode="gated", group_mask0=mask0, group_mask1=mask1)
        if self._pending is not None:
            self.active_epoch = epoch
            self._active_mask0 = mask0
            self._active_mask1 = mask1
            self._pending = None
            LOGGER.debug("committed mask epoch=%d at sample accept boundary", epoch)
        self._inflight = RuntimeResult(epoch, inference)
        return self._inflight

    def complete_sample(self) -> None:
        if self._inflight is None:
            raise RuntimeError("no sample is running")
        if self._result is not None:
            raise RuntimeError("result slot is full")
        self._result = self._inflight
        self._inflight = None

    def accept_result(self) -> RuntimeResult:
        if self._result is None:
            raise RuntimeError("no result to accept")
        result = self._result
        self._result = None
        return result

    def state_clear(self) -> None:
        """清动态运行计数，不回退已提交的门控版本。"""
        if self.running or self._result is not None:
            raise RuntimeError("cannot clear while runtime is occupied")
        if self._frozen:
            raise RuntimeError("infer freeze rejects dynamic clear")
        self.clear_count += 1

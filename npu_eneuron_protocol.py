"""NPU + ENeuron 门控版本和单槽结果的最小事务参考模型。"""

from dataclasses import dataclass
from enum import Enum
import logging
from typing import Sequence

from npu_eneuron_reference import (
    BIAS0_MAX, BIAS0_MIN, BIAS1_MAX, BIAS1_MIN,
    InferenceResult, NpuConfig, NpuReference, _validate_integer_range,
)


LOGGER = logging.getLogger(__name__)

MODEL_WORD_COUNT = 634
MASK_WORD_COUNT = 19
MASK0_BITS = 512
MASK1_BITS = 80

class ModelCommandKind(str, Enum):
    MODEL_BEGIN = "MODEL_BEGIN"
    DATA = "DATA"
    MODEL_COMMIT = "MODEL_COMMIT"


@dataclass(frozen=True)
class DecodedModel:
    """由固定 634-word 镜像解码出的不可变模型参数。"""

    weights0: tuple[tuple[int, ...], ...]
    bias0: tuple[int, ...]
    weights1: tuple[tuple[int, ...], ...]
    bias1: tuple[int, ...]


@dataclass(frozen=True)
class DecodedMasks:
    """由固定 19-word 镜像解码出的两层不可变门控位。"""

    mask0: tuple[bool, ...]
    mask1: tuple[bool, ...]


class MaskCommandKind(str, Enum):
    """19-word mask 配置端口的最小命令集合。"""

    MASK_BEGIN = "MASK_BEGIN"
    DATA = "DATA"
    MASK_COMMIT = "MASK_COMMIT"
    MASK_ABORT = "MASK_ABORT"

@dataclass(frozen=True)
class ModelCommand:
    kind: object
    word: object = 0

@dataclass(frozen=True)
class ModelStepResult:
    cmd_ready: bool
    cmd_accepted: bool
    error_valid: bool
    error_code: str | None
    state: str
    word_index: int
    model_valid: bool

class ModelConfigPort:
    EMPTY = "empty"
    LOADING = "loading"
    COMPLETE = "complete"
    COMMITTED = "committed"

    def __init__(self, model: NpuReference) -> None:
        self._model = model
        self._state = self.EMPTY
        self._word_index = 0
        self._words: list[object] = []
        self._pending_error: str | None = None
        self._model_valid = False
        self._frozen = False

    @property
    def state(self) -> str: return self._state
    @property
    def word_index(self) -> int: return self._word_index
    @property
    def model_valid(self) -> bool: return self._model_valid

    def set_frozen(self, frozen: bool) -> None:
        if frozen and self._state not in {self.EMPTY, self.COMMITTED}:
            raise RuntimeError("cannot freeze while model staging is occupied")
        self._frozen = bool(frozen)

    def step(self, cmd_valid: bool, command: ModelCommand | None, response_ready: bool) -> ModelStepResult:
        if self._pending_error is not None:
            code = self._pending_error
            if response_ready: self._pending_error = None
            return self._result(False, False, True, code)
        if not cmd_valid: return self._result(True, False, False, None)
        code = self._execute(command)
        if code is not None: self._pending_error = code
        return self._result(True, True, code is not None, code)

    def _result(self, ready: bool, accepted: bool, error: bool, code: str | None) -> ModelStepResult:
        return ModelStepResult(ready, accepted, error, code, self._state, self._word_index, self._model_valid)

    def _execute(self, command: ModelCommand | None) -> str | None:
        if self._frozen: return "FROZEN"
        if not isinstance(command, ModelCommand) or not isinstance(command.kind, ModelCommandKind): return "BAD_COMMAND"
        if command.kind is ModelCommandKind.MODEL_BEGIN:
            if self._state != self.EMPTY: return "BAD_STATE"
            self._words, self._word_index, self._state = [], 0, "loading"
            return None
        if command.kind is ModelCommandKind.DATA:
            if self._state != self.LOADING: return "BAD_STATE"
            if type(command.word) is not int or not 0 <= command.word <= 0xFFFFFFFF: return "BAD_WORD"
            try:
                candidate = self._words + [command.word]
                if len(candidate) in range(513, 545):
                    _validate_integer_range(_signed(command.word, 32), minimum=BIAS0_MIN, maximum=BIAS0_MAX, label="layer0 bias")
                if len(candidate) in range(625, 635):
                    _validate_integer_range(_signed(command.word, 32), minimum=BIAS1_MIN, maximum=BIAS1_MAX, label="layer1 bias")
            except ValueError: return "BAD_WORD"
            self._words.append(command.word); self._word_index += 1
            if self._word_index == MODEL_WORD_COUNT: self._state = "complete"
            return None
        if command.kind is ModelCommandKind.MODEL_COMMIT:
            if self._state != "complete": return "BAD_STATE"
            try: load_model_words(self._model, self._words)
            except (ValueError, RuntimeError): return "BAD_MODEL"
            self._model_valid, self._state = True, "committed"
            return None
        return "BAD_COMMAND"


@dataclass(frozen=True)
class MaskCommand:
    """一拍配置命令；字段保持原始值，边界错误由端口握手后报告。"""

    kind: object
    epoch: object = 0
    word: object = 0


@dataclass(frozen=True)
class MaskStepResult:
    """配置端口一拍后的公开状态和错误响应。"""

    cmd_ready: bool
    cmd_accepted: bool
    error_valid: bool
    error_code: str | None
    state: str
    word_index: int
    active_epoch: int


def _validate_uint32(value: object, label: str) -> int:
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        LOGGER.debug("reject non-uint32 %s value=%r", label, value)
        raise ValueError(f"{label} must be a uint32 integer")
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
    image = tuple(_validate_uint32(word, "model word") for word in snapshot)

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


def decode_mask_words(words: Sequence[object]) -> DecodedMasks:
    """按 V1 的 LSB-first 512+80 bit 规则解码完整 mask 镜像。"""
    snapshot = tuple(words)
    if len(snapshot) != MASK_WORD_COUNT:
        raise ValueError("mask image must contain exactly 19 words")
    image = tuple(_validate_uint32(word, "mask word") for word in snapshot)
    if image[18] & 0xFFFF0000:
        LOGGER.debug("reject nonzero mask word 18 reserved bits value=0x%08x", image[18])
        raise ValueError("mask word 18 reserved bits must be zero")

    mask0 = tuple(bool((image[index // 32] >> (index % 32)) & 1) for index in range(MASK0_BITS))
    mask1 = tuple(bool((image[16 + index // 32] >> (index % 32)) & 1) for index in range(MASK1_BITS))
    return DecodedMasks(mask0, mask1)


class MaskConfigPort:
    """19-word mask 配置口的单槽四态参考实现。

    命令只在没有待消费错误响应时被接受。非法命令完成握手后产生一个稳定
    错误码；错误响应被接受前，端口不会再接受下一条配置命令。
    """

    EMPTY = "empty"
    LOADING = "loading"
    COMPLETE = "complete"
    PUBLISHED = "published"

    def __init__(self) -> None:
        self._state = self.EMPTY
        self._word_index = 0
        self._active_epoch = 0
        self._active_masks = DecodedMasks((True,) * MASK0_BITS, (True,) * MASK1_BITS)
        self._staging_epoch: int | None = None
        self._staging_words: list[int] = []
        self._published_epoch: int | None = None
        self._published_masks: DecodedMasks | None = None
        self._pending_error: str | None = None
        self._frozen = False

    @property
    def state(self) -> str:
        return self._state

    @property
    def word_index(self) -> int:
        return self._word_index

    @property
    def active_epoch(self) -> int:
        return self._active_epoch

    @property
    def active_masks(self) -> DecodedMasks:
        return self._active_masks

    @property
    def published_epoch(self) -> int | None:
        return self._published_epoch

    @property
    def frozen(self) -> bool:
        return self._frozen

    def set_infer_freeze(self, frozen: bool) -> None:
        """只允许在 staging 为空时切换推理冻结。"""
        if frozen and self._state != self.EMPTY:
            raise RuntimeError("cannot freeze while mask staging is occupied")
        self._frozen = bool(frozen)

    def accept_sample_boundary(self) -> int:
        """在后续样本首 beat 接受时把 published mask 交换为 active。"""
        if self._state != self.PUBLISHED or self._published_masks is None:
            return self._active_epoch
        published_epoch = self._published_epoch
        if published_epoch is None:
            raise RuntimeError("published mask epoch is missing")
        self._active_epoch = published_epoch
        self._active_masks = self._published_masks
        self._published_epoch = None
        self._published_masks = None
        self._staging_epoch = None
        self._staging_words = []
        self._word_index = 0
        self._state = self.EMPTY
        LOGGER.debug("activated mask epoch=%d at sample boundary", self._active_epoch)
        return self._active_epoch

    def step(
        self,
        cmd_valid: bool,
        command: MaskCommand | None,
        response_ready: bool,
    ) -> MaskStepResult:
        """推进一个配置时钟周期并返回公开握手状态。"""
        if self._pending_error is not None:
            error_code = self._pending_error
            if response_ready:
                self._pending_error = None
            return self._result(False, False, True, error_code)

        if not cmd_valid:
            return self._result(True, False, False, None)

        error_code = self._execute(command)
        if error_code is not None:
            self._pending_error = error_code
        return self._result(True, True, error_code is not None, error_code)

    def _result(
        self,
        cmd_ready: bool,
        cmd_accepted: bool,
        error_valid: bool,
        error_code: str | None,
    ) -> MaskStepResult:
        return MaskStepResult(
            cmd_ready,
            cmd_accepted,
            error_valid,
            error_code,
            self._state,
            self._word_index,
            self._active_epoch,
        )

    def _execute(self, command: MaskCommand | None) -> str | None:
        if self._frozen:
            return "FROZEN"
        if not isinstance(command, MaskCommand):
            return "BAD_COMMAND"
        if not isinstance(command.kind, MaskCommandKind):
            return "BAD_COMMAND"

        kind = command.kind
        if kind is MaskCommandKind.MASK_BEGIN:
            if self._state != self.EMPTY:
                return "BAD_STATE"
            try:
                epoch = _validate_uint32(command.epoch, "mask epoch")
            except ValueError:
                return "BAD_EPOCH"
            expected = (self._active_epoch + 1) & 0xFFFFFFFF
            if epoch != expected:
                return "BAD_EPOCH"
            self._staging_epoch = epoch
            self._staging_words = []
            self._word_index = 0
            self._state = self.LOADING
            LOGGER.debug("began mask staging epoch=%d", epoch)
            return None

        if kind is MaskCommandKind.DATA:
            if self._state != self.LOADING:
                return "BAD_STATE"
            try:
                word = _validate_uint32(command.word, "mask word")
            except ValueError:
                return "BAD_WORD"
            if self._word_index == MASK_WORD_COUNT - 1 and word & 0xFFFF0000:
                return "BAD_RESERVED"
            self._staging_words.append(word)
            self._word_index += 1
            if self._word_index == MASK_WORD_COUNT:
                self._state = self.COMPLETE
            return None

        if kind is MaskCommandKind.MASK_COMMIT:
            if self._state != self.COMPLETE or self._staging_epoch is None:
                return "BAD_STATE"
            try:
                epoch = _validate_uint32(command.epoch, "mask epoch")
            except ValueError:
                return "BAD_EPOCH"
            expected = (self._active_epoch + 1) & 0xFFFFFFFF
            if epoch != expected or epoch != self._staging_epoch:
                return "BAD_EPOCH"
            self._published_masks = decode_mask_words(tuple(self._staging_words))
            self._published_epoch = epoch
            self._state = self.PUBLISHED
            LOGGER.debug("published mask epoch=%d", epoch)
            return None

        if kind is MaskCommandKind.MASK_ABORT:
            if self._state not in {self.LOADING, self.COMPLETE}:
                return "BAD_STATE"
            self._staging_epoch = None
            self._staging_words = []
            self._word_index = 0
            self._state = self.EMPTY
            LOGGER.debug("aborted mask staging")
            return None

        return "BAD_COMMAND"


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
        self._mask_port: MaskConfigPort | None = None
        self._model_port: ModelConfigPort | None = None
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
    def frozen(self) -> bool:
        """运行时是否处于推理冻结。"""
        return self._frozen

    def bind_mask_port(self, port: MaskConfigPort) -> None:
        """绑定可选 mask 配置端口，令 freeze 判定覆盖两侧状态。"""
        if not isinstance(port, MaskConfigPort):
            raise TypeError("mask port must be a MaskConfigPort")
        if self.running or self._result is not None or self._pending is not None:
            raise RuntimeError("cannot bind mask port while runtime is occupied")
        self._mask_port = port
        LOGGER.debug("bound mask configuration port")

    def bind_model_port(self, port: ModelConfigPort) -> None:
        if self.running or self._result is not None or self._pending is not None:
            raise RuntimeError("cannot bind model port while runtime is occupied")
        self._model_port = port
        LOGGER.debug("bound model configuration port")

    @property
    def running(self) -> bool:
        return self._inflight is not None

    def set_infer_freeze(self, frozen: bool) -> None:
        if self.running or self._result is not None or self._pending is not None:
            raise RuntimeError("cannot change infer freeze while runtime is occupied")
        if self._mask_port is not None and self._mask_port.state != MaskConfigPort.EMPTY:
            raise RuntimeError("cannot change infer freeze while mask staging is occupied")
        if self._model_port is not None and self._model_port.state not in {ModelConfigPort.EMPTY, ModelConfigPort.COMMITTED}:
            raise RuntimeError("cannot change infer freeze while model staging is occupied")
        requested = bool(frozen)
        if self._mask_port is not None:
            self._mask_port.set_infer_freeze(requested)
        if self._model_port is not None:
            self._model_port.set_frozen(requested)
        self._frozen = requested
        LOGGER.debug("set runtime infer freeze=%s", requested)

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

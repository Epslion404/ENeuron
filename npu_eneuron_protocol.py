"""NPU + ENeuron 门控版本和单槽结果的最小事务参考模型。"""

from dataclasses import dataclass
import logging
from typing import Sequence

from npu_eneuron_reference import InferenceResult, NpuConfig, NpuReference


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PendingMasks:
    epoch: int
    mask0: tuple[bool, ...]
    mask1: tuple[bool, ...]


class NpuEpochRuntime:
    """用双版本门控和一个结果槽表达样本边界与背压合同。"""

    def __init__(self, model: NpuReference, config: NpuConfig | None = None) -> None:
        self.model = model
        self.config = config or model.config
        self.active_epoch = 0
        self._active_mask0 = self._all_open_mask(self.config.hidden_size * (self.config.input_size // self.config.group_size))
        self._active_mask1 = self._all_open_mask(self.config.output_size * (self.config.hidden_size // self.config.group_size))
        self._pending: _PendingMasks | None = None
        self._running = False
        self._frozen = False
        self._result: InferenceResult | None = None
        self.clear_count = 0

    @staticmethod
    def _all_open_mask(size: int) -> tuple[bool, ...]:
        return (True,) * size

    @property
    def result(self) -> InferenceResult | None:
        """当前结果槽；未被接受时对象和内容都保持稳定。"""
        return self._result

    @property
    def running(self) -> bool:
        return self._running

    def set_infer_freeze(self, frozen: bool) -> None:
        if self._running:
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

    def begin_sample(self, image: Sequence[int]) -> tuple[int, InferenceResult]:
        """锁存 active 版本并计算样本；结果未接受时禁止覆盖。"""
        if self._running:
            raise RuntimeError("sample already running")
        if self._result is not None:
            raise RuntimeError("result backpressure blocks next sample")
        self._running = True
        snapshot_epoch = self.active_epoch
        result = self.model.infer(image, mode="gated", group_mask0=self._active_mask0, group_mask1=self._active_mask1)
        return snapshot_epoch, result

    def complete_sample(self, result: InferenceResult) -> None:
        if not self._running:
            raise RuntimeError("no sample is running")
        if self._result is not None:
            raise RuntimeError("result slot is full")
        self._result = result
        self._running = False
        if self._pending is not None:
            self.active_epoch = self._pending.epoch
            self._active_mask0 = self._pending.mask0
            self._active_mask1 = self._pending.mask1
            self._pending = None
            LOGGER.debug("committed mask epoch=%d at sample boundary", self.active_epoch)

    def accept_result(self) -> InferenceResult:
        if self._result is None:
            raise RuntimeError("no result to accept")
        result = self._result
        self._result = None
        return result

    def state_clear(self) -> None:
        """清动态运行计数，不回退已提交的门控版本。"""
        if self._running or self._result is not None:
            raise RuntimeError("cannot clear while runtime is occupied")
        if self._frozen:
            raise RuntimeError("infer freeze rejects dynamic clear")
        self.clear_count += 1

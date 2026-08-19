"""Pulse-Mini 四输入脉冲单元的整数黄金模型。

本文件只描述 P2 行为合同，不试图模拟 RTL 的实现细节。模型固定四条
输入、四位有符号连接(-7..+7)、八位有符号饱和胞体、阈值 6、一个 tick
的不应期和长度为 3 的时间窗口。所有命令都经过一个一槽响应口；响应未
被消费时，新的命令不会被接受。

命令字段约定：
  MODE_SET     arg0 = 0/1/2 (CONFIG/TRAIN/INFER)
  STATE_CLEAR  无参数
  TICK         arg0[3:0] = 输入掩码，arg1[0] = train_post
  CAPTURE      无参数
  FEEDBACK     arg0 = 00/01/11 (0/+1/-1)，10 非法
  WEIGHT_WRITE arg0 = 地址 0..3，arg1 = 四位编码或有符号值
  WEIGHT_READ  arg0 = 地址 0..3

模型使用标准库，便于独立运行和审计。``execute`` 是便捷的“发送并立即
消费响应”接口；``cycle`` 用来验证真实 valid/ready 背压行为。
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any, Sequence


LOGGER = logging.getLogger("pulse_mini_reference")

# 固定手算向量：权重 (-7,-3,0,+2) 时，四位输入掩码对应的直接贡献。
# 该表故意写成字面常量，便于 RTL 联调时独立核对，而不是从被测模型推导。
INPUT_MASK_GOLDEN_VECTORS: tuple[tuple[int, int], ...] = (
    (0x0, 0), (0x1, -7), (0x2, -3), (0x3, -10),
    (0x4, 0), (0x5, -7), (0x6, -3), (0x7, -10),
    (0x8, 2), (0x9, -5), (0xA, -1), (0xB, -8),
    (0xC, 2), (0xD, -5), (0xE, -1), (0xF, -8),
)


class Opcode(IntEnum):
    MODE_SET = 0
    STATE_CLEAR = 1
    TICK = 2
    CAPTURE = 3
    FEEDBACK = 4
    WEIGHT_WRITE = 5
    WEIGHT_READ = 6


class Mode(IntEnum):
    CONFIG = 0
    TRAIN = 1
    INFER = 2


class Status(str, Enum):
    OK = "ok"
    BAD_OPCODE = "bad_opcode"
    BAD_ARG = "bad_arg"
    BAD_MODE = "bad_mode"
    BUSY_PENDING = "busy_pending"
    NO_PENDING = "no_pending"


@dataclass(frozen=True)
class Command:
    """一条主机命令。未使用字段必须为零，模型会报告 BAD_ARG。"""

    opcode: Opcode | int | str
    arg0: int = 0
    arg1: int = 0


@dataclass(frozen=True)
class Response:
    """一条严格有序响应；``data`` 为有符号解释，``raw_data`` 为低四位。"""

    sequence: int
    opcode: str
    status: Status
    data: int = 0
    raw_data: int = 0
    spike: int = 0
    pending_valid: bool = False
    mode: Mode = Mode.CONFIG

    @property
    def ok(self) -> bool:
        return self.status is Status.OK


@dataclass(frozen=True)
class CycleResult:
    """一个逻辑命令周期的可见握手和响应信号。"""

    cmd_ready: bool
    rsp_valid: bool
    rsp_accepted: bool
    response: Response | None


@dataclass(frozen=True)
class StateView:
    """算法状态快照，便于测试逐字段冻结和日志审计。"""

    mode: Mode
    weights: tuple[int, ...]
    soma: int
    refractory: int
    pre_age: tuple[int, ...]
    post_age: int
    positive_evidence: tuple[bool, ...]
    negative_evidence: tuple[bool, ...]
    captured_direction: tuple[int, ...]
    pending_valid: bool
    last_spike: int


def saturate(value: int, low: int, high: int) -> int:
    """饱和而不是回绕。"""

    return max(low, min(high, value))


def encode_signed4(value: int) -> int:
    """将 -8..+7 映射为四位二补数；Pulse-Mini 不允许 -8。"""

    return value & 0xF


def decode_weight(value: int) -> int:
    """解析 WEIGHT_WRITE 的四位数据或 Python 有符号写法。

    0..7 同时是正数和四位编码；9..15 解释为 -7..-1；8(-8) 明确非法。
    -7..-1 可直接传入。其它数值不接受，避免静默截断。
    """

    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("weight must be an integer")
    if -7 <= value <= 7:
        return value
    if 0 <= value <= 0xF:
        decoded = value - 0x10 if value & 0x8 else value
        if decoded == -8:
            raise ValueError("-8 is outside the Pulse-Mini weight range")
        return decoded
    raise ValueError("weight is outside four-bit range")


class PulseMiniReference:
    """固定四输入 Pulse-Mini 的可审计黄金模型。"""

    N_INPUTS = 4
    WEIGHT_MIN = -7
    WEIGHT_MAX = 7
    SOMA_MIN = -128
    SOMA_MAX = 127
    THRESHOLD = 6
    REFRACTORY_LENGTH = 1
    WINDOW = 3

    def __init__(
        self,
        *,
        initial_weights: Sequence[int] | None = None,
        init_weight: int = 0,
        threshold: int = THRESHOLD,
        window: int = WINDOW,
        refractory_length: int = REFRACTORY_LENGTH,
    ) -> None:
        if threshold != self.THRESHOLD or window != self.WINDOW:
            raise ValueError("P2 contract fixes threshold=6 and window=3")
        if refractory_length != self.REFRACTORY_LENGTH:
            raise ValueError("P2 contract fixes refractory_length=1")
        if initial_weights is None:
            initial_weights = [init_weight] * self.N_INPUTS
        if len(initial_weights) != self.N_INPUTS:
            raise ValueError("Pulse-Mini has exactly four inputs")
        self._initial_weights = [decode_weight(int(value)) for value in initial_weights]
        self.mode = Mode.CONFIG
        self.weights = list(self._initial_weights)
        self.soma = 0
        self.refractory = 0
        self.pre_age = [0] * self.N_INPUTS
        self.post_age = 0
        self.positive_evidence = [False] * self.N_INPUTS
        self.negative_evidence = [False] * self.N_INPUTS
        self.captured_direction = [0] * self.N_INPUTS
        self.pending_valid = False
        self.last_spike = 0
        self.spike_count = 0
        self._next_sequence = 0
        self._response: Response | None = None
        self.event_log: list[dict[str, Any]] = []

    @property
    def cmd_ready(self) -> bool:
        """响应槽为空时才接受下一条命令。"""

        return self._response is None

    @property
    def rsp_valid(self) -> bool:
        return self._response is not None

    @property
    def response_pending(self) -> Response | None:
        return self._response

    @property
    def state(self) -> StateView:
        return StateView(
            mode=self.mode,
            weights=tuple(self.weights),
            soma=self.soma,
            refractory=self.refractory,
            pre_age=tuple(self.pre_age),
            post_age=self.post_age,
            positive_evidence=tuple(self.positive_evidence),
            negative_evidence=tuple(self.negative_evidence),
            captured_direction=tuple(self.captured_direction),
            pending_valid=self.pending_valid,
            last_spike=self.last_spike,
        )

    def state_digest(self) -> dict[str, Any]:
        """返回 JSON 可序列化的完整算法状态。"""

        value = self.state
        return {
            "mode": value.mode.name,
            "weights": list(value.weights),
            "soma": value.soma,
            "refractory": value.refractory,
            "pre_age": list(value.pre_age),
            "post_age": value.post_age,
            "positive_evidence": list(value.positive_evidence),
            "negative_evidence": list(value.negative_evidence),
            "captured_direction": list(value.captured_direction),
            "pending_valid": value.pending_valid,
            "last_spike": value.last_spike,
        }

    def reset(self) -> None:
        """模拟外部硬复位：恢复模式、动态状态和初始连接。"""

        self.mode = Mode.CONFIG
        self.weights = list(self._initial_weights)
        self.soma = 0
        self.refractory = 0
        self.pre_age = [0] * self.N_INPUTS
        self.post_age = 0
        self.positive_evidence = [False] * self.N_INPUTS
        self.negative_evidence = [False] * self.N_INPUTS
        self.captured_direction = [0] * self.N_INPUTS
        self.pending_valid = False
        self.last_spike = 0
        self.spike_count = 0
        self._response = None
        self._next_sequence = 0
        self.event_log.clear()

    def cycle(
        self,
        *,
        cmd_valid: bool = False,
        command: Command | None = None,
        rsp_ready: bool = False,
    ) -> CycleResult:
        """推进一个逻辑命令周期。

        响应在命令接受后的下一次 ``cycle`` 可见。为保持一槽合同，
        ``cmd_ready`` 按周期开始时的响应槽计算，因此不允许同拍替换响应。
        """

        visible_response = self._response
        rsp_valid = visible_response is not None
        rsp_accepted = bool(rsp_valid and rsp_ready)
        if rsp_accepted:
            self._response = None

        cmd_ready = visible_response is None
        if cmd_valid and cmd_ready:
            self._response = self._dispatch(command)

        return CycleResult(
            cmd_ready=cmd_ready,
            rsp_valid=rsp_valid,
            rsp_accepted=rsp_accepted,
            response=visible_response,
        )

    def execute(self, command: Command) -> Response:
        """发送一条命令并消费其响应，适合黄金向量和单元测试。"""

        if not self.cmd_ready:
            raise RuntimeError("response slot is occupied; use cycle() for backpressure")
        accepted = self.cycle(cmd_valid=True, command=command, rsp_ready=False)
        if not accepted.cmd_ready:
            raise AssertionError("command was unexpectedly not accepted")
        delivered = self.cycle(rsp_ready=True)
        if delivered.response is None:
            raise AssertionError("accepted command did not produce a response")
        return delivered.response

    # 便于不同测试/驱动代码使用的同义入口。
    issue = execute
    dispatch = execute

    def _dispatch(self, command: Command | None) -> Response:
        sequence = self._next_sequence
        self._next_sequence += 1
        before = self.state_digest()
        opcode_name = "UNKNOWN"
        status = Status.BAD_OPCODE
        data = 0
        raw_data = 0
        spike = 0
        details: dict[str, Any] = {}

        opcode = self._normalize_opcode(command.opcode if command is not None else None)
        if opcode is None:
            reason = "unknown opcode"
            response = self._make_response(sequence, opcode_name, status, data, raw_data, spike)
            self._log(sequence, opcode_name, status, reason, before, details)
            return response
        opcode_name = opcode.name
        arg0 = command.arg0 if command is not None else 0
        arg1 = command.arg1 if command is not None else 0
        try:
            if opcode is Opcode.MODE_SET:
                status, details = self._mode_set(arg0, arg1)
            elif opcode is Opcode.STATE_CLEAR:
                status, details = self._state_clear(arg0, arg1)
            elif opcode is Opcode.TICK:
                status, spike, details = self._tick_command(arg0, arg1)
            elif opcode is Opcode.CAPTURE:
                status, details = self._capture(arg0, arg1)
            elif opcode is Opcode.FEEDBACK:
                status, details = self._feedback(arg0, arg1)
            elif opcode is Opcode.WEIGHT_WRITE:
                status, details = self._weight_write(arg0, arg1)
            elif opcode is Opcode.WEIGHT_READ:
                status, data, raw_data, details = self._weight_read(arg0, arg1)
        except (TypeError, ValueError):
            status = Status.BAD_ARG
            details = {"reason": "argument type or range"}
        response = self._make_response(sequence, opcode_name, status, data, raw_data, spike)
        self._log(sequence, opcode_name, status, details.get("reason", ""), before, details)
        return response

    @staticmethod
    def _normalize_opcode(value: Opcode | int | str | None) -> Opcode | None:
        try:
            if isinstance(value, str):
                return Opcode[value.upper()]
            return Opcode(value)  # type: ignore[arg-type]
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_mode(value: int | str) -> Mode:
        if isinstance(value, str):
            return Mode[value.upper()]
        return Mode(value)

    @staticmethod
    def _unused_zero(arg0: int, arg1: int) -> None:
        if arg0 != 0 or arg1 != 0:
            raise ValueError("unused command arguments must be zero")

    def _make_response(
        self,
        sequence: int,
        opcode: str,
        status: Status,
        data: int,
        raw_data: int,
        spike: int,
    ) -> Response:
        return Response(
            sequence=sequence,
            opcode=opcode,
            status=status,
            data=data,
            raw_data=raw_data & 0xF,
            spike=int(bool(spike)),
            pending_valid=self.pending_valid,
            mode=self.mode,
        )

    def _mode_set(self, arg0: int | str, arg1: int) -> tuple[Status, dict[str, Any]]:
        if arg1 != 0:
            return Status.BAD_ARG, {"reason": "arg1 must be zero"}
        try:
            mode = self._normalize_mode(arg0)
        except (KeyError, TypeError, ValueError):
            return Status.BAD_ARG, {"reason": "mode must be CONFIG/TRAIN/INFER"}
        if self.pending_valid:
            return Status.BUSY_PENDING, {"reason": "pending feedback must be consumed"}
        self.mode = mode
        return Status.OK, {"new_mode": mode.name}

    def _state_clear(self, arg0: int, arg1: int) -> tuple[Status, dict[str, Any]]:
        self._unused_zero(arg0, arg1)
        if self.pending_valid:
            return Status.BUSY_PENDING, {"reason": "clear requires no pending feedback"}
        self.soma = 0
        self.refractory = 0
        self.pre_age = [0] * self.N_INPUTS
        self.post_age = 0
        self.positive_evidence = [False] * self.N_INPUTS
        self.negative_evidence = [False] * self.N_INPUTS
        self.captured_direction = [0] * self.N_INPUTS
        self.last_spike = 0
        return Status.OK, {"reason": "dynamic and learning state cleared"}

    def _tick_command(self, input_mask: int, train_post: int) -> tuple[Status, int, dict[str, Any]]:
        if not isinstance(input_mask, int) or input_mask < 0 or input_mask > 0xF:
            return Status.BAD_ARG, 0, {"reason": "input mask must be four bits"}
        if train_post not in (0, 1):
            return Status.BAD_ARG, 0, {"reason": "train_post must be 0 or 1"}
        if self.mode is Mode.CONFIG:
            return Status.BAD_MODE, 0, {"reason": "TICK is unavailable in CONFIG"}
        if self.pending_valid:
            return Status.BUSY_PENDING, 0, {"reason": "pending feedback blocks TICK"}
        if self.mode is Mode.INFER and train_post:
            return Status.BAD_MODE, 0, {"reason": "train_post is unavailable in INFER"}
        spike, details = self._tick(input_mask, bool(train_post), learning=self.mode is Mode.TRAIN)
        return Status.OK, spike, details

    def _tick(self, input_mask: int, train_post: bool, *, learning: bool) -> tuple[int, dict[str, Any]]:
        old_pre = tuple(self.pre_age)
        old_post = self.post_age
        old_soma = self.soma
        was_refractory = self.refractory > 0
        active = tuple(index for index in range(self.N_INPUTS) if input_mask & (1 << index))
        natural_spike = False
        total = 0
        candidate = self.soma

        # 不应期只屏蔽当前树突对胞体的贡献；不使用内部复位网络。
        if was_refractory:
            self.soma = 0
            self.refractory = max(0, self.refractory - 1)
        else:
            total = sum(self.weights[index] for index in active)
            candidate = saturate(self.soma + total, self.SOMA_MIN, self.SOMA_MAX)
            if candidate >= self.THRESHOLD:
                natural_spike = True
                self.soma = 0
                self.refractory = self.REFRACTORY_LENGTH
            else:
                self.soma = candidate

        post_event = natural_spike or train_post
        if learning:
            # 训练期间，输入在同拍遇到 post 或窗口内已有 post 都保留；
            # 两种证据都出现时 CAPTURE 映射为中性，因而与事件顺序无关。
            if not was_refractory:
                for index in active:
                    if post_event:
                        self.positive_evidence[index] = True
                    if old_post > 0:
                        self.negative_evidence[index] = True
            if post_event:
                for index, age in enumerate(old_pre):
                    if age > 0:
                        self.positive_evidence[index] = True

            # 输入窗口在不应期内保持不变；post 窗口仍可由 train_post 装载。
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
            "contribution": total,
            "candidate": candidate,
            "post_event": int(post_event),
            "natural_spike": int(natural_spike),
        }

    def _capture(self, arg0: int, arg1: int) -> tuple[Status, dict[str, Any]]:
        self._unused_zero(arg0, arg1)
        if self.mode is not Mode.TRAIN:
            return Status.BAD_MODE, {"reason": "CAPTURE requires TRAIN"}
        if self.pending_valid:
            return Status.BUSY_PENDING, {"reason": "only one capture may be pending"}
        directions: list[int] = []
        for positive, negative in zip(self.positive_evidence, self.negative_evidence):
            directions.append(1 if positive and not negative else -1 if negative and not positive else 0)
        self.captured_direction = directions
        self.pending_valid = True
        return Status.OK, {"captured_direction": list(directions)}

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
        self.captured_direction = [0] * self.N_INPUTS
        self.pending_valid = False
        return Status.OK, {
            "feedback": feedback,
            "old_weights": old_weights,
            "deltas": deltas,
            "new_weights": list(self.weights),
        }

    def _weight_write(self, address: int, value: int) -> tuple[Status, dict[str, Any]]:
        if not isinstance(address, int) or address < 0 or address >= self.N_INPUTS:
            return Status.BAD_ARG, {"reason": "weight address must be 0..3"}
        try:
            decoded = decode_weight(value)
        except ValueError as exc:
            return Status.BAD_ARG, {"reason": str(exc)}
        if self.mode is not Mode.CONFIG:
            return Status.BAD_MODE, {"reason": "WEIGHT_WRITE requires CONFIG"}
        old = self.weights[address]
        self.weights[address] = decoded
        return Status.OK, {"address": address, "old_weight": old, "new_weight": decoded}

    def _weight_read(self, address: int, arg1: int) -> tuple[Status, int, int, dict[str, Any]]:
        if arg1 != 0:
            return Status.BAD_ARG, 0, 0, {"reason": "arg1 must be zero"}
        if not isinstance(address, int) or address < 0 or address >= self.N_INPUTS:
            return Status.BAD_ARG, 0, 0, {"reason": "weight address must be 0..3"}
        value = self.weights[address]
        return Status.OK, value, encode_signed4(value), {"address": address, "weight": value}

    def _log(
        self,
        sequence: int,
        opcode: str,
        status: Status,
        reason: str,
        before: dict[str, Any],
        details: dict[str, Any],
    ) -> None:
        entry = {
            "sequence": sequence,
            "opcode": opcode,
            "status": status.value,
            "reason": reason,
            "before": before,
            "after": self.state_digest(),
            "details": copy.deepcopy(details),
        }
        self.event_log.append(entry)
        LOGGER.debug(json.dumps(entry, sort_keys=True, ensure_ascii=True))


__all__ = [
    "Command",
    "CycleResult",
    "Mode",
    "Opcode",
    "PulseMiniReference",
    "Response",
    "StateView",
    "Status",
    "INPUT_MASK_GOLDEN_VECTORS",
    "decode_weight",
    "encode_signed4",
    "saturate",
]

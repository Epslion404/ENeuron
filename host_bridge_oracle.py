"""Host Bridge V1 的独立 128-bit codec 与逐命令黄金模型。

`HostBridgeOracle.execute` 表示一条命令已从 command FIFO 消费，并且最终响应
已被 response FIFO 接受。FIFO、CDC 和逐周期等待由后续 T3/T4 模型负责；本模块
只冻结协议首错链、架构状态提交和 Tile 事务副作用。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum

from rtl_reference import RtlReferenceNeuron
from rtl_tile_cosim import TileOracle, TileTransaction, apply_transaction


LOGGER = logging.getLogger("host_bridge_oracle")


class Opcode(IntEnum):
    """Host Bridge V1 命令编码。"""

    EP_START = 0x01
    TICK_BEGIN = 0x02
    INPUT_EVENT = 0x03
    TICK_COMMIT = 0x04
    EP_END = 0x05
    MOD_COMMIT = 0x06
    WEIGHT_WRITE = 0x07
    WEIGHT_READ = 0x08
    ABORT = 0x09
    STATUS_READ = 0x0A


class Status(IntEnum):
    """Host Bridge V1 响应状态编码。"""

    OK = 0x00
    BAD_OPCODE = 0x01
    BAD_STATE = 0x02
    EPISODE_ID = 0x03
    TICK_ID = 0x04
    EVENT_COUNT = 0x05
    SYNAPSE_RANGE = 0x06
    DUP_EVENT = 0x07
    RESERVED_08 = 0x08
    SNAPSHOT_BUSY = 0x09
    COMMIT_ID = 0x0A
    ADDRESS = 0x0B
    BAD_FIELD = 0x0C
    RESERVED_0D = 0x0D
    COUNTER_WRAP = 0x0E
    INTERNAL_FATAL = 0x0F


class FatalPhase(IntEnum):
    """首次内部故障的固定阶段编码。"""

    NONE = 0x00
    EP_START_CLEAR_WAIT = 0x01
    TICK_WAIT = 0x02
    EP_END_FLUSH_WAIT = 0x03
    EP_END_SNAPSHOT_WAIT = 0x04
    MOD_WAIT = 0x05
    WEIGHT_WAIT = 0x06
    ABORT_CLEAR_WAIT = 0x07
    CONTROLLER_INTERNAL = 0x08


@dataclass(frozen=True)
class Flit:
    """统一的 128-bit command/response payload。"""

    opcode: int
    flags: int
    txn_id: int
    episode_id: int
    tick_id: int
    arg0: int
    arg1: int

    def __post_init__(self) -> None:
        fields = (
            ("opcode", self.opcode, 8),
            ("flags", self.flags, 8),
            ("txn_id", self.txn_id, 16),
            ("episode_id", self.episode_id, 16),
            ("tick_id", self.tick_id, 16),
            ("arg0", self.arg0, 32),
            ("arg1", self.arg1, 32),
        )
        for name, value, width in fields:
            if not isinstance(value, int) or not 0 <= value < (1 << width):
                raise ValueError(f"{name} 必须是 {width}-bit 无符号整数")

    def pack(self) -> int:
        """按协议位序打包成无符号 128-bit 整数。"""
        return (
            (self.opcode << 120)
            | (self.flags << 112)
            | (self.txn_id << 96)
            | (self.episode_id << 80)
            | (self.tick_id << 64)
            | (self.arg0 << 32)
            | self.arg1
        )

    @classmethod
    def unpack(cls, value: int) -> Flit:
        """从无符号 128-bit 整数解码。"""
        if not isinstance(value, int) or not 0 <= value < (1 << 128):
            raise ValueError("flit 必须是 128-bit 无符号整数")
        return cls(
            opcode=(value >> 120) & 0xFF,
            flags=(value >> 112) & 0xFF,
            txn_id=(value >> 96) & 0xFFFF,
            episode_id=(value >> 80) & 0xFFFF,
            tick_id=(value >> 64) & 0xFFFF,
            arg0=(value >> 32) & 0xFFFFFFFF,
            arg1=value & 0xFFFFFFFF,
        )

    def to_bytes(self) -> bytes:
        """编码为网络字节序的 16-byte payload。"""
        return self.pack().to_bytes(16, byteorder="big")

    @classmethod
    def from_bytes(cls, data: bytes) -> Flit:
        """从网络字节序的 16-byte payload 解码。"""
        if len(data) != 16:
            raise ValueError("flit 必须恰好包含 16 bytes")
        return cls.unpack(int.from_bytes(data, byteorder="big"))


def encode_modulators(values: tuple[int, int, int, int]) -> int:
    """编码 H0/H1/O0/O1 四个 -1/0/+1 调制值。"""
    if len(values) != 4:
        raise ValueError("必须提供四个 modulator")
    code_by_value = {-1: 0b11, 0: 0b00, 1: 0b01}
    encoded = 0
    for index, value in enumerate(values):
        try:
            code = code_by_value[value]
        except KeyError as error:
            raise ValueError("modulator 只允许 -1、0、+1") from error
        encoded |= code << (index * 2)
    return encoded


def decode_modulators(value: int) -> tuple[int, int, int, int]:
    """解码低 8 bit；2'b10 是协议非法值。"""
    if not isinstance(value, int) or not 0 <= value <= 0xFF:
        raise ValueError("modulator payload 必须是 8-bit 无符号整数")
    value_by_code = {0b11: -1, 0b00: 0, 0b01: 1}
    decoded: list[int] = []
    for index in range(4):
        code = (value >> (index * 2)) & 0b11
        if code == 0b10:
            raise ValueError("2'b10 是非法 modulator 编码")
        decoded.append(value_by_code[code])
    return decoded[0], decoded[1], decoded[2], decoded[3]


class ReferenceTileBackend:
    """把现有 `TileOracle` 收窄成 Host Bridge 所需的事务接口。"""

    def __init__(self, oracle: TileOracle | None = None) -> None:
        self.oracle = oracle if oracle is not None else TileOracle.create()
        self.transaction_id = 0
        self.last_hidden_spikes = 0
        self.last_output_spikes = 0

    @property
    def neurons(self) -> tuple[RtlReferenceNeuron, ...]:
        return self.oracle.neurons

    @property
    def pending_hidden(self) -> int:
        return self.oracle.pending_hidden

    @pending_hidden.setter
    def pending_hidden(self, value: int) -> None:
        self.oracle.pending_hidden = value & 0x3

    @property
    def snapshot_valid(self) -> bool:
        return self.oracle.snapshot_valid

    @snapshot_valid.setter
    def snapshot_valid(self, value: bool) -> None:
        self.oracle.snapshot_valid = bool(value)

    @property
    def pending_commit_id(self) -> int:
        return self.oracle.pending_commit_id

    @pending_commit_id.setter
    def pending_commit_id(self, value: int) -> None:
        self.oracle.pending_commit_id = value & 0xFFFF

    @property
    def pending_episode_id(self) -> int:
        return self.oracle.pending_episode_id

    @pending_episode_id.setter
    def pending_episode_id(self, value: int) -> None:
        self.oracle.pending_episode_id = value & 0xFFFF

    @property
    def last_commit_id(self) -> int:
        return self.oracle.last_commit_id

    @last_commit_id.setter
    def last_commit_id(self, value: int) -> None:
        self.oracle.last_commit_id = value & 0xFFFF

    @property
    def last_commit_valid(self) -> bool:
        return self.oracle.last_commit_valid

    @last_commit_valid.setter
    def last_commit_valid(self, value: bool) -> None:
        self.oracle.last_commit_valid = bool(value)

    @property
    def weight_epoch(self) -> int:
        return self.oracle.weight_epoch

    def _apply(self, transaction: TileTransaction) -> tuple[int, ...]:
        state, self.oracle = apply_transaction(
            self.oracle,
            transaction,
            self.transaction_id,
        )
        self.transaction_id += 1
        if state[8]:
            raise RuntimeError(f"Tile 拒绝了 {transaction.kind} 事务")
        self.last_hidden_spikes = state[6]
        self.last_output_spikes = state[7]
        return state

    def state_clear(self) -> None:
        self._apply(TileTransaction("clear"))

    def tick(self, input_mask: int, learn_enable: bool) -> tuple[int, int]:
        state = self._apply(
            TileTransaction("tick", mask=input_mask & 0xF, learn_enable=learn_enable)
        )
        return state[6], state[7]

    def route_flush(self, learn_enable: bool) -> int:
        state = self._apply(TileTransaction("route_flush", learn_enable=learn_enable))
        return state[7]

    def snapshot(self, commit_id: int, episode_id: int) -> None:
        self._apply(
            TileTransaction(
                "snapshot",
                commit_id=commit_id,
                episode_id=episode_id,
                learn_enable=True,
            )
        )

    def mod_commit(
        self,
        commit_id: int,
        modulators: tuple[int, int, int, int],
    ) -> None:
        self._apply(
            TileTransaction(
                "mod",
                commit_id=commit_id,
                modulators=modulators,
                learn_enable=True,
            )
        )
        # 现有 Python Tile reference 使用无界整数；wire contract 明确为 32-bit modulo。
        self.oracle.weight_epoch &= 0xFFFFFFFF

    @staticmethod
    def address_valid(neuron: int, weight: int) -> bool:
        return 0 <= neuron < 4 and 0 <= weight < (4 if neuron < 2 else 2)

    def weight_write(self, neuron: int, weight: int, value: int) -> None:
        self._apply(
            TileTransaction(
                "weight",
                neuron_addr=neuron,
                weight_addr=weight,
                weight_wdata=value,
                learn_enable=True,
            )
        )

    def weight_read(self, neuron: int, weight: int) -> int:
        if not self.address_valid(neuron, weight):
            raise RuntimeError("Tile 权重读地址非法")
        return self.neurons[neuron].weights[weight]

    def persistent_state(self) -> tuple[object, ...]:
        """返回 STATE_CLEAR/ABORT 必须保留的全部 Tile 真值。"""
        return (
            tuple(tuple(neuron.weights) for neuron in self.neurons),
            tuple(tuple(neuron.eligibility_snapshot) for neuron in self.neurons),
            self.snapshot_valid,
            self.pending_commit_id,
            self.pending_episode_id,
            self.last_commit_valid,
            self.last_commit_id,
            self.weight_epoch,
        )

    def observable_state(self) -> tuple[object, ...]:
        """返回协议错误原子性检查所需的完整 Tile 可观察状态。"""
        neuron_state = tuple(
            (
                neuron.current,
                neuron.membrane,
                neuron.refractory,
                neuron.threshold,
                neuron.post_trace,
                tuple(neuron.weights),
                tuple(neuron.pre_trace),
                tuple(neuron.eligibility),
                neuron.snapshot_valid,
                tuple(neuron.eligibility_snapshot),
            )
            for neuron in self.neurons
        )
        return (
            neuron_state,
            self.pending_hidden,
            self.snapshot_valid,
            self.pending_commit_id,
            self.pending_episode_id,
            self.last_commit_valid,
            self.last_commit_id,
            self.weight_epoch,
        )

    def hard_reset(self) -> None:
        self.oracle = TileOracle.create()
        self.transaction_id = 0
        self.last_hidden_spikes = 0
        self.last_output_spikes = 0


class HostBridgeOracle:
    """Host Bridge V1 的单槽、逐命令事务级黄金模型。"""

    def __init__(self, tile: ReferenceTileBackend | None = None) -> None:
        self.tile = tile if tile is not None else ReferenceTileBackend()
        self._clear_bridge_state()

    def _clear_bridge_state(self) -> None:
        self.episode_active = False
        self.episode_train = False
        self.active_episode_id = 0
        self.next_tick_ext = 0
        self.tick_open = False
        self.expected_event_count = 0
        self.seen_event_count = 0
        self.seen_mask = 0
        self.active_command_reg = 0
        self.response_reg = 0
        self.ep_end_flush_spikes = 0
        self.fatal_error = False
        self.fatal_opcode = 0
        self.fatal_phase = FatalPhase.NONE
        self.last_ep_end_flush_spikes = 0

    def hard_reset(self) -> None:
        """执行破坏性 hard reset，包括 Tile 权重和 commit 元数据。"""
        LOGGER.info("Host Bridge oracle hard reset")
        self.tile.hard_reset()
        self._clear_bridge_state()

    def record_controller_fault(self, opcode: int | Opcode) -> None:
        """测试/scoreboard 注入口：记录不属于 Tile phase 的控制器内部故障。"""
        raw_opcode = int(opcode)
        if not 0 <= raw_opcode <= 0xFF:
            raise ValueError("fatal opcode 必须是 8-bit 无符号整数")
        if not self.fatal_error:
            self.fatal_error = True
            self.fatal_opcode = raw_opcode
            self.fatal_phase = FatalPhase.CONTROLLER_INTERNAL
            LOGGER.error("Host Bridge oracle controller internal fatal: opcode=0x%02x", raw_opcode)

    @property
    def tick_exhausted(self) -> bool:
        return bool(self.next_tick_ext & 0x10000)

    def architectural_state(self) -> tuple[object, ...]:
        """返回 Host 可见的 session/input-tick/fatal 状态。"""
        return (
            self.episode_active,
            self.episode_train,
            self.active_episode_id,
            self.next_tick_ext,
            self.tick_open,
            self.expected_event_count,
            self.seen_event_count,
            self.seen_mask,
            self.fatal_error,
            int(self.fatal_opcode),
            int(self.fatal_phase),
        )

    def working_state(self) -> tuple[int, int, int]:
        """返回当前单槽事务工作寄存器。execute 返回后应全部释放。"""
        return self.active_command_reg, self.response_reg, self.ep_end_flush_spikes

    @staticmethod
    def _response(
        command: Flit,
        status: Status,
        *,
        episode_id: int | None = None,
        tick_id: int | None = None,
        arg0: int = 0,
        arg1: int = 0,
    ) -> Flit:
        return Flit(
            opcode=command.opcode,
            flags=int(status),
            txn_id=command.txn_id,
            episode_id=command.episode_id if episode_id is None else episode_id,
            tick_id=command.tick_id if tick_id is None else tick_id,
            arg0=arg0 & 0xFFFFFFFF,
            arg1=arg1 & 0xFFFFFFFF,
        )

    @staticmethod
    def _opcode(command: Flit) -> Opcode | None:
        try:
            return Opcode(command.opcode)
        except ValueError:
            return None

    @staticmethod
    def _static_fields_valid(opcode: Opcode, command: Flit) -> bool:
        if opcode == Opcode.EP_START:
            return (
                command.flags & ~0x1 == 0
                and command.tick_id == 0
                and command.arg0 == 0
                and command.arg1 == 0
            )
        if opcode in (Opcode.TICK_BEGIN, Opcode.INPUT_EVENT):
            return command.flags == 0 and command.arg0 <= 0x7 and command.arg1 == 0
        if opcode == Opcode.TICK_COMMIT:
            return command.flags == 0 and command.arg0 == 0 and command.arg1 == 0
        if opcode == Opcode.EP_END:
            return (
                command.flags == 0
                and command.tick_id == 0
                and command.arg0 <= 0xFFFF
                and command.arg1 == 0
            )
        if opcode == Opcode.MOD_COMMIT:
            if not (
                command.flags == 0
                and command.tick_id == 0
                and command.arg0 <= 0xFFFF
                and command.arg1 <= 0xFF
            ):
                return False
            try:
                decode_modulators(command.arg1)
            except ValueError:
                return False
            return True
        if opcode == Opcode.WEIGHT_WRITE:
            return (
                command.flags == 0
                and command.episode_id == 0
                and command.tick_id == 0
                and command.arg0 <= 0xFFF
                and command.arg1 == 0
            )
        if opcode == Opcode.WEIGHT_READ:
            return (
                command.flags == 0
                and command.episode_id == 0
                and command.tick_id == 0
                and command.arg0 <= 0xF
                and command.arg1 == 0
            )
        if opcode == Opcode.ABORT:
            return (
                command.flags == 0
                and command.tick_id == 0
                and command.arg0 == 0
                and command.arg1 == 0
            )
        if opcode == Opcode.STATUS_READ:
            return (
                command.flags == 0
                and command.episode_id == 0
                and command.tick_id == 0
                and command.arg0 <= 1
                and command.arg1 == 0
            )
        raise AssertionError(f"未处理 opcode {opcode}")

    @staticmethod
    def _weight_address(command: Flit) -> tuple[int, int]:
        return command.arg0 & 0x3, (command.arg0 >> 2) & 0x3

    @staticmethod
    def _signed_weight_data(command: Flit) -> int:
        raw = (command.arg0 >> 4) & 0xFF
        return raw - 0x100 if raw & 0x80 else raw

    def _dynamic_error(self, opcode: Opcode, command: Flit) -> Status | None:
        if opcode == Opcode.EP_START:
            train = bool(command.flags & 1)
            if self.episode_active:
                return Status.BAD_STATE
            if train and self.tile.snapshot_valid:
                return Status.SNAPSHOT_BUSY
            if train and self.tile.last_commit_valid and self.tile.last_commit_id == 0xFFFF:
                return Status.COUNTER_WRAP
            return None

        if opcode == Opcode.TICK_BEGIN:
            if not self.episode_active or self.tick_open:
                return Status.BAD_STATE
            if command.episode_id != self.active_episode_id:
                return Status.EPISODE_ID
            if self.tick_exhausted:
                return Status.COUNTER_WRAP
            if command.tick_id != (self.next_tick_ext & 0xFFFF):
                return Status.TICK_ID
            if command.arg0 > 4:
                return Status.EVENT_COUNT
            return None

        if opcode == Opcode.INPUT_EVENT:
            if not self.episode_active or not self.tick_open:
                return Status.BAD_STATE
            if command.episode_id != self.active_episode_id:
                return Status.EPISODE_ID
            if command.tick_id != (self.next_tick_ext & 0xFFFF):
                return Status.TICK_ID
            synapse = command.arg0 & 0x7
            if synapse >= 4:
                return Status.SYNAPSE_RANGE
            if self.seen_mask & (1 << synapse):
                return Status.DUP_EVENT
            if self.seen_event_count >= self.expected_event_count:
                return Status.EVENT_COUNT
            return None

        if opcode == Opcode.TICK_COMMIT:
            if not self.episode_active or not self.tick_open:
                return Status.BAD_STATE
            if command.episode_id != self.active_episode_id:
                return Status.EPISODE_ID
            if command.tick_id != (self.next_tick_ext & 0xFFFF):
                return Status.TICK_ID
            if self.seen_event_count != self.expected_event_count:
                return Status.EVENT_COUNT
            return None

        if opcode == Opcode.EP_END:
            if not self.episode_active or self.tick_open:
                return Status.BAD_STATE
            if command.episode_id != self.active_episode_id:
                return Status.EPISODE_ID
            commit_id = command.arg0 & 0xFFFF
            if not self.episode_train and commit_id != 0:
                return Status.BAD_FIELD
            if self.episode_train and self.tile.snapshot_valid:
                return Status.SNAPSHOT_BUSY
            if (
                self.episode_train
                and self.tile.last_commit_valid
                and self.tile.last_commit_id == 0xFFFF
            ):
                return Status.COUNTER_WRAP
            if (
                self.episode_train
                and self.tile.last_commit_valid
                and commit_id <= self.tile.last_commit_id
            ):
                return Status.COMMIT_ID
            return None

        if opcode == Opcode.MOD_COMMIT:
            if self.episode_active:
                return Status.BAD_STATE
            if not self.tile.snapshot_valid:
                return Status.COMMIT_ID
            if command.episode_id != self.tile.pending_episode_id:
                return Status.EPISODE_ID
            if (command.arg0 & 0xFFFF) != self.tile.pending_commit_id:
                return Status.COMMIT_ID
            return None

        neuron, weight = self._weight_address(command)
        if opcode == Opcode.WEIGHT_READ:
            if self.episode_active:
                return Status.BAD_STATE
            if not self.tile.address_valid(neuron, weight):
                return Status.ADDRESS
            return None

        if opcode == Opcode.WEIGHT_WRITE:
            if self.episode_active:
                return Status.BAD_STATE
            if self.tile.snapshot_valid:
                return Status.SNAPSHOT_BUSY
            if not self.tile.address_valid(neuron, weight):
                return Status.ADDRESS
            return None

        if opcode == Opcode.ABORT:
            if not self.episode_active:
                return Status.BAD_STATE
            if command.episode_id != self.active_episode_id:
                return Status.EPISODE_ID
            return None

        if opcode == Opcode.STATUS_READ:
            return None

        raise AssertionError(f"未处理 opcode {opcode}")

    def _latch_fatal(self, opcode: Opcode, phase: FatalPhase, error: Exception) -> None:
        if not self.fatal_error:
            self.fatal_error = True
            self.fatal_opcode = opcode
            self.fatal_phase = phase
            LOGGER.error(
                "Host Bridge oracle internal fatal: opcode=%s phase=%s error=%s",
                opcode.name,
                phase.name,
                error,
            )

    def _run_tile(
        self,
        opcode: Opcode,
        phase: FatalPhase,
        operation,
    ):
        try:
            return operation()
        except Exception as error:  # Tile backend 是显式外部故障边界。
            self._latch_fatal(opcode, phase, error)
            raise

    def _clear_session(self) -> None:
        self.episode_active = False
        self.episode_train = False
        self.active_episode_id = 0
        self.next_tick_ext = 0
        self.tick_open = False
        self.expected_event_count = 0
        self.seen_event_count = 0
        self.seen_mask = 0

    def _status_response(self, command: Flit) -> Flit:
        if command.arg0 == 0:
            arg0 = 0
            arg0 |= int(self.episode_active)
            arg0 |= int(self.episode_train) << 1
            arg0 |= int(self.tick_open) << 2
            arg0 |= int(self.tick_exhausted) << 3
            arg0 |= int(self.fatal_error) << 4
            arg0 |= self.expected_event_count << 8
            arg0 |= self.seen_event_count << 11
            arg0 |= self.seen_mask << 14
            fatal_opcode = int(self.fatal_opcode) if self.fatal_error else 0
            fatal_phase = int(self.fatal_phase) if self.fatal_error else 0
            return self._response(
                command,
                Status.OK,
                episode_id=self.active_episode_id if self.episode_active else 0,
                tick_id=self.next_tick_ext & 0xFFFF,
                arg0=arg0,
                arg1=fatal_opcode | (fatal_phase << 8),
            )

        snapshot_valid = self.tile.snapshot_valid
        arg0 = self.tile.last_commit_id if self.tile.last_commit_valid else 0
        arg0 |= int(snapshot_valid) << 16
        arg0 |= int(self.tile.last_commit_valid) << 17
        return self._response(
            command,
            Status.OK,
            episode_id=self.tile.pending_episode_id if snapshot_valid else 0,
            tick_id=self.tile.pending_commit_id if snapshot_valid else 0,
            arg0=arg0,
            arg1=self.tile.weight_epoch,
        )

    def _execute_valid(self, opcode: Opcode, command: Flit) -> Flit:
        if opcode == Opcode.EP_START:
            self._run_tile(
                opcode,
                FatalPhase.EP_START_CLEAR_WAIT,
                self.tile.state_clear,
            )
            self.episode_active = True
            self.episode_train = bool(command.flags & 1)
            self.active_episode_id = command.episode_id
            self.next_tick_ext = 0
            self.tick_open = False
            self.expected_event_count = 0
            self.seen_event_count = 0
            self.seen_mask = 0
            return self._response(command, Status.OK)

        if opcode == Opcode.TICK_BEGIN:
            self.tick_open = True
            self.expected_event_count = command.arg0 & 0x7
            self.seen_event_count = 0
            self.seen_mask = 0
            return self._response(command, Status.OK)

        if opcode == Opcode.INPUT_EVENT:
            synapse = command.arg0 & 0x7
            self.seen_event_count += 1
            self.seen_mask |= 1 << synapse
            return self._response(command, Status.OK)

        if opcode == Opcode.TICK_COMMIT:
            hidden, output = self._run_tile(
                opcode,
                FatalPhase.TICK_WAIT,
                lambda: self.tile.tick(self.seen_mask, self.episode_train),
            )
            self.tick_open = False
            self.expected_event_count = 0
            self.seen_event_count = 0
            self.seen_mask = 0
            self.next_tick_ext += 1
            return self._response(command, Status.OK, arg0=hidden | (output << 2))

        if opcode == Opcode.EP_END:
            output = self._run_tile(
                opcode,
                FatalPhase.EP_END_FLUSH_WAIT,
                lambda: self.tile.route_flush(self.episode_train),
            )
            self.ep_end_flush_spikes = output & 0x3
            self.last_ep_end_flush_spikes = self.ep_end_flush_spikes
            if self.episode_train:
                self._run_tile(
                    opcode,
                    FatalPhase.EP_END_SNAPSHOT_WAIT,
                    lambda: self.tile.snapshot(command.arg0 & 0xFFFF, command.episode_id),
                )
            response = self._response(
                command,
                Status.OK,
                arg0=self.ep_end_flush_spikes << 2,
                arg1=self.tile.weight_epoch,
            )
            self._clear_session()
            return response

        if opcode == Opcode.MOD_COMMIT:
            modulators = decode_modulators(command.arg1 & 0xFF)
            self._run_tile(
                opcode,
                FatalPhase.MOD_WAIT,
                lambda: self.tile.mod_commit(command.arg0 & 0xFFFF, modulators),
            )
            return self._response(
                command,
                Status.OK,
                arg0=command.arg0 & 0xFFFF,
                arg1=self.tile.weight_epoch,
            )

        if opcode == Opcode.WEIGHT_WRITE:
            neuron, weight = self._weight_address(command)
            value = self._signed_weight_data(command)
            self._run_tile(
                opcode,
                FatalPhase.WEIGHT_WAIT,
                lambda: self.tile.weight_write(neuron, weight, value),
            )
            return self._response(command, Status.OK)

        if opcode == Opcode.WEIGHT_READ:
            neuron, weight = self._weight_address(command)
            value = self._run_tile(
                opcode,
                FatalPhase.WEIGHT_WAIT,
                lambda: self.tile.weight_read(neuron, weight),
            )
            return self._response(command, Status.OK, arg0=value & 0xFFFFFFFF)

        if opcode == Opcode.ABORT:
            self._run_tile(
                opcode,
                FatalPhase.ABORT_CLEAR_WAIT,
                self.tile.state_clear,
            )
            self._clear_session()
            return self._response(command, Status.OK)

        if opcode == Opcode.STATUS_READ:
            return self._status_response(command)

        raise AssertionError(f"未处理 opcode {opcode}")

    def execute(self, command: Flit) -> Flit:
        """消费一条命令，并返回 response FIFO 已接受的响应。"""
        self.active_command_reg = command.pack()
        LOGGER.debug(
            "execute opcode=0x%02x txn=%d episode=%d tick=%d",
            command.opcode,
            command.txn_id,
            command.episode_id,
            command.tick_id,
        )
        try:
            opcode = self._opcode(command)
            if self.fatal_error and opcode != Opcode.STATUS_READ:
                response = self._response(command, Status.INTERNAL_FATAL)
            elif opcode is None:
                response = self._response(command, Status.BAD_OPCODE)
            elif not self._static_fields_valid(opcode, command):
                response = self._response(command, Status.BAD_FIELD)
            else:
                error = self._dynamic_error(opcode, command)
                if error is not None:
                    response = self._response(command, error)
                else:
                    try:
                        response = self._execute_valid(opcode, command)
                    except Exception:
                        response = self._response(command, Status.INTERNAL_FATAL)
            self.response_reg = response.pack()
            return response
        finally:
            # execute 的边界等价于 response_accept，同拍释放事务工作状态。
            self.active_command_reg = 0
            self.response_reg = 0
            self.ep_end_flush_spikes = 0

"""局部 2:4 剪枝 RTL 的事务级黄金模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable


class Mode(IntEnum):
    CONFIG = 0
    TRAIN = 1
    INFER = 2
    INVALID = 3


class Opcode(IntEnum):
    OBSERVE = 0
    PRUNE_CLEAR = 1
    PRUNE_COMMIT = 2
    MASK_READ = 3


class Status(IntEnum):
    OK = 0
    BAD_OPCODE = 1
    BAD_MODE = 2
    UNSAFE = 3
    STALE_ID = 4
    ALREADY_COMMITTED = 5
    BAD_ARG = 6


MODEL_GAINS = {
    "eneuron": 1,
    "pulse_mini_l": 2,
    "pulse_mini_l2": 1,
}


@dataclass(frozen=True)
class GateTransaction:
    """一个已握手的命令、CONFIG 写或纯 issue 事务。"""

    kind: int  # 0=command, 1=config mask write, 2=issue only
    mode: int = Mode.CONFIG
    opcode: int = Opcode.MASK_READ
    txn_id: int = 0
    raw_evidence_flat: int = 0
    modulator_nonzero: int = 0
    core_idle: int = 1
    pending_snapshot: int = 0
    pending_mod_commit: int = 0
    issue_valid: int = 0
    activity_mask: int = 0
    issue_layer_output: int = 0
    cfg_mask: int = 0b0011
    response_hold_cycles: int = 0
    inject_busy_command: int = 0

    def as_line(self) -> str:
        values = (
            self.kind,
            int(self.mode),
            int(self.opcode),
            self.txn_id,
            self.raw_evidence_flat,
            self.modulator_nonzero,
            self.core_idle,
            self.pending_snapshot,
            self.pending_mod_commit,
            self.issue_valid,
            self.activity_mask,
            self.issue_layer_output,
            self.cfg_mask,
            self.response_hold_cycles,
            self.inject_busy_command,
        )
        return " ".join(str(value) for value in values)


def pack_levels(levels: Iterable[int]) -> int:
    values = tuple(levels)
    if len(values) != 4 or any(value < 0 or value > 3 for value in values):
        raise ValueError("levels must contain four values within 0..3")
    return sum(value << (2 * index) for index, value in enumerate(values))


def unpack_levels(flat: int) -> tuple[int, int, int, int]:
    return tuple((flat >> (2 * index)) & 0x3 for index in range(4))  # type: ignore[return-value]


def scale_levels(flat: int, gain: int) -> tuple[int, int, int, int]:
    return tuple(min(3, gain * value) for value in unpack_levels(flat))  # type: ignore[return-value]


class LocalPruneRtlReference:
    """与 `local_prune_gate_2of4.sv` 可见状态一致的原子模型。"""

    def __init__(self, *, model_name: str) -> None:
        if model_name not in MODEL_GAINS:
            raise ValueError(f"unknown model: {model_name}")
        self.gain = MODEL_GAINS[model_name]
        self.utility = [0, 0, 0, 0]
        self.structural_mask = 0b1111
        self.mask_valid = False
        self.last_observation_valid = False
        self.last_observation_id = 0
        self.last_commit_valid = False
        self.last_commit_id = 0
        self.mask_commits = 0
        self.illegal_commands = 0
        self.hidden_dense_reads = 0
        self.hidden_reads_issued = 0
        self.hidden_synapse_ops = 0
        self.hidden_reads_saved = 0
        self.output_dense_reads = 0
        self.output_reads_issued = 0
        self.output_synapse_ops = 0
        self.output_reads_saved = 0
        self.inactive_groups = 0
        self.groups_skipped = 0

    @property
    def effective_mask(self) -> int:
        return self.structural_mask if self.mask_valid else 0b1111

    def _issue(self, transaction: GateTransaction) -> None:
        if not transaction.issue_valid:
            return
        activity = transaction.activity_mask & 0xF
        issue = activity & self.effective_mask
        dense = activity.bit_count()
        issued = issue.bit_count()
        saved = dense - issued
        if activity == 0:
            self.inactive_groups += 1
        elif issue == 0:
            self.groups_skipped += 1
        if transaction.issue_layer_output:
            self.output_dense_reads += dense
            self.output_reads_issued += issued
            self.output_synapse_ops += issued
            self.output_reads_saved += saved
        else:
            self.hidden_dense_reads += dense
            self.hidden_reads_issued += issued
            self.hidden_synapse_ops += issued
            self.hidden_reads_saved += saved

    def _reject(self, status: Status) -> Status:
        self.illegal_commands += 1
        return status

    def _observe(self, transaction: GateTransaction) -> Status:
        if transaction.mode != Mode.TRAIN:
            return self._reject(Status.BAD_MODE)
        if self.last_observation_valid and transaction.txn_id <= self.last_observation_id:
            return self._reject(Status.STALE_ID)
        if transaction.modulator_nonzero:
            levels = scale_levels(transaction.raw_evidence_flat, self.gain)
            active = self.effective_mask
            for index, level in enumerate(levels):
                if active & (1 << index):
                    self.utility[index] = min(15, max(0, self.utility[index] - 1) + level)
        self.last_observation_valid = True
        self.last_observation_id = transaction.txn_id
        return Status.OK

    def _clear(self, transaction: GateTransaction) -> Status:
        if transaction.mode != Mode.CONFIG:
            return self._reject(Status.BAD_MODE)
        self.utility = [0, 0, 0, 0]
        self.structural_mask = 0b1111
        self.mask_valid = False
        self.last_observation_valid = False
        self.last_observation_id = 0
        self.last_commit_valid = False
        self.last_commit_id = 0
        return Status.OK

    def _commit(self, transaction: GateTransaction) -> Status:
        if transaction.mode != Mode.TRAIN:
            return self._reject(Status.BAD_MODE)
        if (
            not transaction.core_idle
            or transaction.issue_valid
            or transaction.pending_snapshot
            or transaction.pending_mod_commit
        ):
            return self._reject(Status.UNSAFE)
        if self.mask_valid:
            return self._reject(Status.ALREADY_COMMITTED)
        if self.last_commit_valid and transaction.txn_id <= self.last_commit_id:
            return self._reject(Status.STALE_ID)
        ranked = sorted(range(4), key=lambda index: (self.utility[index], -index), reverse=True)
        self.structural_mask = (1 << ranked[0]) | (1 << ranked[1])
        self.mask_valid = True
        self.last_commit_valid = True
        self.last_commit_id = transaction.txn_id
        self.mask_commits += 1
        return Status.OK

    def _command(self, transaction: GateTransaction) -> Status:
        if transaction.opcode == Opcode.OBSERVE:
            return self._observe(transaction)
        if transaction.opcode == Opcode.PRUNE_CLEAR:
            return self._clear(transaction)
        if transaction.opcode == Opcode.PRUNE_COMMIT:
            return self._commit(transaction)
        if transaction.opcode == Opcode.MASK_READ:
            if transaction.mode not in (Mode.CONFIG, Mode.TRAIN, Mode.INFER):
                return self._reject(Status.BAD_MODE)
            return Status.OK
        return self._reject(Status.BAD_OPCODE)

    def _config_write(self, transaction: GateTransaction) -> bool:
        if transaction.mode != Mode.CONFIG or (transaction.cfg_mask & 0xF).bit_count() != 2:
            self.illegal_commands += 1
            return True
        self.structural_mask = transaction.cfg_mask & 0xF
        self.mask_valid = True
        return False

    def apply(self, transaction: GateTransaction) -> tuple[int, ...]:
        self._issue(transaction)
        status = Status.OK
        cfg_error = False
        response_id = 0
        response_mask = self.effective_mask
        if transaction.kind == 0:
            response_id = transaction.txn_id & 0xFFFF
            status = self._command(transaction)
            response_mask = self.effective_mask
        elif transaction.kind == 1:
            cfg_error = self._config_write(transaction)
            response_mask = self.effective_mask
        elif transaction.kind != 2:
            raise ValueError("transaction kind must be 0, 1 or 2")
        return self.row(
            kind=transaction.kind,
            status=int(status),
            response_id=response_id,
            response_mask=response_mask,
            cfg_error=int(cfg_error),
        )

    def row(
        self,
        *,
        kind: int,
        status: int,
        response_id: int,
        response_mask: int,
        cfg_error: int,
    ) -> tuple[int, ...]:
        utility_flat = sum(value << (4 * index) for index, value in enumerate(self.utility))
        return (
            kind,
            status,
            response_id,
            response_mask,
            cfg_error,
            utility_flat,
            self.structural_mask,
            int(self.mask_valid),
            int(self.last_observation_valid),
            self.last_observation_id,
            int(self.last_commit_valid),
            self.last_commit_id,
            self.mask_commits,
            self.illegal_commands,
            self.hidden_dense_reads,
            self.hidden_reads_issued,
            self.hidden_synapse_ops,
            self.hidden_reads_saved,
            self.output_dense_reads,
            self.output_reads_issued,
            self.output_synapse_ops,
            self.output_reads_saved,
            self.inactive_groups,
            self.groups_skipped,
        )


__all__ = [
    "GateTransaction",
    "LocalPruneRtlReference",
    "MODEL_GAINS",
    "Mode",
    "Opcode",
    "Status",
    "pack_levels",
    "scale_levels",
]

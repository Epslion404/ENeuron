"""Host Bridge 训练命令账本与可复现哈希。"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from host_bridge_oracle import Flit, Opcode, Status


LOGGER = logging.getLogger("m3_training_ledger")

_DOMAIN = b"ENeuron/M3TrainingLedger/v1\0"


@dataclass(frozen=True)
class OpcodeStatistics:
    """一个 opcode 在账本中的出现次数和成功次数。"""

    seen: int
    successful: int


@dataclass(frozen=True)
class TrainingLedgerReport:
    """训练账本的 canonical 摘要、哈希链和关键命令统计。"""

    canonical_sha256: str
    hash_chain: tuple[str, ...]
    weight_write: OpcodeStatistics
    mod_commit: OpcodeStatistics


def audit_training_ledger(
    flits: Sequence[Flit],
    training_start: int,
) -> TrainingLedgerReport:
    """审计按 Host Bridge 响应语义记录的 Flit 序列。"""

    records = tuple(flits)
    if not isinstance(training_start, int) or not 0 <= training_start <= len(records):
        raise ValueError("training_start 必须位于 Flit 序列边界内")
    if any(not isinstance(flit, Flit) for flit in records):
        raise TypeError("训练账本只能包含 HostBridge Flit")

    # 训练边界包含 training_start 指向的记录；失败命令也必须保留为违规证据。
    for index, flit in enumerate(records[training_start:], start=training_start):
        if flit.opcode == int(Opcode.WEIGHT_WRITE):
            LOGGER.error(
                "训练账本拒绝 WEIGHT_WRITE index=%d status=%d txn_id=%d",
                index,
                flit.flags,
                flit.txn_id,
            )
            raise ValueError(
                f"training_start 后禁止 WEIGHT_WRITE: index={index} status={flit.flags}"
            )

    # 固定宽度头部把版本、训练边界和记录数量一并绑定到摘要。
    header = (
        _DOMAIN
        + training_start.to_bytes(8, byteorder="big")
        + len(records).to_bytes(8, byteorder="big")
    )
    canonical_records = tuple(
        index.to_bytes(8, byteorder="big") + flit.to_bytes()
        for index, flit in enumerate(records)
    )
    canonical_sha256 = hashlib.sha256(header + b"".join(canonical_records)).hexdigest()

    previous = hashlib.sha256(header).digest()
    hash_chain: list[str] = []
    for record in canonical_records:
        previous = hashlib.sha256(previous + record).digest()
        hash_chain.append(previous.hex())

    weight_write = _opcode_statistics(records, Opcode.WEIGHT_WRITE)
    mod_commit = _opcode_statistics(records, Opcode.MOD_COMMIT)
    LOGGER.info(
        "训练账本完成 flits=%d training_start=%d weight_write=%d/%d mod_commit=%d/%d",
        len(records),
        training_start,
        weight_write.successful,
        weight_write.seen,
        mod_commit.successful,
        mod_commit.seen,
    )
    return TrainingLedgerReport(
        canonical_sha256=canonical_sha256,
        hash_chain=tuple(hash_chain),
        weight_write=weight_write,
        mod_commit=mod_commit,
    )


def _opcode_statistics(flits: Sequence[Flit], opcode: Opcode) -> OpcodeStatistics:
    """按响应 status 统计指定 opcode；flags=0 表示成功。"""

    matching = tuple(flit for flit in flits if flit.opcode == int(opcode))
    successful = sum(flit.flags == int(Status.OK) for flit in matching)
    return OpcodeStatistics(seen=len(matching), successful=successful)

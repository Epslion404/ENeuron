"""原始 Goal M3 的独立冻结向量验收器。"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from host_bridge_oracle import Opcode, Status
from m3_task import M3CommandPlan, M3RtlReport, run_rtl_m3
from m3_training_ledger import audit_training_ledger


LOGGER = logging.getLogger("m3_acceptance")

EXPECTED_COMMAND_COUNT = 957
EXPECTED_TRAINING_START = 64
EXPECTED_COMMAND_SHA256 = (
    "191d7c588411515f4386685b6dfcd8ce7e3894a21f87ff3a54a40de2f9989c09"
)
EXPECTED_LEDGER_SHA256 = (
    "cb63bcc596843607cdb7c774a91a8ffd38d9b21ee304cd266ecd33e2974a5256"
)
EXPECTED_CHAIN_TAIL = (
    "cf4b268a199675d71462f1b6ec55a76f38691f4e6dbd90d9cf8d1b72e1509a74"
)
EXPECTED_FINAL_WEIGHTS = (
    (-6, -7, 7, 7),
    (7, 7, -6, -7),
    (7, -7),
    (-7, 7),
)


@dataclass(frozen=True)
class ExpectedCommit:
    """冻结的一次本地学习定点转移。"""

    modulators: tuple[int, int, int, int]
    pre_weights: tuple[tuple[int, ...], ...]
    snapshots: tuple[tuple[int, ...], ...]
    deltas: tuple[tuple[int, ...], ...]
    post_weights: tuple[tuple[int, ...], ...]


EXPECTED_COMMITS = (
    ExpectedCommit(
        modulators=(1, -1, 1, -1),
        pre_weights=((2, 2, 2, 2), (2, 2, 2, 2), (2, 2), (2, 2)),
        snapshots=((0, 0, 36, 39), (0, 0, 36, 39), (39, 39), (39, 39)),
        deltas=((0, 0, 4, 4), (0, 0, -5, -5), (4, 4), (-5, -5)),
        post_weights=((2, 2, 6, 6), (2, 2, -3, -3), (6, 6), (-3, -3)),
    ),
    ExpectedCommit(
        modulators=(-1, 1, -1, 1),
        pre_weights=((2, 2, 6, 6), (2, 2, -3, -3), (6, 6), (-3, -3)),
        snapshots=((36, 39, 0, 0), (36, 39, 0, 0), (39, 39), (16, 16)),
        deltas=((-5, -5, 0, 0), (4, 4, 0, 0), (-5, -5), (2, 2)),
        post_weights=((-3, -3, 6, 6), (6, 6, -3, -3), (1, 1), (-1, -1)),
    ),
    ExpectedCommit(
        modulators=(1, -1, 1, -1),
        pre_weights=((-3, -3, 6, 6), (6, 6, -3, -3), (1, 1), (-1, -1)),
        snapshots=((0, 0, 48, 54), (0, 0, 21, 27), (79, 0), (79, 0)),
        deltas=((0, 0, 6, 6), (0, 0, -3, -4), (9, 0), (-10, 0)),
        post_weights=((-3, -3, 7, 7), (6, 6, -6, -7), (7, 1), (-7, -1)),
    ),
    ExpectedCommit(
        modulators=(-1, 1, -1, 1),
        pre_weights=((-3, -3, 7, 7), (6, 6, -6, -7), (7, 1), (-7, -1)),
        snapshots=((21, 27, 0, 0), (48, 54, 0, 0), (0, 79), (0, 79)),
        deltas=((-3, -4, 0, 0), (6, 6, 0, 0), (0, -10), (0, 9)),
        post_weights=((-6, -7, 7, 7), (7, 7, -6, -7), (7, -7), (-7, 7)),
    ),
)


@dataclass(frozen=True)
class M3AcceptanceSummary:
    """供一键 Goal 审计和机器摘要使用的最小签核结果。"""

    command_count: int
    training_start: int
    command_sha256: str
    ledger_sha256: str
    ledger_chain_tail: str
    mod_commit_count: int
    weight_write_count: int
    noisy_correct: int
    noisy_total: int
    final_weights: tuple[tuple[int, ...], ...]


def _flatten(weights: tuple[tuple[int, ...], ...]) -> tuple[int, ...]:
    return tuple(value for neuron in weights for value in neuron)


def verify_m3_report(
    plan: M3CommandPlan,
    report: M3RtlReport,
) -> M3AcceptanceSummary:
    """独立检查任务结果、账本、快照公式、读回和冻结哈希。"""

    command_sha256 = hashlib.sha256(
        b"".join(request.to_bytes() for request in plan.commands)
    ).hexdigest()
    if (len(plan.commands), plan.training_start, command_sha256) != (
        EXPECTED_COMMAND_COUNT,
        EXPECTED_TRAINING_START,
        EXPECTED_COMMAND_SHA256,
    ):
        raise AssertionError(
            "M3 命令计划漂移: "
            f"count={len(plan.commands)} training_start={plan.training_start} "
            f"sha256={command_sha256}"
        )
    if plan.commands[plan.training_start].opcode != int(Opcode.EP_START) or not (
        plan.commands[plan.training_start].flags & 1
    ):
        raise AssertionError("M3 training_start 未指向首个 TRAIN EP_START")
    if any(
        request.opcode == int(Opcode.WEIGHT_WRITE)
        for request in plan.commands[plan.training_start :]
    ):
        raise AssertionError("M3 训练区间出现 WEIGHT_WRITE 命令")

    if (report.pretrain_predictions, report.clean_predictions) != ((-1, -1), (0, 1)):
        raise AssertionError(
            "M3 clean 任务结果漂移: "
            f"pretrain={report.pretrain_predictions} clean={report.clean_predictions}"
        )
    if (report.noisy_correct, report.noisy_total) != (20, 20):
        raise AssertionError(
            f"M3 扰动任务失败: {report.noisy_correct}/{report.noisy_total}"
        )
    if report.weight_epoch != 4 or report.final_weights != EXPECTED_FINAL_WEIGHTS:
        raise AssertionError(
            f"M3 最终状态漂移: epoch={report.weight_epoch} weights={report.final_weights}"
        )

    if len(report.responses) != len(plan.commands):
        raise AssertionError("M3 响应数量与命令数量不一致")
    for index, (request, response) in enumerate(
        zip(plan.commands, report.responses, strict=True)
    ):
        if response.flags != int(Status.OK):
            raise AssertionError(f"M3 response[{index}] status={response.flags}")
        if (
            response.opcode,
            response.txn_id,
            response.episode_id,
            response.tick_id,
        ) != (
            request.opcode,
            request.txn_id,
            request.episode_id,
            request.tick_id,
        ):
            raise AssertionError(f"M3 response[{index}] 未对应原命令")

    if report.ledger.weight_write.seen or report.ledger.weight_write.successful:
        raise AssertionError(
            "M3 WEIGHT_WRITE 账本非零: "
            f"seen={report.ledger.weight_write.seen} "
            f"successful={report.ledger.weight_write.successful}"
        )
    if (report.ledger.mod_commit.seen, report.ledger.mod_commit.successful) != (4, 4):
        raise AssertionError(f"M3 MOD_COMMIT 账本错误: {report.ledger.mod_commit}")
    independent_ledger = audit_training_ledger(
        report.responses,
        training_start=plan.training_start,
    )
    if report.ledger != independent_ledger:
        raise AssertionError("M3 报告账本与独立重算不一致")
    if report.ledger.canonical_sha256 != EXPECTED_LEDGER_SHA256:
        raise AssertionError(
            f"M3 响应账本哈希漂移: {report.ledger.canonical_sha256}"
        )
    if not report.ledger.hash_chain or report.ledger.hash_chain[-1] != EXPECTED_CHAIN_TAIL:
        raise AssertionError("M3 响应账本 hash chain 尾值漂移")

    if len(report.commit_evidence) != len(EXPECTED_COMMITS):
        raise AssertionError("M3 eligibility 证据数量错误")
    for commit_id, (actual, expected) in enumerate(
        zip(report.commit_evidence, EXPECTED_COMMITS, strict=True)
    ):
        if actual.commit_id != commit_id or actual.weight_epoch != commit_id + 1:
            raise AssertionError(f"M3 commit/epoch 序列错误: commit={commit_id}")
        if actual.modulators != expected.modulators:
            raise AssertionError(f"M3 modulator 漂移: commit={commit_id}")
        if actual.eligibility_snapshots != expected.snapshots:
            raise AssertionError(f"M3 eligibility 快照漂移: commit={commit_id}")
        if actual.pre_weights != expected.pre_weights:
            raise AssertionError(f"M3 前权重漂移: commit={commit_id}")
        if actual.deltas != expected.deltas:
            raise AssertionError(f"M3 定点 delta 漂移: commit={commit_id}")
        if actual.expected_weights != expected.post_weights:
            raise AssertionError(f"M3 期望后权重漂移: commit={commit_id}")
        if actual.read_weights != _flatten(expected.post_weights):
            raise AssertionError(f"M3 RTL 权重读回漂移: commit={commit_id}")

    LOGGER.info(
        "M3 acceptance PASS: commands=%d ledger=%s commits=4 noisy=20/20",
        len(plan.commands),
        report.ledger.canonical_sha256,
    )
    return M3AcceptanceSummary(
        command_count=len(plan.commands),
        training_start=plan.training_start,
        command_sha256=command_sha256,
        ledger_sha256=report.ledger.canonical_sha256,
        ledger_chain_tail=report.ledger.hash_chain[-1],
        mod_commit_count=report.ledger.mod_commit.successful,
        weight_write_count=report.ledger.weight_write.seen,
        noisy_correct=report.noisy_correct,
        noisy_total=report.noisy_total,
        final_weights=report.final_weights,
    )


def run_m3_acceptance(seed: int = 0x4D33) -> M3AcceptanceSummary:
    """生成冻结计划、运行真实双时钟 RTL 并执行独立验收。"""

    plan = M3CommandPlan.build()
    return verify_m3_report(plan, run_rtl_m3(plan, seed=seed))

"""原始 Goal M3 的最小、确定性 Host 训练任务。"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from host_bridge_controller_cosim import command
from host_bridge_oracle import (
    Flit,
    HostBridgeOracle,
    Opcode,
    Status,
    decode_modulators,
    encode_modulators,
)
from host_bridge_system_cosim import run_command_sequence
from m3_training_ledger import TrainingLedgerReport, audit_training_ledger
from network_sim import make_noisy_dataset
from neuron_sim import TrialEvents, make_trial


LOGGER = logging.getLogger("m3_task")
TRAIN_EPOCHS = 2
NOISY_SEED = 3
NOISY_COUNT = 20
WEIGHT_ADDRESSES = tuple(
    neuron | (weight << 2)
    for neuron in range(4)
    for weight in range(4 if neuron < 2 else 2)
)


@dataclass(frozen=True)
class M3Report:
    """最小任务在协议 oracle 上的可审核结果。"""

    pretrain_predictions: tuple[int, int]
    clean_predictions: tuple[int, int]
    noisy_correct: int
    noisy_total: int
    weight_epoch: int
    final_weights: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class M3EpisodePlan:
    """一个 episode 的任务标签及产生输出 spike 的响应位置。"""

    phase: str
    label: int
    output_response_indices: tuple[int, ...]


@dataclass(frozen=True)
class M3CommitPlan:
    """一次训练提交及其后 12 个公开权重读回位置。"""

    commit_id: int
    label: int
    response_index: int
    weight_read_indices: tuple[int, ...]


@dataclass(frozen=True)
class M3CommandPlan:
    """真实 Host Bridge M3 run 的冻结命令流和解码索引。"""

    commands: tuple[Flit, ...]
    training_start: int
    episodes: tuple[M3EpisodePlan, ...]
    commits: tuple[M3CommitPlan, ...]
    final_weight_read_indices: tuple[int, ...]
    status_response_index: int

    @classmethod
    def build(cls) -> M3CommandPlan:
        """构造训练前、训练、冻结推理和最终状态读回的单一命令流。"""

        builder = _M3PlanBuilder()
        for label in (0, 1):
            builder.add_episode(make_trial(label), label=label, phase="pretrain")

        training_start = len(builder.commands)
        commit_id = 0
        for _epoch in range(TRAIN_EPOCHS):
            for label in (0, 1):
                builder.add_episode(
                    make_trial(label),
                    label=label,
                    phase="train",
                    train=True,
                    commit_id=commit_id,
                    modulators=_teacher_modulators(label),
                )
                commit_id += 1

        for label in (0, 1):
            builder.add_episode(make_trial(label), label=label, phase="clean")
        for events, label in make_noisy_dataset(seed=NOISY_SEED, count=NOISY_COUNT):
            builder.add_episode(events, label=label, phase="noisy")

        final_reads = builder.add_weight_reads()
        status_index = builder.add(command(Opcode.STATUS_READ, arg0=1))
        plan = cls(
            commands=tuple(builder.commands),
            training_start=training_start,
            episodes=tuple(builder.episodes),
            commits=tuple(builder.commits),
            final_weight_read_indices=final_reads,
            status_response_index=status_index,
        )
        LOGGER.info(
            "M3 command plan built: commands=%d training_start=%d episodes=%d commits=%d",
            len(plan.commands),
            plan.training_start,
            len(plan.episodes),
            len(plan.commits),
        )
        return plan


@dataclass(frozen=True)
class M3CommitEvidence:
    """一次 MOD 的参考快照、定点增量和 RTL 公开读回。"""

    commit_id: int
    modulators: tuple[int, int, int, int]
    pre_weights: tuple[tuple[int, ...], ...]
    eligibility_snapshots: tuple[tuple[int, ...], ...]
    deltas: tuple[tuple[int, ...], ...]
    expected_weights: tuple[tuple[int, ...], ...]
    read_weights: tuple[int, ...]
    weight_epoch: int


@dataclass(frozen=True)
class M3RtlReport:
    """同一真实双时钟 RTL run 的任务、学习来源和读回证据。"""

    responses: tuple[Flit, ...]
    pretrain_predictions: tuple[int, int]
    clean_predictions: tuple[int, int]
    noisy_correct: int
    noisy_total: int
    weight_epoch: int
    post_commit_weight_reads: tuple[tuple[int, ...], ...]
    final_weights: tuple[tuple[int, ...], ...]
    commit_evidence: tuple[M3CommitEvidence, ...]
    ledger: TrainingLedgerReport


class _M3PlanBuilder:
    """用单调 transaction/episode ID 生成可直接发送的 V1 命令。"""

    def __init__(self) -> None:
        self.commands: list[Flit] = []
        self.episodes: list[M3EpisodePlan] = []
        self.commits: list[M3CommitPlan] = []
        self.txn_id = 1
        self.episode_id = 1

    def add(self, request: Flit) -> int:
        """补入当前 ID，返回命令与响应共用的序列索引。"""

        indexed = command(
            request.opcode,
            flags=request.flags,
            txn_id=self.txn_id,
            episode_id=request.episode_id,
            tick_id=request.tick_id,
            arg0=request.arg0,
            arg1=request.arg1,
        )
        index = len(self.commands)
        self.commands.append(indexed)
        self.txn_id += 1
        return index

    def add_episode(
        self,
        events: TrialEvents,
        *,
        label: int,
        phase: str,
        train: bool = False,
        commit_id: int = 0,
        modulators: tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> None:
        """追加完整 episode；训练 episode 立即提交并读回全部权重。"""

        episode_id = self.episode_id
        output_indices: list[int] = []
        self.add(
            command(
                Opcode.EP_START,
                flags=int(train),
                episode_id=episode_id,
            )
        )
        for tick_id, active_inputs in enumerate(events):
            active = tuple(active_inputs)
            self.add(
                command(
                    Opcode.TICK_BEGIN,
                    episode_id=episode_id,
                    tick_id=tick_id,
                    arg0=len(active),
                )
            )
            for synapse_id in active:
                self.add(
                    command(
                        Opcode.INPUT_EVENT,
                        episode_id=episode_id,
                        tick_id=tick_id,
                        arg0=synapse_id,
                    )
                )
            output_indices.append(
                self.add(
                    command(
                        Opcode.TICK_COMMIT,
                        episode_id=episode_id,
                        tick_id=tick_id,
                    )
                )
            )
        output_indices.append(
            self.add(
                command(
                    Opcode.EP_END,
                    episode_id=episode_id,
                    arg0=commit_id if train else 0,
                )
            )
        )
        self.episodes.append(
            M3EpisodePlan(
                phase=phase,
                label=label,
                output_response_indices=tuple(output_indices),
            )
        )
        if train:
            mod_index = self.add(
                command(
                    Opcode.MOD_COMMIT,
                    episode_id=episode_id,
                    arg0=commit_id,
                    arg1=encode_modulators(modulators),
                )
            )
            self.commits.append(
                M3CommitPlan(
                    commit_id=commit_id,
                    label=label,
                    response_index=mod_index,
                    weight_read_indices=self.add_weight_reads(),
                )
            )
        self.episode_id += 1

    def add_weight_reads(self) -> tuple[int, ...]:
        """按 H0/H1/O0/O1 的固定地址顺序读回 12 个权重。"""

        return tuple(
            self.add(command(Opcode.WEIGHT_READ, arg0=address))
            for address in WEIGHT_ADDRESSES
        )


def _strict_decode(counts: tuple[int, int]) -> int:
    """零活动或平局均 abstain，禁止隐式偏向类别 0。"""
    if max(counts) == 0 or counts[0] == counts[1]:
        return -1
    return 0 if counts[0] > counts[1] else 1


def _expect_ok(response_status: int, operation: str) -> None:
    if response_status != int(Status.OK):
        raise AssertionError(f"{operation} 返回 status=0x{response_status:02x}")


def _teacher_modulators(label: int) -> tuple[int, int, int, int]:
    """返回冻结的 H0/H1/O0/O1 神经元级 Teacher 调制。"""

    if label == 0:
        return (1, -1, 1, -1)
    if label == 1:
        return (-1, 1, -1, 1)
    raise ValueError(f"M3 只定义二分类标签，收到 label={label}")


def _signed32(value: int) -> int:
    """把 WEIGHT_READ 的 32-bit 符号扩展结果还原为 Python 整数。"""

    return value - (1 << 32) if value & (1 << 31) else value


def _flatten_weights(weights: Sequence[Sequence[int]]) -> tuple[int, ...]:
    return tuple(value for neuron_weights in weights for value in neuron_weights)


def _nest_weights(weights: Sequence[int]) -> tuple[tuple[int, ...], ...]:
    frozen = tuple(weights)
    if len(frozen) != len(WEIGHT_ADDRESSES):
        raise AssertionError(f"M3 权重数量错误: {len(frozen)}")
    return (frozen[0:4], frozen[4:8], frozen[8:10], frozen[10:12])


def _read_weight_vector(
    responses: Sequence[Flit],
    indices: Sequence[int],
) -> tuple[int, ...]:
    """从公开 WEIGHT_READ 响应恢复固定地址顺序的 signed 权重。"""

    values: list[int] = []
    for index in indices:
        response = responses[index]
        _expect_ok(response.flags, f"WEIGHT_READ[{index}]")
        values.append(_signed32(response.arg0))
    return tuple(values)


def _decode_episode(
    episode: M3EpisodePlan,
    responses: Sequence[Flit],
) -> tuple[int, tuple[int, int]]:
    """累计 TICK_COMMIT 与 EP_END flush 的真实输出 spike。"""

    counts = [0, 0]
    for index in episode.output_response_indices:
        response = responses[index]
        _expect_ok(response.flags, f"{episode.phase} response[{index}]")
        output_mask = (response.arg0 >> 2) & 0x3
        counts[0] += output_mask & 1
        counts[1] += (output_mask >> 1) & 1
    frozen_counts = (counts[0], counts[1])
    return _strict_decode(frozen_counts), frozen_counts


def _reference_commit_evidence(plan: M3CommandPlan) -> tuple[M3CommitEvidence, ...]:
    """从独立 reference 状态提取快照，并重新计算每个定点权重转移。"""

    bridge = HostBridgeOracle()
    commits_by_index = {commit.response_index: commit for commit in plan.commits}
    evidence: list[M3CommitEvidence] = []
    for index, request in enumerate(plan.commands):
        commit = commits_by_index.get(index)
        if commit is None:
            bridge.execute(request)
            continue

        modulators = decode_modulators(request.arg1 & 0xFF)
        pre_weights = tuple(tuple(neuron.weights) for neuron in bridge.tile.neurons)
        snapshots = tuple(
            tuple(neuron.eligibility_snapshot) for neuron in bridge.tile.neurons
        )
        deltas = tuple(
            tuple(
                (modulator * eligibility) >> neuron.learning_shift
                for eligibility in snapshot
            )
            for neuron, snapshot, modulator in zip(
                bridge.tile.neurons,
                snapshots,
                modulators,
                strict=True,
            )
        )
        expected_weights = tuple(
            tuple(
                max(neuron.weight_min, min(neuron.weight_max, weight + delta))
                for weight, delta in zip(neuron_weights, neuron_deltas, strict=True)
            )
            for neuron, neuron_weights, neuron_deltas in zip(
                bridge.tile.neurons,
                pre_weights,
                deltas,
                strict=True,
            )
        )
        response = bridge.execute(request)
        _expect_ok(response.flags, f"reference MOD_COMMIT[{commit.commit_id}]")
        actual_weights = tuple(tuple(neuron.weights) for neuron in bridge.tile.neurons)
        if actual_weights != expected_weights:
            raise AssertionError(
                f"reference 定点公式不一致 commit={commit.commit_id}: "
                f"actual={actual_weights} expected={expected_weights}"
            )
        evidence.append(
            M3CommitEvidence(
                commit_id=commit.commit_id,
                modulators=modulators,
                pre_weights=pre_weights,
                eligibility_snapshots=snapshots,
                deltas=deltas,
                expected_weights=expected_weights,
                read_weights=(),
                weight_epoch=response.arg1,
            )
        )
    return tuple(evidence)


def _run_episode(
    bridge: HostBridgeOracle,
    events: TrialEvents,
    *,
    txn_id: int,
    episode_id: int,
    train: bool,
    commit_id: int = 0,
    modulators: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> tuple[int, tuple[int, int]]:
    """通过公开 Host 命令执行一次完整 episode，并累计输出 spike。"""
    counts = [0, 0]
    response = bridge.execute(
        command(
            Opcode.EP_START,
            txn_id=txn_id,
            flags=int(train),
            episode_id=episode_id,
        )
    )
    txn_id += 1
    _expect_ok(response.flags, "EP_START")

    for tick_id, active_inputs in enumerate(events):
        response = bridge.execute(
            command(
                Opcode.TICK_BEGIN,
                txn_id=txn_id,
                episode_id=episode_id,
                tick_id=tick_id,
                arg0=len(active_inputs),
            )
        )
        txn_id += 1
        _expect_ok(response.flags, "TICK_BEGIN")

        for synapse_id in active_inputs:
            response = bridge.execute(
                command(
                    Opcode.INPUT_EVENT,
                    txn_id=txn_id,
                    episode_id=episode_id,
                    tick_id=tick_id,
                    arg0=synapse_id,
                )
            )
            txn_id += 1
            _expect_ok(response.flags, "INPUT_EVENT")

        response = bridge.execute(
            command(
                Opcode.TICK_COMMIT,
                txn_id=txn_id,
                episode_id=episode_id,
                tick_id=tick_id,
            )
        )
        txn_id += 1
        _expect_ok(response.flags, "TICK_COMMIT")
        output_mask = (response.arg0 >> 2) & 0x3
        counts[0] += output_mask & 1
        counts[1] += (output_mask >> 1) & 1

    response = bridge.execute(
        command(
            Opcode.EP_END,
            txn_id=txn_id,
            episode_id=episode_id,
            arg0=commit_id if train else 0,
        )
    )
    txn_id += 1
    _expect_ok(response.flags, "EP_END")
    output_mask = (response.arg0 >> 2) & 0x3
    counts[0] += output_mask & 1
    counts[1] += (output_mask >> 1) & 1

    if train:
        response = bridge.execute(
            command(
                Opcode.MOD_COMMIT,
                txn_id=txn_id,
                episode_id=episode_id,
                arg0=commit_id,
                arg1=encode_modulators(modulators),
            )
        )
        txn_id += 1
        _expect_ok(response.flags, "MOD_COMMIT")

    return txn_id, (counts[0], counts[1])


def run_oracle_m3() -> M3Report:
    """运行冻结的两轮 Teacher 训练，并验证未训练扰动输入。"""
    bridge = HostBridgeOracle()
    txn_id = 1
    episode_id = 1

    pretrain: list[int] = []
    for label in (0, 1):
        txn_id, counts = _run_episode(
            bridge,
            make_trial(label),
            txn_id=txn_id,
            episode_id=episode_id,
            train=False,
        )
        episode_id += 1
        pretrain.append(_strict_decode(counts))

    commit_id = 0
    for _epoch in range(TRAIN_EPOCHS):
        for label in (0, 1):
            txn_id, _counts = _run_episode(
                bridge,
                make_trial(label),
                txn_id=txn_id,
                episode_id=episode_id,
                train=True,
                commit_id=commit_id,
                modulators=_teacher_modulators(label),
            )
            episode_id += 1
            commit_id += 1

    clean: list[int] = []
    for label in (0, 1):
        txn_id, counts = _run_episode(
            bridge,
            make_trial(label),
            txn_id=txn_id,
            episode_id=episode_id,
            train=False,
        )
        episode_id += 1
        clean.append(_strict_decode(counts))

    noisy_correct = 0
    noisy_dataset = make_noisy_dataset(seed=NOISY_SEED, count=NOISY_COUNT)
    for events, label in noisy_dataset:
        txn_id, counts = _run_episode(
            bridge,
            events,
            txn_id=txn_id,
            episode_id=episode_id,
            train=False,
        )
        episode_id += 1
        noisy_correct += int(_strict_decode(counts) == label)

    final_weights = tuple(tuple(neuron.weights) for neuron in bridge.tile.neurons)
    LOGGER.info(
        "M3 oracle complete: commits=%d noisy=%d/%d weights=%s",
        bridge.tile.weight_epoch,
        noisy_correct,
        len(noisy_dataset),
        final_weights,
    )
    return M3Report(
        pretrain_predictions=(pretrain[0], pretrain[1]),
        clean_predictions=(clean[0], clean[1]),
        noisy_correct=noisy_correct,
        noisy_total=len(noisy_dataset),
        weight_epoch=bridge.tile.weight_epoch,
        final_weights=final_weights,
    )


def run_rtl_m3(plan: M3CommandPlan, seed: int = 0x4D33) -> M3RtlReport:
    """在同一个真实双时钟 Host Bridge + Tile run 中完成 M3。"""

    reference = _reference_commit_evidence(plan)
    responses = run_command_sequence(plan.commands, seed=seed)
    if len(responses) != len(plan.commands):
        raise AssertionError(
            f"M3 响应数量错误: actual={len(responses)} expected={len(plan.commands)}"
        )
    for index, response in enumerate(responses):
        _expect_ok(response.flags, f"M3 command[{index}]")

    decoded = tuple(
        (episode, *_decode_episode(episode, responses)) for episode in plan.episodes
    )
    pretrain = tuple(
        prediction
        for episode, prediction, _counts in decoded
        if episode.phase == "pretrain"
    )
    clean = tuple(
        prediction
        for episode, prediction, _counts in decoded
        if episode.phase == "clean"
    )
    noisy = tuple(
        (episode.label, prediction)
        for episode, prediction, _counts in decoded
        if episode.phase == "noisy"
    )
    if len(pretrain) != 2 or len(clean) != 2:
        raise AssertionError(
            f"M3 clean episode 数量错误: pretrain={len(pretrain)} clean={len(clean)}"
        )

    post_commit_reads = tuple(
        _read_weight_vector(responses, commit.weight_read_indices)
        for commit in plan.commits
    )
    if len(reference) != len(plan.commits):
        raise AssertionError(
            f"M3 reference commit 数量错误: {len(reference)} != {len(plan.commits)}"
        )

    commit_evidence: list[M3CommitEvidence] = []
    for commit, expected, read_weights in zip(
        plan.commits,
        reference,
        post_commit_reads,
        strict=True,
    ):
        response = responses[commit.response_index]
        expected_epoch = commit.commit_id + 1
        if response.arg1 != expected_epoch or expected.weight_epoch != expected_epoch:
            raise AssertionError(
                f"M3 weight_epoch 错误 commit={commit.commit_id}: "
                f"rtl={response.arg1} reference={expected.weight_epoch}"
            )
        expected_flat = _flatten_weights(expected.expected_weights)
        if read_weights != expected_flat:
            raise AssertionError(
                f"M3 权重读回不符合 eligibility 公式 commit={commit.commit_id}: "
                f"read={read_weights} expected={expected_flat}"
            )
        commit_evidence.append(
            M3CommitEvidence(
                commit_id=expected.commit_id,
                modulators=expected.modulators,
                pre_weights=expected.pre_weights,
                eligibility_snapshots=expected.eligibility_snapshots,
                deltas=expected.deltas,
                expected_weights=expected.expected_weights,
                read_weights=read_weights,
                weight_epoch=response.arg1,
            )
        )

    final_weight_vector = _read_weight_vector(
        responses,
        plan.final_weight_read_indices,
    )
    if not post_commit_reads or final_weight_vector != post_commit_reads[-1]:
        raise AssertionError(
            "M3 冻结推理改变了权重: "
            f"after_train={post_commit_reads[-1] if post_commit_reads else ()} "
            f"after_infer={final_weight_vector}"
        )
    status_response = responses[plan.status_response_index]
    _expect_ok(status_response.flags, "M3 final STATUS_READ")
    ledger = audit_training_ledger(responses, training_start=plan.training_start)
    noisy_correct = sum(label == prediction for label, prediction in noisy)
    report = M3RtlReport(
        responses=responses,
        pretrain_predictions=(pretrain[0], pretrain[1]),
        clean_predictions=(clean[0], clean[1]),
        noisy_correct=noisy_correct,
        noisy_total=len(noisy),
        weight_epoch=status_response.arg1,
        post_commit_weight_reads=post_commit_reads,
        final_weights=_nest_weights(final_weight_vector),
        commit_evidence=tuple(commit_evidence),
        ledger=ledger,
    )
    LOGGER.info(
        "M3 RTL complete: commands=%d commits=%d noisy=%d/%d epoch=%d ledger=%s",
        len(plan.commands),
        report.ledger.mod_commit.successful,
        report.noisy_correct,
        report.noisy_total,
        report.weight_epoch,
        report.ledger.canonical_sha256,
    )
    return report

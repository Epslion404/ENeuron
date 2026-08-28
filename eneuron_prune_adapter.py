"""ENeuron 4→2→2 网络的 B1 局部 2:4 剪枝薄适配器。"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import random
from dataclasses import dataclass, replace
from typing import Sequence

from local_prune_reference import (
    IssueResult,
    LocalPrune2of4,
    PruneCommitResult,
    PruneMode,
    ScoreMethod,
)
from network_sim import DigitalSNN2Layer, NetworkEpisode, PendingCommit


LOGGER = logging.getLogger("eneuron_prune_adapter")


@dataclass(frozen=True)
class PrunedSampleResult:
    """一次样本运行结果及逐 tick 的两个隐藏层发射掩码。"""

    episode: NetworkEpisode
    hidden_issue_masks: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class CapturedPruneCommit:
    """已按当前结构掩码冻结并量化的学习快照。"""

    pending: PendingCommit
    hidden_evidence_levels: tuple[tuple[int, int, int, int], ...]


@dataclass(frozen=True)
class TrainedSampleResult:
    sample: PrunedSampleResult
    snapshot: CapturedPruneCommit


@dataclass(frozen=True)
class HiddenObservation:
    """足以从同一稠密 checkpoint 重放 S0-S3 评分的审计记录。"""

    commit_id: int
    hidden_weights_before: tuple[tuple[int, ...], tuple[int, ...]]
    hidden_evidence_levels: tuple[tuple[int, int, int, int], ...]
    hidden_modulator: tuple[int, int]


def quantize_eligibility(value: int) -> int:
    """把 ENeuron 资格迹幅度量化为 0..3，非零证据至少保留一级。"""

    magnitude = abs(int(value))
    return min(3, (magnitude + 15) // 16)


class ENeuronB1PruneAdapter:
    """只在两个四输入隐藏神经元前增加独立剪枝门。"""

    def __init__(self, *, score_method: ScoreMethod, init_seed: int | None = None) -> None:
        self.network = DigitalSNN2Layer(init_seed=init_seed)
        self.hidden_gates = (
            LocalPrune2of4(score_method=score_method),
            LocalPrune2of4(score_method=score_method),
        )
        self.hidden_eligibility_snapshot = ([0] * 4, [0] * 4)
        self._captured: dict[int, CapturedPruneCommit] = {}
        self.observation_ledger: list[HiddenObservation] = []
        self.refractory_gate_skips = [0, 0]
        self.output_weight_reads_issued = 0
        self.output_synapse_ops_issued = 0

    @staticmethod
    def _activity_mask(active_inputs: Sequence[int]) -> int:
        mask = 0
        for index in sorted(set(active_inputs)):
            if index < 0 or index >= 4:
                raise ValueError("input spike index out of range")
            mask |= 1 << index
        return mask

    def _step_tick(self, active_inputs: Sequence[int], tick: int) -> tuple[int, int]:
        activity_mask = self._activity_mask(active_inputs)
        for neuron in self.network.output:
            if neuron.refractory == 0:
                work = len(self.network.pending_hidden)
                self.output_weight_reads_issued += work
                self.output_synapse_ops_issued += work
        output_fired = tuple(
            neuron.step(
                self.network.pending_hidden,
                tick,
                learn_enable=self.network.train_enable,
            )
            for neuron in self.network.output
        )
        issues: list[IssueResult] = []
        issue_masks: list[int] = []
        hidden_fired: list[int] = []
        for index, (neuron, gate) in enumerate(zip(self.network.hidden, self.hidden_gates)):
            if neuron.refractory > 0:
                issue_mask = 0
                self.refractory_gate_skips[index] += 1
            else:
                issue = gate.issue(activity_mask)
                issue_mask = issue.issue_mask
                issues.append(issue)
            issue_masks.append(issue_mask)
            filtered = tuple(index for index in range(4) if issue_mask & (1 << index))
            hidden_fired.append(
                neuron.step(filtered, tick, learn_enable=self.network.train_enable)
            )

        self.network.pending_hidden = tuple(
            index for index, fired in enumerate(hidden_fired) if fired
        )
        self.network.hidden_counts = [
            count + fired for count, fired in zip(self.network.hidden_counts, hidden_fired)
        ]
        self.network.output_counts = [
            count + fired for count, fired in zip(self.network.output_counts, output_fired)
        ]
        return issue_masks[0], issue_masks[1]

    def run_sample(
        self,
        events: Sequence[Sequence[int]],
        *,
        label: int,
        train: bool,
    ) -> PrunedSampleResult:
        mode = PruneMode.TRAIN if train else PruneMode.INFER
        for gate in self.hidden_gates:
            gate.set_mode(mode)
        self.network.begin_episode(label=label, train=train)
        issue_history = tuple(
            self._step_tick(tuple(active_inputs), tick)
            for tick, active_inputs in enumerate(events)
        )
        for neuron in self.network.output:
            if neuron.refractory == 0:
                work = len(self.network.pending_hidden)
                self.output_weight_reads_issued += work
                self.output_synapse_ops_issued += work
        self.network.flush_route(len(events))
        result = PrunedSampleResult(self.network.end_episode(), issue_history)
        LOGGER.debug(
            "sample label=%d train=%s hidden_issues=%s",
            label,
            train,
            issue_history,
        )
        return result

    def capture_commit(self, commit_id: int) -> CapturedPruneCommit:
        """锁存一次训练快照，并在进入权重更新前清除被剪位置。"""

        pending = self.network.capture_commit(commit_id)
        masked_hidden: list[tuple[int, int, int, int]] = []
        evidence_levels: list[tuple[int, int, int, int]] = []
        for eligibility, gate in zip(pending.hidden_eligibility, self.hidden_gates):
            mask = gate.mask_read(log_event=False)
            masked = tuple(
                value if mask & (1 << index) else 0
                for index, value in enumerate(eligibility)
            )
            masked_hidden.append(masked)  # type: ignore[arg-type]
            evidence_levels.append(
                tuple(quantize_eligibility(value) for value in masked)  # type: ignore[arg-type]
            )

        masked_pending = replace(pending, hidden_eligibility=tuple(masked_hidden))
        self.network.pending_commits[commit_id] = masked_pending
        self.hidden_eligibility_snapshot = tuple(
            list(values) for values in masked_hidden
        )  # type: ignore[assignment]
        snapshot = CapturedPruneCommit(masked_pending, tuple(evidence_levels))
        self._captured[commit_id] = snapshot
        LOGGER.debug(
            "capture commit_id=%d hidden_evidence_levels=%s",
            commit_id,
            snapshot.hidden_evidence_levels,
        )
        return snapshot

    def apply_modulator(
        self,
        *,
        hidden_modulator: Sequence[int],
        output_modulator: Sequence[int],
        commit_id: int,
    ) -> None:
        """提交原网络调制；成功后才把非零隐藏调制记入局部分数。"""

        snapshot = self._captured.get(commit_id)
        if snapshot is None:
            raise ValueError("unknown or uncaptured commit_id")
        hidden_values = tuple(hidden_modulator)
        output_values = tuple(output_modulator)
        hidden_weights_before = tuple(
            tuple(neuron.weights) for neuron in self.network.hidden
        )
        self.network.apply_host_modulator(
            hidden_values,
            output_values,
            commit_id=commit_id,
        )
        for weights_before, gate, value, evidence in zip(
            hidden_weights_before,
            self.hidden_gates,
            hidden_values,
            snapshot.hidden_evidence_levels,
        ):
            if value:
                gate.observe(
                    weights=weights_before,
                    evidence_levels=evidence,
                    modulator=value,
                    observation_id=commit_id,
                )
        if any(hidden_values):
            self.observation_ledger.append(
                HiddenObservation(
                    commit_id,
                    hidden_weights_before,  # type: ignore[arg-type]
                    snapshot.hidden_evidence_levels,
                    hidden_values,  # type: ignore[arg-type]
                )
            )
        del self._captured[commit_id]
        LOGGER.debug(
            "mod_commit commit_id=%d hidden_modulator=%s output_modulator=%s",
            commit_id,
            hidden_values,
            output_values,
        )

    def branch_for_score(self, score_method: ScoreMethod) -> ENeuronB1PruneAdapter:
        """复制共同稠密 checkpoint，并重放相同的已提交局部证据。"""

        if self.network.episode_active or self.network.pending_commits or self._captured:
            raise RuntimeError("checkpoint branch requires an idle adapter without pending commits")
        if any(gate.mask_valid for gate in self.hidden_gates):
            raise RuntimeError("checkpoint branch must be created before pruning")

        branch = ENeuronB1PruneAdapter(score_method=score_method)
        branch.network = copy.deepcopy(self.network)
        branch.hidden_eligibility_snapshot = tuple(
            list(values) for values in self.hidden_eligibility_snapshot
        )  # type: ignore[assignment]
        for gate in branch.hidden_gates:
            gate.set_mode(PruneMode.TRAIN)
        for observation in self.observation_ledger:
            for index, gate in enumerate(branch.hidden_gates):
                value = observation.hidden_modulator[index]
                if value:
                    gate.observe(
                        weights=observation.hidden_weights_before[index],
                        evidence_levels=observation.hidden_evidence_levels[index],
                        modulator=value,
                        observation_id=observation.commit_id,
                    )
        branch.observation_ledger = list(self.observation_ledger)
        LOGGER.debug(
            "score_branch score_method=%s observations=%d",
            score_method.name,
            len(branch.observation_ledger),
        )
        return branch

    def random_mask_branch(self, *, seed: int) -> ENeuronB1PruneAdapter:
        """从共同 checkpoint 生成确定性的随机 2:4 负对照分支。"""

        branch = self.branch_for_score(ScoreMethod.S0)
        rng = random.Random(seed)
        for gate in branch.hidden_gates:
            selected = rng.sample(range(4), 2)
            mask = sum(1 << index for index in selected)
            gate.set_mode(PruneMode.CONFIG)
            gate.mask_write(mask)
            gate.set_mode(PruneMode.TRAIN)
        branch._clear_pruned_history()
        LOGGER.debug(
            "random_branch seed=%d masks=%s",
            seed,
            tuple(gate.mask_read(log_event=False) for gate in branch.hidden_gates),
        )
        return branch

    def mask_branch(self, masks: Sequence[int]) -> ENeuronB1PruneAdapter:
        """从共同 checkpoint 安装跨模型完全相同的 CONFIG 随机对照掩码。"""
        if len(masks) != 2:
            raise ValueError("mask branch requires two hidden masks")
        branch = self.branch_for_score(ScoreMethod.S0)
        for gate, mask in zip(branch.hidden_gates, masks):
            gate.set_mode(PruneMode.CONFIG)
            gate.mask_write(mask)
            gate.set_mode(PruneMode.TRAIN)
        branch._clear_pruned_history()
        return branch

    def _clear_pruned_history(self) -> None:
        for neuron, gate, snapshot in zip(
            self.network.hidden,
            self.hidden_gates,
            self.hidden_eligibility_snapshot,
        ):
            mask = gate.mask_read(log_event=False)
            for index in range(4):
                if not mask & (1 << index):
                    neuron.pre_trace[index] = 0
                    neuron.eligibility[index] = 0
                    snapshot[index] = 0

    def prune_hidden(self, *, commit_id: int) -> tuple[PruneCommitResult, PruneCommitResult]:
        """在无 pending 学习事务时原子剪枝两个隐藏四输入组。"""

        if self.network.episode_active:
            raise RuntimeError("prune_hidden requires an idle network")
        if self.network.pending_commits or self._captured:
            raise RuntimeError("prune_hidden requires no pending learning transaction")
        if not isinstance(commit_id, int) or isinstance(commit_id, bool):
            raise TypeError("commit_id must be an integer")
        if not 0 <= commit_id <= LocalPrune2of4.COMMIT_ID_MAX:
            raise ValueError("commit_id must be within 0..65535")
        for gate in self.hidden_gates:
            if gate.mode is not PruneMode.TRAIN:
                raise RuntimeError("prune_hidden requires TRAIN mode")
            if gate.mask_valid:
                raise RuntimeError("V1 forbids a second prune without PRUNE_CLEAR")
            if gate.last_commit_id is not None and commit_id <= gate.last_commit_id:
                raise ValueError("commit_id must increase strictly")

        results = tuple(
            gate.prune_commit(
                weights=neuron.weights,
                commit_id=commit_id,
                core_idle=True,
                pending_snapshot=False,
                pending_mod_commit=False,
            )
            for neuron, gate in zip(self.network.hidden, self.hidden_gates)
        )
        self._clear_pruned_history()
        LOGGER.debug(
            "prune_commit commit_id=%d masks=%s",
            commit_id,
            tuple(result.mask for result in results),
        )
        return results  # type: ignore[return-value]

    def train_sample(
        self,
        events: Sequence[Sequence[int]],
        *,
        label: int,
        hidden_modulator: Sequence[int],
        output_modulator: Sequence[int],
        commit_id: int,
    ) -> TrainedSampleResult:
        """运行、捕获并调制一个 B1 训练样本。"""

        sample = self.run_sample(events, label=label, train=True)
        snapshot = self.capture_commit(commit_id)
        self.apply_modulator(
            hidden_modulator=hidden_modulator,
            output_modulator=output_modulator,
            commit_id=commit_id,
        )
        return TrainedSampleResult(sample, snapshot)

    def checkpoint_sha256(self) -> str:
        """绑定学习状态、分数、掩码和本地证据账本。"""
        payload = {
            "neurons": [
                {
                    "weights": list(neuron.weights),
                    "pre_trace": list(neuron.pre_trace),
                    "post_trace": neuron.post_trace,
                    "eligibility": list(neuron.eligibility),
                    "threshold": neuron.threshold,
                }
                for neuron in self.network.neurons
            ],
            "hidden_gates": [
                {
                    "score_method": gate.score_method.name,
                    "utility": list(gate.utility),
                    "structural_mask": gate.structural_mask,
                    "mask_valid": gate.mask_valid,
                    "last_commit_id": gate.last_commit_id,
                    "last_observation_id": gate.last_observation_id,
                }
                for gate in self.hidden_gates
            ],
            "observations": [observation.__dict__ for observation in self.observation_ledger],
            "weight_epoch": self.network.weight_epoch,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def learning_fingerprint(self) -> tuple[object, ...]:
        """推理期间必须冻结的持久学习状态与结构状态。"""
        return (
            tuple(tuple(neuron.weights) for neuron in self.network.neurons),
            tuple(tuple(gate.utility) for gate in self.hidden_gates),
            tuple(gate.mask_read(log_event=False) for gate in self.hidden_gates),
        )

    def work_counters(self) -> dict[str, int | str]:
        """给 B1 runner 提供范围明确的全网络累计工作量。"""
        hidden_dense = sum(gate.dense_weight_reads_requested for gate in self.hidden_gates)
        hidden_reads = sum(gate.weight_reads_issued for gate in self.hidden_gates)
        hidden_ops = sum(gate.synapse_ops_issued for gate in self.hidden_gates)
        hidden_saved = sum(gate.reads_saved_by_structure for gate in self.hidden_gates)
        return {
            "scope": "full_4x2x2_hidden_structural_output_dense",
            "hidden_dense_reads_requested": hidden_dense,
            "hidden_weight_reads_issued": hidden_reads,
            "hidden_synapse_ops_issued": hidden_ops,
            "hidden_reads_saved_by_structure": hidden_saved,
            "output_weight_reads_issued": self.output_weight_reads_issued,
            "output_synapse_ops_issued": self.output_synapse_ops_issued,
            "network_weight_reads_issued": hidden_reads + self.output_weight_reads_issued,
            "network_synapse_ops_issued": hidden_ops + self.output_synapse_ops_issued,
            "refractory_gate_skips": sum(self.refractory_gate_skips),
        }

    def snapshot(self) -> dict[str, object]:
        return {
            "weights": [list(neuron.weights) for neuron in self.network.neurons],
            "masks": [gate.mask_read(log_event=False) for gate in self.hidden_gates],
            "utilities": [list(gate.utility) for gate in self.hidden_gates],
            "checkpoint_sha256": self.checkpoint_sha256(),
            "work_counters": self.work_counters(),
        }


__all__ = [
    "CapturedPruneCommit",
    "ENeuronB1PruneAdapter",
    "HiddenObservation",
    "PrunedSampleResult",
    "PruneCommitResult",
    "TrainedSampleResult",
    "quantize_eligibility",
]

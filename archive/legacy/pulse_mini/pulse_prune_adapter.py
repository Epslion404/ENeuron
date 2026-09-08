"""Pulse-Mini-L/L2 的 B1 局部剪枝薄适配器。"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Sequence

from local_prune_reference import LocalPrune2of4, PruneMode, ScoreMethod
from pulse_mini_network import NetworkTick, PulseMiniNetwork
from pulse_mini_reference import Command, Mode, Opcode, PulseMiniReference, Status


@dataclass(frozen=True)
class PulseEvidenceCommit:
    sequence: int
    phase: str
    layer: str
    neuron: int
    weights_before: tuple[int, ...]
    raw_evidence: tuple[int, ...]
    evidence_levels: tuple[int, ...]
    modulator: int
    weights_after: tuple[int, ...]


class PulsePruneAdapter:
    """不改神经元方程，只在网络输入与 CAPTURE/FEEDBACK 边界旁路。"""

    def __init__(self, *, core_type: type[PulseMiniReference]) -> None:
        self.core_type = core_type
        self.network = PulseMiniNetwork(core_type=core_type)
        self.controllers: list[LocalPrune2of4] = []
        self.evidence_ledger: list[PulseEvidenceCommit] = []
        self.parent_checkpoint_sha256: str | None = None
        self._observation_ids = [0, 0]
        self.refractory_gate_skips = [0, 0]
        self.output_weight_reads_issued = 0
        self.output_synapse_ops_issued = 0

    @property
    def direct_weight_write_count(self) -> int:
        """从四个真实核心账本统计成功写权重命令，禁止用常量冒充。"""
        return sum(
            1
            for core in self.network.cores
            for entry in core.event_log
            if entry["opcode"] == "WEIGHT_WRITE" and entry["status"] == Status.OK.value
        )

    def checkpoint_sha256(self) -> str:
        """绑定四核状态、路由状态和证据账本，证明所有分支同源。"""
        payload = {
            "core_type": self.core_type.__name__,
            "cores": [core.state_digest() for core in self.network.cores],
            "pending_hidden": self.network.pending_hidden,
            "tick_index": self.network.tick_index,
            "evidence": [entry.__dict__ for entry in self.evidence_ledger],
            "controllers": [
                {
                    "score_method": controller.score_method.name,
                    "mode": controller.mode.name,
                    "utility": list(controller.utility),
                    "structural_mask": controller.structural_mask,
                    "mask_valid": controller.mask_valid,
                    "last_commit_id": controller.last_commit_id,
                    "last_observation_id": controller.last_observation_id,
                }
                for controller in self.controllers
            ],
            "direct_weight_write_count": self.direct_weight_write_count,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def branch(self, *, score_method: ScoreMethod) -> PulsePruneAdapter:
        """从同一个稠密 warm-up 检查点分支，并重放本地证据。"""
        if self.controllers:
            raise RuntimeError("only an unpruned dense warm-up checkpoint may branch")
        child = PulsePruneAdapter(core_type=self.core_type)
        child.network = copy.deepcopy(self.network)
        child.evidence_ledger = copy.deepcopy(self.evidence_ledger)
        child.parent_checkpoint_sha256 = self.checkpoint_sha256()
        child.controllers = [LocalPrune2of4(score_method=score_method) for _ in range(2)]
        for controller in child.controllers:
            controller.set_mode(PruneMode.TRAIN)
        for entry in child.evidence_ledger:
            child._observe(entry)
        return child

    def _hidden_issue_masks(self, input_mask: int) -> tuple[int, int]:
        if not self.controllers:
            return input_mask, input_mask
        masks: list[int] = []
        for index, (core, controller) in enumerate(zip(self.network.hidden, self.controllers)):
            # 不应期在核心内部已知，真实 lane 不需要发权重读取；也不能把它
            # 伪装成结构剪枝节省，因此不调用结构控制器计数。
            if core.refractory > 0:
                masks.append(0)
                self.refractory_gate_skips[index] += 1
            else:
                masks.append(controller.issue(input_mask).issue_mask)
        return masks[0], masks[1]

    def _count_output_issue(self, pending_hidden: int) -> None:
        """输出层保持稠密，但仍记录实际发出的读取和突触操作。"""
        for core in self.network.output:
            if core.refractory == 0:
                work = pending_hidden.bit_count()
                self.output_weight_reads_issued += work
                self.output_synapse_ops_issued += work

    def _tick_masked(self, input_mask: int, train_post_mask: int = 0) -> NetworkTick:
        """分别在两个隐藏核的命令发射前应用本地结构掩码。"""
        pending_before = self.network.pending_hidden
        hidden_masks = self._hidden_issue_masks(input_mask)
        hidden_spikes = 0
        output_spikes = 0
        for index, core in enumerate(self.network.hidden):
            response = core.execute(
                Command(Opcode.TICK, hidden_masks[index], (train_post_mask >> index) & 1)
            )
            if response.status is not Status.OK:
                raise RuntimeError(f"hidden TICK rejected: {response.status.name}")
            hidden_spikes |= response.spike << index
        self._count_output_issue(pending_before)
        for index, core in enumerate(self.network.output):
            response = core.execute(
                Command(Opcode.TICK, pending_before, (train_post_mask >> (index + 2)) & 1)
            )
            if response.status is not Status.OK:
                raise RuntimeError(f"output TICK rejected: {response.status.name}")
            output_spikes |= response.spike << index
        self.network.pending_hidden = hidden_spikes
        result = NetworkTick(
            input_mask,
            train_post_mask,
            hidden_spikes,
            output_spikes,
            pending_before,
            hidden_spikes,
        )
        self.network.ledger.append({
            "op": "TICK",
            **result.__dict__,
            "hidden_issue_masks": list(hidden_masks),
        })
        self.network.tick_index += 1
        return result

    def _flush_pending_output(self) -> int:
        """只排空一拍隐藏路由，不让隐藏核凭空再推进一个逻辑 tick。"""
        pending_before = self.network.pending_hidden
        output_spikes = 0
        self._count_output_issue(pending_before)
        for index, core in enumerate(self.network.output):
            response = core.execute(Command(Opcode.TICK, pending_before, 0))
            if response.status is not Status.OK:
                raise RuntimeError(f"output route flush rejected: {response.status.name}")
            output_spikes |= response.spike << index
        self.network.pending_hidden = 0
        self.network.ledger.append({
            "op": "ROUTE_FLUSH",
            "pending_hidden_before": pending_before,
            "output_spikes": output_spikes,
        })
        return output_spikes

    def _observe(self, entry: PulseEvidenceCommit) -> None:
        if not self.controllers or entry.layer != "hidden" or entry.modulator == 0:
            return
        neuron = entry.neuron
        observation_id = self._observation_ids[neuron]
        self.controllers[neuron].observe(
            weights=entry.weights_before,
            evidence_levels=entry.evidence_levels,
            modulator=entry.modulator,
            observation_id=observation_id,
        )
        self._observation_ids[neuron] += 1

    def train_hidden_once(self, *, neuron: int, feature: int, phase: str) -> PulseEvidenceCommit:
        if neuron not in (0, 1):
            raise ValueError("hidden neuron must be 0 or 1")
        for controller in self.controllers:
            controller.set_mode(PruneMode.TRAIN)
        self.network.mode_set(Mode.TRAIN)
        self.network.state_clear()
        self._tick_masked(feature)
        self._tick_masked(0, 1 << neuron)
        for _ in range(6):
            self._tick_masked(0)

        direction = self.network.capture(neuron)
        weights_before = tuple(self.network.hidden[neuron].weights)
        self.network.feedback(neuron, +1)
        weights_after = tuple(self.network.hidden[neuron].weights)
        entry = PulseEvidenceCommit(
            sequence=len(self.evidence_ledger),
            phase=phase,
            layer="hidden",
            neuron=neuron,
            weights_before=weights_before,
            raw_evidence=direction,
            evidence_levels=tuple(abs(value) for value in direction),
            modulator=1,
            weights_after=weights_after,
        )
        self.evidence_ledger.append(entry)
        self._observe(entry)
        return entry

    def _train_output_once(self, *, neuron: int, feature: int, train_post: int) -> None:
        for controller in self.controllers:
            controller.set_mode(PruneMode.TRAIN)
        self.network.mode_set(Mode.TRAIN)
        self.network.state_clear()
        for tick_index in range(8):
            self._tick_masked(
                feature if tick_index < 6 else 0,
                train_post if tick_index == 6 else 0,
            )
        self.network.capture(neuron)
        self.network.feedback(neuron, +1)

    def train_p8(self, *, repetitions: int, phase: str) -> None:
        """复用 P8 顺序；hidden 证据进入旁路，output 保持稠密。"""
        if repetitions <= 0:
            raise ValueError("repetitions must be positive")
        for neuron, feature in ((0, 0b0001), (1, 0b0010)):
            for _ in range(repetitions):
                self.train_hidden_once(neuron=neuron, feature=feature, phase=phase)
        for neuron, feature, train_post in ((2, 0b0001, 0b0100), (3, 0b0010, 0b1000)):
            for _ in range(repetitions):
                self._train_output_once(neuron=neuron, feature=feature, train_post=train_post)

    def prune_score(self, *, commit_id: int) -> tuple[int, int]:
        if not self.controllers:
            raise RuntimeError("branch() must install controllers before pruning")
        self.network.mode_set(Mode.TRAIN)
        masks = tuple(
            controller.prune_commit(
                weights=self.network.hidden[index].weights,
                commit_id=commit_id,
                core_idle=True,
                pending_snapshot=False,
                pending_mod_commit=False,
            ).mask
            for index, controller in enumerate(self.controllers)
        )
        # 剪枝提交边界清除旧窗口证据；权重保持不变。
        self.network.state_clear()
        return masks  # type: ignore[return-value]

    def install_random_masks(self, masks: Sequence[int]) -> tuple[int, int]:
        if len(masks) != 2 or not self.controllers:
            raise ValueError("random control requires two initialized hidden controllers")
        for controller, mask in zip(self.controllers, masks):
            controller.set_mode(PruneMode.CONFIG)
            controller.mask_write(mask)
            controller.set_mode(PruneMode.TRAIN)
        self.network.state_clear()
        return tuple(controller.mask_read() for controller in self.controllers)  # type: ignore[return-value]

    def infer_counts(self, events: Sequence[Sequence[int]]) -> tuple[int, int]:
        for controller in self.controllers:
            controller.set_mode(PruneMode.INFER)
        self.network.mode_set(Mode.INFER)
        self.network.state_clear()
        counts = [0, 0]
        for active in events:
            input_mask = sum(1 << index for index in active)
            result = self._tick_masked(input_mask)
            for index in range(2):
                counts[index] += (result.output_spikes >> index) & 1
        flushed = self._flush_pending_output()
        for index in range(2):
            counts[index] += (flushed >> index) & 1
        return counts[0], counts[1]

    def learning_fingerprint(self) -> tuple[object, ...]:
        """只包含推理期间必须冻结的学习状态。"""
        return (
            self.network.weights,
            tuple(tuple(controller.utility) for controller in self.controllers),
            tuple(controller.mask_read() for controller in self.controllers),
            tuple(controller.mask_valid for controller in self.controllers),
        )

    def work_counters(self) -> dict[str, int | str]:
        hidden_dense = sum(
            controller.dense_weight_reads_requested for controller in self.controllers
        )
        hidden_reads = sum(controller.weight_reads_issued for controller in self.controllers)
        hidden_ops = sum(controller.synapse_ops_issued for controller in self.controllers)
        hidden_saved = sum(controller.reads_saved_by_structure for controller in self.controllers)
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
            "core_type": self.core_type.__name__,
            "weights": [list(weights) for weights in self.network.weights],
            "controllers": [
                {
                    "utility": list(controller.utility),
                    "mask": controller.mask_read(),
                    "mask_valid": controller.mask_valid,
                    "dense_weight_reads_requested": controller.dense_weight_reads_requested,
                    "weight_reads_issued": controller.weight_reads_issued,
                    "synapse_ops_issued": controller.synapse_ops_issued,
                    "reads_saved_by_structure": controller.reads_saved_by_structure,
                }
                for controller in self.controllers
            ],
            "checkpoint_sha256": self.checkpoint_sha256(),
            "parent_checkpoint_sha256": self.parent_checkpoint_sha256,
            "direct_weight_write_count": self.direct_weight_write_count,
            "work_counters": self.work_counters(),
        }


__all__ = ["PulseEvidenceCommit", "PulsePruneAdapter"]

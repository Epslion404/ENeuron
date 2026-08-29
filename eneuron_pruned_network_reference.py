"""ENeuron 4→8→2 剪枝网络的独立事务级 Python 黄金模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from rtl_reference import RtlReferenceNeuron


N_NEURONS = 10
N_HIDDEN = 8
MODE_TRAIN = 1
MODE_INFER = 2


@dataclass(frozen=True)
class NetworkTransaction:
    """一个通过网络公开接口提交的事务。"""

    kind: str
    mode: int
    mask: int = 0
    broadcast: bool = False
    neuron: int = 0
    command_id: int = 0
    modulator: int = 0
    weight_addr: int = 0
    weight_data: int = 0
    backpressure: int = 0


@dataclass(frozen=True)
class NetworkState:
    """只包含 RTL 顶层正式公开、可由 Host 观察的状态。"""

    status: int
    hidden_spikes: int
    output_spikes: int
    pending_hidden: int
    commit_epoch: int
    issue_masks: int
    structural_masks: int
    mask_valids: int
    utilities: int
    observation_valids: int
    observation_ids: int
    commit_valids: int
    commit_ids: int
    pending_snapshot_valids: int
    pending_snapshot_ids: int
    membranes: int
    thresholds: int
    core_snapshot_valids: int
    eligibility_snapshots: int
    hidden_dense_reads: int
    hidden_reads_issued: int
    hidden_reads_saved: int
    output_dense_reads: int
    output_reads_issued: int
    output_reads_saved: int
    weights: tuple[int, ...]


@dataclass
class GateState:
    utility: list[int]
    structural_mask: int = 0b1111
    mask_valid: bool = False
    last_observation_id: int | None = None
    last_commit_id: int | None = None
    dense_reads: int = 0
    reads_issued: int = 0
    reads_saved: int = 0


def _pack(values: Iterable[int], width: int) -> int:
    result = 0
    lane_mask = (1 << width) - 1
    for index, value in enumerate(values):
        result |= (value & lane_mask) << (index * width)
    return result


def _indices(mask: int) -> tuple[int, ...]:
    return tuple(index for index in range(4) if mask & (1 << index))


def _quantize_snapshot(value: int) -> int:
    magnitude = abs(value)
    if magnitude == 0:
        return 0
    if magnitude <= 16:
        return 1
    if magnitude <= 32:
        return 2
    return 3


class ENeuronPrunedNetworkReference:
    """复现网络公开事务语义，不复用 RTL 控制器实现。"""

    def __init__(self) -> None:
        self.cores = [RtlReferenceNeuron(n_inputs=4) for _ in range(N_NEURONS)]
        self.gates = [GateState([0, 0, 0, 0]) for _ in range(N_NEURONS)]
        self.pending_snapshot_valids = [False] * N_NEURONS
        self.pending_snapshot_ids = [0] * N_NEURONS
        self.pending_hidden = 0
        self.hidden_spikes = 0
        self.output_spikes = 0
        self.commit_epoch = 0
        self.mode = MODE_TRAIN

    def _targets(self, transaction: NetworkTransaction) -> tuple[int, ...]:
        if transaction.broadcast:
            return tuple(range(N_NEURONS))
        if not 0 <= transaction.neuron < N_NEURONS:
            raise ValueError("neuron address out of range")
        return (transaction.neuron,)

    def _effective_mask(self, neuron: int) -> int:
        gate = self.gates[neuron]
        return gate.structural_mask if gate.mask_valid else 0b1111

    def _issue(self, neuron: int, activity: int) -> int:
        gate = self.gates[neuron]
        issue_mask = activity & self._effective_mask(neuron)
        dense = activity.bit_count()
        issued = issue_mask.bit_count()
        gate.dense_reads += dense
        gate.reads_issued += issued
        gate.reads_saved += dense - issued
        return issue_mask

    def _tick(self, input_mask: int) -> None:
        old_pending = self.pending_hidden
        hidden = 0
        output = 0
        learn = self.mode == MODE_TRAIN
        for neuron in range(N_HIDDEN):
            issue_mask = self._issue(neuron, input_mask)
            state = self.cores[neuron].tick(
                _indices(issue_mask), learn_enable=learn, tick_valid=True
            )
            hidden |= state.spike << neuron
        for output_index in range(2):
            neuron = N_HIDDEN + output_index
            activity = (old_pending >> (output_index * 4)) & 0xF
            issue_mask = self._issue(neuron, activity)
            state = self.cores[neuron].tick(
                _indices(issue_mask), learn_enable=learn, tick_valid=True
            )
            output |= state.spike << output_index
        self.hidden_spikes = hidden
        self.output_spikes = output
        self.pending_hidden = hidden

    def _flush(self) -> None:
        old_pending = self.pending_hidden
        output = 0
        learn = self.mode == MODE_TRAIN
        for output_index in range(2):
            neuron = N_HIDDEN + output_index
            activity = (old_pending >> (output_index * 4)) & 0xF
            issue_mask = self._issue(neuron, activity)
            state = self.cores[neuron].tick(
                _indices(issue_mask), learn_enable=learn, tick_valid=True
            )
            output |= state.spike << output_index
        self.hidden_spikes = 0
        self.output_spikes = output
        self.pending_hidden = 0

    def _clear(self, transaction: NetworkTransaction) -> None:
        for neuron in self._targets(transaction):
            self.cores[neuron].tick((), tick_valid=False, state_clear=True)

    def _snapshot(self, transaction: NetworkTransaction) -> None:
        if self.mode != MODE_TRAIN:
            raise ValueError("snapshot requires TRAIN")
        for neuron in self._targets(transaction):
            if self.pending_snapshot_valids[neuron]:
                raise ValueError("snapshot already pending")
        for neuron in self._targets(transaction):
            self.cores[neuron].tick(
                (), learn_enable=True, tick_valid=False, snapshot_we=True
            )
            self.pending_snapshot_valids[neuron] = True
            self.pending_snapshot_ids[neuron] = transaction.command_id

    def _observe_gate(self, neuron: int, observation_id: int) -> None:
        gate = self.gates[neuron]
        if gate.last_observation_id is not None and observation_id <= gate.last_observation_id:
            raise ValueError("observation ID must increase")
        active_mask = self._effective_mask(neuron)
        for lane, value in enumerate(self.cores[neuron].eligibility_snapshot):
            if active_mask & (1 << lane):
                gate.utility[lane] = min(
                    15,
                    max(0, gate.utility[lane] - 1) + _quantize_snapshot(value),
                )
        gate.last_observation_id = observation_id

    def _mod(self, transaction: NetworkTransaction) -> None:
        if self.mode != MODE_TRAIN:
            raise ValueError("mod requires TRAIN")
        targets = self._targets(transaction)
        for neuron in targets:
            if (
                not self.pending_snapshot_valids[neuron]
                or self.pending_snapshot_ids[neuron] != transaction.command_id
            ):
                raise ValueError("mod ID does not match pending snapshot")
        for neuron in targets:
            if transaction.modulator != 0:
                self._observe_gate(neuron, transaction.command_id)
            self.cores[neuron].tick(
                (),
                learn_enable=True,
                tick_valid=False,
                mod_valid=True,
                modulator=transaction.modulator,
            )
            # wrapper 的 pending 元数据总会消费；核心零 MOD 按既有合同保留
            # committed snapshot，非零 MOD 才由核心 S_MOD_COMMIT 清 valid。
            self.pending_snapshot_valids[neuron] = False

    def _weight(self, transaction: NetworkTransaction) -> None:
        if self.mode != MODE_TRAIN:
            raise ValueError("weight write requires TRAIN")
        for neuron in self._targets(transaction):
            self.cores[neuron].tick(
                (),
                learn_enable=True,
                tick_valid=False,
                weight_we=True,
                weight_addr=transaction.weight_addr,
                weight_wdata=transaction.weight_data,
            )

    def _commit(self, transaction: NetworkTransaction) -> None:
        if self.mode != MODE_TRAIN:
            raise ValueError("commit requires TRAIN")
        if any(self.pending_snapshot_valids):
            raise ValueError("commit requires no pending snapshot")
        for gate in self.gates:
            if gate.mask_valid:
                raise ValueError("second commit is forbidden")
            if gate.last_commit_id is not None and transaction.command_id <= gate.last_commit_id:
                raise ValueError("commit ID must increase")
        for gate in self.gates:
            selected = sorted(
                range(4), key=lambda lane: (gate.utility[lane], -lane), reverse=True
            )[:2]
            gate.structural_mask = sum(1 << lane for lane in selected)
            gate.mask_valid = True
            gate.last_commit_id = transaction.command_id
        for core in self.cores:
            core.tick((), tick_valid=False, state_clear=True)
        self.commit_epoch += 1

    def execute(self, transaction: NetworkTransaction) -> NetworkState:
        self.mode = transaction.mode
        if transaction.kind == "tick":
            self._tick(transaction.mask)
        elif transaction.kind == "flush":
            self._flush()
        elif transaction.kind == "clear":
            self._clear(transaction)
        elif transaction.kind == "snapshot":
            self._snapshot(transaction)
        elif transaction.kind == "mod":
            self._mod(transaction)
        elif transaction.kind == "weight":
            self._weight(transaction)
        elif transaction.kind == "commit":
            self._commit(transaction)
        elif transaction.kind != "read":
            raise ValueError(f"unknown transaction kind: {transaction.kind}")
        return self.state(status=0)

    def state(self, *, status: int) -> NetworkState:
        masks = [gate.structural_mask for gate in self.gates]
        valids = [int(gate.mask_valid) for gate in self.gates]
        utilities = [lane for gate in self.gates for lane in gate.utility]
        observation_valids = [int(gate.last_observation_id is not None) for gate in self.gates]
        observation_ids = [gate.last_observation_id or 0 for gate in self.gates]
        commit_valids = [int(gate.last_commit_id is not None) for gate in self.gates]
        commit_ids = [gate.last_commit_id or 0 for gate in self.gates]
        pending_valids = [int(value) for value in self.pending_snapshot_valids]
        pending_ids = list(self.pending_snapshot_ids)
        issue_masks = [0] * N_HIDDEN + [
            ((self.pending_hidden >> (index * 4)) & 0xF)
            & self._effective_mask(N_HIDDEN + index)
            for index in range(2)
        ]
        hidden_gates = self.gates[:N_HIDDEN]
        output_gates = self.gates[N_HIDDEN:]
        return NetworkState(
            status=status,
            hidden_spikes=self.hidden_spikes,
            output_spikes=self.output_spikes,
            pending_hidden=self.pending_hidden,
            commit_epoch=self.commit_epoch,
            issue_masks=_pack(issue_masks, 4),
            structural_masks=_pack(masks, 4),
            mask_valids=_pack(valids, 1),
            utilities=_pack(utilities, 4),
            observation_valids=_pack(observation_valids, 1),
            observation_ids=_pack(observation_ids, 16),
            commit_valids=_pack(commit_valids, 1),
            commit_ids=_pack(commit_ids, 16),
            pending_snapshot_valids=_pack(pending_valids, 1),
            pending_snapshot_ids=_pack(pending_ids, 16),
            membranes=_pack((core.membrane for core in self.cores), 16),
            thresholds=_pack((core.threshold for core in self.cores), 8),
            core_snapshot_valids=_pack(
                (int(core.snapshot_valid) for core in self.cores), 1
            ),
            eligibility_snapshots=_pack(
                (
                    value
                    for core in self.cores
                    for value in core.eligibility_snapshot
                ),
                12,
            ),
            hidden_dense_reads=sum(gate.dense_reads for gate in hidden_gates),
            hidden_reads_issued=sum(gate.reads_issued for gate in hidden_gates),
            hidden_reads_saved=sum(gate.reads_saved for gate in hidden_gates),
            output_dense_reads=sum(gate.dense_reads for gate in output_gates),
            output_reads_issued=sum(gate.reads_issued for gate in output_gates),
            output_reads_saved=sum(gate.reads_saved for gate in output_gates),
            weights=tuple(weight for core in self.cores for weight in core.weights),
        )


__all__ = [
    "ENeuronPrunedNetworkReference",
    "MODE_INFER",
    "MODE_TRAIN",
    "NetworkState",
    "NetworkTransaction",
]

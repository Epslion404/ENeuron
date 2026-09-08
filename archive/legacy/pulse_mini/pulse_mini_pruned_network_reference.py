"""Pulse-Mini-L/L2 4→8→2 剪枝网络的独立 Python 事务 oracle。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pulse_mini_l2_reference import PulseMiniL2Reference
from pulse_mini_reference import Command, Mode, Opcode, PulseMiniReference, Status


N_NEURONS = 10
N_HIDDEN = 8


@dataclass(frozen=True)
class NetworkTransaction:
    kind: str
    broadcast: bool = False
    neuron: int = 0
    arg0: int = 0
    arg1: int = 0
    command_id: int = 0
    hidden_post: int = 0
    output_post: int = 0
    backpressure: int = 0


@dataclass
class GateState:
    utility: list[int]
    mask: int = 0b1111
    valid: bool = False
    observe_count: int = 0
    refractory_skips: int = 0
    dense_reads: int = 0
    issued_reads: int = 0
    saved_reads: int = 0


@dataclass(frozen=True)
class NetworkState:
    hidden_spikes: int
    output_spikes: int
    pending_hidden: int
    commit_epoch: int
    issue_masks: int
    structural_masks: int
    mask_valids: int
    pending_valids: int
    modes: int
    weights: int
    soma: int
    refractory: int
    leak_timer: int
    pre_age: int
    post_age: int
    positive: int
    negative: int
    captured: int
    utility: int
    observe_counts: int
    refractory_skips: int
    hidden_dense: int
    hidden_issued: int
    hidden_saved: int
    output_dense: int
    output_issued: int
    output_saved: int


def _pack(values: Iterable[int], width: int) -> int:
    result = 0
    mask = (1 << width) - 1
    for index, value in enumerate(values):
        result |= (value & mask) << (index * width)
    return result


class PulseMiniPrunedNetworkReference:
    """共享网络语义；``l2`` 只选择单核证据模型。"""

    def __init__(self, *, l2: bool) -> None:
        core_type = PulseMiniL2Reference if l2 else PulseMiniReference
        self.l2 = l2
        self.cores = [core_type() for _ in range(N_NEURONS)]
        self.gates = [GateState([0, 0, 0, 0]) for _ in range(N_NEURONS)]
        self.pending_hidden = 0
        self.hidden_spikes = 0
        self.output_spikes = 0
        self.commit_epoch = 0

    def _targets(self, tx: NetworkTransaction) -> range | tuple[int]:
        return range(N_NEURONS) if tx.broadcast else (tx.neuron,)

    def _effective_mask(self, index: int) -> int:
        gate = self.gates[index]
        return gate.mask if gate.valid else 0b1111

    def _tick_core(self, index: int, activity: int, train_post: int) -> int:
        core = self.cores[index]
        gate = self.gates[index]
        issue = activity & self._effective_mask(index)
        if core.refractory:
            gate.refractory_skips += 1
            issued_arg = 0
        else:
            dense = activity.bit_count()
            issued = issue.bit_count()
            gate.dense_reads += dense
            gate.issued_reads += issued
            gate.saved_reads += dense - issued
            issued_arg = issue
        response = core.execute(Command(Opcode.TICK, issued_arg, train_post))
        if response.status is not Status.OK:
            raise AssertionError(response)
        return response.spike

    def _tick(self, tx: NetworkTransaction) -> None:
        old_pending = self.pending_hidden
        hidden = 0
        output = 0
        for index in range(N_HIDDEN):
            hidden |= self._tick_core(index, tx.arg0, (tx.hidden_post >> index) & 1) << index
        for output_index in range(2):
            activity = (old_pending >> (output_index * 4)) & 0xF
            output |= self._tick_core(
                N_HIDDEN + output_index,
                activity,
                (tx.output_post >> output_index) & 1,
            ) << output_index
        self.hidden_spikes = hidden
        self.output_spikes = output
        self.pending_hidden = hidden

    def _flush(self, tx: NetworkTransaction) -> None:
        output = 0
        for output_index in range(2):
            activity = (self.pending_hidden >> (output_index * 4)) & 0xF
            output |= self._tick_core(
                N_HIDDEN + output_index,
                activity,
                (tx.output_post >> output_index) & 1,
            ) << output_index
        self.hidden_spikes = 0
        self.output_spikes = output
        self.pending_hidden = 0

    def _host(self, tx: NetworkTransaction) -> None:
        opcodes = {
            "mode": Opcode.MODE_SET,
            "clear": Opcode.STATE_CLEAR,
            "capture": Opcode.CAPTURE,
            "feedback": Opcode.FEEDBACK,
            "weight_write": Opcode.WEIGHT_WRITE,
            "weight_read": Opcode.WEIGHT_READ,
        }
        for index in self._targets(tx):
            core = self.cores[index]
            old_direction = tuple(core.captured_direction)
            response = core.execute(Command(opcodes[tx.kind], tx.arg0, tx.arg1))
            if response.status is not Status.OK:
                raise AssertionError((tx, response))
            if tx.kind == "feedback" and tx.arg0 in (1, 3):
                gate = self.gates[index]
                gain = 1 if self.l2 else 2
                for lane, direction in enumerate(old_direction):
                    if self._effective_mask(index) & (1 << lane):
                        evidence = min(3, abs(direction) * gain)
                        gate.utility[lane] = min(
                            15, max(0, gate.utility[lane] - 1) + evidence
                        )
                gate.observe_count += 1

    def _commit(self) -> None:
        for gate in self.gates:
            selected = sorted(
                range(4), key=lambda lane: (gate.utility[lane], -lane), reverse=True
            )[:2]
            gate.mask = sum(1 << lane for lane in selected)
            gate.valid = True
        for core in self.cores:
            response = core.execute(Command(Opcode.STATE_CLEAR))
            if response.status is not Status.OK:
                raise AssertionError(response)
        self.commit_epoch += 1

    def execute(self, tx: NetworkTransaction) -> NetworkState:
        if tx.kind == "tick":
            self._tick(tx)
        elif tx.kind == "flush":
            self._flush(tx)
        elif tx.kind == "commit":
            self._commit()
        else:
            self._host(tx)
        return self.state()

    def state(self) -> NetworkState:
        states = [core.state for core in self.cores]
        captured = []
        for state in states:
            captured.extend(state.captured_direction)
        if self.l2:
            positive = _pack(
                (int(value) for state in states for value in state.positive_evidence), 2
            )
            negative = _pack(
                (int(value) for state in states for value in state.negative_evidence), 2
            )
        else:
            positive = _pack(
                (_pack((int(value) for value in state.positive_evidence), 1)
                 for state in states), 8
            )
            negative = _pack(
                (_pack((int(value) for value in state.negative_evidence), 1)
                 for state in states), 8
            )
        return NetworkState(
            hidden_spikes=self.hidden_spikes,
            output_spikes=self.output_spikes,
            pending_hidden=self.pending_hidden,
            commit_epoch=self.commit_epoch,
            issue_masks=0,
            structural_masks=_pack((gate.mask for gate in self.gates), 4),
            mask_valids=_pack((gate.valid for gate in self.gates), 1),
            pending_valids=_pack((state.pending_valid for state in states), 1),
            modes=_pack((int(state.mode) for state in states), 2),
            weights=_pack((value for state in states for value in state.weights), 4),
            soma=_pack((state.soma for state in states), 8),
            refractory=_pack((state.refractory for state in states), 4),
            leak_timer=_pack((state.leak_timer for state in states), 4),
            pre_age=_pack((value for state in states for value in state.pre_age), 4),
            post_age=_pack((state.post_age for state in states), 4),
            positive=positive,
            negative=negative,
            captured=_pack(captured, 3),
            utility=_pack((value for gate in self.gates for value in gate.utility), 4),
            observe_counts=_pack((gate.observe_count for gate in self.gates), 32),
            refractory_skips=_pack((gate.refractory_skips for gate in self.gates), 32),
            hidden_dense=sum(gate.dense_reads for gate in self.gates[:8]),
            hidden_issued=sum(gate.issued_reads for gate in self.gates[:8]),
            hidden_saved=sum(gate.saved_reads for gate in self.gates[:8]),
            output_dense=sum(gate.dense_reads for gate in self.gates[8:]),
            output_issued=sum(gate.issued_reads for gate in self.gates[8:]),
            output_saved=sum(gate.saved_reads for gate in self.gates[8:]),
        )


__all__ = ["NetworkState", "NetworkTransaction", "PulseMiniPrunedNetworkReference"]

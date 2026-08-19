"""把两层数字 SNN 包装成可测试的 valid/ready 周期传输模型。"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Sequence

from network_sim import DigitalSNN2Layer, NetworkEpisode, PendingCommit


LOGGER = logging.getLogger("cycle_transport")


class BackpressureError(RuntimeError):
    """输入或输出 FIFO 没有可用槽位。"""


@dataclass(frozen=True)
class InputEvent:
    episode_id: int
    tick: int
    synapse_id: int


@dataclass(frozen=True)
class SpikeEvent:
    episode_id: int
    tick: int
    neuron_id: int


class TileCycleTransport:
    """模拟 Host 与片上 tile 之间的有界事件接口。"""

    def __init__(self, network: DigitalSNN2Layer, input_fifo_depth: int = 8, output_fifo_depth: int = 8) -> None:
        if input_fifo_depth <= 0 or output_fifo_depth <= 0:
            raise ValueError("FIFO depth must be positive")
        self.network = network
        self.input_fifo_depth = input_fifo_depth
        self.output_fifo_depth = output_fifo_depth
        self.input_fifo: deque[InputEvent] = deque()
        self.output_fifo: deque[SpikeEvent] = deque()
        self.episode_id: int | None = None
        self.label = 0
        self.train = False
        self.next_tick = 0
        self.expected_event_count: int | None = None
        self.seen_synapses: set[int] = set()
        self.last_summary: NetworkEpisode | None = None
        self.accepted_input_events = 0
        self.rejected_input_events = 0
        self.duplicate_input_events = 0
        self.emitted_spikes = 0

    def begin_episode(self, episode_id: int, label: int, train: bool) -> None:
        if self.episode_id is not None:
            raise RuntimeError("episode already active")
        if self.input_fifo or self.output_fifo:
            raise RuntimeError("FIFO must be drained before EPISODE_START")
        self.episode_id = episode_id
        self.label = label
        self.train = train
        self.next_tick = 0
        self.last_summary = None
        self.network.begin_episode(label=label, train=train, episode_id=episode_id)

    def begin_tick(self, tick: int, event_count: int) -> None:
        """对应 TICK_BEGIN；声明数量后才允许接收该 tick 的事件。"""
        if self.episode_id is None:
            raise RuntimeError("no active episode")
        if self.expected_event_count is not None:
            raise RuntimeError("previous tick has not been committed")
        if tick != self.next_tick:
            raise ValueError("tick must equal the next expected tick")
        if event_count < 0 or event_count > self.input_fifo_depth:
            raise ValueError("event_count must fit the input FIFO")
        self.expected_event_count = event_count
        self.seen_synapses = set()

    def push_input(self, event: InputEvent) -> bool:
        """对应 valid/ready；False 表示 ready=0，事件未被接受。"""
        if self.episode_id != event.episode_id:
            raise ValueError("episode_id mismatch")
        if self.expected_event_count is None:
            raise RuntimeError("TICK_BEGIN is required before INPUT_EVENT")
        if event.tick != self.next_tick:
            raise ValueError("events must target the current tick")
        if event.synapse_id < 0 or event.synapse_id >= self.network.input_count:
            raise ValueError("synapse_id out of range")
        if event.synapse_id in self.seen_synapses:
            self.duplicate_input_events += 1
            raise ValueError("duplicate synapse in the same tick")
        if len(self.input_fifo) >= self.expected_event_count:
            self.rejected_input_events += 1
            return False
        self.input_fifo.append(event)
        self.seen_synapses.add(event.synapse_id)
        self.accepted_input_events += 1
        return True

    def tick_commit(self) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """原子提交当前 tick 的所有输入，然后只做一次跨阈值判断。"""
        if self.episode_id is None:
            raise RuntimeError("no active episode")
        if self.expected_event_count is None:
            raise RuntimeError("TICK_BEGIN is required before TICK_COMMIT")
        if len(self.input_fifo) != self.expected_event_count:
            raise RuntimeError("accepted input count does not match event_count")
        if len(self.output_fifo) + len(self.network.output) > self.output_fifo_depth:
            raise BackpressureError("output FIFO cannot reserve worst-case spike fanout")
        active = tuple(event.synapse_id for event in self.input_fifo)
        self.input_fifo.clear()
        self.expected_event_count = None
        self.seen_synapses = set()
        hidden_fired, output_fired = self.network.step_tick(active, self.next_tick)
        for neuron_id, fired in enumerate(output_fired):
            if fired:
                self.output_fifo.append(SpikeEvent(self.episode_id, self.next_tick, neuron_id))
                self.emitted_spikes += 1
        self.next_tick += 1
        return hidden_fired, output_fired

    def pop_output(self, limit: int | None = None) -> tuple[SpikeEvent, ...]:
        count = len(self.output_fifo) if limit is None else min(limit, len(self.output_fifo))
        return tuple(self.output_fifo.popleft() for _ in range(count))

    def end_episode(self) -> NetworkEpisode:
        if self.episode_id is None:
            raise RuntimeError("no active episode")
        if self.input_fifo or self.expected_event_count is not None:
            raise RuntimeError("pending input events must be committed before episode end")
        if self.network.pending_hidden and len(self.output_fifo) + len(self.network.output) > self.output_fifo_depth:
            raise BackpressureError("output FIFO cannot reserve route flush")
        flush_history = self.network.flush_route(self.next_tick)
        for offset, output_fired in enumerate(flush_history):
            for neuron_id, fired in enumerate(output_fired):
                if fired:
                    self.output_fifo.append(SpikeEvent(self.episode_id, self.next_tick + offset, neuron_id))
                    self.emitted_spikes += 1
        self.last_summary = self.network.end_episode()
        summary = self.last_summary
        self.episode_id = None
        self.train = False
        return summary

    def capture_commit(self, commit_id: int) -> PendingCommit:
        if self.last_summary is None:
            raise RuntimeError("EPISODE_END is required before commit capture")
        return self.network.capture_commit(commit_id)

    def commit_modulator(
        self,
        commit_id: int,
        hidden_modulator: Sequence[int],
        output_modulator: Sequence[int],
    ) -> None:
        self.network.apply_host_modulator(hidden_modulator, output_modulator, commit_id=commit_id)

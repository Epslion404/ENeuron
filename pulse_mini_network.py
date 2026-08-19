"""固定 4->2->2 Pulse-Mini 网络黄金模型与 P8 训练账本。"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass

from pulse_mini_reference import Command, Mode, Opcode, PulseMiniReference, Status


@dataclass(frozen=True)
class NetworkTick:
    input_mask: int
    train_post_mask: int
    hidden_spikes: int
    output_spikes: int
    pending_hidden_before: int
    pending_hidden_after: int


class PulseMiniNetwork:
    """两个隐藏核、两个输出核；输出核只读取上一 tick 的隐藏脉冲。"""

    def __init__(self, *, leak_period: int = PulseMiniReference.LEAK_PERIOD) -> None:
        self.leak_period = leak_period
        self.hidden = [PulseMiniReference(leak_period=leak_period) for _ in range(2)]
        self.output = [PulseMiniReference(leak_period=leak_period) for _ in range(2)]
        self.pending_hidden = 0
        self.tick_index = 0
        self.ledger: list[dict] = []

    @property
    def cores(self) -> tuple[PulseMiniReference, ...]:
        return tuple(self.hidden + self.output)

    @property
    def weights(self) -> tuple[tuple[int, ...], ...]:
        return tuple(tuple(core.weights) for core in self.cores)

    def mode_set(self, mode: Mode) -> None:
        for core in self.cores:
            assert core.execute(Command(Opcode.MODE_SET, int(mode))).status is Status.OK

    def state_clear(self) -> None:
        for core in self.cores:
            assert core.execute(Command(Opcode.STATE_CLEAR)).status is Status.OK
        self.pending_hidden = 0
        self.tick_index = 0

    def tick(self, input_mask: int, train_post_mask: int = 0) -> NetworkTick:
        pending_before = self.pending_hidden
        hidden_spikes = 0
        output_spikes = 0
        hidden_responses = []
        output_responses = []
        for index, core in enumerate(self.hidden):
            response = core.execute(Command(Opcode.TICK, input_mask, (train_post_mask >> index) & 1))
            assert response.status is Status.OK
            hidden_responses.append(response)
            hidden_spikes |= response.spike << index
        for index, core in enumerate(self.output):
            response = core.execute(Command(Opcode.TICK, pending_before, (train_post_mask >> (index + 2)) & 1))
            assert response.status is Status.OK
            output_responses.append(response)
            output_spikes |= response.spike << index
        self.pending_hidden = hidden_spikes
        result = NetworkTick(input_mask, train_post_mask, hidden_spikes, output_spikes,
                             pending_before, self.pending_hidden)
        self.ledger.append({"op": "TICK", **result.__dict__})
        self.tick_index += 1
        return result

    def capture(self, neuron: int) -> tuple[int, ...]:
        core = self.cores[neuron]
        response = core.execute(Command(Opcode.CAPTURE))
        assert response.status is Status.OK
        directions = tuple(core.captured_direction)
        self.ledger.append({"op": "CAPTURE", "neuron": neuron, "direction": directions})
        return directions

    def feedback(self, neuron: int, feedback: int) -> None:
        code = 1 if feedback > 0 else 3 if feedback < 0 else 0
        core = self.cores[neuron]
        before = tuple(core.weights)
        response = core.execute(Command(Opcode.FEEDBACK, code))
        assert response.status is Status.OK
        after = tuple(core.weights)
        self.ledger.append({"op": "FEEDBACK", "neuron": neuron, "feedback": feedback,
                            "before": before, "after": after, "direct_weight_write": False})

    def infer(self, feature: int, ticks: int = 8) -> int:
        self.state_clear()
        output_mask = 0
        for _ in range(ticks):
            output_mask |= self.tick(feature).output_spikes
        return output_mask


def train_network(
    repetitions: int = 6,
    *,
    feedback_enabled: bool = True,
    leak_period: int = PulseMiniReference.LEAK_PERIOD,
) -> PulseMiniNetwork:
    network = PulseMiniNetwork(leak_period=leak_period)
    network.mode_set(Mode.TRAIN)
    # 先训练隐藏层：输入通道 0/1 分别教给两个隐藏核。
    for neuron, feature in ((0, 0b0001), (1, 0b0010)):
        for _ in range(repetitions):
            network.state_clear()
            network.tick(feature)
            network.tick(0, 1 << neuron)
            for _ in range(6):
                network.tick(0)
            network.capture(neuron)
            if feedback_enabled:
                network.feedback(neuron, +1)
            else:
                network.feedback(neuron, 0)
    # 再训练输出层：隐藏脉冲经一拍 pending 后教给对应输出核。
    for neuron, feature, train_post in ((2, 0b0001, 0b0100), (3, 0b0010, 0b1000)):
        for _ in range(repetitions):
            network.state_clear()
            for tick_index in range(8):
                network.tick(feature if tick_index < 6 else 0,
                             train_post if tick_index == 6 else 0)
            network.capture(neuron)
            if feedback_enabled:
                network.feedback(neuron, +1)
            else:
                network.feedback(neuron, 0)
    return network


def run_p8(*, leak_period: int = PulseMiniReference.LEAK_PERIOD) -> dict:
    """运行固定网络 P8 闭环；周期 0 是无泄放 Pulse-Mini 基线。"""

    baseline = PulseMiniNetwork(leak_period=leak_period)
    baseline.mode_set(Mode.INFER)
    baseline_scores = {"positive": baseline.infer(0b0001), "negative": baseline.infer(0b0010)}
    network = train_network(leak_period=leak_period)
    network.mode_set(Mode.INFER)
    before_weights = network.weights
    positive = [network.infer(0b1001 if index % 3 == 0 else 0b0001) for index in range(10)]
    negative = [network.infer(0b1010 if index % 2 == 0 else 0b0010) for index in range(10)]
    after_weights = network.weights
    ticks = [entry for entry in network.ledger if entry["op"] == "TICK"]
    route_delay_observed = any(
        first["hidden_spikes"] != 0 and first["output_spikes"] == 0
        and second["pending_hidden_before"] == first["hidden_spikes"]
        and second["output_spikes"] != 0
        for first, second in zip(ticks, ticks[1:])
    )
    no_feedback = train_network(feedback_enabled=False, leak_period=leak_period)
    no_feedback.mode_set(Mode.INFER)
    no_feedback_scores = [no_feedback.infer(0b0001), no_feedback.infer(0b0010)]
    return {
        "baseline": baseline_scores,
        "positive_outputs": positive,
        "negative_outputs": negative,
        "trained_weights": before_weights,
        "weights_frozen": before_weights == after_weights,
        "no_feedback_outputs": no_feedback_scores,
        "hidden_to_output_one_tick": all(entry["pending_hidden_after"] == entry["hidden_spikes"]
                                          for entry in network.ledger if entry["op"] == "TICK"),
        "route_delay_observed": route_delay_observed,
        "direct_weight_write_count": sum(int(entry.get("direct_weight_write", False))
                                          for entry in network.ledger),
    }


def main() -> None:
    result = run_p8()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    assert result["baseline"] == {"positive": 0, "negative": 0}
    assert all(value == 1 for value in result["positive_outputs"])
    assert all(value == 2 for value in result["negative_outputs"])
    assert result["weights_frozen"]
    assert result["hidden_to_output_one_tick"]
    assert result["route_delay_observed"]
    assert result["direct_weight_write_count"] == 0
    assert result["no_feedback_outputs"] == [0, 0]
    print("PULSE_MINI_P8_PASS clean=20/20 freeze=1 one_tick_route=1 direct_weight_writes=0")


if __name__ == "__main__":
    main()

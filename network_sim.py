"""只使用数字 LIF/可塑突触的两层事件驱动网络。

片上部分只负责：事件处理、膜电位、spike、资格迹线和权重提交。
片外 HostTrainer 负责：目标标签、调制向量、训练顺序和评估。
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Iterable, Sequence

from neuron_sim import ThreeFactorNeuron, TrialEvents, make_trial


LOGGER = logging.getLogger("network_sim")


@dataclass(frozen=True)
class NetworkEpisode:
    label: int
    prediction: int
    hidden_spikes: tuple[int, ...]
    output_spikes: tuple[int, ...]


@dataclass(frozen=True)
class PendingCommit:
    """episode 结束时锁存的 eligibility，避免主机总线延迟覆盖学习状态。"""

    commit_id: int
    episode_id: int
    weight_epoch: int
    hidden_eligibility: tuple[tuple[int, ...], ...]
    output_eligibility: tuple[tuple[int, ...], ...]


class DigitalSNN2Layer:
    """最小两层网络：4 输入 -> 2 隐藏 -> 2 输出。"""

    def __init__(
        self,
        input_count: int = 4,
        hidden_count: int = 2,
        output_count: int = 2,
        route_latency: int = 1,
        hidden_wta: bool = False,
        output_wta: bool = False,
        init_seed: int | None = None,
        max_pending_commits: int = 8,
    ) -> None:
        if hidden_count != 2 or output_count != 2:
            raise ValueError("首版协议固定为二分类的 2 个隐藏和 2 个输出神经元")
        if route_latency != 1:
            raise ValueError("首版硬件合同固定为 1 tick 路由延迟")
        if max_pending_commits <= 0:
            raise ValueError("max_pending_commits must be positive")
        self.input_count = input_count
        self.route_latency = route_latency
        self.hidden_wta = hidden_wta
        self.output_wta = output_wta
        self.hidden = [ThreeFactorNeuron(input_count) for _ in range(hidden_count)]
        self.output = [ThreeFactorNeuron(hidden_count) for _ in range(output_count)]

        # 降低首版阈值，使简单脉冲模式能在少量事件下产生可观察响应。
        for neuron in self.hidden:
            neuron.base_threshold = 4
            neuron.threshold = 4
        for neuron in self.output:
            neuron.base_threshold = 2
            neuron.threshold = 2

        if init_seed is None:
            # 输出读出器只做很小的初始非对称，避免两个输出神经元永远同相。
            self.output[0].weights = [2, 1]
            self.output[1].weights = [1, 2]
        else:
            rng = random.Random(init_seed)
            for neuron in self.neurons:
                neuron.weights = [rng.randint(1, 3) for _ in neuron.weights]
        self.train_enable = False
        self.pending_hidden: tuple[int, ...] = ()
        self.pending_commits: dict[int, PendingCommit] = {}
        self.max_pending_commits = max_pending_commits
        self.weight_epoch = 0
        self.next_commit_to_apply: int | None = None
        self.max_captured_commit_id: int | None = None
        self.episode_active = False
        self.episode_train = False
        self.last_episode_train = False
        self.active_episode_id: int | None = None
        self.last_episode_id: int | None = None
        self.next_episode_id = 0
        self.episode_label = 0
        self.hidden_counts = [0 for _ in self.hidden]
        self.output_counts = [0 for _ in self.output]
        self.hidden_wta_pointer = 0
        self.output_wta_pointer = 0

    @property
    def neurons(self) -> tuple[ThreeFactorNeuron, ...]:
        return tuple(self.hidden + self.output)

    def reset_state(self) -> None:
        for neuron in self.neurons:
            neuron.reset_episode()
        self.pending_hidden = ()
        self.hidden_counts = [0 for _ in self.hidden]
        self.output_counts = [0 for _ in self.output]

    def _predict(self) -> int:
        counts = [neuron.spike_count for neuron in self.output]
        if max(counts, default=0) == 0:
            return -1
        return 0 if counts[0] >= counts[1] else 1

    def _step_layer(
        self,
        neurons: Sequence[ThreeFactorNeuron],
        active_inputs: Iterable[int],
        tick: int,
        use_wta: bool,
        pointer_name: str,
    ) -> tuple[int, ...]:
        if not use_wta:
            return tuple(neuron.step(active_inputs, tick, learn_enable=self.train_enable) for neuron in neurons)

        for neuron in neurons:
            neuron.prepare_step(active_inputs, learn_enable=self.train_enable)
        candidates = [
            index
            for index, neuron in enumerate(neurons)
            if not neuron.prepared_refractory and neuron.v >= neuron.threshold
        ]
        winner: int | None = None
        if candidates:
            max_score = max(neurons[index].v - neurons[index].threshold for index in candidates)
            tied = [index for index in candidates if neurons[index].v - neurons[index].threshold == max_score]
            pointer = int(getattr(self, pointer_name))
            winner = min(tied, key=lambda index: (index - pointer) % len(neurons))
            setattr(self, pointer_name, (winner + 1) % len(neurons))

        return tuple(
            neuron.commit_prepared_step(
                tick,
                allow_fire=index == winner,
                inhibit=winner is not None and index != winner,
                learn_enable=self.train_enable,
            )
            for index, neuron in enumerate(neurons)
        )

    def begin_episode(
        self,
        label: int,
        train: bool = False,
        episode_id: int | None = None,
    ) -> None:
        """对应硬件 EPISODE_START，清动态状态但保留所有权重。"""
        if self.episode_active:
            raise RuntimeError("episode already active")
        self.reset_state()
        self.episode_label = label
        self.train_enable = train
        self.episode_train = train
        self.episode_active = True
        if episode_id is None:
            episode_id = self.next_episode_id
            self.next_episode_id += 1
        self.active_episode_id = episode_id

    def step_tick(self, active_inputs: Iterable[int], tick: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """对应 TICK_COMMIT；同一 tick 的输入必须在调用前收集完成。"""
        if not self.episode_active:
            raise RuntimeError("no active episode")
        output_fired = self._step_layer(
            self.output,
            self.pending_hidden,
            tick,
            self.output_wta,
            "output_wta_pointer",
        )
        hidden_fired = self._step_layer(
            self.hidden,
            active_inputs,
            tick,
            self.hidden_wta,
            "hidden_wta_pointer",
        )
        self.pending_hidden = tuple(index for index, fired in enumerate(hidden_fired) if fired)
        self.hidden_counts = [count + fired for count, fired in zip(self.hidden_counts, hidden_fired)]
        self.output_counts = [count + fired for count, fired in zip(self.output_counts, output_fired)]
        return hidden_fired, output_fired

    def flush_route(self, start_tick: int) -> tuple[tuple[int, ...], ...]:
        """排空隐藏到输出的一拍 FIFO，防止 episode 尾部 spike 丢失。"""
        fired_history: list[tuple[int, ...]] = []
        for flush_offset in range(self.route_latency):
            output_fired = self._step_layer(
                self.output,
                self.pending_hidden,
                start_tick + flush_offset,
                self.output_wta,
                "output_wta_pointer",
            )
            self.output_counts = [count + fired for count, fired in zip(self.output_counts, output_fired)]
            self.pending_hidden = ()
            fired_history.append(output_fired)
        return tuple(fired_history)

    def end_episode(self) -> NetworkEpisode:
        """对应 EPISODE_END，返回片外 Host 所需的最小输出摘要。"""
        if not self.episode_active:
            raise RuntimeError("no active episode")
        result = NetworkEpisode(
            label=self.episode_label,
            prediction=self._predict(),
            hidden_spikes=tuple(self.hidden_counts),
            output_spikes=tuple(self.output_counts),
        )
        self.last_episode_train = self.episode_train
        self.last_episode_id = self.active_episode_id
        self.active_episode_id = None
        self.episode_active = False
        self.train_enable = False
        return result

    def run_episode(self, events: TrialEvents, label: int, train: bool = False) -> NetworkEpisode:
        """整段调用只是逐周期协议的便捷包装。"""
        self.begin_episode(label=label, train=train)
        for tick, active_inputs in enumerate(events):
            self.step_tick(active_inputs, tick)
        self.flush_route(len(events))
        return self.end_episode()

    def capture_commit(self, commit_id: int) -> PendingCommit:
        """在 episode_end 锁存学习状态，之后允许主机延迟到达。"""
        if self.episode_active or not self.last_episode_train or self.last_episode_id is None:
            raise RuntimeError("必须在 train=True 的 EPISODE_END 后捕获 commit")
        if commit_id in self.pending_commits:
            raise ValueError("duplicate commit_id")
        if len(self.pending_commits) >= self.max_pending_commits:
            raise RuntimeError("pending commit buffer is full")
        if self.max_captured_commit_id is not None and commit_id <= self.max_captured_commit_id:
            raise ValueError("commit_id must increase monotonically")
        if self.next_commit_to_apply is None:
            self.next_commit_to_apply = commit_id
        self.max_captured_commit_id = commit_id
        commit = PendingCommit(
            commit_id=commit_id,
            episode_id=self.last_episode_id,
            weight_epoch=self.weight_epoch,
            hidden_eligibility=tuple(tuple(neuron.eligibility) for neuron in self.hidden),
            output_eligibility=tuple(tuple(neuron.eligibility) for neuron in self.output),
        )
        self.pending_commits[commit_id] = commit
        return commit

    def apply_host_modulator(
        self,
        hidden_modulator: Sequence[int],
        output_modulator: Sequence[int],
        commit_id: int | None = None,
    ) -> None:
        """模拟 Host 通过寄存器/事件接口提交 signed modulator。"""
        if len(hidden_modulator) != len(self.hidden) or len(output_modulator) != len(self.output):
            raise ValueError("调制向量长度必须匹配神经元数量")
        if self.episode_active:
            raise RuntimeError("MOD_COMMIT requires an idle tile")
        if commit_id is not None and not self.last_episode_train:
            raise RuntimeError("MOD_COMMIT requires a training episode")
        if commit_id is None:
            if not self.last_episode_train:
                raise RuntimeError("必须先以 train=True 运行 episode 才能提交训练调制")
            for neuron, value in zip(self.hidden, hidden_modulator):
                neuron.apply_modulator(value)
            for neuron, value in zip(self.output, output_modulator):
                neuron.apply_modulator(value)
        else:
            if self.next_commit_to_apply != commit_id:
                raise ValueError("commit_id must be applied in capture order")
            commit = self.pending_commits.pop(commit_id, None)
            if commit is None:
                raise ValueError("unknown, duplicate, or expired commit_id")
            for neuron, value, eligibility in zip(self.hidden, hidden_modulator, commit.hidden_eligibility):
                neuron.apply_modulator_from_eligibility(eligibility, value)
            for neuron, value, eligibility in zip(self.output, output_modulator, commit.output_eligibility):
                neuron.apply_modulator_from_eligibility(eligibility, value)
            self.weight_epoch += 1
            if self.pending_commits:
                self.next_commit_to_apply = min(self.pending_commits)
            else:
                self.next_commit_to_apply = None

    def inference(self, events: TrialEvents, label: int = 0) -> NetworkEpisode:
        """推理路径禁止权重写回。"""
        return self.run_episode(events, label=label, train=False)

    def complexity(self) -> dict[str, int]:
        state_bits = sum(int(neuron.complexity()["state_bits"]) for neuron in self.neurons)
        event_ops = sum(int(neuron.complexity()["event_ops"]) for neuron in self.neurons)
        synapses = self.hidden[0].n_inputs * len(self.hidden) + len(self.hidden) * len(self.output)
        return {
            "neuron_count": len(self.neurons),
            "synapse_count": synapses,
            "state_bits_proxy": state_bits,
            "event_ops_proxy": event_ops,
        }


class HostTrainingController:
    """片外目标/奖励生成器，片上不实现标签或损失函数。"""

    @staticmethod
    def teacher_modulator(label: int) -> tuple[tuple[int, int], tuple[int, int]]:
        """给每层生成 signed 局部调制；这是片外监督协议的一种最小实现。"""
        if label == 0:
            return (1, -1), (1, -1)
        if label == 1:
            return (-1, 1), (-1, 1)
        raise ValueError("首版只支持标签 0 和 1")

    @staticmethod
    def reward_modulator(
        label: int,
        result: NetworkEpisode,
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """片外只生成标量 reward，再按片上活动路径门控到各神经元。"""
        reward = 1 if label == result.prediction else -1
        hidden = tuple(reward if count > 0 else 0 for count in result.hidden_spikes)
        output = tuple(reward if count > 0 else 0 for count in result.output_spikes)
        return hidden, output

    def train(
        self,
        network: DigitalSNN2Layer,
        dataset: Sequence[tuple[TrialEvents, int]],
        epochs: int = 30,
        seed: int = 7,
        mode: str = "teacher",
    ) -> list[float]:
        if mode not in {"teacher", "reward"}:
            raise ValueError("mode must be 'teacher' or 'reward'")
        rng = random.Random(seed)
        history: list[float] = []
        commit_id = 0
        for epoch in range(epochs):
            order = list(range(len(dataset)))
            rng.shuffle(order)
            correct = 0
            for index in order:
                events, label = dataset[index]
                result = network.run_episode(events, label=label, train=True)
                network.capture_commit(commit_id)
                if mode == "teacher":
                    hidden_modulator, output_modulator = self.teacher_modulator(label)
                else:
                    hidden_modulator, output_modulator = self.reward_modulator(label, result)
                network.apply_host_modulator(hidden_modulator, output_modulator, commit_id=commit_id)
                commit_id += 1
                correct += int(result.prediction == label)
            accuracy = correct / len(dataset)
            history.append(accuracy)
            LOGGER.debug("host epoch=%d accuracy=%.3f", epoch, accuracy)
        return history

    def train_hybrid(
        self,
        network: DigitalSNN2Layer,
        dataset: Sequence[tuple[TrialEvents, int]],
        feature_epochs: int = 30,
        reward_epochs: int = 100,
        seed: int = 7,
    ) -> dict[str, list[float]]:
        """先目标塑造隐藏特征，再用探索+reward训练输出动作层。"""
        rng = random.Random(seed)
        feature_history: list[float] = []
        reward_history: list[float] = []
        commit_id = 0

        for _ in range(feature_epochs):
            order = list(range(len(dataset)))
            rng.shuffle(order)
            correct = 0
            for index in order:
                events, label = dataset[index]
                result = network.run_episode(events, label=label, train=True)
                network.capture_commit(commit_id)
                hidden_modulator, _ = self.teacher_modulator(label)
                network.apply_host_modulator(hidden_modulator, (0, 0), commit_id=commit_id)
                commit_id += 1
                correct += int(result.prediction == label)
            feature_history.append(correct / len(dataset))

        # Host 通过状态端口重新初始化输出读出器，隐藏特征权重保持冻结。
        for neuron in network.output:
            neuron.weights = [rng.randint(1, 3) for _ in neuron.weights]

        for epoch in range(reward_epochs):
            order = list(range(len(dataset)))
            rng.shuffle(order)
            epsilon = max(0.05, 0.4 * (1.0 - epoch / max(1, reward_epochs)))
            correct = 0
            for index in order:
                events, label = dataset[index]
                result = network.run_episode(events, label=label, train=True)
                network.capture_commit(commit_id)
                if result.prediction < 0 or rng.random() < epsilon:
                    action = rng.randrange(len(network.output))
                else:
                    action = result.prediction
                reward = 1 if action == label else -1
                output_modulator = tuple(
                    reward if neuron_id == action else 0 for neuron_id in range(len(network.output))
                )
                network.apply_host_modulator((0, 0), output_modulator, commit_id=commit_id)
                commit_id += 1
                correct += int(action == label)
            reward_history.append(correct / len(dataset))

        return {"feature": feature_history, "reward": reward_history}

    def evaluate(
        self,
        network: DigitalSNN2Layer,
        dataset: Sequence[tuple[TrialEvents, int]],
    ) -> float:
        correct = 0
        for events, label in dataset:
            result = network.inference(events, label=label)
            correct += int(result.prediction == label)
        return correct / len(dataset)


def make_dataset() -> tuple[tuple[TrialEvents, int], ...]:
    """基础二分类数据；两类脉冲总数相同，只改变通道。"""
    return ((make_trial(0), 0), (make_trial(1), 1))


def make_noisy_dataset(seed: int, count: int = 20) -> tuple[tuple[TrialEvents, int], ...]:
    """生成丢失一个事件或增加一个同类事件的测试集。"""
    rng = random.Random(seed)
    dataset: list[tuple[TrialEvents, int]] = []
    for index in range(count):
        label = index % 2
        events = [list(tick) for tick in make_trial(label)]
        occupied = [tick for tick, values in enumerate(events) if values]
        if rng.random() < 0.5:
            events[rng.choice(occupied)] = []
        if rng.random() < 0.5:
            tick = rng.randrange(1, 10)
            events[tick].append(0 if label == 1 else 2)
        normalized = tuple(tuple(sorted(set(tick))) for tick in events)
        dataset.append((normalized, label))
    return tuple(dataset)

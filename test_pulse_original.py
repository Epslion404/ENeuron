"""P1 原始计数器/分频基线的确定性行为测试。

该测试使用与 RTL 相同的整数状态转移，专门固定原始方案的成本与缺陷：
学习计数器上限回绕、计数越大周期越短、胞体阈值发放以及同步睡眠清零。
它不把 P1 的通过结果解释为 Pulse-Mini 或任务级训练能力。
"""

from dataclasses import dataclass


@dataclass
class OriginalModel:
    learn_bits: int = 3
    div_bits: int = 3
    soma_bits: int = 8
    threshold: int = 2
    sleep_length: int = 2
    n_inputs: int = 4

    def __post_init__(self) -> None:
        self.learn_max = (1 << self.learn_bits) - 1
        self.div_max = (1 << self.div_bits) - 1
        self.learn = [0] * self.n_inputs
        self.progress = [0] * self.n_inputs
        self.soma = 0
        self.sleep = 0
        self.spike = 0
        self.dendrite = [0] * self.n_inputs

    def tick(self, inputs: tuple[int, ...], learns: tuple[int, ...]) -> None:
        self.spike = 0
        self.dendrite = [0] * self.n_inputs
        next_learn = self.learn[:]
        next_progress = self.progress[:]
        for i in range(self.n_inputs):
            if learns[i]:
                next_learn[i] = 0 if self.learn[i] == self.learn_max else self.learn[i] + 1
            effective = next_learn[i]
            period = max(1, min(self.learn_max - effective, self.div_max))
            if inputs[i]:
                if period == 1 or self.progress[i] >= period - 1:
                    self.dendrite[i] = 1
                    next_progress[i] = 0
                else:
                    next_progress[i] = self.progress[i] + 1
        self.learn = next_learn
        self.progress = next_progress
        if self.sleep:
            self.soma = 0
            self.sleep -= 1
            return
        self.soma += sum(self.dendrite)
        if self.soma >= self.threshold:
            self.spike = 1
            self.soma = 0
            self.sleep = self.sleep_length


def test_learning_counter_wraps_at_upper_limit() -> None:
    model = OriginalModel()
    for _ in range(model.learn_max):
        model.tick((0, 0, 0, 0), (1, 0, 0, 0))
    assert model.learn[0] == model.learn_max
    model.tick((0, 0, 0, 0), (1, 0, 0, 0))
    assert model.learn[0] == 0


def test_larger_learning_count_shortens_divider_period() -> None:
    weak = OriginalModel()
    strong = OriginalModel()
    strong.learn[0] = 5
    weak_latency = None
    strong_latency = None
    for tick_index in range(1, 8):
        weak.tick((1, 0, 0, 0), (0, 0, 0, 0))
        strong.tick((1, 0, 0, 0), (0, 0, 0, 0))
        if weak_latency is None and weak.dendrite[0]:
            weak_latency = tick_index
        if strong_latency is None and strong.dendrite[0]:
            strong_latency = tick_index
    assert weak_latency == 7
    assert strong_latency == 2
    assert strong_latency < weak_latency


def test_soma_fires_and_synchronous_sleep_clears_accumulator() -> None:
    model = OriginalModel()
    model.learn = [model.learn_max] * 4  # period=1 for all four lanes
    model.tick((1, 1, 0, 0), (0, 0, 0, 0))
    assert model.spike == 1
    assert model.sleep == model.sleep_length
    model.tick((1, 1, 1, 1), (0, 0, 0, 0))
    assert model.spike == 0
    assert model.soma == 0
    assert model.sleep == model.sleep_length - 1


def test_only_positive_learning_path_exists() -> None:
    model = OriginalModel()
    model.learn[0] = 2
    model.tick((0, 0, 0, 0), (0, 0, 0, 0))
    assert model.learn[0] == 2
    # 原始接口没有负反馈/抑制位；learn=0 只能保持或再次递增。
    model.tick((0, 0, 0, 0), (1, 0, 0, 0))
    assert model.learn[0] == 3


if __name__ == "__main__":
    tests = [
        test_learning_counter_wraps_at_upper_limit,
        test_larger_learning_count_shortens_divider_period,
        test_soma_fires_and_synchronous_sleep_clears_accumulator,
        test_only_positive_learning_path_exists,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("PULSE_ORIGINAL_PYTHON_PASS tests=4")

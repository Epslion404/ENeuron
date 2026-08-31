"""运行多次训练顺序和输入扰动实验，生成可复核的比较结果。"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Callable

from neuron_sim import BaseNeuron, CounterIFNeuron, PairSTDPNeuron, ThreeFactorNeuron, make_trial


CandidateFactory = Callable[[int], BaseNeuron]


def train_once(factory: CandidateFactory, order_seed: int, epochs: int = 30) -> BaseNeuron:
    neuron = factory(4)
    rng = random.Random(order_seed)
    for _ in range(epochs):
        order = [1, 0]
        rng.shuffle(order)
        for label in order:
            neuron.run_trial(
                make_trial(label),
                label=label,
                modulator=1 if label == 1 else -1,
                train=True,
            )
    return neuron


def noisy_trial(label: int, seed: int) -> tuple[tuple[int, ...], ...]:
    rng = random.Random(seed)
    events = [list(tick) for tick in make_trial(label)]
    occupied = [index for index, tick in enumerate(events) if tick]
    if rng.random() < 0.5:
        events[rng.choice(occupied)] = []
    if rng.random() < 0.5:
        tick = rng.randrange(1, 10)
        events[tick].append(0 if label == 1 else 2)
    return tuple(tuple(sorted(set(tick))) for tick in events)


def main() -> None:
    factories: dict[str, CandidateFactory] = {
        "counter_if": CounterIFNeuron,
        "pair_stdp_lif": PairSTDPNeuron,
        "three_factor_lif": ThreeFactorNeuron,
    }
    summary: dict[str, object] = {"epochs": 30, "order_seeds": 10}
    candidates: dict[str, object] = {}

    for name, factory in factories.items():
        margins: list[int] = []
        successes = 0
        final_weights: list[list[int]] = []
        for seed in range(10):
            neuron = train_once(factory, seed)
            positive = neuron.inference(make_trial(1), 1).spike_count
            negative = neuron.inference(make_trial(0), 0).spike_count
            margin = positive - negative
            margins.append(margin)
            successes += int(margin > 0)
            final_weights.append(list(neuron.weights))
        candidates[name] = {
            "separation_rate": successes / 10,
            "margins": margins,
            "final_weights": final_weights,
            "complexity": factory(4).complexity(),
        }

    recommended = train_once(ThreeFactorNeuron, 0)
    noisy_positive = [recommended.inference(noisy_trial(1, seed), 1).spike_count for seed in range(100)]
    noisy_negative = [recommended.inference(noisy_trial(0, seed), 0).spike_count for seed in range(100)]
    summary["candidates"] = candidates
    summary["recommended_noise_test"] = {
        "positive_mean_spikes": sum(noisy_positive) / len(noisy_positive),
        "negative_mean_spikes": sum(noisy_negative) / len(noisy_negative),
        "positive_nonzero_rate": sum(value > 0 for value in noisy_positive) / len(noisy_positive),
        "negative_zero_rate": sum(value == 0 for value in noisy_negative) / len(noisy_negative),
    }
    Path("artifacts/results/sweep_results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("多次训练顺序实验")
    print("候选                 区分成功率  平均间隔  状态位")
    print("-" * 58)
    for name, item in candidates.items():
        assert isinstance(item, dict)
        complexity = item["complexity"]
        assert isinstance(complexity, dict)
        margins = item["margins"]
        assert isinstance(margins, list)
        print(
            f"{name:<20} {item['separation_rate']:>8.0%}  "
            f"{sum(margins) / len(margins):>8.2f}  {complexity['state_bits']:>6}"
        )
    print("推荐模型扰动测试")
    print(json.dumps(summary["recommended_noise_test"], ensure_ascii=False))


if __name__ == "__main__":
    main()

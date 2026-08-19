"""比较片外可寻址监督调制与全局奖励调制。"""

from __future__ import annotations

import json
from pathlib import Path

from network_sim import DigitalSNN2Layer, HostTrainingController, make_dataset, make_noisy_dataset


def main() -> None:
    host = HostTrainingController()
    clean = make_dataset()
    results: dict[str, object] = {}
    for mode in ("teacher", "reward", "hybrid"):
        clean_scores: list[float] = []
        noisy_scores: list[float] = []
        for seed in range(20):
            network = (
                DigitalSNN2Layer(hidden_wta=True, output_wta=True, init_seed=seed)
                if mode in {"reward", "hybrid"}
                else DigitalSNN2Layer()
            )
            if mode == "hybrid":
                host.train_hybrid(network, clean, feature_epochs=30, reward_epochs=100, seed=seed)
            else:
                host.train(network, clean, epochs=30, seed=seed, mode=mode)
            clean_scores.append(host.evaluate(network, clean))
            noisy_scores.append(host.evaluate(network, make_noisy_dataset(seed=seed, count=100)))
        results[mode] = {
            "seeds": 20,
            "clean_success_rate": sum(score == 1.0 for score in clean_scores) / len(clean_scores),
            "clean_mean_accuracy": sum(clean_scores) / len(clean_scores),
            "noisy_mean_accuracy": sum(noisy_scores) / len(noisy_scores),
            "clean_scores": clean_scores,
        }

    Path("network_sweep_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("两层网络 20 seeds sweep")
    for mode, result in results.items():
        assert isinstance(result, dict)
        print(
            f"{mode:<8} clean_success={result['clean_success_rate']:.1%} "
            f"clean_mean={result['clean_mean_accuracy']:.1%} "
            f"noisy_mean={result['noisy_mean_accuracy']:.1%}"
        )
    print("结果已写入 network_sweep_results.json")


if __name__ == "__main__":
    main()

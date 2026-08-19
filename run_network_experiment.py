"""运行片外监督调制的两层数字 SNN 实验。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from network_sim import DigitalSNN2Layer, HostTrainingController, make_dataset, make_noisy_dataset


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    network = DigitalSNN2Layer()
    host = HostTrainingController()
    clean = make_dataset()
    noisy = make_noisy_dataset(seed=3, count=100)
    history = host.train(network, clean, epochs=30, seed=7)
    result = {
        "training_epochs": len(history),
        "last_epoch_accuracy": history[-1],
        "clean_accuracy": host.evaluate(network, clean),
        "noisy_accuracy": host.evaluate(network, noisy),
        "hidden_weights": [list(neuron.weights) for neuron in network.hidden],
        "output_weights": [list(neuron.weights) for neuron in network.output],
        "complexity": network.complexity(),
        "train_protocol": "host_label_to_signed_local_modulator",
    }
    Path("network_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("两层数字 SNN + 片外调制实验")
    print(f"训练最后一轮准确率: {result['last_epoch_accuracy']:.1%}")
    print(f"干净数据推理准确率: {result['clean_accuracy']:.1%}")
    print(f"扰动数据推理准确率: {result['noisy_accuracy']:.1%}")
    print(f"隐藏层权重: {result['hidden_weights']}")
    print(f"输出层权重: {result['output_weights']}")
    print(f"复杂度代理: {result['complexity']}")
    print("结果已写入 network_results.json")


if __name__ == "__main__":
    main()

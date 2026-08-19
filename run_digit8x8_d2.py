"""运行 D2 多种子实验并落盘机器可读摘要。"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import subprocess
from pathlib import Path

from digit8x8 import load_fixture, load_manifest
from digit8x8_d2 import D2Network, _evaluate_network, run_d2_experiment


LOGGER = logging.getLogger("run_digit8x8_d2")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _run_fixed_weight(fixture: Path, manifest: Path, seed: int) -> dict[str, object]:
    samples = load_fixture(fixture)
    split = load_manifest(manifest)["splits"]
    network = D2Network(init_seed=seed)
    test = _evaluate_network(network, samples, [int(value) for value in split["test"]])
    return {"test": test.as_dict(), "output_weights": [list(weights) for weights in network.output_weights]}


def _run_label_shuffle(fixture: Path, manifest: Path, seed: int, epochs: int) -> dict[str, object]:
    samples = load_fixture(fixture)
    split = load_manifest(manifest)["splits"]
    train_ids = [int(value) for value in split["train"]]
    shuffled_labels = [samples[sample_id].label for sample_id in train_ids]
    random.Random(seed).shuffle(shuffled_labels)
    network = D2Network(init_seed=seed)
    for epoch in range(epochs):
        order = list(range(len(train_ids)))
        random.Random(seed + epoch).shuffle(order)
        for position in order:
            sample_id = train_ids[position]
            sample = samples[sample_id]
            network.train_sample(sample.sample_id, sample.pixels, shuffled_labels[position])
    test = _evaluate_network(network, samples, [int(value) for value in split["test"]])
    return {"test": test.as_dict(), "output_weights": [list(weights) for weights in network.output_weights]}


def run_report(
    fixture: Path,
    manifest: Path,
    seeds: list[int],
    epochs: int,
) -> dict[str, object]:
    primary: list[dict[str, object]] = []
    for seed in seeds:
        result = run_d2_experiment(fixture, manifest, epochs=epochs, seed=seed)
        model = result["models"]["d2_teacher"]
        primary.append({"seed": seed, **model})
        LOGGER.info(
            "seed=%d validation_bacc=%.4f validation_coverage=%.4f test_bacc=%.4f test_coverage=%.4f",
            seed,
            model["validation"]["balanced_accuracy"],
            model["validation"]["coverage"],
            model["test"]["balanced_accuracy"],
            model["test"]["coverage"],
        )
    controls = {
        "fixed_weight_seed0": _run_fixed_weight(fixture, manifest, seed=0),
        "label_shuffle_seed0": _run_label_shuffle(fixture, manifest, seed=0, epochs=epochs),
    }
    return {
        "format": "eneuron_digit8x8_d2_report_v1",
        "config": {
            "fixture": str(fixture),
            "manifest": str(manifest),
            "seeds": seeds,
            "epochs": epochs,
            "architecture": "64->16->4->10",
            "teacher_window": "input_then_next_tick_teacher_post_then_3_empty_ticks",
            "fixture_sha256": _sha256(fixture),
            "manifest_sha256": _sha256(manifest),
            "runner_source_sha256": _sha256(Path(__file__).resolve()),
            "model_source_sha256": _sha256(Path("digit8x8_d2.py")),
            "git_commit": _git_commit(),
        },
        "primary": primary,
        "controls": controls,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 ENeuron 8x8 D2 多种子实验")
    parser.add_argument("--fixture", type=Path, default=Path("digit8x8_fixture.json"))
    parser.add_argument("--manifest", type=Path, default=Path("digit8x8_manifest.json"))
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(10)))
    parser.add_argument("--output", type=Path, default=Path("digit8x8_d2_results.json"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_report(args.fixture, args.manifest, args.seeds, args.epochs)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"DIGIT8X8_D2_REPORT_WRITTEN path={args.output.resolve()} seeds={len(args.seeds)}")


if __name__ == "__main__":
    main()

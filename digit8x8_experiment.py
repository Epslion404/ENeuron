"""8x8 数字识别的软件基线与分层实验工具。

本文件先提供 D1 的非学习基线。所有分类器只使用冻结 fixture 与编码结果，
不修改 ENeuron 状态，也不把软件上限冒充硬件证据。
"""

from __future__ import annotations

import json
import logging
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from digit8x8 import DigitSample, TIME_STEPS, encode_rank_order, load_fixture, load_manifest


LOGGER = logging.getLogger("digit8x8_experiment")
LABELS = tuple(range(10))


@dataclass(frozen=True)
class ClassificationMetrics:
    sample_count: int
    balanced_accuracy: float
    accuracy: float
    macro_f1: float
    coverage: float
    abstain_rate: float
    confusion: tuple[tuple[int, ...], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "sample_count": self.sample_count,
            "balanced_accuracy": self.balanced_accuracy,
            "accuracy": self.accuracy,
            "macro_f1": self.macro_f1,
            "coverage": self.coverage,
            "abstain_rate": self.abstain_rate,
            "confusion": [list(row) for row in self.confusion],
        }


def latency_features(pixels: Sequence[int]) -> tuple[int, ...]:
    """将每个像素映射为发放 tick，未选中像素使用 TIME_STEPS。"""
    features = [TIME_STEPS] * 64
    for tick, events in enumerate(encode_rank_order(pixels)):
        for pixel_index in events:
            features[pixel_index] = tick
    return tuple(features)


def event_count_features(pixels: Sequence[int]) -> tuple[int, ...]:
    """只保留总事件数，用于检测恒定事件数泄漏基线。"""
    return (sum(len(events) for events in encode_rank_order(pixels)),)


def time_summary_features(pixels: Sequence[int], keep: str) -> tuple[int, ...]:
    events = encode_rank_order(pixels)
    selected = tuple(index for index, tick_events in enumerate(events) if tick_events)
    if keep == "first":
        return (selected[0] if selected else TIME_STEPS,)
    if keep == "last":
        return (selected[-1] if selected else TIME_STEPS,)
    raise ValueError("keep must be first or last")


@dataclass(frozen=True)
class NearestCentroidClassifier:
    centroids: tuple[tuple[float, ...], ...]

    def predict(self, features: Sequence[float]) -> int:
        distances = [sum((float(a) - b) ** 2 for a, b in zip(features, centroid)) for centroid in self.centroids]
        best = min(distances)
        winners = [label for label, distance in enumerate(distances) if distance == best]
        return winners[0] if len(winners) == 1 else -1


def train_nearest_centroid(
    samples: Sequence[DigitSample],
    train_ids: Iterable[int],
    feature_fn=latency_features,
) -> NearestCentroidClassifier:
    by_id = {sample.sample_id: sample for sample in samples}
    sums = [[0.0] * len(feature_fn(samples[0].pixels)) for _ in LABELS]
    counts = [0] * len(LABELS)
    for sample_id in train_ids:
        sample = by_id[int(sample_id)]
        features = feature_fn(sample.pixels)
        for index, value in enumerate(features):
            sums[sample.label][index] += float(value)
        counts[sample.label] += 1
    if any(count == 0 for count in counts):
        raise ValueError("every label needs at least one training sample")
    centroids = tuple(tuple(value / counts[label] for value in sums[label]) for label in LABELS)
    return NearestCentroidClassifier(centroids)


def evaluate_predictions(labels: Sequence[int], predictions: Sequence[int]) -> ClassificationMetrics:
    if len(labels) != len(predictions):
        raise ValueError("labels and predictions must have equal length")
    confusion = [[0] * len(LABELS) for _ in LABELS]
    per_class_tp = [0] * len(LABELS)
    per_class_fp = [0] * len(LABELS)
    per_class_fn = [0] * len(LABELS)
    actual_counts = [0] * len(LABELS)
    covered = 0
    correct = 0
    for label, prediction in zip(labels, predictions):
        actual_counts[label] += 1
        if prediction < 0:
            per_class_fn[label] += 1
            continue
        covered += 1
        if prediction == label:
            correct += 1
            per_class_tp[label] += 1
        else:
            per_class_fn[label] += 1
            per_class_fp[prediction] += 1
            confusion[label][prediction] += 1
        confusion[label][label] += 1 if prediction == label else 0
    recalls = []
    f1s = []
    for label in LABELS:
        support = actual_counts[label]
        recalls.append(per_class_tp[label] / support if support else 0.0)
        denominator = 2 * per_class_tp[label] + per_class_fp[label] + per_class_fn[label]
        f1s.append(2 * per_class_tp[label] / denominator if denominator else 0.0)
    sample_count = len(labels)
    coverage = covered / sample_count if sample_count else 0.0
    return ClassificationMetrics(
        sample_count=sample_count,
        balanced_accuracy=sum(recalls) / len(recalls),
        accuracy=correct / sample_count if sample_count else 0.0,
        macro_f1=sum(f1s) / len(f1s),
        coverage=coverage,
        abstain_rate=1.0 - coverage,
        confusion=tuple(tuple(row) for row in confusion),
    )


def run_nearest_centroid(
    samples: Sequence[DigitSample],
    manifest: dict[str, object],
    feature_fn=latency_features,
) -> dict[str, ClassificationMetrics]:
    classifier = train_nearest_centroid(samples, manifest["splits"]["train"], feature_fn)
    by_id = {sample.sample_id: sample for sample in samples}
    results: dict[str, ClassificationMetrics] = {}
    for split, ids in manifest["splits"].items():
        labels = [by_id[int(sample_id)].label for sample_id in ids]
        predictions = [classifier.predict(feature_fn(by_id[int(sample_id)].pixels)) for sample_id in ids]
        results[split] = evaluate_predictions(labels, predictions)
    return results


def run_d1(
    fixture_path: str | Path,
    manifest_path: str | Path,
    *,
    label_shuffle_seed: int = 20260819,
) -> dict[str, object]:
    samples = load_fixture(fixture_path)
    manifest = load_manifest(manifest_path)
    by_id = {sample.sample_id: sample for sample in samples}
    result: dict[str, object] = {
        "format": "eneuron_digit8x8_d1_v1",
        "fixture_sha256": manifest["fixture_sha256"],
        "models": {},
    }
    result["models"]["nearest_centroid_latency"] = {
        split: metrics.as_dict() for split, metrics in run_nearest_centroid(samples, manifest).items()
    }
    result["models"]["nearest_centroid_event_count"] = {
        split: metrics.as_dict()
        for split, metrics in run_nearest_centroid(samples, manifest, event_count_features).items()
    }
    result["models"]["nearest_centroid_first_tick"] = {
        split: metrics.as_dict()
        for split, metrics in run_nearest_centroid(
            samples, manifest, lambda pixels: time_summary_features(pixels, "first")
        ).items()
    }
    result["models"]["nearest_centroid_last_tick"] = {
        split: metrics.as_dict()
        for split, metrics in run_nearest_centroid(
            samples, manifest, lambda pixels: time_summary_features(pixels, "last")
        ).items()
    }

    shuffled = list(manifest["splits"]["train"])
    rng = random.Random(label_shuffle_seed)
    labels = [by_id[int(sample_id)].label for sample_id in shuffled]
    rng.shuffle(labels)
    shuffled_samples = [DigitSample(sample.sample_id, labels[index], sample.pixels) for index, sample in enumerate(by_id[int(sample_id)] for sample_id in shuffled)]
    remapped = {sample.sample_id: sample for sample in shuffled_samples}
    merged = [remapped.get(sample.sample_id, sample) for sample in samples]
    result["models"]["label_shuffle_latency"] = {
        split: metrics.as_dict() for split, metrics in run_nearest_centroid(merged, manifest).items()
    }
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_d1("digit8x8_fixture.json", "digit8x8_manifest.json")
    Path("digit8x8_d1_results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    test = result["models"]["nearest_centroid_latency"]["test"]
    print(f"DIGIT8X8_D1_PASS test_balanced_accuracy={test['balanced_accuracy']:.4f} coverage={test['coverage']:.4f}")


if __name__ == "__main__":
    main()

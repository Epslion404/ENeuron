"""一次性将本机 digits 数据转换为仓库内的固定 8x8 fixture。

该脚本只用于生成可审计输入；运行时编码器不依赖 sklearn。生成后应检查
fixture 与 manifest 的 SHA-256，并把二者作为同一版本提交。
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from sklearn.datasets import load_digits


ROOT = Path(__file__).resolve().parent
FIXTURE_PATH = ROOT / "digit8x8_fixture.json"
MANIFEST_PATH = ROOT / "digit8x8_manifest.json"
SEED = 20260819


def canonical_json(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()


def main() -> None:
    dataset = load_digits()
    rows = []
    for sample_id, (pixels, label) in enumerate(zip(dataset.data, dataset.target)):
        quantized = [int(round(float(value) * 15.0 / 16.0)) for value in pixels]
        if any(value < 0 or value > 15 for value in quantized):
            raise ValueError("unexpected source pixel range")
        rows.append({"sample_id": sample_id, "label": int(label), "pixels": quantized})

    fixture = {
        "format": "eneuron_digit8x8_fixture_v1",
        "source": "sklearn.datasets.load_digits",
        "source_shape": [8, 8],
        "pixel_range": [0, 15],
        "samples": rows,
    }
    FIXTURE_PATH.write_bytes(canonical_json(fixture))

    per_label: dict[int, list[int]] = {label: [] for label in range(10)}
    for row in rows:
        per_label[row["label"]].append(row["sample_id"])
    rng = random.Random(SEED)
    splits = {"train": [], "validation": [], "test": []}
    for label in range(10):
        ids = per_label[label][:]
        rng.shuffle(ids)
        train_end = int(len(ids) * 0.7)
        validation_end = int(len(ids) * 0.85)
        splits["train"].extend(sorted(ids[:train_end]))
        splits["validation"].extend(sorted(ids[train_end:validation_end]))
        splits["test"].extend(sorted(ids[validation_end:]))
    for split in splits.values():
        split.sort()

    fixture_sha256 = hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest()
    manifest = {
        "format": "eneuron_digit8x8_manifest_v1",
        "fixture": FIXTURE_PATH.name,
        "fixture_sha256": fixture_sha256,
        "split_seed": SEED,
        "splits": splits,
        "split_label_counts": {
            name: {str(label): sum(rows[index]["label"] == label for index in ids) for label in range(10)}
            for name, ids in splits.items()
        },
        "dataset_label_counts": {str(label): count for label, count in sorted(Counter(row["label"] for row in rows).items())},
        "encoding": {
            "name": "rank_order_latency",
            "rank_k": 16,
            "time_steps": 16,
            "tie_break": "pixel_index_ascending",
            "events_per_sample": 16,
            "label_independent": True,
        },
    }
    MANIFEST_PATH.write_bytes(canonical_json(manifest))
    print(json.dumps({"fixture": FIXTURE_PATH.name, "manifest": MANIFEST_PATH.name, "samples": len(rows)}, sort_keys=True))


if __name__ == "__main__":
    main()

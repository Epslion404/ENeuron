from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from b3_accuracy_merge import merge


def _summary(path: Path, rows: list[dict[str, object]], logits_key: str) -> None:
    samples = []
    for row in rows:
        samples.append({
            "sample_id": row["sample_id"],
            "input_sha256": row["input_sha256"],
            "label": row["label"],
            "mask_epoch": row["mask_epoch"],
            "input_crc": row["input_crc"],
            "status": 2,
            "logits": row[logits_key],
        })
    path.write_text(json.dumps({
        "model_id": 3,
        "preprocess": "uint4_64_low_nibble_first_v1",
        "bitstream_sha256": "bit",
        "xsa_sha256": "xsa",
        "elf_sha256": "elf-dense" if "dense" in path.name else "elf-live",
        "benchmark_manifest_sha256": "manifest",
        "accuracy_capture": {"status": 2, "samples": samples},
    }), encoding="utf-8")


class B3AccuracyMergeTests(unittest.TestCase):
    def test_pairs_same_inputs_and_preserves_labels(self) -> None:
        rows = [
            {"sample_id": 2, "input_sha256": "a", "label": 0, "mask_epoch": 2,
             "input_crc": 11, "dense_logits": [3, 0], "live_logits": [3, 0]},
            {"sample_id": 1, "input_sha256": "b", "label": 1, "mask_epoch": 3,
             "input_crc": 12, "dense_logits": [0, 3], "live_logits": [0, 3]},
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dense = root / "dense.json"
            live = root / "live.json"
            _summary(dense, rows, "dense_logits")
            _summary(live, rows, "live_logits")
            result = merge([dense], [live])
            self.assertEqual([row["sample_id"] for row in result["samples"]], ["1", "2"])
            self.assertEqual([row["label"] for row in result["samples"]], [1, 0])
            self.assertEqual(result["identity"]["benchmark_manifest_sha256"], "manifest")
            self.assertEqual(result["identity"]["dense_elf_sha256"], "elf-dense")
            self.assertEqual(result["identity"]["live_elf_sha256"], "elf-live")


if __name__ == "__main__":
    unittest.main()

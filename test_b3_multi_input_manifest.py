from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from b3_multi_input_manifest import build_multi_input_manifest, write_multi_input_manifest


class B3MultiInputManifestTests(unittest.TestCase):
    def test_sixty_four_samples_are_unique_and_reference_checked(self) -> None:
        manifest = build_multi_input_manifest(sample_count=64, seed=0xB3221)
        self.assertEqual(manifest["schema"], "eneuron_b3_multi_input_v1")
        self.assertEqual(manifest["sample_count"], 64)
        samples = manifest["samples"]
        self.assertEqual(len(samples), 64)
        self.assertEqual(len({sample["sample_id"] for sample in samples}), 64)
        self.assertEqual(len({sample["input_sha256"] for sample in samples}), 64)
        for sample in samples:
            self.assertEqual(len(sample["input_beats"]), 8)
            self.assertEqual(len(sample["dense_logits"]), 10)
            self.assertEqual(len(sample["live_logits"]), 10)
            self.assertEqual(len(sample["live_mask_words"]), 19)
            self.assertEqual(sample["active_groups"] + sample["skipped_groups"], 592)
            self.assertEqual(sample["dense_mask_epoch"], 1)
            self.assertEqual(sample["live_mask_epoch"], sample["sample_index"] + 2)
            self.assertEqual(sample["mask_epoch"], sample["live_mask_epoch"])
            packed = bytes(sample["pixels"])
            self.assertEqual(hashlib.sha256(packed).hexdigest(), sample["input_sha256"])

    def test_manifest_is_deterministic_and_round_trips(self) -> None:
        first = build_multi_input_manifest(sample_count=8, seed=7)
        second = build_multi_input_manifest(sample_count=8, seed=7)
        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "multi.json"
            write_multi_input_manifest(path, first)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), first)

    def test_sample_count_range_is_bounded_by_board_scratch(self) -> None:
        with self.assertRaises(ValueError):
            build_multi_input_manifest(sample_count=0)
        with self.assertRaises(ValueError):
            build_multi_input_manifest(sample_count=65)


if __name__ == "__main__":
    unittest.main()

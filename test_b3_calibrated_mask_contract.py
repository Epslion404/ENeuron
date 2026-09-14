"""B3-22.3 合同：校准 group_4way mask 生成、格式与 held-out manifest。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from b3_calibrated_mask import (
    CALIBRATION_POLICY,
    HELDOUT_SCHEMA,
    SCHEMA,
    DEFAULT_CHUNK_DIRECTORY,
    DEFAULT_HELDOUT_PATH,
    DEFAULT_MASK_PATH,
    _chunk_paths,
    calibrated_mask_from_votes,
    load_chunk_samples,
    calibration_votes,
)
from b3_fixed_vector_manifest import load_b3_manifest, model_words_from_manifest
from eneuron_group4way_live import GROUP_COUNT


ROOT = Path(__file__).resolve().parent


def _two_of_four_violations(mask_words: tuple[int, ...]) -> int:
    violations = 0
    for base in range(0, 512, 4):
        ones = sum((mask_words[(base + offset) // 32] >> ((base + offset) % 32)) & 1 for offset in range(4))
        violations += 1 if ones != 2 else 0
    for base in range(512, 592, 4):
        ones = sum((mask_words[(base + offset) // 32] >> ((base + offset) % 32)) & 1 for offset in range(4))
        violations += 1 if ones != 2 else 0
    return violations


class B3CalibratedMaskContractTests(unittest.TestCase):
    def test_zero_votes_use_stable_tie_break_and_reserved_bits(self) -> None:
        mask_words = calibrated_mask_from_votes([0] * GROUP_COUNT)
        self.assertEqual(_two_of_four_violations(mask_words), 0)
        self.assertEqual(mask_words[0], 0x33333333)
        self.assertEqual(mask_words[18], 0x00003333)

    def test_majority_vote_mask_is_deterministic_and_two_of_four(self) -> None:
        manifest = load_b3_manifest()
        model_words = model_words_from_manifest(manifest)
        samples = [
            {"pixels": [0] * 64},
            {"pixels": [15] * 64},
            {"pixels": [(index * 5) & 0xF for index in range(64)]},
        ]
        first = calibrated_mask_from_votes(calibration_votes(samples, model_words))
        second = calibrated_mask_from_votes(calibration_votes(samples, model_words))
        self.assertEqual(first, second)
        self.assertEqual(_two_of_four_violations(first), 0)
        self.assertEqual(sum(1 for word in first for bit in range(32) if (word >> bit) & 1), 296)

    def test_shipped_calibration_mask_and_heldout_manifest(self) -> None:
        mask_document = json.loads(DEFAULT_MASK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(mask_document["schema"], SCHEMA)
        self.assertEqual(mask_document["identity"]["policy"], CALIBRATION_POLICY)
        self.assertEqual(mask_document["active_groups"], 296)
        words = tuple(int(word, 0) for word in mask_document["mask_words"])
        self.assertEqual(_two_of_four_violations(words), 0)
        self.assertEqual(words[18] >> 16, 0)

        heldout = json.loads(DEFAULT_HELDOUT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(heldout["schema"], HELDOUT_SCHEMA)
        self.assertEqual(heldout["sample_count"], 64)
        self.assertTrue(all(sample["mask_epoch"] == 1 for sample in heldout["samples"]))
        self.assertTrue(all("calibrated_static_logits" in sample for sample in heldout["samples"]))

        if DEFAULT_CHUNK_DIRECTORY.is_dir():
            manifest = load_b3_manifest()
            model_words = model_words_from_manifest(manifest)
            calibration_samples = load_chunk_samples(
                _chunk_paths(DEFAULT_CHUNK_DIRECTORY, 0, 7), 512
            )
            rebuilt = calibrated_mask_from_votes(calibration_votes(calibration_samples, model_words))
            self.assertEqual([f"0x{word:08X}" for word in rebuilt], mask_document["mask_words"])


if __name__ == "__main__":
    unittest.main()

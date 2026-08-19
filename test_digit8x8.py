import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from digit8x8 import (
    IMAGE_SIDE,
    PATCH_COUNT,
    RANK_K,
    TIME_STEPS,
    encode_patch_masks,
    encode_rank_order,
    load_fixture,
    load_manifest,
    reconstruct_pixel_events,
)


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "digit8x8_fixture.json"
MANIFEST = ROOT / "digit8x8_manifest.json"


class Digit8x8ContractTests(unittest.TestCase):
    def test_fixture_is_fixed_size_balanced_and_split_disjoint(self):
        samples = load_fixture(FIXTURE)
        manifest = load_manifest(MANIFEST)
        self.assertGreaterEqual(len(samples), 1000)
        self.assertEqual({len(sample.pixels) for sample in samples}, {IMAGE_SIDE * IMAGE_SIDE})
        self.assertEqual(set(manifest["splits"]), {"train", "validation", "test"})
        split_ids = [set(manifest["splits"][name]) for name in ("train", "validation", "test")]
        self.assertEqual(sum(map(len, split_ids)), len(samples))
        self.assertEqual(len(set.union(*split_ids)), len(samples))
        self.assertEqual(len(set.intersection(*split_ids)), 0)
        for split in split_ids:
            labels = [samples[index].label for index in split]
            self.assertEqual(set(labels), set(range(10)))

    def test_rank_order_is_deterministic_and_has_constant_event_count(self):
        sample = load_fixture(FIXTURE)[0]
        first = encode_rank_order(sample.pixels)
        second = encode_rank_order(sample.pixels)
        self.assertEqual(first, second)
        self.assertEqual(len(first), TIME_STEPS)
        self.assertEqual(sum(len(events) for events in first), RANK_K)
        self.assertTrue(all(len(set(events)) == len(events) for events in first))

    def test_tie_breaking_is_pixel_index_order(self):
        pixels = tuple([7] * (IMAGE_SIDE * IMAGE_SIDE))
        events = encode_rank_order(pixels)
        selected = [pixel for tick in events for pixel in tick]
        self.assertEqual(selected, list(range(RANK_K)))

    def test_patch_masks_round_trip_to_flat_pixel_events(self):
        sample = load_fixture(FIXTURE)[13]
        events = encode_rank_order(sample.pixels)
        patch_masks = encode_patch_masks(sample.pixels)
        self.assertEqual(len(patch_masks), TIME_STEPS)
        self.assertTrue(all(len(masks) == PATCH_COUNT for masks in patch_masks))
        self.assertEqual(reconstruct_pixel_events(patch_masks), events)

    def test_encoder_has_no_label_or_global_rng_dependency(self):
        sample = load_fixture(FIXTURE)[27]
        before = hashlib.sha256(json.dumps(sample.pixels).encode()).hexdigest()
        first = encode_patch_masks(sample.pixels)
        second = encode_patch_masks(sample.pixels)
        after = hashlib.sha256(json.dumps(sample.pixels).encode()).hexdigest()
        self.assertEqual(first, second)
        self.assertEqual(before, after)

    def test_manifest_binds_fixture_sha256(self):
        manifest = load_manifest(MANIFEST)
        digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertEqual(manifest["fixture_sha256"], digest)


if __name__ == "__main__":
    unittest.main()

import copy
import json
import unittest
from pathlib import Path

from verify_b2_dma_address_layout import validate_layout
from tools.ci.classify_changes import classify_paths


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "tools" / "repro" / "b2_dma_address_layout.json"


class B2DmaAddressLayoutTests(unittest.TestCase):
    def setUp(self):
        self.layout = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_frozen_layout_passes(self):
        self.assertEqual(validate_layout(self.layout), [])

    def test_rejects_overlap(self):
        candidate = copy.deepcopy(self.layout)
        candidate["regions"][1]["base"] = candidate["regions"][0]["base"]
        self.assertTrue(any("overlap" in error for error in validate_layout(candidate)))

    def test_rejects_unaligned_region(self):
        candidate = copy.deepcopy(self.layout)
        candidate["regions"][0]["base"] += 32
        self.assertTrue(any("aligned" in error for error in validate_layout(candidate)))

    def test_rejects_region_outside_verified_window(self):
        candidate = copy.deepcopy(self.layout)
        candidate["regions"][0]["base"] = candidate["verified_window"]["end_exclusive"]
        self.assertTrue(any("window" in error for error in validate_layout(candidate)))

    def test_rejects_payload_larger_than_region(self):
        candidate = copy.deepcopy(self.layout)
        candidate["regions"][0]["payload_bytes"] = candidate["regions"][0]["capacity_bytes"] + 1
        self.assertTrue(any("payload" in error for error in validate_layout(candidate)))

    def test_verifier_uses_targeted_repro_gate(self):
        scopes = classify_paths(["verify_b2_dma_address_layout.py"])
        self.assertTrue(scopes["t1_repro"])
        self.assertFalse(scopes["full_repository"])


if __name__ == "__main__":
    unittest.main()

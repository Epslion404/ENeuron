"""B3 固定向量黄金 manifest 合同。"""

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "tools" / "repro" / "b3_fixed_vector_manifest.json"


class B3FixedVectorManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_freezes_model_and_target(self) -> None:
        self.assertEqual(self.manifest["schema"], "eneuron_b3_fixed_vector_v1")
        self.assertEqual(self.manifest["target"]["part"], "xc7z020clg484-2")
        self.assertEqual(self.manifest["target"]["protocol"], "ENB2_PACKET_NPU_V1")
        self.assertEqual(self.manifest["model"]["word_count"], 634)
        self.assertEqual(len(self.manifest["model"]["nonzero_words"]), 19)

    def test_sample_has_fixed_eight_beats_and_mode_outputs(self) -> None:
        sample = self.manifest["samples"][0]
        self.assertEqual(sample["sample_id"], "0x12345678")
        self.assertEqual(len(sample["input_beats"]), 8)
        self.assertEqual(set(sample["modes"]), {
            "b3_dense", "b3_full_open", "b3_bypass", "b3_static_mixed", "b3_live_eneuron"
        })
        for mode in sample["modes"].values():
            self.assertEqual(len(mode["expected_logits"]), 10)
            self.assertEqual(mode["mask_granularity"], "group_4way")

    def test_gated_modes_include_replayable_mask_words(self) -> None:
        modes = self.manifest["samples"][0]["modes"]
        for name in ("b3_dense", "b3_full_open", "b3_static_mixed", "b3_live_eneuron"):
            self.assertEqual(len(modes[name]["mask_words_data"]), 19)
        self.assertNotIn("mask_words_data", modes["b3_bypass"])

    def test_static_mixed_is_explicitly_not_strict_lane_2of4(self) -> None:
        mode = self.manifest["samples"][0]["modes"]["b3_static_mixed"]
        self.assertFalse(mode["strict_2of4_candidate"])
        self.assertEqual(mode["active_groups"], 296)
        self.assertEqual(mode["skipped_groups"], 296)
        self.assertEqual(mode["prediction_class"], 9)


if __name__ == "__main__":
    unittest.main()

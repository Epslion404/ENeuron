"""QAT 剪枝仿真数据的最小合同：可证伪性、删除统计与精度事实。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ARTIFACT = ROOT / "artifacts" / "results" / "b3_qat_pruning_diagnostic.json"


class B3QatPruningEvalContractTests(unittest.TestCase):
    def setUp(self) -> None:
        if not ARTIFACT.is_file():
            self.skipTest("QAT pruning diagnostic not generated")
        self.report = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    def test_manifest_matches_canonical_packing(self) -> None:
        self.assertEqual(self.report["schema"], "eneuron_b3_qat_pruning_diagnostic_v1")
        self.assertEqual(self.report["identity"]["packed_words_sha256"],
                         "3cf17775eda5ce264f1a8ba657098075718fcc7fff275b1596ee40268fa0a862")
        self.assertEqual(self.report["accuracy"]["heldout"], 64)

    def test_gate_is_falsifiable_and_deletion_is_meaningful(self) -> None:
        self.assertEqual(self.report["falsifiability"]["verdict"], "FALSIFIABLE")
        self.assertEqual(self.report["model"]["nonzero_weight_groups"], 533)
        self.assertEqual(self.report["model"]["metas_with_nonzero_group"], 148)
        self.assertEqual(self.report["mask"]["distinct_live_masks"], 64)
        self.assertGreater(self.report["deletion"]["deleted_nonzero_contribution_instances"], 0)
        self.assertGreater(self.report["deletion"]["deleted_nonzero_weight_instances"], 0)

    def test_accuracy_and_output_deviation_are_recorded(self) -> None:
        accuracy = self.report["accuracy"]
        self.assertGreater(accuracy["dense_accuracy"], 0.9)
        self.assertLess(accuracy["live_accuracy"], accuracy["dense_accuracy"])
        self.assertGreater(accuracy["accuracy_drop_live_pp"], 1.0)
        self.assertLess(self.report["output"]["prediction_agreement_live"], 1.0)
        self.assertGreater(self.report["output"]["max_abs_logit_error_live"], 0)


if __name__ == "__main__":
    unittest.main()

"""NP2 最小量化扫描与统计合同测试。"""

from __future__ import annotations

import unittest

from local_prune_b2 import B2Checkpoint, B2Evidence
from local_prune_np2 import run_np2_scan, scale_checkpoint_evidence


class LocalPruneNp2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_np2_scan(seeds=tuple(range(10)))

    def test_scan_requires_ten_distinct_seeds(self) -> None:
        with self.assertRaises(ValueError):
            run_np2_scan(seeds=tuple(range(9)))
        with self.assertRaises(ValueError):
            run_np2_scan(seeds=(0,) * 10)

    def test_evidence_gain_is_global_integer_and_saturates_to_two_bits(self) -> None:
        checkpoint = B2Checkpoint(
            "probe",
            (object(),),
            ((B2Evidence("stable", (0, 0, 0, 0), (0, 1, 2, 3), 1),),),
        )
        scaled = scale_checkpoint_evidence(checkpoint, gain=2)
        self.assertEqual(scaled.ledgers[0][0].evidence_levels, (0, 2, 3, 3))
        with self.assertRaises(ValueError):
            scale_checkpoint_evidence(checkpoint, gain=0)
        with self.assertRaises(TypeError):
            scale_checkpoint_evidence(checkpoint, gain=True)

    def test_minimal_fixed_gain_recovers_all_three_models(self) -> None:
        models = self.result["models"]
        self.assertEqual(models["eneuron"]["selected_gain"], 1)
        self.assertEqual(models["pulse_mini_l"]["selected_gain"], 2)
        self.assertEqual(models["pulse_mini_l2"]["selected_gain"], 1)
        for model in models.values():
            self.assertTrue(model["algorithm_gate_pass"])
            selected = model["gains"][str(model["selected_gain"])]
            self.assertEqual(selected["balanced_accuracy"], 1.0)
            self.assertEqual(selected["coverage"], 1.0)
            self.assertEqual(selected["network_weight_reads_issued"], 160)

    def test_scan_reports_mask_ties_saturation_and_stability(self) -> None:
        for model in self.result["models"].values():
            for gain in model["gains"].values():
                audit = gain["audit"]
                self.assertEqual(len(audit["masks"]), 8)
                self.assertEqual(sum(audit["mask_distribution"].values()), 8)
                for field in (
                    "boundary_tie_rate",
                    "lane_saturation_rate",
                    "final_window_stability",
                    "pre_mislead_match_rate",
                ):
                    self.assertGreaterEqual(audit[field], 0.0)
                    self.assertLessEqual(audit[field], 1.0)

    def test_gain_is_not_tuned_per_seed(self) -> None:
        self.assertEqual(self.result["seeds"], list(range(10)))
        for model in self.result["models"].values():
            self.assertIsInstance(model["selected_gain"], int)
            self.assertEqual(len(model["random_balanced_accuracy_values"]), 10)


if __name__ == "__main__":
    unittest.main()

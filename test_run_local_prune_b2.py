"""B2 结果生成器轻量合同测试。"""

from __future__ import annotations

import unittest

from local_prune_b2 import run_b2_matrix
from run_local_prune_b2 import SOURCE_FILES, decide_model


class RunLocalPruneB2Tests(unittest.TestCase):
    def test_matrix_requires_ten_distinct_seeds(self) -> None:
        with self.assertRaises(ValueError):
            run_b2_matrix(seeds=tuple(range(9)))
        with self.assertRaises(ValueError):
            run_b2_matrix(seeds=(0,) * 10)

    def test_decision_requires_accuracy_random_advantage_and_work_gate(self) -> None:
        summary = {
            "dense": {"median_balanced_accuracy": 1.0, "median_coverage": 1.0},
            "random": {"median_balanced_accuracy": 0.5, "median_coverage": 0.5},
            "S0": {"median_balanced_accuracy": 0.5, "median_coverage": 0.5},
            "S2": {"median_balanced_accuracy": 1.0, "median_coverage": 1.0},
            "S3": {"median_balanced_accuracy": 1.0, "median_coverage": 1.0},
            "gates": {
                "s2_minus_random_median_pp": 50.0,
                "s2_not_below_random_seeds": 10,
                "s2_minus_s0_median_pp": 50.0,
            },
        }
        decision = decide_model(summary, full_network_reduction=1 / 3)
        self.assertTrue(decision["algorithm_gate_pass"])
        self.assertFalse(decision["system_work_gate_pass"])
        self.assertFalse(decision["rtl_go"])
        self.assertEqual(decision["recommended_score"], "S2")

    def test_decision_rejects_coverage_drop_even_when_accuracy_passes(self) -> None:
        summary = {
            "dense": {"median_balanced_accuracy": 1.0, "median_coverage": 1.0},
            "random": {"median_balanced_accuracy": 0.5, "median_coverage": 0.5},
            "S0": {"median_balanced_accuracy": 0.5, "median_coverage": 0.5},
            "S2": {"median_balanced_accuracy": 1.0, "median_coverage": 0.5},
            "S3": {"median_balanced_accuracy": 1.0, "median_coverage": 0.5},
            "gates": {
                "s2_minus_random_median_pp": 50.0,
                "s2_not_below_random_seeds": 10,
                "s2_minus_s0_median_pp": 50.0,
            },
        }
        decision = decide_model(summary, full_network_reduction=0.5)
        self.assertFalse(decision["algorithm_gate_pass"])
        self.assertFalse(decision["rtl_go"])

    def test_source_hashes_cover_imported_b1_scoring_helpers(self) -> None:
        self.assertIn("local_prune_b1.py", SOURCE_FILES)


if __name__ == "__main__":
    unittest.main()

"""B2.1 三模型输出侧结构剪枝与通道门控合同测试。"""

from __future__ import annotations

import unittest

from local_prune_b21 import run_b21_experiment


class LocalPruneB21Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_b21_experiment(seeds=tuple(range(10)))

    def test_all_three_models_run_all_three_candidates(self) -> None:
        self.assertEqual(set(self.result["models"]), {
            "eneuron",
            "pulse_mini_l",
            "pulse_mini_l2",
        })
        for model in self.result["models"].values():
            self.assertEqual(set(model["candidates"]), {
                "output_2of4",
                "detector_3of4",
                "detector_2of4",
            })

    def test_candidates_cross_accuracy_coverage_and_work_gates(self) -> None:
        expected_reads = {
            "output_2of4": 120,
            "detector_3of4": 120,
            "detector_2of4": 80,
        }
        for model in self.result["models"].values():
            for name, candidate in model["candidates"].items():
                learned = candidate["learned"]
                self.assertEqual(learned["balanced_accuracy"], 1.0)
                self.assertEqual(learned["coverage"], 1.0)
                self.assertEqual(learned["work"]["network_weight_reads_issued"], expected_reads[name])
                self.assertEqual(learned["work"]["network_synapse_ops_issued"], expected_reads[name])
                self.assertTrue(candidate["joint_gate_pass"])
                self.assertEqual(candidate["not_below_random_seeds"], 10)

    def test_work_savings_are_disjoint_and_sum_to_dense_minus_actual(self) -> None:
        for model in self.result["models"].values():
            for candidate in model["candidates"].values():
                work = candidate["learned"]["work"]
                savings = (
                    work["hidden_reads_saved_by_structure"]
                    + work["hidden_reads_saved_by_channel"]
                    + work["output_reads_saved_by_channel"]
                    + work["output_reads_saved_by_structure"]
                )
                self.assertEqual(
                    savings,
                    work["dense_network_weight_reads"] - work["network_weight_reads_issued"],
                )

    def test_output_adaptation_uses_training_transactions_only(self) -> None:
        for model in self.result["models"].values():
            for candidate in model["candidates"].values():
                audit = candidate["learned"]["output_training_audit"]
                self.assertEqual(audit["direct_weight_writes"], 0)
                self.assertEqual(audit["threshold_writes"], 0)
                self.assertEqual(audit["observations_per_output"], 2)
                self.assertTrue(audit["pruned_output_weights_unchanged"])

    def test_kiss_selects_output_2of4_and_limits_claim(self) -> None:
        for model in self.result["models"].values():
            self.assertEqual(model["recommended_candidate"], "output_2of4")
            self.assertEqual(model["selection_claim"], "redundancy_elimination_not_score_superiority")

    def test_scan_requires_ten_distinct_seeds(self) -> None:
        with self.assertRaises(ValueError):
            run_b21_experiment(seeds=tuple(range(9)))
        with self.assertRaises(ValueError):
            run_b21_experiment(seeds=(0,) * 10)


if __name__ == "__main__":
    unittest.main()

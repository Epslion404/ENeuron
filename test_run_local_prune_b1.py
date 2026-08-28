"""B1 固定结果生成器测试。"""

from __future__ import annotations

import unittest

from run_local_prune_b1 import build_results


class RunLocalPruneB1Tests(unittest.TestCase):
    def test_builds_three_models_with_shared_random_masks_and_complete_branches(self) -> None:
        result = build_results(seed=7, eneuron_fine_tune_epochs=2, pulse_fine_tune_repetitions=1)

        self.assertEqual(
            tuple(result["models"]),
            ("eneuron", "pulse_mini_l", "pulse_mini_l2"),
        )
        expected_branches = {"dense", "random", "S0", "S1", "S2", "S3"}
        random_masks = {
            tuple(model["branches"]["random"]["masks"])
            for model in result["models"].values()
        }
        self.assertEqual(len(random_masks), 1)
        for model in result["models"].values():
            self.assertEqual(set(model["branches"]), expected_branches)
            self.assertEqual(model["branches"]["dense"]["final_metrics"]["correct"], 20)
            self.assertTrue(all(
                model["branches"][method]["final_metrics"]["correct"] == 20
                for method in ("S0", "S1", "S2", "S3")
            ))


if __name__ == "__main__":
    unittest.main()

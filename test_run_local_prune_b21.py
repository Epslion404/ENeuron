"""B2.1 机器结果与 NP4 放行决定合同测试。"""

from __future__ import annotations

import unittest

from run_local_prune_b21 import PREREQUISITE_FILES, SOURCE_FILES, build_results


class RunLocalPruneB21Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = build_results(seeds=tuple(range(10)))

    def test_result_binds_sources_and_np2_np3_artifacts(self) -> None:
        self.assertIn("local_prune_b21.py", SOURCE_FILES)
        self.assertEqual(set(self.result["source_sha256"]), set(SOURCE_FILES))
        self.assertEqual(set(self.result["prerequisite_sha256"]), set(PREREQUISITE_FILES))

    def test_all_models_are_released_only_for_np4_implementation(self) -> None:
        for decision in self.result["decisions"].values():
            self.assertTrue(decision["np2_pass"])
            self.assertTrue(decision["np3_pass"])
            self.assertTrue(decision["b21_joint_gate_pass"])
            self.assertTrue(decision["np4_implementation_go"])
            self.assertEqual(decision["recommended_candidate"], "output_2of4")
            self.assertFalse(decision["rtl_proven"])

    def test_claim_does_not_promote_redundancy_tie_to_score_superiority(self) -> None:
        self.assertFalse(self.result["claim_boundary"]["score_superiority_proven"])
        for model in self.result["models"].values():
            self.assertEqual(
                model["selection_claim"],
                "redundancy_elimination_not_score_superiority",
            )


if __name__ == "__main__":
    unittest.main()

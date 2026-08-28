"""NP3 机器结果生成器合同测试。"""

from __future__ import annotations

import unittest

from run_local_prune_np3 import SOURCE_FILES, build_results


class RunLocalPruneNp3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = build_results()

    def test_result_binds_runtime_sources(self) -> None:
        self.assertIn("local_prune_np3.py", SOURCE_FILES)
        self.assertIn("local_prune_b2.py", SOURCE_FILES)
        self.assertEqual(set(self.result["source_sha256"]), set(SOURCE_FILES))

    def test_machine_decision_selects_one_shot_for_all_models(self) -> None:
        for decision in self.result["decisions"].values():
            self.assertTrue(decision["np3_pass"])
            self.assertEqual(decision["recommended_flow"], "S2_one_shot")
            self.assertFalse(decision["rtl_go"])

    def test_wrong_sign_is_required_to_fail(self) -> None:
        for model in self.result["models"].values():
            self.assertEqual(
                model["branches"]["S2_wrong_sign"]["after_fine_tune"]["balanced_accuracy"],
                0.0,
            )


if __name__ == "__main__":
    unittest.main()

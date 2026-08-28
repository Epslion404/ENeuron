"""NP2 机器结果生成器合同测试。"""

from __future__ import annotations

import unittest

from run_local_prune_np2 import SOURCE_FILES, build_results


class RunLocalPruneNp2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = build_results(seeds=tuple(range(10)))

    def test_result_binds_all_runtime_sources(self) -> None:
        self.assertIn("local_prune_b1.py", SOURCE_FILES)
        self.assertIn("local_prune_b2.py", SOURCE_FILES)
        self.assertIn("local_prune_np2.py", SOURCE_FILES)
        self.assertEqual(set(self.result["source_sha256"]), set(SOURCE_FILES))

    def test_result_freezes_three_model_selection(self) -> None:
        self.assertEqual(self.result["models"]["eneuron"]["selected_gain"], 1)
        self.assertEqual(self.result["models"]["pulse_mini_l"]["selected_gain"], 2)
        self.assertEqual(self.result["models"]["pulse_mini_l2"]["selected_gain"], 1)
        self.assertTrue(all(
            model["algorithm_gate_pass"]
            for model in self.result["models"].values()
        ))

    def test_claim_boundary_remains_software_only(self) -> None:
        boundary = self.result["claim_boundary"]
        self.assertFalse(boundary["rtl_proven"])
        self.assertFalse(boundary["system_work_gate_proven"])
        self.assertFalse(boundary["image_pruning_proven"])


if __name__ == "__main__":
    unittest.main()

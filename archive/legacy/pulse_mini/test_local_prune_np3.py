"""NP3 一次/渐进剪枝、错误符号与 TRAIN 账本合同测试。"""

from __future__ import annotations

import unittest

from local_prune_np3 import run_np3_experiment


class LocalPruneNp3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_np3_experiment()

    def test_all_three_models_use_np2_frozen_gains(self) -> None:
        self.assertEqual(set(self.result["models"]), {
            "eneuron",
            "pulse_mini_l",
            "pulse_mini_l2",
        })
        self.assertEqual(self.result["models"]["eneuron"]["evidence_gain"], 1)
        self.assertEqual(self.result["models"]["pulse_mini_l"]["evidence_gain"], 2)
        self.assertEqual(self.result["models"]["pulse_mini_l2"]["evidence_gain"], 1)

    def test_one_shot_and_progressive_share_parent_budget_and_result(self) -> None:
        for model in self.result["models"].values():
            one_shot = model["branches"]["S2_one_shot"]
            progressive = model["branches"]["S2_progressive"]
            self.assertEqual(one_shot["parent_checkpoint_sha256"], progressive["parent_checkpoint_sha256"])
            self.assertEqual(one_shot["fine_tune_observations_per_detector"], 2)
            self.assertEqual(progressive["fine_tune_observations_per_detector"], 2)
            self.assertEqual(one_shot["after_fine_tune"]["balanced_accuracy"], 1.0)
            self.assertEqual(progressive["after_fine_tune"]["balanced_accuracy"], 1.0)
            self.assertEqual(one_shot["final_masks"], progressive["final_masks"])
            for top3, final_mask in zip(progressive["stage1_masks"], progressive["final_masks"]):
                self.assertEqual(top3.bit_count(), 3)
                self.assertEqual(final_mask.bit_count(), 2)
                self.assertEqual(final_mask & top3, final_mask)

    def test_wrong_sign_changes_real_training_and_collapses_task(self) -> None:
        for model in self.result["models"].values():
            branch = model["branches"]["S2_wrong_sign"]
            self.assertEqual(branch["after_fine_tune"]["balanced_accuracy"], 0.0)
            self.assertEqual(branch["after_fine_tune"]["coverage"], 0.0)
            for entry in branch["training_ledger"]:
                self.assertEqual(entry["expected_modulator"], 1)
                self.assertEqual(entry["applied_modulator"], -1)

    def test_training_ledger_proves_structure_and_pruned_weights_are_frozen(self) -> None:
        for model in self.result["models"].values():
            for branch in model["branches"].values():
                self.assertEqual(branch["mask_write_count"], 0)
                self.assertEqual(branch["prune_commit_counts"], [1] * 8)
                self.assertTrue(branch["mask_stable_during_fine_tune"])
                self.assertTrue(branch["pruned_weights_unchanged"])
                self.assertTrue(branch["pruned_history_zero"])
                self.assertTrue(branch["infer_freeze_pass"])

    def test_progressive_stage_is_software_training_mask_not_second_commit(self) -> None:
        for model in self.result["models"].values():
            branch = model["branches"]["S2_progressive"]
            self.assertEqual(branch["stage1_kind"], "software_3of4_training_mask")
            self.assertEqual(branch["prune_commit_counts"], [1] * 8)


if __name__ == "__main__":
    unittest.main()

"""B1 公平实验的公共合同测试。"""

from __future__ import annotations

import unittest

from local_prune_b1 import (
    B1Variant,
    exact_two_random_masks,
    run_eneuron_b1,
    run_pulse_b1,
    score_binary_outputs,
    strict_single_active,
)
from pulse_mini_l2_reference import PulseMiniL2Reference
from pulse_mini_reference import PulseMiniReference


class LocalPruneB1ContractTests(unittest.TestCase):
    def test_strict_decoder_abstains_on_zero_or_multi_active_outputs(self) -> None:
        self.assertIsNone(strict_single_active((0, 0)))
        self.assertIsNone(strict_single_active((1, 1)))
        self.assertIsNone(strict_single_active((3, 1)))
        self.assertEqual(strict_single_active((2, 0)), 0)
        self.assertEqual(strict_single_active((0, 4)), 1)

    def test_binary_metrics_count_abstention_as_incorrect(self) -> None:
        metrics = score_binary_outputs(
            labels=(0, 0, 1, 1),
            scores=((2, 0), (1, 1), (0, 3), (0, 0)),
        )
        self.assertEqual(metrics.correct, 2)
        self.assertEqual(metrics.covered, 2)
        self.assertEqual(metrics.total, 4)
        self.assertEqual(metrics.accuracy, 0.5)
        self.assertEqual(metrics.coverage, 0.5)
        self.assertEqual(metrics.balanced_accuracy, 0.5)

    def test_random_control_is_deterministic_exact_two_and_neuron_local(self) -> None:
        first = exact_two_random_masks(seed=17, count=8)
        second = exact_two_random_masks(seed=17, count=8)
        different = exact_two_random_masks(seed=18, count=8)
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertTrue(all(mask.bit_count() == 2 for mask in first))
        self.assertGreater(len(set(first)), 1)

    def test_variant_names_cover_dense_random_and_all_scores(self) -> None:
        self.assertEqual(
            tuple(variant.value for variant in B1Variant),
            ("dense", "random", "S0", "S1", "S2", "S3"),
        )

    def test_pulse_b1_uses_one_parent_checkpoint_and_freezes_infer(self) -> None:
        for model_id, core_type in (
            ("pulse_mini_l", PulseMiniReference),
            ("pulse_mini_l2", PulseMiniL2Reference),
        ):
            result = run_pulse_b1(model_id=model_id, core_type=core_type, seed=7)
            parent_hashes = {
                branch["parent_checkpoint_sha256"]
                for branch in result["branches"].values()
            }
            self.assertEqual(len(parent_hashes), 1)
            self.assertTrue(all(
                branch["inference_learning_state_frozen"]
                for branch in result["branches"].values()
            ))
            self.assertEqual(result["branches"]["dense"]["masks"], [15, 15])
            self.assertTrue(all(
                mask.bit_count() == 2
                for name, branch in result["branches"].items()
                if name != "dense"
                for mask in branch["masks"]
            ))
            self.assertTrue(all(
                branch["work_by_stage"]["total"]["scope"]
                == "full_4x2x2_hidden_structural_output_dense"
                for branch in result["branches"].values()
            ))
            self.assertEqual(
                result["branches"]["dense"]["work_by_stage"]["total"]
                ["hidden_reads_saved_by_structure"],
                0,
            )

    def test_eneuron_b1_uses_one_parent_checkpoint_and_exact_two_masks(self) -> None:
        result = run_eneuron_b1(seed=7, warmup_epochs=30, fine_tune_epochs=2)
        parent_hashes = {
            branch["parent_checkpoint_sha256"]
            for branch in result["branches"].values()
        }
        self.assertEqual(len(parent_hashes), 1)
        self.assertTrue(all(
            branch["inference_learning_state_frozen"]
            for branch in result["branches"].values()
        ))
        self.assertEqual(result["branches"]["dense"]["masks"], [15, 15])
        self.assertTrue(all(
            mask.bit_count() == 2
            for name, branch in result["branches"].items()
            if name != "dense"
            for mask in branch["masks"]
        ))


if __name__ == "__main__":
    unittest.main()

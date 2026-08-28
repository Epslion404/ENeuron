"""B2 冗余 detector 压力任务合同。"""

from __future__ import annotations

import unittest

from local_prune_b2 import (
    build_b2_dataset,
    build_eneuron_b2_checkpoint,
    build_pulse_b2_checkpoint,
    run_b2_seed,
)
from pulse_mini_l2_reference import PulseMiniL2Reference
from pulse_mini_reference import PulseMiniReference


class LocalPruneB2Tests(unittest.TestCase):
    def test_dataset_is_balanced_and_uses_complementary_channel_pairs(self) -> None:
        samples = build_b2_dataset()
        self.assertEqual(len(samples), 20)
        self.assertEqual(sum(sample.label == 0 for sample in samples), 10)
        self.assertEqual(sum(sample.label == 1 for sample in samples), 10)
        self.assertEqual(
            {sample.input_mask for sample in samples if sample.label == 0},
            {0b0001, 0b0100},
        )
        self.assertEqual(
            {sample.input_mask for sample in samples if sample.label == 1},
            {0b0010, 0b1000},
        )

    def test_checkpoints_saturate_weights_but_preserve_model_specific_evidence(self) -> None:
        eneuron = build_eneuron_b2_checkpoint()
        pulse_l = build_pulse_b2_checkpoint(PulseMiniReference)
        pulse_l2 = build_pulse_b2_checkpoint(PulseMiniL2Reference)

        for checkpoint in (eneuron, pulse_l, pulse_l2):
            self.assertTrue(all(tuple(abs(value) for value in core.weights) == (7, 7, 7, 7)
                                for core in checkpoint.cores))
            self.assertEqual(len(checkpoint.ledgers), 8)
        self.assertEqual(max(max(entry.evidence_levels) for entry in pulse_l.ledgers[0]), 1)
        self.assertEqual(max(max(entry.evidence_levels) for entry in pulse_l2.ledgers[0]), 2)
        self.assertEqual(max(max(entry.evidence_levels) for entry in eneuron.ledgers[0]), 3)

    def test_one_seed_separates_accumulated_evidence_from_last_snapshot(self) -> None:
        result = run_b2_seed(seed=0)

        for model_id in ("eneuron", "pulse_mini_l2"):
            model = result[model_id]
            self.assertEqual(model["S2"]["correct"], 20)
            self.assertEqual(model["S3"]["correct"], 20)
            self.assertEqual(model["S1"]["correct"], 0)
            self.assertLess(
                model["S2"]["work"]["network_weight_reads_issued"],
                model["dense"]["work"]["network_weight_reads_issued"],
            )
        self.assertEqual(result["pulse_mini_l"]["S2"]["correct"], 0)
        self.assertEqual(result["pulse_mini_l"]["S3"]["correct"], 0)

    def test_random_masks_are_shared_across_three_models(self) -> None:
        result = run_b2_seed(seed=4)
        masks = {
            tuple(model["random"]["masks"])
            for model in result.values()
        }
        self.assertEqual(len(masks), 1)
        self.assertTrue(all(mask.bit_count() == 2 for mask in next(iter(masks))))


if __name__ == "__main__":
    unittest.main()

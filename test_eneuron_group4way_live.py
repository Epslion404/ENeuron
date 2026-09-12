"""B3-09：ENeuron S2 组级 live mask 必须由证据决策，不能重放静态 mixed。"""

from __future__ import annotations

import unittest

from b3_fixed_vector_manifest import (
    load_b3_manifest,
    mode_mask_words,
    model_words_from_manifest,
    sample_inputs_from_manifest,
)
from eneuron_group4way_live import decide_group4way_live
from npu_eneuron_protocol import decode_mask_words
from npu_eneuron_reference import NpuReference
from npu_eneuron_protocol import load_model_words


class ENeuronGroup4WayLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_b3_manifest()
        cls.model_words = model_words_from_manifest(cls.manifest)
        cls.pixels = sample_inputs_from_manifest(cls.manifest["samples"][0])
        cls.decision = decide_group4way_live(cls.model_words, cls.pixels)

    def test_decision_keeps_exactly_two_groups_in_each_meta(self) -> None:
        self.assertEqual(self.decision.active_groups, 296)
        self.assertEqual(self.decision.skipped_groups, 296)
        self.assertEqual(self.decision.mask_granularity, "group_4way")
        self.assertFalse(self.decision.strict_2of4_candidate)
        self.assertEqual(self.decision.score_method, "S2")
        self.assertEqual(self.decision.gain, 1)
        self.assertEqual(len(self.decision.commits), 148)
        for commit in self.decision.commits:
            self.assertEqual(bin(commit.mask).count("1"), 2)
            self.assertEqual(len(commit.evidence_levels), 4)
            self.assertEqual(len(commit.selected), 2)

    def test_live_mask_is_not_the_frozen_static_mixed_replay(self) -> None:
        static_words = mode_mask_words(self.manifest["samples"][0]["modes"]["b3_static_mixed"])
        self.assertNotEqual(self.decision.mask_words, static_words)

    def test_same_input_and_model_are_deterministic(self) -> None:
        second = decide_group4way_live(self.model_words, self.pixels)
        self.assertEqual(second.mask_words, self.decision.mask_words)
        self.assertEqual(second.logits, self.decision.logits)
        self.assertEqual(
            [commit.selected for commit in second.commits],
            [commit.selected for commit in self.decision.commits],
        )

    def test_npu_reference_matches_decision_logits_and_group_counts(self) -> None:
        model = NpuReference()
        load_model_words(model, self.model_words)
        decoded = decode_mask_words(self.decision.mask_words)
        result = model.infer(
            self.pixels,
            mode="gated",
            group_mask0=decoded.mask0,
            group_mask1=decoded.mask1,
        )
        self.assertEqual(result.logits, self.decision.logits)
        self.assertEqual(result.group_reads, self.decision.active_groups)
        self.assertEqual(result.prediction, self.decision.prediction_class)

    def test_manifest_live_mode_matches_oracle(self) -> None:
        mode = self.manifest["samples"][0]["modes"]["b3_live_eneuron"]
        self.assertEqual(mode["decision_source"], "live_eneuron_s2")
        self.assertEqual(tuple(int(str(word), 0) for word in mode["mask_words_data"]), self.decision.mask_words)
        self.assertEqual(tuple(mode["expected_logits"]), self.decision.logits)
        self.assertFalse(mode["strict_2of4_candidate"])

    def test_ledger_records_evidence_gain_epoch_and_sample(self) -> None:
        self.assertEqual(self.decision.mask_epoch, 1)
        self.assertEqual(self.decision.sample_id, 0x12345678)
        self.assertEqual(self.decision.commits[0].gain, 1)
        self.assertTrue(all(0 <= level <= 3 for commit in self.decision.commits for level in commit.evidence_levels))


if __name__ == "__main__":
    unittest.main()

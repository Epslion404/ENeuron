"""B3 manifest 与 Python 参考模型共享读取合同。"""

from __future__ import annotations

import unittest

from b3_fixed_vector_manifest import (
    load_b3_manifest,
    mode_mask_words,
    model_words_from_manifest,
    reference_from_manifest,
    sample_inputs_from_manifest,
)
from npu_eneuron_protocol import decode_mask_words


class B3FixedVectorManifestLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_b3_manifest()
        cls.sample = cls.manifest["samples"][0]

    def test_reconstructs_model_and_input_from_shared_manifest(self) -> None:
        self.assertEqual(len(model_words_from_manifest(self.manifest)), 634)
        self.assertEqual(sample_inputs_from_manifest(self.sample), (1, 2, 3, 4, 5, 6, 7, 8) * 8)

    def test_reference_matches_dense_and_static_board_outputs(self) -> None:
        model = reference_from_manifest(self.manifest)
        dense = self.sample["modes"]["b3_dense"]
        static = self.sample["modes"]["b3_static_mixed"]
        image = sample_inputs_from_manifest(self.sample)
        dense_result = model.infer(image, mode="bypass")
        self.assertEqual(list(dense_result.logits), dense["expected_logits"])
        self.assertEqual(dense_result.prediction, dense["prediction_class"])
        mask = decode_mask_words(mode_mask_words(static))
        static_result = model.infer(image, mode="gated", group_mask0=mask.mask0, group_mask1=mask.mask1)
        self.assertEqual(list(static_result.logits), static["expected_logits"])
        self.assertEqual(static_result.prediction, static["prediction_class"])
        self.assertEqual(static_result.group_reads, static["active_groups"])


if __name__ == "__main__":
    unittest.main()

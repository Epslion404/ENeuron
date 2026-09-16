"""QAT 可证明无损动态跳过基线的结果合同。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ARTIFACT = ROOT / "artifacts" / "results" / "b3_qat_lossless_skip_diagnostic.json"


class B3QatLosslessSkipContractTests(unittest.TestCase):
    def setUp(self) -> None:
        if not ARTIFACT.is_file():
            self.skipTest("lossless skip diagnostic not generated")
        self.report = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    def test_identity_and_lossless_output(self) -> None:
        self.assertEqual(self.report["schema"], "eneuron_b3_qat_lossless_skip_diagnostic_v2")
        self.assertEqual(self.report["samples"], 397)
        self.assertEqual(self.report["output"]["prediction_agreement"], 1.0)
        self.assertEqual(self.report["output"]["logit_exact_match"], 1.0)
        self.assertEqual(self.report["output"]["max_abs_logit_error"], 0)

    def test_candidate_is_not_strict_2of4_and_has_nonzero_skip(self) -> None:
        sparsity = self.report["sparsity"]
        self.assertFalse(sparsity["strict_2of4"])
        self.assertGreater(sparsity["skip_rate"], 0.35)
        self.assertLess(sparsity["estimated_npu_cycles_mean"], 1900)
        self.assertGreater(sparsity["estimated_core_speedup"], 1.30)
        self.assertGreater(sparsity["breakdown"]["zero_activation"]["count"], 0)
        self.assertGreater(sparsity["breakdown"]["zero_weight"]["count"], 0)


if __name__ == "__main__":
    unittest.main()

"""公共剪枝控制器机器摘要的新鲜度和声明边界测试。"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from verify_local_prune_rtl import RESULT_PATH, ROOT, SOURCE_FILES


class VerifyLocalPruneRtlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))

    def test_source_hashes_are_current(self) -> None:
        self.assertEqual(set(self.result["source_sha256"]), set(SOURCE_FILES))
        for name in SOURCE_FILES:
            actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            self.assertEqual(self.result["source_sha256"][name], actual, name)

    def test_np4_np5_common_controller_gates(self) -> None:
        self.assertEqual(
            self.result["status"],
            "COMMON_CONTROLLER_NP4_NP5_PASS_INTEGRATION_PENDING",
        )
        self.assertEqual(self.result["fixed_evidence_gains"], {
            "eneuron": 1,
            "pulse_mini_l": 2,
            "pulse_mini_l2": 1,
        })
        self.assertEqual(self.result["cosim"]["transactions_total"], 60000)
        self.assertEqual(self.result["formal"]["depth"], 32)
        self.assertTrue(self.result["formal"]["successful_commit_reachable"])

    def test_unproven_integration_is_not_promoted(self) -> None:
        scope = self.result["hardware_scope"]
        self.assertFalse(scope["eneuron_snapshot_export_integrated"])
        self.assertFalse(scope["pulse_feedback_wrapper_integrated"])
        self.assertFalse(scope["existing_4x2x2_output_2of4_integrated"])
        self.assertFalse(scope["shared_lane_skip_cycles_proven"])
        self.assertFalse(scope["vivado_resource_timing_proven"])


if __name__ == "__main__":
    unittest.main()

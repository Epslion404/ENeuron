"""公共剪枝控制器机器摘要的新鲜度和声明边界测试。"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from verify_local_prune_rtl import (
    EVIDENCE_INPUTS,
    RESULT_PATH,
    ROOT,
    SOURCE_FILES,
    SOURCE_HASH_POLICY,
    canonical_sha256,
    canonical_sha256_bytes,
)


class VerifyLocalPruneRtlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))

    def test_source_hashes_are_current(self) -> None:
        self.assertEqual(set(self.result["source_sha256"]), set(SOURCE_FILES))
        for name in SOURCE_FILES:
            self.assertEqual(self.result["source_sha256"][name],
                             canonical_sha256(ROOT / name), name)

    def test_binding_is_independent_of_line_endings(self) -> None:
        """The same text must hash identically in an LF and in a CRLF working tree."""

        for name in SOURCE_FILES:
            with self.subTest(name=name):
                lf = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
                crlf = lf.replace(b"\n", b"\r\n")
                self.assertEqual(canonical_sha256_bytes(lf), canonical_sha256_bytes(crlf))
                self.assertEqual(canonical_sha256_bytes(lf), self.result["source_sha256"][name])
                if b"\n" in lf:
                    self.assertNotEqual(
                        hashlib.sha256(lf).hexdigest(),
                        hashlib.sha256(crlf).hexdigest(),
                        "the naive raw digest must stay EOL sensitive, otherwise this test is vacuous",
                    )

    def test_hash_policy_is_declared(self) -> None:
        self.assertEqual(self.result["schema"], "eneuron.local_prune_rtl.v2")
        self.assertIn("normalised to LF", self.result["source_hash_policy"])
        self.assertEqual(SOURCE_HASH_POLICY, self.result["source_hash_policy"])
        self.assertIn(".gitattributes", self.result["eol_policy"])

    def test_moved_sources_cannot_silently_rebind_evidence(self) -> None:
        moved = self.result["source_changes_since_previous_signature"]
        previous = self.result["previous_signature"]
        current = self.result["source_sha256"]
        self.assertEqual(set(previous), set(SOURCE_FILES))
        for name in SOURCE_FILES:
            self.assertEqual(previous[name] != current[name], name in moved, name)
        for block, entry in self.result["provenance"].items():
            with self.subTest(block=block):
                declared = [name for name in EVIDENCE_INPUTS[block] if name in moved]
                self.assertEqual(entry["inputs_moved_since_previous_signature"], declared)
                self.assertEqual(entry["inputs_unchanged_since_previous_signature"], not declared)
                if declared and not entry["reverified_in_this_run"]:
                    self.assertTrue(entry.get("reason"), "a moved block must state why it was not re-run")
                    self.assertTrue(entry.get("reverify_command"), "and how to re-run it")
                if entry["reverified_in_this_run"]:
                    self.assertNotIn("reason", entry)

    def test_formal_block_may_only_be_inherited_while_its_inputs_are_identical(self) -> None:
        entry = self.result["provenance"]["formal"]
        previous = self.result["previous_signature"]
        current = self.result["source_sha256"]
        changed = [name for name in EVIDENCE_INPUTS["formal"] if previous[name] != current[name]]
        self.assertEqual(entry["inputs_unchanged_since_previous_signature"], not changed)
        self.assertEqual(entry["inputs_moved_since_previous_signature"], changed)
        if not entry["reverified_in_this_run"] and not changed:
            self.assertTrue(all(current[name] == previous[name]
                                for name in EVIDENCE_INPUTS["formal"]))

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

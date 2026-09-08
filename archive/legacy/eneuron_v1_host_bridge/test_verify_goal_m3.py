"""一键 Goal 审计必须包含原始 Goal M3 的独立签核。"""

from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import verify_goal
from m3_acceptance import M3AcceptanceSummary


SUMMARY = M3AcceptanceSummary(
    command_count=957,
    training_start=64,
    command_sha256="1" * 64,
    ledger_sha256="2" * 64,
    ledger_chain_tail="3" * 64,
    mod_commit_count=4,
    weight_write_count=0,
    noisy_correct=20,
    noisy_total=20,
    final_weights=((-6, -7, 7, 7), (7, 7, -6, -7), (7, -7), (-7, 7)),
)


class VerifyGoalM3Tests(unittest.TestCase):
    def test_verify_m3_writes_machine_readable_signoff(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="eneuron_m3_signoff_")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)

        with mock.patch.object(verify_goal, "ROOT", root), mock.patch.object(
            verify_goal,
            "run_m3_acceptance",
            return_value=SUMMARY,
        ):
            actual = verify_goal.verify_m3()

        self.assertEqual(actual, SUMMARY)
        values = verify_goal.read_key_values(root / "m3_signoff_summary.txt")
        self.assertEqual(values["RESULT"], "PASS")
        self.assertEqual(values["SCHEMA"], "M3_RTL_CLOSURE_V1")
        self.assertEqual(values["COMMAND_COUNT"], "957")
        self.assertEqual(values["TRAINING_WEIGHT_WRITE_COUNT"], "0")
        self.assertEqual(values["MOD_COMMIT_COUNT"], "4")
        self.assertEqual(values["NOISY_ACCURACY"], "20/20")

    def test_main_runs_m3_gate_before_report_signoff(self) -> None:
        calls: list[str] = []

        def mark(name: str):
            return lambda: calls.append(name)

        with mock.patch.object(
            verify_goal,
            "parse_args",
            return_value=argparse.Namespace(rerun_vivado=False),
        ), mock.patch.object(
            verify_goal, "verify_software", side_effect=mark("software")
        ), mock.patch.object(
            verify_goal, "verify_m3", side_effect=mark("m3")
        ), mock.patch.object(
            verify_goal, "verify_reports", side_effect=mark("reports")
        ), mock.patch.object(
            verify_goal, "write_t0_signoff_summary", side_effect=mark("t0")
        ):
            self.assertEqual(verify_goal.main(), 0)

        self.assertEqual(calls, ["software", "m3", "reports", "t0"])


if __name__ == "__main__":
    unittest.main()

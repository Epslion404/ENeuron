"""M3 独立验收器的冻结向量与反例测试。"""

from __future__ import annotations

import unittest
from dataclasses import replace

from m3_acceptance import verify_m3_report
from m3_task import M3CommandPlan, run_rtl_m3
from m3_training_ledger import OpcodeStatistics


class M3AcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = M3CommandPlan.build()
        cls.report = run_rtl_m3(cls.plan)

    def test_accepts_frozen_real_rtl_run_and_hashes(self) -> None:
        summary = verify_m3_report(self.plan, self.report)

        self.assertEqual(summary.command_count, 957)
        self.assertEqual(summary.training_start, 64)
        self.assertEqual(
            summary.command_sha256,
            "191d7c588411515f4386685b6dfcd8ce7e3894a21f87ff3a54a40de2f9989c09",
        )
        self.assertEqual(
            summary.ledger_sha256,
            "cb63bcc596843607cdb7c774a91a8ffd38d9b21ee304cd266ecd33e2974a5256",
        )
        self.assertEqual(summary.mod_commit_count, 4)
        self.assertEqual(summary.weight_write_count, 0)

    def test_rejects_changed_eligibility_snapshot(self) -> None:
        first = self.report.commit_evidence[0]
        changed_h0 = (first.eligibility_snapshots[0][0] + 1,) + first.eligibility_snapshots[0][1:]
        changed = replace(
            first,
            eligibility_snapshots=(changed_h0,) + first.eligibility_snapshots[1:],
        )
        report = replace(
            self.report,
            commit_evidence=(changed,) + self.report.commit_evidence[1:],
        )

        with self.assertRaisesRegex(AssertionError, "eligibility|快照"):
            verify_m3_report(self.plan, report)

    def test_rejects_training_weight_write_or_task_drift(self) -> None:
        changed_ledger = replace(
            self.report.ledger,
            weight_write=OpcodeStatistics(seen=1, successful=0),
        )
        with self.assertRaisesRegex(AssertionError, "WEIGHT_WRITE"):
            verify_m3_report(
                self.plan,
                replace(self.report, ledger=changed_ledger),
            )

        with self.assertRaisesRegex(AssertionError, "clean|任务"):
            verify_m3_report(
                self.plan,
                replace(self.report, clean_predictions=(0, 0)),
            )


if __name__ == "__main__":
    unittest.main()

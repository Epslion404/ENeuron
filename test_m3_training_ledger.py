"""M3 训练命令账本的行为回归。"""

from __future__ import annotations

import unittest

from host_bridge_oracle import Flit, Opcode, Status
from m3_training_ledger import audit_training_ledger


class TrainingLedgerTests(unittest.TestCase):
    def test_safe_ledger_reports_canonical_hashes_and_opcode_statistics(self) -> None:
        flits = (
            Flit(int(Opcode.WEIGHT_WRITE), int(Status.OK), 1, 0, 0, 0x10, 0),
            Flit(int(Opcode.WEIGHT_WRITE), int(Status.ADDRESS), 2, 0, 0, 0x20, 0),
            Flit(int(Opcode.EP_START), int(Status.OK), 3, 7, 0, 0, 0),
            Flit(int(Opcode.MOD_COMMIT), int(Status.OK), 4, 7, 0, 9, 1),
            Flit(int(Opcode.MOD_COMMIT), int(Status.COMMIT_ID), 5, 7, 0, 10, 0),
        )

        report = audit_training_ledger(flits, training_start=2)

        self.assertEqual(
            report.canonical_sha256,
            "3a10cb19a538b289d07ee4f8d9cc1502920fcba1fd021dfe55a631e166fbcbee",
        )
        self.assertEqual(
            report.hash_chain,
            (
                "08c4d28bb2e80b34d0e419ffd7ce8647c31438818fae6a096fb6baa94ba2baad",
                "be11034cb34f73d2f658fb6ec0479ef3607f5b82b0d80c69c1b045365788caa5",
                "c7596f8368ae827ede1034b8cc07b05c6dfacd2b570978caf403f9c21716244b",
                "802ba8526e92c69d4d3ed42dc458c847f95a876ff50185acc0bf4d83c6f6404c",
                "640a812c202e30d9a7d15f0639efeeca9758c1f31ad722afe914b51b9f05fe9f",
            ),
        )
        self.assertEqual(report.weight_write.seen, 2)
        self.assertEqual(report.weight_write.successful, 1)
        self.assertEqual(report.mod_commit.seen, 2)
        self.assertEqual(report.mod_commit.successful, 1)

    def test_weight_write_at_or_after_training_start_fails_even_when_rejected(self) -> None:
        flits = (
            Flit(int(Opcode.WEIGHT_WRITE), int(Status.OK), 1, 0, 0, 0x10, 0),
            Flit(int(Opcode.WEIGHT_WRITE), int(Status.BAD_STATE), 2, 0, 0, 0x20, 0),
        )

        with self.assertRaisesRegex(
            ValueError,
            r"training_start 后禁止 WEIGHT_WRITE: index=1 status=2",
        ):
            audit_training_ledger(flits, training_start=1)


if __name__ == "__main__":
    unittest.main()

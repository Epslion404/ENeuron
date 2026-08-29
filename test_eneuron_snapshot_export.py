"""ENeuron committed eligibility snapshot 公开接口合同。"""

from __future__ import annotations

import unittest

from eneuron_snapshot_export_cosim import run_snapshot_export_contract


class ENeuronSnapshotExportTests(unittest.TestCase):
    def test_committed_snapshot_export_is_atomic_and_preserved_by_state_clear(self) -> None:
        run_snapshot_export_contract()


if __name__ == "__main__":
    unittest.main()

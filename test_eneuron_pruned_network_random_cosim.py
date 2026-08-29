"""NP4B4 ENeuron 4→8→2 长事务 Python/RTL 协同仿真。"""

from __future__ import annotations

import unittest

from eneuron_pruned_network_random_cosim import run_matrix


class ENeuronPrunedNetworkRandomCosimTests(unittest.TestCase):
    def test_minimal_random_oracle_tracer(self) -> None:
        summary = run_matrix(seeds=(23,), transaction_count=64)
        self.assertEqual(summary["transactions"], 64)
        self.assertEqual(summary["pruned_weight_changes"], 0)
        self.assertEqual(summary["pruned_utility_changes"], 0)

    def test_twenty_seeds_by_one_thousand_transactions(self) -> None:
        summary = run_matrix(seeds=tuple(range(101, 121)), transaction_count=1000)
        self.assertEqual(summary["transactions"], 20_000)
        self.assertEqual(summary["pruned_snapshot_zeroing_transitions"], 277)
        self.assertEqual(summary["pruned_weight_changes"], 0)
        self.assertEqual(summary["pruned_utility_changes"], 0)


if __name__ == "__main__":
    unittest.main()

"""ENeuron NP4B4 正式摘要的快速合同测试。"""

from __future__ import annotations

import unittest

from run_eneuron_pruned_network_signoff import SEEDS, build_summary
from verify_eneuron_pruned_network_summary import verify_summary


class ENeuronPrunedNetworkSignoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = {
            "seeds": 20,
            "transactions_per_seed": 1000,
            "transactions": 20_000,
            "pruned_snapshot_zeroing_transitions": 277,
            "pruned_weight_changes": 0,
            "pruned_utility_changes": 0,
        }

    def test_fixed_summary_is_accepted(self) -> None:
        summary = build_summary(self.raw)
        self.assertEqual(summary["seed_values"], list(SEEDS))
        verify_summary(summary)

    def test_wrong_seed_set_is_rejected(self) -> None:
        summary = build_summary(self.raw)
        summary["seed_values"] = list(range(100, 120))
        with self.assertRaisesRegex(AssertionError, "seed_values"):
            verify_summary(summary)


if __name__ == "__main__":
    unittest.main()

import unittest

from pulse_mini_pruned_network_random_cosim import run_matrix, run_seed


class PulseMiniPrunedNetworkRandomCosimTests(unittest.TestCase):
    def test_l_tracer_1_seed_64_transactions(self) -> None:
        run_seed(0, 64, l2=False)

    def test_l2_tracer_1_seed_64_transactions(self) -> None:
        run_seed(0, 64, l2=True)

    def test_l_twenty_seeds_by_one_thousand_transactions(self) -> None:
        summary = run_matrix(seeds=tuple(range(201, 221)), transaction_count=1000, l2=False)
        self.assertEqual(summary["status"], "PULSE_L_NP4B4_PASS")
        self.assertEqual(summary["transactions"], 20_000)
        self.assertEqual(summary["commits"], 20)
        self.assertEqual(summary["pruned_weight_changes"], 0)
        self.assertEqual(summary["pruned_evidence_changes"], 0)
        self.assertEqual(summary["pruned_utility_changes"], 0)

    def test_l2_twenty_seeds_by_one_thousand_transactions(self) -> None:
        summary = run_matrix(seeds=tuple(range(301, 321)), transaction_count=1000, l2=True)
        self.assertEqual(summary["status"], "PULSE_L2_NP4B4_PASS")
        self.assertEqual(summary["transactions"], 20_000)
        self.assertEqual(summary["commits"], 20)
        self.assertEqual(summary["pruned_weight_changes"], 0)
        self.assertEqual(summary["pruned_evidence_changes"], 0)
        self.assertEqual(summary["pruned_utility_changes"], 0)


if __name__ == "__main__":
    unittest.main()

import unittest

from pulse_mini_network import run_p8


class PulseMiniNetworkTests(unittest.TestCase):
    def test_p8_network_closure(self) -> None:
        result = run_p8()
        self.assertEqual(result["baseline"], {"positive": 0, "negative": 0})
        self.assertTrue(all(value == 1 for value in result["positive_outputs"]))
        self.assertTrue(all(value == 2 for value in result["negative_outputs"]))
        self.assertTrue(result["weights_frozen"])
        self.assertTrue(result["hidden_to_output_one_tick"])
        self.assertTrue(result["route_delay_observed"])
        self.assertEqual(result["direct_weight_write_count"], 0)
        self.assertEqual(result["no_feedback_outputs"], [0, 0])


if __name__ == "__main__":
    unittest.main()

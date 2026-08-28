import unittest

from pulse_mini_l2_reference import PulseMiniL2Reference
from pulse_mini_network import PulseMiniNetwork, run_p8
from pulse_mini_reference import PulseMiniReference


class PulseMiniNetworkTests(unittest.TestCase):
    def test_constructor_injects_core_type_and_preserves_l_default(self) -> None:
        default_network = PulseMiniNetwork()
        l2_network = PulseMiniNetwork(core_type=PulseMiniL2Reference)

        self.assertTrue(all(type(core) is PulseMiniReference for core in default_network.cores))
        self.assertTrue(all(type(core) is PulseMiniL2Reference for core in l2_network.cores))

    def test_l2_p8_network_closure_preserves_one_tick_route(self) -> None:
        result = run_p8(core_type=PulseMiniL2Reference)

        self.assertEqual(result["baseline"], {"positive": 0, "negative": 0})
        self.assertTrue(all(value == 1 for value in result["positive_outputs"]))
        self.assertTrue(all(value == 2 for value in result["negative_outputs"]))
        self.assertEqual(
            result["trained_weights"],
            ((6, 0, 0, 0), (0, 6, 0, 0), (6, 0, 0, 0), (0, 6, 0, 0)),
        )
        self.assertTrue(result["weights_frozen"])
        self.assertTrue(result["hidden_to_output_one_tick"])
        self.assertTrue(result["route_delay_observed"])
        self.assertEqual(result["direct_weight_write_count"], 0)
        self.assertEqual(result["no_feedback_outputs"], [0, 0])

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

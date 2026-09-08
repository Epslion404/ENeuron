import unittest

from pulse_mini_task import run_p5


class PulseMiniTaskTests(unittest.TestCase):
    def test_training_gate_and_negative_controls(self) -> None:
        result = run_p5()
        self.assertEqual(result["before"], {"correct": 10, "total": 20})
        self.assertEqual(result["after"], {"correct": 20, "total": 20})
        self.assertLess(result["no_feedback"]["correct"], 19)
        self.assertLess(result["reversed_feedback"]["correct"], 19)
        self.assertLess(result["label_shuffled"]["correct"], 19)
        self.assertEqual(result["train_weight_write_count"], 0)
        self.assertEqual(result["final_weights"], [6, -6, 0, 0])


if __name__ == "__main__":
    unittest.main()

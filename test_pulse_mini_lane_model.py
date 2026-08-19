import unittest

from pulse_mini_lane_model import compare


class PulseMiniLaneModelTests(unittest.TestCase):
    def test_full_parallel_is_one_cycle_per_tick(self):
        point = compare(128, 128)
        self.assertEqual(point.cycles_per_tick, 1)
        self.assertEqual(point.feedback_cycles_per_all_core_update, 1)

    def test_single_lane_scales_linearly(self):
        point = compare(128, 1)
        self.assertEqual(point.cycles_per_tick, 128)
        self.assertEqual(point.feedback_cycles_per_all_core_update, 128)

    def test_partial_lane_rounds_up(self):
        self.assertEqual(compare(128, 3).cycles_per_tick, 43)


if __name__ == "__main__":
    unittest.main()

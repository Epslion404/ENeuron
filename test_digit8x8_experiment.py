import unittest
from pathlib import Path

from digit8x8_experiment import run_d1, run_nearest_centroid
from digit8x8 import load_fixture, load_manifest


ROOT = Path(__file__).resolve().parent


class Digit8x8ExperimentTests(unittest.TestCase):
    def test_rank_latency_baseline_is_materially_above_chance(self):
        result = run_d1(ROOT / "digit8x8_fixture.json", ROOT / "digit8x8_manifest.json")
        test = result["models"]["nearest_centroid_latency"]["test"]
        self.assertGreaterEqual(test["balanced_accuracy"], 0.60)
        self.assertGreaterEqual(test["coverage"], 0.80)

    def test_constant_event_count_has_no_class_information(self):
        result = run_d1(ROOT / "digit8x8_fixture.json", ROOT / "digit8x8_manifest.json")
        test = result["models"]["nearest_centroid_event_count"]["test"]
        self.assertLessEqual(test["coverage"], 0.20)
        self.assertLessEqual(test["balanced_accuracy"], 0.20)

    def test_label_shuffle_collapses_latency_baseline(self):
        result = run_d1(ROOT / "digit8x8_fixture.json", ROOT / "digit8x8_manifest.json")
        test = result["models"]["label_shuffle_latency"]["test"]
        self.assertLessEqual(test["balanced_accuracy"], 0.20)

    def test_metrics_are_balanced_over_all_ten_labels(self):
        samples = load_fixture(ROOT / "digit8x8_fixture.json")
        manifest = load_manifest(ROOT / "digit8x8_manifest.json")
        metrics = run_nearest_centroid(samples, manifest)["test"]
        self.assertEqual(len(metrics.confusion), 10)
        self.assertEqual(sum(sum(row) for row in metrics.confusion), metrics.sample_count)


if __name__ == "__main__":
    unittest.main()

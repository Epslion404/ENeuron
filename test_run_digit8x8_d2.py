import unittest
from pathlib import Path

from run_digit8x8_d2 import run_report


ROOT = Path(__file__).resolve().parent


class D2ReportRunnerTests(unittest.TestCase):
    def test_runner_emits_primary_and_negative_control_sections(self):
        result = run_report(
            ROOT / "digit8x8_fixture.json",
            ROOT / "digit8x8_manifest.json",
            seeds=[0],
            epochs=1,
        )
        self.assertEqual(len(result["primary"]), 1)
        self.assertIn("fixed_weight_seed0", result["controls"])
        self.assertIn("label_shuffle_seed0", result["controls"])
        self.assertIn("test", result["primary"][0])
        for field in ("fixture_sha256", "manifest_sha256", "runner_source_sha256", "model_source_sha256", "git_commit"):
            self.assertIn(field, result["config"])


if __name__ == "__main__":
    unittest.main()

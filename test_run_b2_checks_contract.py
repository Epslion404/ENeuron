import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class RunB2ChecksContractTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / "run_b2_checks.ps1").read_text(encoding="utf-8")

    def test_runner_exists_with_expected_modes(self):
        self.assertIn('[switch]$Full', self.source)
        self.assertIn('[switch]$Vivado', self.source)
        self.assertIn('workflow_resume.ps1', self.source)

    def test_runner_expands_b2_tests_before_pytest(self):
        self.assertIn('Get-ChildItem -LiteralPath $repoRoot -Filter "test_b2_*.py"', self.source)
        self.assertIn('"-X", "utf8", "-m", "pytest", "-q"', self.source)

    def test_runner_keeps_repro_and_diff_checks(self):
        self.assertIn('tools/repro/verify_repository.py', self.source)
        self.assertIn('"diff", "--check"', self.source)
        self.assertIn('exit 1', self.source)


if __name__ == "__main__":
    unittest.main()

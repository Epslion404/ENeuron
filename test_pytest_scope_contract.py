"""当前主线 pytest 收集边界合同。"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent


class PytestScopeContractTests(unittest.TestCase):
    def test_legacy_archive_is_not_a_daily_gate(self) -> None:
        config = (ROOT / "pytest.ini").read_text(encoding="utf-8")
        self.assertIn("norecursedirs", config)
        self.assertIn("    archive", config)
        for stale_test in (
            "test_formal_local_prune_commit_barrier.py",
            "test_compare_simulation.py",
            "test_np4b5_negative_controls.py",
            "test_rtl_cosim.py",
            "test_rtl_smoke.py",
            "test_rtl_tile_cosim.py",
            "test_run_digit8x8_d2.py",
            "test_run_local_prune_b1.py",
            "test_run_local_prune_b2.py",
            "test_run_local_prune_b21.py",
            "test_run_local_prune_np2.py",
            "test_run_local_prune_np3.py",
            "test_verify_local_prune_rtl.py",
        ):
            self.assertIn(f"--ignore={stale_test}", config)

        archive_readme = (ROOT / "archive/legacy/README.md").read_text(encoding="utf-8")
        self.assertIn("不再参与当前日常开发门", archive_readme)


if __name__ == "__main__":
    unittest.main()

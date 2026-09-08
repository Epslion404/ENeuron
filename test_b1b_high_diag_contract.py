"""验证 B1-06B 高地址诊断入口的可复现合同。"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIAG_DIR = ROOT / "boards" / "hellozynq" / "b1b_sw"


class B1BHighDiagContractTests(unittest.TestCase):
    def test_independent_ocm_diagnostic_sources_exist(self) -> None:
        source = DIAG_DIR / "src" / "high_diag.c"
        build_script = DIAG_DIR / "run_b1b_high_diag_build.ps1"
        runner = DIAG_DIR / "run_b1b_high_diag_board.ps1"
        linker = DIAG_DIR / "ocm_high_diag.ld"
        arm_script = DIAG_DIR / "arm_b1b_high_diag.tcl"

        for path in (source, build_script, runner, linker, arm_script):
            self.assertTrue(path.is_file(), f"缺少 B1-06B 文件: {path}")

        source_text = source.read_text(encoding="utf-8")
        build_text = build_script.read_text(encoding="utf-8")
        runner_text = runner.read_text(encoding="utf-8")
        linker_text = linker.read_text(encoding="utf-8")
        self.assertIn("0x10000000U", source_text)
        self.assertIn("RESULT_RECORD_BASE", source_text)
        self.assertIn("ENEURON_B1B_HIGH_DIAG_READY", source_text)
        self.assertIn("readelf", build_text)
        self.assertIn("arm-none-eabi-nm", build_text)
        self.assertIn("git_worktree_clean", build_text)
        self.assertIn("arm_b1b_high_diag.tcl", runner_text)
        self.assertIn("probe_b1b_high_diag.tcl", runner_text)
        self.assertIn("runner_error", runner_text)
        self.assertIn("OCM/CPU probe failed", runner_text)
        self.assertIn("source_sha256", runner_text)
        self.assertIn("linker_sha256", runner_text)
        self.assertIn("Current worktree is not clean", runner_text)
        self.assertIn("ocm_app", linker_text)
        self.assertIn("0x0002F000", linker_text)


if __name__ == "__main__":
    unittest.main()

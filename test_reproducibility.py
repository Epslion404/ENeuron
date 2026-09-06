"""GitHub 仓库复现入口的合同测试。"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.ci.classify_changes import classify_paths


ROOT = Path(__file__).resolve().parent


class ReproducibilityContractTests(unittest.TestCase):
    def test_manifest_lists_t1_closure(self) -> None:
        manifest = json.loads((ROOT / "tools/repro/repro_manifest.json").read_text(encoding="utf-8"))
        required = set(manifest["required_tracked_files"])
        self.assertIn("npu_zynq7020_t1_wrapper.sv", required)
        self.assertIn("tb_npu_zynq7020_t1_wrapper.sv", required)
        self.assertIn("xpm_fifo_async_sim.sv", required)

    def test_t1_changes_select_repro_gate(self) -> None:
        selected = classify_paths(["npu_zynq7020_t1_wrapper.sv"])
        self.assertTrue(selected["t1_repro"])


if __name__ == "__main__":
    unittest.main()

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
        self.assertIn("tb_npu_zynq7020_t1_fifo_boundary.sv", required)
        self.assertIn("tb_npu_zynq7020_t1_fence_accept.sv", required)
        self.assertIn("tb_npu_zynq7020_t2_variable_clocks.sv", required)
        self.assertIn("docs/planning/NPU_ZYNQ7020_T1_TLAST_BOUNDARY_V1.md", required)
        self.assertIn("docs/planning/NPU_ZYNQ7020_T2_TEST_PLAN_V1.md", required)
        self.assertIn("xpm_fifo_async_sim.sv", required)

    def test_t1_changes_select_repro_gate(self) -> None:
        selected = classify_paths(["npu_zynq7020_t1_wrapper.sv"])
        self.assertTrue(selected["t1_repro"])

    def test_host_window_state_uses_npu_domain_synchronizer(self) -> None:
        source = (ROOT / "npu_zynq7020_t1_wrapper.sv").read_text(encoding="utf-8")
        self.assertIn("sample_window_open_host_npu_d1", source)
        self.assertIn("sample_window_open_host_npu_d2", source)
        self.assertNotIn("host_window_active_npu_d1 <= sample_window_open_host", source)

    def test_error_status_uses_second_cdc_stage(self) -> None:
        source = (ROOT / "npu_zynq7020_t1_wrapper.sv").read_text(encoding="utf-8")
        self.assertIn("assign host_error = error_host_sync[1]", source)

    def test_t1_tlast_boundary_is_explicitly_outer(self) -> None:
        source = (ROOT / "npu_zynq7020_t1_wrapper.sv").read_text(encoding="utf-8").lower()
        decision = (ROOT / "docs/planning/NPU_ZYNQ7020_T1_TLAST_BOUNDARY_V1.md").read_text(encoding="utf-8")
        self.assertNotIn("tlast", source)
        self.assertIn("N/A", decision)
        self.assertIn("外层提示", decision)


if __name__ == "__main__":
    unittest.main()

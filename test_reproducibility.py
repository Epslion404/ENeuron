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

    def test_t2_fifo_matrix_has_reproducible_entrypoint(self) -> None:
        manifest = json.loads((ROOT / "tools/repro/repro_manifest.json").read_text(encoding="utf-8"))
        required = set(manifest["required_tracked_files"])
        verifier = (ROOT / "tools/repro/verify_repository.py").read_text(encoding="utf-8")
        self.assertIn("tb_xpm_fifo_async_matrix.sv", required)
        self.assertIn('parser.add_argument("--t2-fifo-matrix"', verifier)
        self.assertIn("REPRO_G2_T2_FIFO_MATRIX_PASS", verifier)

    def test_t2_interleave_reset_has_reproducible_entrypoint(self) -> None:
        manifest = json.loads((ROOT / "tools/repro/repro_manifest.json").read_text(encoding="utf-8"))
        verifier = (ROOT / "tools/repro/verify_repository.py").read_text(encoding="utf-8")
        self.assertIn("tb_npu_zynq7020_t2_interleave_reset.sv", manifest["required_tracked_files"])
        self.assertIn('parser.add_argument("--t2-interleave-reset"', verifier)
        self.assertIn("REPRO_G2_T2_INTERLEAVE_RESET_PASS", verifier)

    def test_t2_full_matrix_has_reproducible_entrypoint(self) -> None:
        verifier = (ROOT / "tools/repro/verify_repository.py").read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--t2-full-matrix"', verifier)
        self.assertIn("REPRO_G2_T2_FULL_MATRIX_PASS", verifier)

    def test_t2_random_matrix_has_reproducible_entrypoint(self) -> None:
        verifier = (ROOT / "tools/repro/verify_repository.py").read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--t2-random-matrix"', verifier)
        self.assertIn("REPRO_G2_T2_RANDOM_MATRIX_PASS", verifier)

    def test_t3_vivado_entries_are_reproducible(self) -> None:
        manifest = json.loads((ROOT / "tools/repro/repro_manifest.json").read_text(encoding="utf-8"))
        required = set(manifest["required_tracked_files"])
        expected = {
            "run_vivado_npu_zynq7020_t3_xsim.ps1",
            "vivado_npu_zynq7020_t3_xsim.tcl",
            "run_vivado_npu_zynq7020_t3_ooc.ps1",
            "vivado_npu_zynq7020_t3_ooc.tcl",
        }
        self.assertTrue(expected.issubset(required))

        xsim = (ROOT / "vivado_npu_zynq7020_t3_xsim.tcl").read_text(encoding="utf-8")
        self.assertIn("xc7z020clg400-1", xsim)
        self.assertIn("XPM_LIBRARIES {XPM_FIFO}", xsim)
        self.assertIn("T1_PROTOCOL_SKELETON_PASS", xsim)
        self.assertNotIn("xpm_fifo_async_sim.sv", xsim)

        ooc = (ROOT / "vivado_npu_zynq7020_t3_ooc.tcl").read_text(encoding="utf-8")
        self.assertIn("xc7z020clg400-1", ooc)
        self.assertIn("npu_zynq7020_t1_wrapper", ooc)
        self.assertIn("DSP48E1_COUNT", ooc)
        self.assertIn("PHYSICAL_GATE", ooc)
        self.assertIn("EXTERNAL_CDC_CRITICAL", ooc)
        self.assertIn("EXTERNAL_CDC_WARNING", ooc)
        self.assertIn("phys_opt_design -directive AggressiveExplore", ooc)

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

    def test_lane_products_are_not_gated_by_compute_state(self) -> None:
        source = (ROOT / "npu_eneuron_single_clock_skeleton.sv").read_text(encoding="utf-8")
        self.assertIn("lane_activation_0 = lane_activation_latched_0", source)
        self.assertNotIn("if (compute_state == COMPUTE_L0_GROUP_EXECUTE", source)

    def test_fifo_busy_crossing_is_aggregated_and_registered(self) -> None:
        source = (ROOT / "npu_zynq7020_t1_wrapper.sv").read_text(encoding="utf-8")
        self.assertIn("host_local_fifo_busy_reg", source)
        self.assertIn("npu_local_fifo_busy_reg", source)
        self.assertIn("host_busy_npu_sync", source)
        self.assertIn("npu_busy_host_sync", source)
        self.assertNotIn("host_cmd_rd_busy_sync", source)
        self.assertNotIn("npu_cmd_wr_busy_sync", source)

    def test_fence_window_opens_from_host_side_response(self) -> None:
        source = (ROOT / "npu_zynq7020_t1_wrapper.sv").read_text(encoding="utf-8")
        self.assertIn("rsp_rd_en && rsp_dout[127:124] == RSP_FENCE", source)
        self.assertNotIn("sample_window_toggle_npu", source)
        self.assertNotIn("sample_window_toggle_host_sync", source)

    def test_t1_tlast_boundary_is_explicitly_outer(self) -> None:
        source = (ROOT / "npu_zynq7020_t1_wrapper.sv").read_text(encoding="utf-8").lower()
        decision = (ROOT / "docs/planning/NPU_ZYNQ7020_T1_TLAST_BOUNDARY_V1.md").read_text(encoding="utf-8")
        self.assertNotIn("tlast", source)
        self.assertIn("N/A", decision)
        self.assertIn("外层提示", decision)


if __name__ == "__main__":
    unittest.main()

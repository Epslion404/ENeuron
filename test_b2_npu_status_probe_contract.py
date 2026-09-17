import unittest
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
HW = ROOT / "boards" / "hellozynq" / "b2_hw"
SW = ROOT / "boards" / "hellozynq" / "b2_sw"


class B2NpuStatusProbeContractTests(unittest.TestCase):
    def setUp(self):
        self.probe = (HW / "b2_npu_status_probe.v").read_text(encoding="utf-8")
        self.top = (HW / "b2_npu_axis_top.v").read_text(encoding="utf-8")
        self.adapter = (ROOT / "b2_npu_packet_adapter.sv").read_text(encoding="utf-8")
        self.wrapper = (ROOT / "npu_zynq7020_t1_wrapper.sv").read_text(encoding="utf-8")
        self.core = (ROOT / "npu_eneuron_single_clock_skeleton.sv").read_text(encoding="utf-8")
        self.bd = (HW / "create_b2_bd.tcl").read_text(encoding="utf-8")
        self.build = (HW / "build_b2.tcl").read_text(encoding="utf-8")
        self.runner = (HW / "run_b2_build.ps1").read_text(encoding="utf-8")
        self.probe_tcl = (SW / "probe_b2_state.tcl").read_text(encoding="utf-8")

    def test_b2_build_fail_closed_requires_four_dsp48e1(self):
        tcl = (HW / "build_b2.tcl").read_text(encoding="utf-8")
        runner = (HW / "run_b2_build.ps1").read_text(encoding="utf-8")
        self.assertIn("B2_NPU_DSP_EXPECTED=4", tcl)
        self.assertIn("REF_NAME == DSP48E1", tcl)
        self.assertIn("B2_NPU_DSP48E1_COUNT=", tcl)
        self.assertIn("xc7z020clg484-2", tcl)
        self.assertNotIn("xc7z020clg400-1", tcl)
        self.assertIn("DSP48E1_COUNT=$dspCountText expected=4", runner)

    def test_legacy_counter_addresses_stay_in_0x00_0x4c(self):
        """0x00–0x4C 的既有实板读口不得被 0x50–0x60 扩展挤走。"""
        self.assertIn("STATUS_ADDR = 12'h000", self.probe)
        self.assertIn("COMMAND_ACCEPT_ADDR = 12'h004", self.probe)
        self.assertIn("EXECUTE_GROUP_ADDR = 12'h048", self.probe)
        self.assertIn("SKIP_GROUP_ADDR = 12'h04C", self.probe)
        self.assertIn("RUNTIME_STATUS_ADDR = 12'h050", self.probe)
        self.assertIn("ACTIVE_MASK_EPOCH_ADDR = 12'h054", self.probe)
        self.assertIn("PENDING_MASK_EPOCH_ADDR = 12'h058", self.probe)
        self.assertIn("LAST_COMPUTE_CYCLES_ADDR = 12'h05C", self.probe)
        self.assertIn("PROTOCOL_ERROR_COUNT_ADDR = 12'h060", self.probe)
        self.assertIn("FENCE_SNAPSHOT_VALID_ADDR = 12'h024", self.probe)

    def test_status_probe_has_read_only_axi_lite_and_snapshot_registers(self):
        for token in (
            "module b2_npu_status_probe",
            "S_AXI",
            "COMMAND_ACCEPT_ADDR",
            "RESULT_COMPLETE_ADDR",
            "EXECUTE_GROUP_ADDR",
            "SKIP_GROUP_ADDR",
            "RUNTIME_STATUS_ADDR",
            "ACTIVE_MASK_EPOCH_ADDR",
            "PENDING_MASK_EPOCH_ADDR",
            "LAST_COMPUTE_CYCLES_ADDR",
            "PROTOCOL_ERROR_COUNT_ADDR",
            "FENCE_SNAPSHOT_VALID_ADDR",
            "FENCE_SNAPSHOT_BASE_ADDR",
            "input wire [255:0] fence_snapshot_counts",
        ):
            self.assertIn(token, self.probe)

    def test_top_exports_all_counter_fields(self):
        for token in (
            "command_accept_count",
            "command_complete_count",
            "sample_accept_count",
            "sample_complete_count",
            "response_accept_count",
            "response_complete_count",
            "result_accept_count",
            "result_complete_count",
            "execute_group_count",
            "skip_group_count",
            "runtime_status",
            "active_mask_epoch",
            "pending_mask_epoch",
            "last_compute_cycles",
            "protocol_error_count",
            "fence_snapshot_valid",
            "fence_snapshot_counts",
        ):
            self.assertIn(token, self.top)

    def test_bd_maps_status_probe_and_counter_wires(self):
        for token in (
            "-reference b2_npu_status_probe b2_npu_status_probe_0",
            "dma_control_smartconnect/M03_AXI",
            "b2_npu_status_probe_0/S_AXI",
            "command_accept_count command_complete_count",
            "execute_group_count skip_group_count",
            "runtime_status active_mask_epoch pending_mask_epoch",
            "last_compute_cycles protocol_error_count",
            "connect_bd_net [get_bd_pins b2_npu_axis_top_0/$pin] [get_bd_pins b2_npu_status_probe_0/$pin]",
            "0x40430000",
        ):
            self.assertIn(token, self.bd)

    def test_build_and_probe_track_status_register_block(self):
        for token in ("b2_npu_status_probe.v", "b2_npu_status_probe"):
            self.assertIn(token, self.build)
            self.assertIn(token, self.runner)
        for token in (
            "B2_NPU_STATUS_BASE",
            "B2_NPU_COMMAND_ACCEPT",
            "B2_NPU_FENCE_SNAPSHOT_VALID",
            "B2_NPU_EXECUTE_GROUP_COUNT",
            "B2_NPU_SKIP_GROUP_COUNT",
            "B2_NPU_RUNTIME_STATUS",
            "B2_NPU_ACTIVE_MASK_EPOCH",
            "B2_NPU_PENDING_MASK_EPOCH",
            "B2_NPU_LAST_COMPUTE_CYCLES",
            "B2_NPU_PROTOCOL_ERROR_COUNT",
            "B2_NPU_FENCE_SNAPSHOT_%02d",
        ):
            self.assertIn(token, self.probe_tcl)

    def test_build_runner_hashes_without_get_file_hash_dependency(self):
        for token in (
            "function Get-FileSha256",
            "System.Security.Cryptography.SHA256",
            "Get-FileSha256 -Path $bitstreamPath",
            "Get-FileSha256 -Path $xsaPath",
        ):
            self.assertIn(token, self.runner)

    def test_mvp_observability_reaches_status_block(self):
        self.assertIn("output logic [31:0] last_compute_cycles", self.core)
        self.assertIn("output logic [31:0] pending_mask_epoch", self.core)
        for token in (
            "host_active_mask_epoch",
            "host_pending_mask_epoch",
            "host_last_compute_cycles",
        ):
            self.assertIn(token, self.wrapper)
        for token in (
            "active_mask_epoch",
            "pending_mask_epoch",
            "last_compute_cycles",
            "protocol_error_count",
            "runtime_status",
        ):
            self.assertIn(token, self.adapter)

    def test_status_probe_rtl_reads_all_registers(self):
        fixed = Path("C:/msys64/ucrt64/bin")
        iverilog = fixed / "iverilog.exe"
        vvp = fixed / "vvp.exe"
        if not iverilog.is_file() or not vvp.is_file():
            found_iverilog = shutil.which("iverilog")
            found_vvp = shutil.which("vvp")
            if not found_iverilog or not found_vvp:
                self.skipTest("Icarus Verilog is unavailable")
            iverilog = Path(found_iverilog)
            vvp = Path(found_vvp)
        with tempfile.TemporaryDirectory(prefix="b2-npu-status-") as temp:
            output = Path(temp) / "status_probe.vvp"
            compile_result = subprocess.run(
                [
                    str(iverilog), "-g2012", "-Wall", "-s", "tb_b2_npu_status_probe",
                    "-o", str(output), str(HW / "b2_npu_status_probe.v"),
                    str(ROOT / "tb_b2_npu_status_probe.sv"),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                encoding="utf-8",
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            simulation = subprocess.run(
                [str(vvp), str(output)], cwd=ROOT, text=True,
                capture_output=True, encoding="utf-8",
            )
            transcript = simulation.stdout + simulation.stderr
            self.assertEqual(simulation.returncode, 0, transcript)
            self.assertIn("B2_NPU_STATUS_PROBE_PASS", transcript)


if __name__ == "__main__":
    unittest.main()

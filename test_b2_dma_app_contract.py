import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
B2_SW = ROOT / "boards" / "hellozynq" / "b2_sw"


class B2DmaAppContractTests(unittest.TestCase):
    def setUp(self):
        self.source = (B2_SW / "src" / "main.c").read_text(encoding="utf-8")
        self.build = (B2_SW / "run_b2_sw_build.ps1").read_text(encoding="utf-8")
        self.board = (B2_SW / "run_b2_board.ps1").read_text(encoding="utf-8")

    def test_sources_exist(self):
        for path in (
            B2_SW / "src" / "main.c",
            B2_SW / "build_b2_sw.tcl",
            B2_SW / "run_b2_sw_build.ps1",
            B2_SW / "program_b2.tcl",
            B2_SW / "run_b2_board.ps1",
            B2_SW / "probe_b2_state.tcl",
        ):
            self.assertTrue(path.is_file(), path)

    def test_uses_frozen_low_address_buffers(self):
        self.assertIn("0x01006000U", self.source)
        self.assertIn("0x01007000U", self.source)
        self.assertIn("MAX_FRAME_BYTES 4096U", self.source)
        self.assertIn("BUFFER_ALIGNMENT 64U", self.source)

    def test_enforces_frozen_transfer_order_and_cache_ownership(self):
        self.assertIn("Xil_DCacheFlushRange", self.source)
        self.assertIn("Xil_DCacheInvalidateRange", self.source)
        self.assertIn("XAXIDMA_DEVICE_TO_DMA", self.source)
        self.assertIn("XAXIDMA_DMA_TO_DEVICE", self.source)
        self.assertLess(
            self.source.index("XAXIDMA_DEVICE_TO_DMA"),
            self.source.index("XAXIDMA_DMA_TO_DEVICE"),
        )

    def test_records_register_snapshot_and_sequence(self):
        for token in (
            "sequence",
            "tx_cr",
            "tx_sr",
            "rx_cr",
            "rx_sr",
            "tx_btt",
            "rx_btt",
            "B2_DMA_PASS",
            "B2_DMA_FAIL",
        ):
            self.assertIn(token, self.source)

    def test_boundary_matrix_and_jtag_ledger_are_present(self):
        for token in (
            "FRAME_LENGTHS",
            "0U, 1U, 4U, 16U, 64U, 512U, 1472U, 4096U",
            "STATUS_LEDGER_BASE",
            "RESULT_STATUS_REJECTED",
            "B2_DMA_PASS frames=",
        ):
            self.assertIn(token, self.source)

    def test_pressure_contract_is_present(self):
        for token in (
            "PRESSURE_FRAME_COUNT 10000U",
            "PRESSURE_LENGTHS",
            "pressure_total",
            "pressure_passed",
            "pressure_failed",
            "pressure_crc32",
            "B2_PRESSURE_PASS",
        ):
            self.assertIn(token, self.source)

    def test_build_is_bound_to_b2_xsa(self):
        self.assertIn("hello_zynq_b2.xsa", self.build)
        self.assertIn("hello_zynq_b2.bit", self.board)
        self.assertIn("xc7z020clg484-2", self.build)

    def test_sw_build_invalidates_stale_xsa_workspace(self):
        self.assertIn("$existingXsaSha", self.build)
        self.assertIn("$b2XsaSha256", self.build)
        self.assertIn("Copy-Item -LiteralPath $xsaSource -Destination $xsaCopy -Force", self.build)

    def test_board_runner_rejects_mismatched_hardware_identity(self):
        self.assertIn("bitstream_sha256", self.board)
        self.assertIn("xsa_sha256", self.board)
        self.assertIn("artifact hash", self.board)

    def test_probe_addresses_have_frozen_fallbacks_for_custom_module_reference(self):
        self.assertIn("MONITOR_MM2S_BASE 0x40410000U", self.source)
        self.assertIn("MONITOR_S2MM_BASE 0x40420000U", self.source)
        self.assertNotIn('MM2S AXI stream probe base address is missing', self.source)
        self.assertNotIn('S2MM AXI stream probe base address is missing', self.source)

    def test_board_runner_waits_for_pressure_terminal_marker(self):
        self.assertIn("B2_PRESSURE_PASS", self.board)
        self.assertIn("B2_DMA_FAIL", self.board)

    def test_board_runner_tolerates_uart_handle_reset_during_fpga_programming(self):
        self.assertIn("catch [System.IO.IOException]", self.board)
        self.assertIn("-not $serial.IsOpen", self.board)

    def test_board_runner_uses_powershell_numeric_literals(self):
        self.assertNotIn("= 0U", self.board)
        self.assertIn("$serialReconnects = [uint32]0", self.board)

    def test_board_runner_archives_post_program_probe(self):
        for token in (
            "$probeTcl = Join-Path $scriptRoot 'probe_b2_state.tcl'",
            "& $XsctPath $probeTcl > $probeStdout 2> $probeStderr",
            "probe_read_available",
            "probe_log_sha256",
        ):
            self.assertIn(token, self.board)


if __name__ == "__main__":
    unittest.main()

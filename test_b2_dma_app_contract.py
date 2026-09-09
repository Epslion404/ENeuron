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

    def test_continuous_buffer_wrap_contract_is_present(self):
        for token in (
            "WRAP_FRAME_COUNT 256U",
            "WRAP_SLOT_BYTES 64U",
            "WRAP_SLOT_COUNT 64U",
            "WRAP_LENGTHS",
            "wrap_status",
            "wrap_slot_mask",
            "B2_WRAP_PASS",
        ):
            self.assertIn(token, self.source)
        for token in (
            "B2_STATUS_WRAP_STATUS",
            "B2_STATUS_WRAP_SLOT_MASK",
            "jtag_wrap_status",
            "jtag_wrap_slot_mask",
            "jtag_wrap_rollovers",
            "jtag_wrap_first_tx_address",
            "B2_WRAP_PASS",
        ):
            self.assertIn(token, self.board)

    def test_wrap_status_does_not_overlap_boundary_ledger(self):
        self.assertIn("WRAP_STATUS_BASE 0x01008280U", self.source)
        probe = (B2_SW / "probe_b2_state.tcl").read_text(encoding="utf-8")
        self.assertIn("0x01008280", probe)

    def test_wrap_probe_offsets_match_struct_layout(self):
        probe = (B2_SW / "probe_b2_state.tcl").read_text(encoding="utf-8")
        for address in (
            "0x010082A0",  # rollovers
            "0x010082A4",  # first TX
            "0x010082A8",  # first RX
            "0x010082AC",  # last TX
            "0x010082B0",  # last RX
        ):
            self.assertIn(address, probe)

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
        self.assertIn("B2_DMA_PASS frames=", self.board)
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

    def test_board_runner_records_jtag_backpressure_summary(self):
        for token in (
            "B2_STATUS_BACKPRESSURE_STATUS",
            "jtag_backpressure_status",
            "jtag_backpressure_stall_cycles",
            "B2_JTAG_STATUS",
        ):
            self.assertIn(token, self.board)

    def test_board_runner_requires_jtag_and_uart_for_overall_pass(self):
        self.assertIn("$uartPass", self.board)
        self.assertIn("$uartPass -and $jtagPass", self.board)
        self.assertIn("$xsctExitCode -eq 0", self.board)
        self.assertIn("-eq 4294967295", self.board)
        self.assertIn("exit 0", (B2_SW / "program_b2.tcl").read_text(encoding="utf-8"))

    def test_board_runner_records_ps_uart_configuration(self):
        for token in (
            "B2_UART_CR",
            "B2_UART_MR",
            "B2_UART_BAUDGEN",
            "jtag_uart_configured",
        ):
            self.assertIn(token, self.board)

    def test_board_runner_rejects_stale_uart_markers_before_current_cpu_run(self):
        for token in (
            "$currentRunStarted",
            "B2_CPU_RUN_PASS",
            "$received.Clear()",
            "DiscardInBuffer",
            "$null -eq $xsctProgress",
        ):
            self.assertIn(token, self.board)
        self.assertIn("WaitForExit(30000)", self.board)

    def test_controlled_backpressure_contract_is_present(self):
        for token in (
            "BACKPRESSURE_FRAME_COUNT",
            "BACKPRESSURE_LENGTHS",
            "backpressure_status",
            "backpressure_stall_cycles",
            "B2_BACKPRESSURE_PASS",
            "B2_BACKPRESSURE_PASS",
        ):
            self.assertIn(token, self.source)
        self.assertIn("B2_BACKPRESSURE_PASS", self.board)

    def test_backpressure_pass_is_fail_closed_on_zero_observed_stall(self):
        self.assertIn("backpressure_stall_cycles == 0U", self.source)
        self.assertIn("backpressure_not_observed", self.source)

    def test_backpressure_config_has_nonzero_period(self):
        self.assertIn("BACKPRESSURE_CONFIG 0x04030201U", self.source)

    def test_terminal_pass_marker_is_repeated_after_completion(self):
        alive_loop = self.source[self.source.index("while (1)") :]
        self.assertIn("B2_DMA_PASS", alive_loop)

    def test_dma_reset_recovery_contract_is_present(self):
        for token in (
            "RECOVERY_STATUS_BASE 0x01008300U",
            "recovery_timeout_observed",
            "recovery_reset_passed",
            "recovery_passed",
            "recovery_failed",
            "B2_RECOVERY_PASS",
            "recovery_after_reset",
        ):
            self.assertIn(token, self.source)
        for token in (
            "B2_STATUS_RECOVERY_STATUS",
            "B2_STATUS_RECOVERY_TIMEOUT",
            "B2_STATUS_RECOVERY_RESET",
            "B2_STATUS_RECOVERY_PASSED",
            "B2_STATUS_RECOVERY_FAILED",
            "B2_RECOVERY_PASS",
        ):
            self.assertIn(token, self.board)
        probe = (B2_SW / "probe_b2_state.tcl").read_text(encoding="utf-8")
        for address in ("0x01008300", "0x01008304", "0x01008308", "0x0100830C", "0x01008310"):
            self.assertIn(address, probe)

    def test_inter_frame_gap_contract_is_present_and_distinct_from_backpressure(self):
        for token in (
            "GAP_STATUS_BASE 0x01008340U",
            "GAP_DELAY_US 1000U",
            "gap_status",
            "gap_requested_us",
            "gap_first_sequence",
            "gap_second_sequence",
            "B2_GAP_PASS",
            "gap_mode",
        ):
            self.assertIn(token, self.source)
        self.assertIn("usleep(GAP_DELAY_US)", self.source)
        self.assertIn("monitor_configure_backpressure(MONITOR_S2MM_BASE, 0U)", self.source)
        self.assertIn("B2_GAP_PASS", self.board)
        self.assertIn("B2_STATUS_GAP_STATUS", self.board)
        probe = (B2_SW / "probe_b2_state.tcl").read_text(encoding="utf-8")
        for address in ("0x01008340", "0x01008344", "0x01008348", "0x0100834C"):
            self.assertIn(address, probe)

    def test_recovery_records_ready_stop_and_ready_restore(self):
        for token in (
            "recovery_s2mm_active_before_stop",
            "recovery_s2mm_active_after_stop",
            "recovery_s2mm_active_after_reset",
            "B2_RECOVERY_PASS timeout=",
            "ready_before=",
            "ready_stopped=",
            "ready_after_reset=",
        ):
            self.assertIn(token, self.source)
        for token in (
            "B2_STATUS_RECOVERY_READY_BEFORE",
            "B2_STATUS_RECOVERY_READY_STOPPED",
            "B2_STATUS_RECOVERY_READY_AFTER_RESET",
        ):
            self.assertIn(token, self.board)
        probe = (B2_SW / "probe_b2_state.tcl").read_text(encoding="utf-8")
        for address in ("0x0100831C", "0x01008320", "0x01008324"):
            self.assertIn(address, probe)

    def test_persistent_ledger_probe_matches_c_layout(self):
        probe = (B2_SW / "probe_b2_state.tcl").read_text(encoding="utf-8")
        self.assertIn("($index * 64)", probe)
        for field in (
            "SEQ", "LEN", "STATUS", "CRC", "ELAPSED", "INVALIDATE",
            "MM2S_BEATS", "S2MM_BEATS", "MM2S_TLAST_LO", "MM2S_TLAST_HI",
            "S2MM_TLAST_LO", "S2MM_TLAST_HI", "MM2S_BYTES_LO", "MM2S_BYTES_HI",
            "S2MM_BYTES_LO", "S2MM_BYTES_HI",
        ):
            self.assertIn("_" + field + "=[mrd", probe)

    def test_board_runner_fail_closes_on_persistent_ledger(self):
        for token in (
            "jtag_ledger",
            "ledger_pass",
            "ledgerLengths",
            "mm2s_beats",
            "s2mm_tlast",
        ):
            self.assertIn(token, self.board)


if __name__ == "__main__":
    unittest.main()

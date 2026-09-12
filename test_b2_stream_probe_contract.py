import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HW = ROOT / "boards" / "hellozynq" / "b2_hw"


class B2StreamProbeContractTests(unittest.TestCase):
    def setUp(self):
        self.bd = (HW / "create_b2_bd.tcl").read_text(encoding="utf-8")
        self.build = (HW / "build_b2.tcl").read_text(encoding="utf-8")
        self.runner = (HW / "run_b2_build.ps1").read_text(encoding="utf-8")
        self.probe = (HW / "axis_stream_probe.v").read_text(encoding="utf-8") if (HW / "axis_stream_probe.v").exists() else ""
        self.state_probe = (ROOT / "boards" / "hellozynq" / "b2_sw" / "probe_b2_state.tcl").read_text(encoding="utf-8")

    def test_probe_source_is_added_before_bd_generation(self):
        self.assertIn("axis_stream_probe.v", self.build)
        self.assertIn("-type module -reference axis_stream_probe", self.bd)

    def test_two_probes_preserve_bidirectional_observation_contract(self):
        for token in (
            "axis_stream_probe_mm2s",
            "axis_stream_probe_s2mm",
            "M_AXIS_MM2S",
            "S_AXIS_S2MM",
            "0x40410000",
            "0x40420000",
            "CONFIG.NUM_MI {3}",
        ):
            self.assertIn(token, self.bd)
        self.assertNotIn("axi_stream_monitor", self.bd)

    def test_probe_counts_required_stream_fields(self):
        for token in (
            "s_axis_tkeep",
            "s_axis_tlast",
            "accepted_beats",
            "total_bytes",
            "tlast_count",
            "last_tkeep",
            "BACKPRESSURE_ADDR",
            "backpressure_config",
            "backpressure_stall",
            "cycle_count",
            "stall_count",
            "starve_count",
            "S_AXI",
            "S_AXIS",
            "M_AXIS",
        ):
            self.assertIn(token, self.probe)

    def test_probe_backpressure_is_registered_and_buffered(self):
        """背压不能把下游 TREADY 组合反馈到上游握手。"""
        for token in (
            "fifo_valid",
            "fifo_tdata",
            "fifo_tkeep",
            "fifo_tlast",
            "backpressure_stall",
            "input_fire",
        ):
            self.assertIn(token, self.probe)
        self.assertNotIn(
            "assign apply_stall = forced_stall && m_axis_tready;",
            self.probe,
        )

    def test_probe_axi_read_address_is_registered_before_data_decode(self):
        for token in (
            "reg [11:0] read_addr",
            "reg read_pending",
            "assign s_axi_arready = s_axi_aresetn && !s_axi_rvalid && !read_pending",
            "read_addr <= s_axi_araddr",
            "read_pending <= 1'b1",
            "if (read_pending && !s_axi_rvalid)",
            "case (read_addr)",
        ):
            self.assertIn(token, self.probe)

    def test_backpressure_phase_starts_on_first_captured_beat(self):
        self.assertIn("else if (input_fire)", self.probe)
        self.assertIn("避免等待 DMA 首拍时相位漂移", self.probe)
        self.assertIn("else if (!fifo_valid)", self.probe)

    def test_backpressure_freezes_phase_while_valid_waits_for_ready(self):
        """已公开的 AXI VALID 在下游阻塞时必须保持，不能被强制背压撤回。"""
        self.assertIn("fifo_valid && !backpressure_stall && !m_axis_tready", self.probe)

    def test_physical_build_uses_explore_and_rejects_bad_timing(self):
        self.assertIn("Performance_Explore", self.build)
        self.assertIn("'axis_stream_probe.v'", self.runner)
        for token in (
            "Assert-B2TimingGreen",
            "timing_impl.rpt",
            "B2_TIMING_PASS",
            "B2_ROUTE_ERRORS",
            "B2_DRC_HARD_ERRORS",
        ):
            self.assertIn(token, self.runner)

    def test_jtag_probe_reads_both_stream_observation_banks(self):
        for token in (
            "emit_probe_state B2_PROBE_MM2S 0x40410000",
            "emit_probe_state B2_PROBE_S2MM 0x40420000",
            "_SAMPLE=",
            "_BEATS=",
            "_TLAST=",
            "_BYTES=",
            "_CYCLES=",
            "_STALL=",
            "_STARVE=",
            "_LAST_TKEEP=",
            "B2_PROBE_READ=UNAVAILABLE",
            "mrd -force -value",
            "_CONFIG=",
        ):
            self.assertIn(token, self.state_probe)

    def test_probe_exposes_controlled_missing_tlast_injection(self):
        for token in (
            "ERROR_CONFIG_ADDR",
            "error_config",
            "drop_tlast",
            "missing_tlast",
            "ERROR_CONFIG_ADDR",
        ):
            self.assertIn(token, self.probe)


if __name__ == "__main__":
    unittest.main()

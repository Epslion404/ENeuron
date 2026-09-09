import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HW = ROOT / "boards" / "hellozynq" / "b2_hw"


class B2StreamProbeContractTests(unittest.TestCase):
    def setUp(self):
        self.bd = (HW / "create_b2_bd.tcl").read_text(encoding="utf-8")
        self.build = (HW / "build_b2.tcl").read_text(encoding="utf-8")
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
            "cycle_count",
            "stall_count",
            "starve_count",
            "S_AXI",
            "S_AXIS",
            "M_AXIS",
        ):
            self.assertIn(token, self.probe)

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
        ):
            self.assertIn(token, self.state_probe)


if __name__ == "__main__":
    unittest.main()

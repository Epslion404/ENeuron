import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HW = ROOT / "boards" / "hellozynq" / "b2_hw"
SW = ROOT / "boards" / "hellozynq" / "b2_sw"


class B2StreamMonitorContractTests(unittest.TestCase):
    def setUp(self):
        self.bd = (HW / "create_b2_bd.tcl").read_text(encoding="utf-8")
        self.build = (HW / "build_b2.tcl").read_text(encoding="utf-8")

    def test_uses_lightweight_stream_probe(self):
        self.assertIn("axis_stream_probe.v", self.build)
        self.assertIn("-type module -reference axis_stream_probe", self.bd)
        self.assertNotIn("axi_stream_monitor", self.bd)

    def test_monitor_register_contract_is_documented_in_software(self):
        source = (SW / "src" / "main.c").read_text(encoding="utf-8")
        for token in (
            "MONITOR_MM2S_BASE",
            "MONITOR_S2MM_BASE",
            "MONITOR_CONTROL_OFFSET",
            "MONITOR_TOTAL_DATA_BEATS_OFFSET",
            "MONITOR_SAMPLE_OFFSET",
            "MONITOR_TOTAL_TLASTS_OFFSET",
            "MONITOR_TOTAL_DATA_BYTES_OFFSET",
            "MONITOR_TOTAL_BUSY_CYCLES_OFFSET",
            "MONITOR_TOTAL_STALL_CYCLES_OFFSET",
            "MONITOR_TOTAL_STARVE_CYCLES_OFFSET",
            "monitor_snapshot",
        ):
            self.assertIn(token, source)

    def test_bd_inserts_probe_and_control_interconnect(self):
        for token in (
            "axis_stream_probe_mm2s",
            "axis_stream_probe_s2mm",
            "dma_control_smartconnect",
            "CONFIG.NUM_MI {3}",
            "M_AXIS_MM2S",
            "S_AXIS_S2MM",
            "S_AXI",
            "M_AXIS",
            "S_AXIS",
            "assign_bd_address",
        ):
            self.assertIn(token, self.bd)

    def test_probe_addresses_are_fixed_and_distinct(self):
        for token in (
            "0x40410000",
            "0x40420000",
            "axis_stream_probe_mm2s/S_AXI",
            "axis_stream_probe_s2mm/S_AXI",
        ):
            self.assertIn(token, self.bd)

    def test_build_keeps_ip_catalog_path_and_source_hashes_local(self):
        self.assertIn("source [file join $script_dir create_b2_bd.tcl]", self.build)


if __name__ == "__main__":
    unittest.main()

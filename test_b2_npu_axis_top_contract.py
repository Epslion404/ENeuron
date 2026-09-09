import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HW = ROOT / "boards" / "hellozynq" / "b2_hw"


class B2NpuAxisTopContractTests(unittest.TestCase):
    def test_axis_top_declares_standard_stream_interfaces(self):
        source = (HW / "b2_npu_axis_top.v").read_text(encoding="utf-8")
        for token in (
            "xilinx.com:interface:axis:1.0 S_AXIS TDATA",
            "xilinx.com:interface:axis:1.0 M_AXIS TDATA",
            "b2_npu_packet_adapter",
            ".host_clk(axis_aclk)",
            ".npu_clk(axis_aclk)",
        ):
            self.assertIn(token, source)

    def test_bd_inserts_packet_npu_between_existing_probes(self):
        source = (HW / "create_b2_bd.tcl").read_text(encoding="utf-8")
        for token in (
            "-reference b2_npu_axis_top b2_npu_axis_top_0",
            "axis_stream_probe_mm2s/M_AXIS",
            "b2_npu_axis_top_0/S_AXIS",
            "b2_npu_axis_top_0/M_AXIS",
            "axis_stream_probe_s2mm/S_AXIS",
            "b2_npu_axis_top_0/axis_aclk",
            "b2_npu_axis_top_0/axis_aresetn",
        ):
            self.assertIn(token, source)

    def test_build_tracks_packet_npu_sources(self):
        tcl = (HW / "build_b2.tcl").read_text(encoding="utf-8")
        runner = (HW / "run_b2_build.ps1").read_text(encoding="utf-8")
        for name in (
            "b2_npu_axis_top.v",
            "b2_npu_packet_adapter.sv",
            "b2_packet_ingress.sv",
            "b2_packet_egress.sv",
            "npu_zynq7020_t1_wrapper.sv",
            "npu_eneuron_single_clock_skeleton.sv",
        ):
            self.assertIn(name, tcl)
            self.assertIn(name, runner)
        self.assertIn("MM2S_PACKET_NPU_S2MM", tcl)


if __name__ == "__main__":
    unittest.main()

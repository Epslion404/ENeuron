import unittest
from pathlib import Path

from tools.ci.classify_changes import classify_paths


ROOT = Path(__file__).resolve().parent
B2_DIR = ROOT / "boards" / "hellozynq" / "b2_hw"
BD_SCRIPT = B2_DIR / "create_b2_bd.tcl"
BUILD_SCRIPT = B2_DIR / "build_b2.tcl"
RUNNER = B2_DIR / "run_b2_build.ps1"


class B2LoopbackContractTests(unittest.TestCase):
    def setUp(self):
        self.bd = BD_SCRIPT.read_text(encoding="utf-8")
        self.build = BUILD_SCRIPT.read_text(encoding="utf-8")
        self.runner = RUNNER.read_text(encoding="utf-8")

    def test_b2_sources_exist(self):
        self.assertTrue(BD_SCRIPT.is_file())
        self.assertTrue(BUILD_SCRIPT.is_file())
        self.assertTrue(RUNNER.is_file())

    def test_ps_exposes_gp0_and_hp0(self):
        self.assertIn("CONFIG.PCW_USE_M_AXI_GP0 {1}", self.bd)
        self.assertIn("CONFIG.PCW_USE_S_AXI_HP0 {1}", self.bd)

    def test_dma_is_simple_mode_and_looped(self):
        self.assertIn("xilinx.com:ip:axi_dma:7.1", self.bd)
        self.assertIn("CONFIG.c_include_sg {0}", self.bd)
        self.assertIn("CONFIG.c_include_mm2s {1}", self.bd)
        self.assertIn("CONFIG.c_include_s2mm {1}", self.bd)
        self.assertIn("axi_dma_0/M_AXIS_MM2S", self.bd)
        self.assertIn("axi_dma_0/S_AXIS_S2MM", self.bd)

    def test_gp0_axi3_is_converted_to_dma_axi4lite(self):
        self.assertIn("xilinx.com:ip:axi_protocol_converter:2.1", self.bd)
        self.assertIn("CONFIG.SI_PROTOCOL {AXI3}", self.bd)
        self.assertIn("CONFIG.MI_PROTOCOL {AXI4LITE}", self.bd)
        self.assertIn("processing_system7_0/M_AXI_GP0", self.bd)
        self.assertIn("axi_protocol_converter_0/S_AXI", self.bd)
        self.assertIn("axi_protocol_converter_0/M_AXI", self.bd)

    def test_build_targets_board_part_and_existing_constraints(self):
        self.assertIn("set part xc7z020clg484-2", self.build)
        self.assertIn("create_b2_bd.tcl", self.build)
        self.assertIn("hello_zynq_b1a.xdc", self.build)
        self.assertIn("hello_zynq_b1a_rgmii_tx.xdc", self.build)
        self.assertIn("xc7z020clg484-2", self.runner)

    def test_b2_sources_use_targeted_repro_gate(self):
        scopes = classify_paths([
            "boards/hellozynq/b2_hw/create_b2_bd.tcl",
            "boards/hellozynq/b2_hw/build_b2.tcl",
            "test_b2_loopback_contract.py",
        ])
        self.assertFalse(scopes["full_repository"])


if __name__ == "__main__":
    unittest.main()

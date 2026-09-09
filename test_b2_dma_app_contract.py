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

    def test_build_is_bound_to_b2_xsa(self):
        self.assertIn("hello_zynq_b2.xsa", self.build)
        self.assertIn("hello_zynq_b2.bit", self.board)
        self.assertIn("xc7z020clg484-2", self.build)


if __name__ == "__main__":
    unittest.main()

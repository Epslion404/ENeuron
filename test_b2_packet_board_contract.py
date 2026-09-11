import unittest
from pathlib import Path

from tools.ci.classify_changes import classify_paths


ROOT = Path(__file__).resolve().parent


class B2PacketBoardContractTests(unittest.TestCase):
    def test_packet_board_sources_exist(self):
        self.assertTrue((ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").is_file())
        self.assertTrue((ROOT / "boards/hellozynq/b2_sw/run_b2_packet_board.ps1").is_file())

    def test_packet_board_contract_markers_are_present(self):
        source = (ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").read_text(encoding="utf-8")
        for token in (
            "B2_PACKET_BEGIN",
            "B2_PACKET_FENCE_PASS",
            "B2_PACKET_RESULT_PASS",
            "B2_PACKET_PASS",
            "ENB2",
            "OP_MODEL_BEGIN",
            "OP_MASK_BEGIN",
        ):
            self.assertIn(token, source)

    def test_packet_board_runner_checks_packet_marker(self):
        source = (ROOT / "boards/hellozynq/b2_sw/run_b2_packet_board.ps1").read_text(encoding="utf-8")
        self.assertIn("B2_PACKET_PASS", source)
        self.assertIn("VID_1A86", source)
        self.assertIn("hello_zynq_b2.bit", source)

    def test_changes_use_b2_board_scope(self):
        scopes = classify_paths([
            "boards/hellozynq/b2_sw/src/packet_main.c",
            "boards/hellozynq/b2_sw/run_b2_packet_board.ps1",
            "test_b2_packet_board_contract.py",
        ])
        self.assertTrue(scopes["full_repository"])


if __name__ == "__main__":
    unittest.main()

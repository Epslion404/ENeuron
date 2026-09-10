import unittest
from pathlib import Path

from tools.ci.classify_changes import classify_paths


ROOT = Path(__file__).resolve().parent


class B2PacketEgressContractTests(unittest.TestCase):
    def test_sources_exist(self):
        self.assertTrue((ROOT / "b2_packet_egress.sv").is_file())
        self.assertTrue((ROOT / "tb_b2_packet_egress.sv").is_file())

    def test_source_declares_response_and_result_framing(self):
        source = (ROOT / "b2_packet_egress.sv").read_text(encoding="utf-8")
        for token in (
            "TYPE_RESPONSE",
            "TYPE_RESULT",
            "rsp_last",
            "ERR_RESULT_METADATA",
            "crc32_word",
            "crc32_byte",
            "crc_byte_index",
            "crc_busy",
            "output_frame_words",
        ):
            self.assertIn(token, source)

    def test_bram_read_requests_are_registered_during_crc_gap(self):
        source = (ROOT / "b2_packet_egress.sv").read_text(encoding="utf-8")
        self.assertNotIn("assign response_mem_rd_en", source)
        self.assertNotIn("assign result_mem_rd_en", source)
        for token in (
            "response_mem_rd_en <= 1'b0",
            "result_mem_rd_en <= 1'b0",
            "output_index == HEADER_WORDS - 1",
            "response_mem_rd_en <= 1'b1",
            "result_mem_rd_en <= 1'b1",
        ):
            self.assertIn(token, source)

    def test_changes_use_t1_repro_scope(self):
        scopes = classify_paths(["b2_packet_egress.sv", "tb_b2_packet_egress.sv", "test_b2_packet_egress_contract.py"])
        self.assertTrue(scopes["t1_repro"])
        self.assertFalse(scopes["full_repository"])


if __name__ == "__main__":
    unittest.main()

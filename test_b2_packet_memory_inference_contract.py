import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class B2PacketMemoryInferenceContractTests(unittest.TestCase):
    def test_large_packet_buffers_request_block_ram(self):
        ingress = (ROOT / "b2_packet_ingress.sv").read_text(encoding="utf-8")
        self.assertGreaterEqual(
            len(__import__("re").findall(r'ram_style\s*=\s*"block"', ingress)),
            4,
        )
        self.assertTrue((ROOT / "b2_packet_bram.sv").is_file())
        bram = (ROOT / "b2_packet_bram.sv").read_text(encoding="utf-8")
        self.assertIn('MEMORY_PRIMITIVE("block")', bram)
        egress = (ROOT / "b2_packet_egress.sv").read_text(encoding="utf-8")
        self.assertIn("response_mem", egress)
        self.assertIn("result_mem", egress)
        self.assertIn("response_word_count + 1'b1 > RESPONSE_WORD_CAPACITY", egress)


if __name__ == "__main__":
    unittest.main()

import subprocess
import unittest
from pathlib import Path

from tools.ci.classify_changes import classify_paths


ROOT = Path(__file__).resolve().parent


class B2PacketIngressContractTests(unittest.TestCase):
    def test_sources_and_repro_entry_exist(self):
        self.assertTrue((ROOT / "b2_packet_ingress.sv").is_file())
        self.assertTrue((ROOT / "tb_b2_packet_ingress.sv").is_file())
        self.assertTrue((ROOT / "b2_packet_protocol.py").is_file())

    def test_source_declares_fixed_frame_and_outputs(self):
        source = (ROOT / "b2_packet_ingress.sv").read_text(encoding="utf-8")
        for token in (
            "MAGIC = 32'h3242_4e45",
            "MAX_PAYLOAD_BYTES = 4096 - HEADER_BYTES - CRC_BYTES",
            "crc32_word",
            "ERR_TLAST_EARLY",
            "ERR_TLAST_LATE",
            "ERR_BAD_CRC",
            "ST_CMD_OUT",
            "ST_SAMPLE_OUT",
        ):
            self.assertIn(token, source)

    def test_payload_ram_write_is_registered(self):
        source = (ROOT / "b2_packet_ingress.sv").read_text(encoding="utf-8")
        for token in (
            "payload_write_pending",
            "payload_write_bank",
            "payload_write_addr",
            "payload_write_data",
            "if (payload_write_pending)",
        ):
            self.assertIn(token, source)
        self.assertNotIn("payload_mem_bank0[payload_word_index >> 2] <= s_data", source)

    def test_changes_use_t1_repro_scope(self):
        scopes = classify_paths(["b2_packet_ingress.sv", "tb_b2_packet_ingress.sv", "test_b2_packet_ingress_contract.py"])
        self.assertTrue(scopes["t1_repro"])
        self.assertFalse(scopes["full_repository"])

    def test_repro_runner_executes_packet_ingress(self):
        result = subprocess.run(
            ["python", "-X", "utf8", "tools/repro/verify_repository.py", "--t1"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("REPRO_G1_T1_PROTOCOL_SLICE_PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()

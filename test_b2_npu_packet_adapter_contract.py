import unittest
from pathlib import Path

from tools.ci.classify_changes import classify_paths


ROOT = Path(__file__).resolve().parent


class B2NpuPacketAdapterContractTests(unittest.TestCase):
    def test_sources_and_repro_entry_exist(self):
        self.assertTrue((ROOT / "b2_npu_packet_adapter.sv").is_file())
        self.assertTrue((ROOT / "tb_b2_npu_packet_adapter.sv").is_file())

    def test_adapter_exposes_packet_stream_and_wrapper_boundary(self):
        source = (ROOT / "b2_npu_packet_adapter.sv").read_text(encoding="utf-8")
        for token in (
            "b2_packet_ingress",
            "npu_zynq7020_t1_wrapper",
            "b2_packet_egress",
            "cmd_sequence_reg",
            "sample_sequence_reg",
        ):
            self.assertIn(token, source)

    def test_changes_use_t1_repro_scope(self):
        scopes = classify_paths([
            "b2_npu_packet_adapter.sv",
            "tb_b2_npu_packet_adapter.sv",
            "test_b2_npu_packet_adapter_contract.py",
        ])
        self.assertTrue(scopes["t1_repro"])
        self.assertFalse(scopes["full_repository"])

    def test_repro_runner_executes_packet_adapter(self):
        import subprocess

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

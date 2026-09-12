import subprocess
import unittest
from pathlib import Path

from tools.ci.classify_changes import classify_paths


ROOT = Path(__file__).resolve().parent


class B2NpuPacketAdapterE2EContractTests(unittest.TestCase):
    def test_sources_exist(self):
        self.assertTrue((ROOT / "tb_b2_npu_packet_adapter_e2e.sv").is_file())

    def test_changes_use_t1_repro_scope(self):
        scopes = classify_paths([
            "tb_b2_npu_packet_adapter_e2e.sv",
            "test_b2_npu_packet_adapter_e2e_contract.py",
        ])
        self.assertTrue(scopes["t1_repro"])
        self.assertFalse(scopes["full_repository"])

    def test_repro_runner_executes_e2e_slice(self):
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

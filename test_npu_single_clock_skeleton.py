"""单时钟 NPU+ENeuron 协议骨架的 Icarus 冒烟测试。"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
IVERILOG = Path(r"C:\msys64\ucrt64\bin\iverilog.exe")
VVP = Path(r"C:\msys64\ucrt64\bin\vvp.exe")


class NpuSingleClockSkeletonTests(unittest.TestCase):
    def test_protocol_skeleton(self) -> None:
        self.assertTrue(IVERILOG.exists(), f"required Icarus path missing: {IVERILOG}")
        self.assertTrue(VVP.exists(), f"required vvp path missing: {VVP}")
        with tempfile.TemporaryDirectory(prefix="eneuron_npu_skeleton_") as temp:
            output = Path(temp) / "skeleton.vvp"
            compile_result = subprocess.run(
                [
                    str(IVERILOG),
                    "-g2012",
                    "-Wall",
                    "-s",
                    "tb_npu_eneuron_single_clock_skeleton",
                    "-o",
                    str(output),
                    "tb_npu_eneuron_single_clock_skeleton.sv",
                    "npu_eneuron_single_clock_skeleton.sv",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run_result = subprocess.run(
                [str(VVP), str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(run_result.returncode, 0, run_result.stdout + run_result.stderr)
            self.assertIn("PASS npu single-clock skeleton protocol", run_result.stdout)


if __name__ == "__main__":
    unittest.main()

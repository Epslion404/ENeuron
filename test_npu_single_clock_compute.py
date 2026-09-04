"""单时钟真实 INT8 计算 tracer 的 Icarus 测试。"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXED_IVERILOG = Path(r"C:\msys64\ucrt64\bin\iverilog.exe")
FIXED_VVP = Path(r"C:\msys64\ucrt64\bin\vvp.exe")


def find_tool(fixed: Path, name: str) -> Path | None:
    if fixed.exists():
        return fixed
    found = shutil.which(name)
    return Path(found) if found else None


class NpuSingleClockComputeTests(unittest.TestCase):
    def test_real_compute_tracer(self) -> None:
        iverilog = find_tool(FIXED_IVERILOG, "iverilog")
        vvp = find_tool(FIXED_VVP, "vvp")
        self.assertIsNotNone(iverilog, "Icarus unavailable")
        self.assertIsNotNone(vvp, "vvp unavailable")
        with tempfile.TemporaryDirectory(prefix="eneuron_npu_compute_") as temp:
            output = Path(temp) / "compute.vvp"
            compiled = subprocess.run(
                [str(iverilog), "-g2012", "-Wall", "-s", "tb_npu_eneuron_single_clock_compute", "-o", str(output),
                 "tb_npu_eneuron_single_clock_compute.sv", "npu_eneuron_single_clock_skeleton.sv"],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            ran = subprocess.run([str(vvp), str(output)], cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            self.assertIn("PASS npu single-clock real compute tracer", ran.stdout)


if __name__ == "__main__":
    unittest.main()

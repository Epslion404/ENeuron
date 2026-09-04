"""单时钟 mask epoch 垂直切片的 Icarus 测试。"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXED_IVERILOG = Path(r"C:\msys64\ucrt64\bin\iverilog.exe")
FIXED_VVP = Path(r"C:\msys64\ucrt64\bin\vvp.exe")


def find_hdl_tool(fixed_path: Path, name: str) -> Path | None:
    """Windows 使用约定的 MSYS2 路径，Linux/CI 使用 PATH 工具。"""
    if fixed_path.exists():
        return fixed_path
    discovered = shutil.which(name)
    return Path(discovered) if discovered else None


class NpuSingleClockMaskTests(unittest.TestCase):
    def test_mask_epoch_slice(self) -> None:
        iverilog = find_hdl_tool(FIXED_IVERILOG, "iverilog")
        vvp = find_hdl_tool(FIXED_VVP, "vvp")
        self.assertIsNotNone(iverilog, "Icarus unavailable")
        self.assertIsNotNone(vvp, "vvp unavailable")
        with tempfile.TemporaryDirectory(prefix="eneuron_npu_mask_") as temp:
            output = Path(temp) / "mask.vvp"
            compiled = subprocess.run(
                [str(iverilog), "-g2012", "-Wall", "-s", "tb_npu_eneuron_single_clock_mask", "-o", str(output),
                 "tb_npu_eneuron_single_clock_mask.sv", "npu_eneuron_single_clock_skeleton.sv"],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            ran = subprocess.run([str(vvp), str(output)], cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            self.assertIn("PASS npu single-clock mask epoch slice", ran.stdout)


if __name__ == "__main__":
    unittest.main()

"""单时钟 NPU+ENeuron 协议骨架的 Icarus 冒烟测试。"""

from __future__ import annotations

import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXED_IVERILOG = Path(r"C:\msys64\ucrt64\bin\iverilog.exe")
FIXED_VVP = Path(r"C:\msys64\ucrt64\bin\vvp.exe")


def find_hdl_tool(fixed_path: Path, name: str) -> Path | None:
    """Windows 优先使用项目约定的 MSYS2 路径，Linux/CI 回退到 PATH。"""
    if fixed_path.exists():
        return fixed_path
    discovered = shutil.which(name)
    return Path(discovered) if discovered else None


class NpuSingleClockSkeletonTests(unittest.TestCase):
    def test_protocol_skeleton(self) -> None:
        iverilog = find_hdl_tool(FIXED_IVERILOG, "iverilog")
        vvp = find_hdl_tool(FIXED_VVP, "vvp")
        self.assertIsNotNone(iverilog, f"Icarus unavailable; checked fixed path {FIXED_IVERILOG} and PATH")
        self.assertIsNotNone(vvp, f"vvp unavailable; checked fixed path {FIXED_VVP} and PATH")
        with tempfile.TemporaryDirectory(prefix="eneuron_npu_skeleton_") as temp:
            output = Path(temp) / "skeleton.vvp"
            compile_result = subprocess.run(
                [
                    str(iverilog),
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
                [str(vvp), str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(run_result.returncode, 0, run_result.stdout + run_result.stderr)
            self.assertIn("PASS npu single-clock skeleton protocol", run_result.stdout)


if __name__ == "__main__":
    unittest.main()

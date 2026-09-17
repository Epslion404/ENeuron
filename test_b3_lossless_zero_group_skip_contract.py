"""无损零组跳过切片的双配置 Icarus 合同。"""

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
    return fixed if fixed.exists() else (Path(shutil.which(name)) if shutil.which(name) else None)


class LosslessZeroGroupSkipContractTests(unittest.TestCase):
    def test_dense_and_lossless_outputs_match_with_expected_counters(self) -> None:
        iverilog = find_tool(FIXED_IVERILOG, "iverilog")
        vvp = find_tool(FIXED_VVP, "vvp")
        self.assertIsNotNone(iverilog, "iverilog unavailable")
        self.assertIsNotNone(vvp, "vvp unavailable")
        with tempfile.TemporaryDirectory(prefix="b3_lossless_zero_group_") as temp:
            for tag, define in (("dense", None), ("lossless", "LOSSLESS_ZERO_GROUP_SKIP")):
                output = Path(temp) / f"{tag}.vvp"
                command = [str(iverilog), "-g2012", "-Wall"]
                if define:
                    command.append(f"-D{define}")
                command += ["-s", "tb_b3_lossless_zero_group_skip", "-o", str(output),
                            "tb_b3_lossless_zero_group_skip.sv", "npu_eneuron_single_clock_skeleton.sv"]
                compiled = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
                self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                ran = subprocess.run([str(vvp), str(output)], cwd=ROOT, text=True,
                                     capture_output=True, check=False)
                self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
                self.assertIn("PASS lossless zero-group skip output/counters", ran.stdout)


if __name__ == "__main__":
    unittest.main()

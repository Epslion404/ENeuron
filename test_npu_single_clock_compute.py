"""单时钟真实 INT8 计算 tracer 的 Icarus 测试。"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
import re
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
    def _run_compute_tracer(self, contract: str | None) -> subprocess.CompletedProcess[str]:
        iverilog = find_tool(FIXED_IVERILOG, "iverilog")
        vvp = find_tool(FIXED_VVP, "vvp")
        self.assertIsNotNone(iverilog, "Icarus unavailable")
        self.assertIsNotNone(vvp, "vvp unavailable")
        with tempfile.TemporaryDirectory(prefix="eneuron_npu_compute_") as temp:
            output = Path(temp) / "compute.vvp"
            command = [str(iverilog), "-g2012", "-Wall"]
            if contract == "v1":
                command.append("-DTIMING_REPAIR_V1_CONTRACT")
            elif contract == "v2":
                command.append("-DTIMING_REPAIR_V2_CONTRACT")
            command.extend([
                "-s", "tb_npu_eneuron_single_clock_compute", "-o", str(output),
                "tb_npu_eneuron_single_clock_compute.sv", "npu_eneuron_single_clock_skeleton.sv",
            ])
            compiled = subprocess.run(
                command,
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            ran = subprocess.run([str(vvp), str(output)], cwd=ROOT, text=True, capture_output=True, check=False)
            return ran

    def test_real_compute_tracer(self) -> None:
        ran = self._run_compute_tracer(contract=None)
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertIn("PASS npu single-clock real compute tracer", ran.stdout)

    def test_timing_repair_v1_contract(self) -> None:
        """V1 的 1860/1856/676/1858 周期合同保留为历史反证。"""
        ran = self._run_compute_tracer(contract="v1")
        self.assertNotEqual(ran.returncode, 0, "V1 historical contract unexpectedly accepted by V2 RTL")
        self.assertIn("compute cycle mismatch got=1902 expected=1860", ran.stdout + ran.stderr)

    def test_timing_repair_v2_contract(self) -> None:
        ran = self._run_compute_tracer(contract="v2")
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertIn("PASS npu single-clock real compute tracer", ran.stdout)

    def test_v2_writeback_and_activation_latches_are_structural(self) -> None:
        rtl = (ROOT / "npu_eneuron_single_clock_skeleton.sv").read_text(encoding="utf-8")
        for index in range(4):
            self.assertRegex(rtl, rf"lane_activation_latched_{index}")
        self.assertIn("COMPUTE_L0_WRITEBACK", rtl)
        self.assertIn("COMPUTE_L1_WRITEBACK", rtl)
        self.assertEqual(rtl.count("hidden_values[compute_unit_index] <="), 1)
        self.assertEqual(rtl.count("logit_values[compute_unit_index] <="), 1)

    def test_four_explicit_dsp_products(self) -> None:
        rtl = (ROOT / "npu_eneuron_single_clock_skeleton.sv").read_text(encoding="utf-8")
        declarations = re.findall(
            r'\(\*\s*use_dsp\s*=\s*"yes"\s*\*\)\s*logic\s+signed\s+\[15:0\]\s+'
            r'(lane_product_[0-3])\s*;',
            rtl,
        )
        self.assertEqual(sorted(declarations), [f"lane_product_{index}" for index in range(4)])
        self.assertEqual(rtl.count('use_dsp = "yes"'), 4)
        self.assertNotRegex(rtl, r'use_dsp[^\n]*(mac_accumulator|lane_sum_latched)')

    def test_vivado_ooc_requires_exactly_four_dsps(self) -> None:
        script = (ROOT / "vivado_npu_single_clock_ooc.tcl").read_text(encoding="utf-8")
        self.assertIn("set expected_dsp 4", script)
        self.assertIn("REF_NAME == DSP48E1", script)
        self.assertIn("$dsp == $expected_dsp", script)
        self.assertIn("$dsp48_count == $expected_dsp", script)
        self.assertIn('$dsp_gate eq "PASS"', script)
        for key in ("EXPECTED_DSP", "DSP48E1_COUNT", "DSP_GATE"):
            self.assertIn(f'puts $fh "{key}=', script)


if __name__ == "__main__":
    unittest.main()

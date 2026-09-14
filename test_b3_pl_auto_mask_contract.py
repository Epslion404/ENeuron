"""B3 路线一合同：PL auto-mask 参考/顺序引擎与 PS 黄金 mask 逐 bit 对照。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from b3_fixed_vector_manifest import load_b3_manifest, model_words_from_manifest


ROOT = Path(__file__).resolve().parent
FIXED_IVERILOG = Path(r"C:\msys64\ucrt64\bin\iverilog.exe")
FIXED_VVP = Path(r"C:\msys64\ucrt64\bin\vvp.exe")
MULTI_INPUT_MANIFEST = ROOT / "tools" / "repro" / "b3_multi_input_manifest.json"
REFERENCE_RTL = ROOT / "eneuron_pl_auto_mask_reference.sv"
ENGINE_RTL = ROOT / "eneuron_pl_auto_mask_engine.sv"
GOLDEN_TB = "tb_b3_pl_auto_mask_golden.sv"
SMOKE_TB = "tb_eneuron_pl_auto_mask_reference.sv"
ENGINE_CYCLE_BUDGET = 2048


def find_tool(fixed: Path, name: str) -> Path | None:
    if fixed.exists():
        return fixed
    found = shutil.which(name)
    return Path(found) if found else None


class B3PlAutoMaskContractTests(unittest.TestCase):
    def _icarus(self) -> tuple[Path, Path]:
        iverilog = find_tool(FIXED_IVERILOG, "iverilog")
        vvp = find_tool(FIXED_VVP, "vvp")
        if iverilog is None or vvp is None:
            self.skipTest("Icarus Verilog unavailable")
        return iverilog, vvp

    def _compile_and_run(
        self,
        tb: str,
        plusargs: list[str],
        defines: tuple[str, ...] = (),
        extra_sources: tuple[Path, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        iverilog, vvp = self._icarus()
        with tempfile.TemporaryDirectory(prefix="eneuron_pl_auto_mask_") as temp:
            output = Path(temp) / "tb.vvp"
            command = [str(iverilog), "-g2012"]
            for define in defines:
                command.append(f"-D{define}")
            command.extend(["-o", str(output), str(REFERENCE_RTL)])
            command.extend(str(source) for source in extra_sources)
            command.append(str(ROOT / tb))
            compiled = subprocess.run(
                command, cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            return subprocess.run(
                [str(vvp), str(output)] + plusargs,
                cwd=ROOT, text=True, capture_output=True, check=False,
            )

    @staticmethod
    def _write_golden_files(temp_path: Path, samples: list[dict], model_words: tuple[int, ...]) -> list[str]:
        model_file = temp_path / "model.mem"
        pixel_file = temp_path / "pixels.mem"
        expected_file = temp_path / "expected.mem"
        model_file.write_text("".join(f"{word:08x}\n" for word in model_words), encoding="ascii")
        pixel_file.write_text(
            "".join(f"{pixel:x}\n" for sample in samples for pixel in sample["pixels"]),
            encoding="ascii",
        )
        expected_file.write_text(
            "".join(
                f"{int(word, 0):08x}\n"
                for sample in samples
                for word in sample["live_mask_words"]
            ),
            encoding="ascii",
        )
        return [
            f"+MODEL={model_file.as_posix()}",
            f"+PIXELS={pixel_file.as_posix()}",
            f"+EXPECTED={expected_file.as_posix()}",
        ]

    def _golden_samples(self) -> tuple[list[dict], tuple[int, ...]]:
        manifest = json.loads(MULTI_INPUT_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "eneuron_b3_multi_input_v1")
        samples = manifest["samples"]
        self.assertEqual(len(samples), 64)
        return samples, model_words_from_manifest(load_b3_manifest())

    def test_smoke_tiebreak_and_packing(self) -> None:
        ran = self._compile_and_run(SMOKE_TB, [])
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertIn("B3_PL_AUTO_MASK_REFERENCE_PASS", ran.stdout)

    def test_reference_64_inputs_match_ps_mask_words(self) -> None:
        samples, model_words = self._golden_samples()
        with tempfile.TemporaryDirectory(prefix="eneuron_pl_auto_mask_golden_") as temp:
            plusargs = self._write_golden_files(Path(temp), samples, model_words)
            ran = self._compile_and_run(GOLDEN_TB, plusargs)
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertIn("B3_PL_AUTO_MASK_GOLDEN_PASS samples=64", ran.stdout)

    def test_engine_64_inputs_match_ps_mask_words_and_cycle_budget(self) -> None:
        samples, model_words = self._golden_samples()
        with tempfile.TemporaryDirectory(prefix="eneuron_pl_auto_mask_engine_") as temp:
            plusargs = self._write_golden_files(Path(temp), samples, model_words)
            ran = self._compile_and_run(
                GOLDEN_TB,
                plusargs,
                defines=("PL_AUTO_MASK_ENGINE",),
                extra_sources=(ENGINE_RTL,),
            )
        self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
        self.assertIn("B3_PL_AUTO_MASK_GOLDEN_PASS samples=64", ran.stdout)
        match = re.search(r"B3_PL_AUTO_MASK_ENGINE_CYCLES=(\d+)", ran.stdout)
        self.assertIsNotNone(match, ran.stdout)
        cycles = int(match.group(1))
        self.assertLessEqual(cycles, ENGINE_CYCLE_BUDGET, f"engine cycle budget exceeded: {cycles}")


if __name__ == "__main__":
    unittest.main()

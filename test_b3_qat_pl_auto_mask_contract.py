"""QAT 模型上 standalone PL auto-mask 引擎的 Icarus 合同（缺 iverilog 时 skip）。"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools" / "repro"))

from b3_qat_pl_auto_mask_sim import (  # noqa: E402
    CYCLE_BUDGET,
    DEFAULT_MANIFEST,
    FIXED_IVERILOG,
    FIXED_VVP,
    run_sim,
    _find_tool,
)


class B3QatPlAutoMaskContractTests(unittest.TestCase):
    def test_engine_matches_python_live_mask_on_qat(self) -> None:
        if _find_tool(FIXED_IVERILOG, "iverilog") is None or _find_tool(FIXED_VVP, "vvp") is None:
            self.skipTest("Icarus Verilog unavailable")
        sim = run_sim(DEFAULT_MANIFEST)
        self.assertEqual(sim["returncode"], 0, sim["stdout"] + sim["stderr"])
        self.assertIn(f"B3_PL_AUTO_MASK_GOLDEN_PASS samples={sim['samples']}", sim["stdout"])
        self.assertIsNotNone(sim["cycles"])
        self.assertLessEqual(sim["cycles"], CYCLE_BUDGET)

    def test_sim_artifact_matches_engine_contract(self) -> None:
        artifact_path = ROOT / "artifacts" / "results" / "b3_qat_pl_auto_mask_sim.json"
        if not artifact_path.is_file():
            self.skipTest("QAT PL auto-mask sim artifact not generated")
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual(artifact["schema"], "eneuron_b3_qat_pl_auto_mask_sim_v1")
        self.assertEqual(artifact["status"], "SIM_PASS")
        self.assertEqual(artifact["samples"], 64)
        self.assertEqual(artifact["bit_exact"], 64)
        self.assertLessEqual(artifact["engine_cycles_per_sample"], artifact["cycle_budget"])


if __name__ == "__main__":
    unittest.main()

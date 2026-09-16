"""QAT-v3 无损零组跳过主 NPU RTL 合同。"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools" / "repro"))

from b3_qat_lossless_zero_group_rtl_sim import (  # noqa: E402
    DEFAULT_MANIFEST,
    DEFAULT_OUTPUT,
    FIXED_IVERILOG,
    FIXED_VVP,
    _find_tool,
    build_artifact,
    run_sim,
)


class B3QatLosslessZeroGroupRtlContractTests(unittest.TestCase):
    def test_qat_vectors_are_bit_exact_on_main_npu_fsm(self) -> None:
        if _find_tool(FIXED_IVERILOG, "iverilog") is None or _find_tool(FIXED_VVP, "vvp") is None:
            self.skipTest("Icarus Verilog unavailable")
        sim = run_sim(DEFAULT_MANIFEST)
        self.assertEqual(sim["returncode"], 0, sim["stdout"] + sim["stderr"])
        artifact = build_artifact(DEFAULT_MANIFEST, sim)
        self.assertEqual(artifact["status"], "SIM_PASS")
        self.assertEqual(artifact["samples"], 397)
        self.assertEqual(artifact["logit_exact_match"], 397)
        self.assertGreater(artifact["skip_rate"], 0.30)
        self.assertGreater(artifact["estimated_core_speedup"], 1.30)

    def test_saved_artifact_preserves_scope_boundary(self) -> None:
        if not DEFAULT_OUTPUT.is_file():
            self.skipTest("RTL simulation artifact not generated")
        artifact = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
        self.assertEqual(artifact["schema"], "eneuron_b3_qat_lossless_zero_group_rtl_sim_v1")
        self.assertEqual(artifact["status"], "SIM_PASS")
        self.assertIn("l0_relu_suffix_early_stop", artifact["excluded_rules"])
        self.assertIn("未做OOC", artifact["boundary"])


if __name__ == "__main__":
    unittest.main()

"""B3 剪枝后功率归因合同：只形成工程观察归因，不得越权关闭任何功耗门。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import b3_power_attribution as attr


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "artifacts/logs/b3_power_attribution_20260914_7cb5a4e"
COUNTS = EVIDENCE / "inputs/valid_inferences_from_pr96.json"
COMMITTED = EVIDENCE / "b3_power_attribution.json"


def _write_lf(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")


class B3PowerAttributionTests(unittest.TestCase):
    def test_committed_analysis_is_reproducible_from_bound_inputs(self) -> None:
        recomputed = attr.analyze(
            attr.DEFAULT_OBSERVATIONS, attr.DEFAULT_POWER_REPORT, extra_counts=COUNTS
        )
        committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
        self.assertEqual(committed, recomputed, "已归档的归因结果与输入不再一致")

    def test_analysis_never_carries_gate_authority(self) -> None:
        analysis = json.loads(COMMITTED.read_text(encoding="utf-8"))
        self.assertEqual(analysis["status"], "POWER_ATTRIBUTION_NOT_ESTABLISHED")
        self.assertEqual(analysis["power_gate"], "OPEN")
        self.assertEqual(analysis["power_goal_status"], "NOT_PROVEN")
        self.assertEqual(analysis["b3_power_measured"], "POWER_NOT_MEASURED")
        self.assertFalse(analysis["claim_boundary"]["pruning_power_benefit_proven"])
        self.assertFalse(analysis["claim_boundary"]["vivado_estimate_used_as_board_power"])
        self.assertEqual(analysis["claim_boundary"]["gate_closure_authority"], "none")
        self.assertTrue(any("PASS" in text for text in analysis["forbidden_claims"]))

    def test_observed_gaps_stay_below_same_config_repeatability(self) -> None:
        analysis = json.loads(COMMITTED.read_text(encoding="utf-8"))
        self.assertIsNotNone(analysis["same_config_repeatability_w"])
        for row in analysis["delta_vs_dense"].values():
            self.assertLess(abs(row["delta_power_w"]), analysis["same_config_repeatability_w"])
            self.assertFalse(row["exceeds_same_config_repeatability"])
        self.assertFalse(analysis["verdict_rules"]["gap_exceeds_same_config_repeatability"])

    def test_idle_baseline_inversion_is_reported_not_hidden(self) -> None:
        analysis = json.loads(COMMITTED.read_text(encoding="utf-8"))
        self.assertFalse(analysis["verdict_rules"]["idle_is_lowest_window"])
        self.assertIn("b3_live_eneuron", analysis["idle_inverted_load_windows"])

    def test_energy_per_inference_uses_only_bound_counts(self) -> None:
        analysis = json.loads(COMMITTED.read_text(encoding="utf-8"))
        live = analysis["energy_per_valid_inference"]["live"]
        self.assertAlmostEqual(live["energy_per_valid_inference_mj"], 0.2909335, places=6)
        self.assertLess(live["delta_vs_dense_mean_percent"], 0)
        for source in analysis["valid_inference_sources"]:
            self.assertEqual(len(source["source_canonical_lf_sha256"]), 64)
            self.assertTrue(source["source_ref"].startswith("codex/b3-power-manual-meter@"))
        idle = next(w for w in analysis["windows"] if w["mode"] == "b3_idle")
        self.assertIsNone(idle["energy_per_valid_inference_mj"], "idle 无有效推理，能耗必须留空")

    def test_missing_counts_are_never_invented(self) -> None:
        payload = json.loads(attr.DEFAULT_OBSERVATIONS.read_text(encoding="utf-8"))
        for item in payload["observations"]:
            item.pop("valid_inferences", None)
        with tempfile.TemporaryDirectory() as tmp:
            obs = Path(tmp) / "observations.json"
            _write_lf(obs, payload)
            analysis = attr.analyze(obs, attr.DEFAULT_POWER_REPORT)
        self.assertTrue(analysis["counts_from_mainline_rollup_only"])
        for window in analysis["windows"]:
            self.assertIsNone(window["energy_per_valid_inference_mj"])
            self.assertIsNone(window["npu_duty_percent"])
        self.assertEqual(analysis["energy_per_valid_inference"], {})

    def test_unbound_count_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare = Path(tmp) / "bare.json"
            _write_lf(bare, {"b3_dense_round_1": 9_000_000})
            with self.assertRaises(ValueError):
                attr.load_extra_counts(bare)
            loose = Path(tmp) / "loose.json"
            _write_lf(loose, {"inferences": [{"mode": "b3_dense_round_1", "valid_inferences": 1}]})
            with self.assertRaises(ValueError):
                attr.load_extra_counts(loose)

    def test_power_inconsistency_fails_closed(self) -> None:
        payload = json.loads(attr.DEFAULT_OBSERVATIONS.read_text(encoding="utf-8"))
        payload["observations"][1]["duration_s"] += 600
        with tempfile.TemporaryDirectory() as tmp:
            obs = Path(tmp) / "observations.json"
            _write_lf(obs, payload)
            with self.assertRaises(ValueError) as ctx:
                attr.load_observations(obs)
            self.assertIn("自洽失败", str(ctx.exception))

    def test_tool_does_not_read_vivado_power_reports(self) -> None:
        text = (ROOT / "b3_power_attribution.py").read_text(encoding="utf-8")
        self.assertNotIn("power_impl", text)
        self.assertNotIn("archive/legacy", text)


if __name__ == "__main__":
    unittest.main()

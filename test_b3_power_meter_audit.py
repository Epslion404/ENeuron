"""B3 功率计读数审计合同：只报缺陷与可辨识性，不改写冻结证据，不关闭任何门。"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import b3_power_meter_audit as audit


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "artifacts/logs/b3_power_meter_audit_20260914_7cb5a4e"
COMMITTED = EVIDENCE / "b3_power_meter_audit.json"
REPORT = ROOT / "docs/reports/B3_POWER_ATTRIBUTION_2026-09-14.md"
OBSERVATIONS = audit.DEFAULT_OBSERVATIONS
TOOL_SOURCE = (ROOT / "b3_power_meter_audit.py").read_text(encoding="utf-8-sig")

SAME_CONFIG_REPEATABILITY_MW = 11.15547
EFFECTS_MW = {
    "vivado_extrapolated_200mhz": 3.487,
    "vivado_raw_100mhz": 1.743,
    "observed_live": 9.944,
    "observed_static": 7.694,
}
CLAIMED_EFFECTS_MW = (EFFECTS_MW["observed_live"], EFFECTS_MW["observed_static"])


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _committed() -> dict[str, object]:
    return json.loads(COMMITTED.read_text(encoding="utf-8"))


class B3PowerMeterAuditTests(unittest.TestCase):
    def test_committed_audit_is_reproducible_from_frozen_input(self) -> None:
        recomputed = audit.analyze(
            OBSERVATIONS, sigma_pair_mw=SAME_CONFIG_REPEATABILITY_MW, effects_mw=EFFECTS_MW
        )
        self.assertEqual(_committed(), recomputed, "已归档的读数审计与输入不再一致")
        self.assertEqual(
            recomputed["inputs"]["observations_sha256_canonical_lf"],
            audit.canonical_lf_sha256(OBSERVATIONS),
        )

    def test_delta_mah_defect_is_reported_without_rewriting_evidence(self) -> None:
        raw_before = _raw_sha256(OBSERVATIONS)
        canonical_before = audit.canonical_lf_sha256(OBSERVATIONS)
        analysis = _committed()
        channels = analysis["channels"]
        self.assertTrue(channels["mwh_channel_self_consistent"], "delta_mWh 必须 5/5 与 readings 一致")
        self.assertFalse(channels["mah_field_self_consistent"])
        self.assertEqual(channels["defect_class"], "DELTA_MAH_FIELD_INCONSISTENT_WITH_READINGS")
        self.assertEqual(
            sorted(channels["windows_with_bad_mAh_field"]),
            ["b3_dense_round_1", "b3_dense_round_2", "b3_live_eneuron", "b3_static_mixed"],
        )
        for row in channels["per_window"]:
            if row["mode"] == "b3_idle":
                self.assertTrue(row["mah_matches_readings"])
                continue
            self.assertFalse(
                row["recorded_mAh_channel_plausible"],
                "抄错的 delta_mAh 必然给出物理上不可能的隐含电压，否则判据不成立",
            )
            self.assertTrue(row["readings_mAh_channel_plausible"])
            self.assertGreater(row["implied_voltage_v_from_recorded_mAh"], 5.5)
        self.assertTrue(analysis["claim_boundary"]["evidence_files_modified"] is False)
        self.assertEqual(channels["evidence_rewrite"], "forbidden")
        self.assertEqual(_raw_sha256(OBSERVATIONS), raw_before, "审计工具不得改写已冻结证据")
        self.assertEqual(canonical_before, audit.canonical_lf_sha256(OBSERVATIONS))
        audit.write_analysis(COMMITTED, analysis)
        self.assertEqual(_raw_sha256(OBSERVATIONS), raw_before)
        self.assertEqual(_committed(), analysis)

    def test_single_transcription_error_at_endpoint_dwarfs_claimed_effect(self) -> None:
        segments = _committed()["segments"]
        self.assertEqual(segments["segment_count"], 20)
        recoveries = segments["shared_reading_recoveries"]
        self.assertEqual(len(recoveries), 1)
        recovery = recoveries[0]
        self.assertEqual(recovery["mode"], "b3_dense_round_2")
        self.assertEqual(recovery["suspect_reading_at"], "20:04:13")
        self.assertGreater(recovery["single_reading_error_mWh"], 10.0)
        self.assertGreater(
            recovery["same_error_at_window_endpoint_power_error_mW"],
            3.0 * max(CLAIMED_EFFECTS_MW),
            "单个抄录错误落到端点必须远大于声称的处理效应，否则不构成阻断性缺陷",
        )
        self.assertGreater(
            recovery["same_error_at_window_endpoint_power_error_mW"],
            SAME_CONFIG_REPEATABILITY_MW,
        )
        self.assertEqual(segments["outlier_count"], 3)
        pair = [s for s in segments["outlier_segments"] if s["mode"] == "b3_dense_round_2"]
        self.assertEqual(len(pair), 2)
        self.assertGreater(pair[0]["deviation_mw"], 100.0)
        self.assertLess(pair[1]["deviation_mw"], -100.0)

    def test_display_quantization_is_coarser_and_accumulator_finer_than_effect(self) -> None:
        segments = _committed()["segments"]
        smallest_effect = min(CLAIMED_EFFECTS_MW)
        self.assertLessEqual(segments["displayed_power_distinct_values"], 8)
        self.assertEqual(len(segments["displayed_current_distinct_values"]), 3)
        self.assertGreater(segments["displayed_current_lsb_power_mw"], max(CLAIMED_EFFECTS_MW))
        self.assertLess(max(segments["endpoint_half_count_resolution_mw"].values()), smallest_effect)
        self.assertLess(min(segments["energy_accumulator_resolution_mw"].values()), smallest_effect)

    def test_treatment_level_is_rank_collinear_with_clock_time(self) -> None:
        ident = _committed()["identifiability"]
        self.assertEqual(ident["discordant_level_time_pairs"], 0)
        self.assertTrue(ident["level_and_time_rank_collinear"])
        self.assertEqual(ident["verdict"], "TREATMENT_NOT_IDENTIFIABLE_FROM_WINDOW_MEANS")
        self.assertGreater(ident["linear_time_fit"]["r2"], 0.5)
        self.assertGreater(abs(ident["linear_time_fit"]["slope_t_stat"]), 2.0)
        self.assertLess(ident["linear_time_fit"]["slope_mw_per_h"], 0.0)
        self.assertEqual(ident["measurement_order"][0], "b3_idle")
        self.assertEqual(ident["measurement_order"][-1], "b3_live_eneuron")
        self.assertEqual(ident["pruning_level_sequence"], [0, 1, 1, 2, 3])

    def test_detrended_residual_sign_depends_on_drift_convention(self) -> None:
        ident = _committed()["identifiability"]
        self.assertGreater(
            ident["same_config_drift_rate_mw_per_h"],
            abs(ident["linear_time_fit"]["slope_mw_per_h"]),
        )
        for mode in ("b3_static_mixed", "b3_live_eneuron"):
            row = ident["detrended_effect"][mode]
            self.assertGreater(row["observed_drop_mw"], 0.0)
            self.assertLess(row["observed_drop_mw"], SAME_CONFIG_REPEATABILITY_MW)
            self.assertFalse(row["sign_stable_across_drift_convention"])
            self.assertGreater(row["detrended_using_regression_rate_mw"], 0.0)
            self.assertLess(row["detrended_using_same_config_rate_mw"], 0.0)
            self.assertLess(
                row["detrended_using_regression_rate_mw"], row["observed_drop_mw"]
            )

    def test_contract_v2_five_rounds_are_underpowered_for_predicted_effects(self) -> None:
        power = _committed()["power_analysis"]
        self.assertAlmostEqual(power["sigma_pair_mw"], SAME_CONFIG_REPEATABILITY_MW, places=3)
        self.assertGreater(power["contract_v2_detectable_effect_mw"], EFFECTS_MW["observed_static"])
        ladder = power["detectable_effect_mw_at_rounds"]
        self.assertEqual(power["contract_v2_detectable_effect_mw"], ladder["5"])
        for left, right in (("5", "20"), ("20", "80"), ("80", "320")):
            self.assertGreater(ladder[left], ladder[right])
        for effect, rounds in power["required_rounds_per_mode"].items():
            self.assertGreater(rounds, power["contract_v2_planned_rounds"], effect)
        self.assertGreater(power["required_rounds_per_mode"]["vivado_raw_100mhz"], 100)

    def test_audit_never_upgrades_measurement_or_reuses_vivado_reports(self) -> None:
        analysis = _committed()
        self.assertEqual(analysis["status"], "POWER_METER_READING_AUDIT_COMPLETE")
        self.assertEqual(analysis["b3_power_measured"], "POWER_NOT_MEASURED")
        self.assertEqual(analysis["power_gate"], "OPEN")
        self.assertEqual(analysis["power_goal_status"], "NOT_PROVEN")
        self.assertEqual(analysis["gate_closure_authority"], "none")
        self.assertFalse(analysis["claim_boundary"]["vivado_estimate_used_as_board_power"])
        self.assertEqual(analysis["claim_boundary"]["measurement_point"], "Type-C 整板输入，非 PL 轨")
        self.assertIn("PASS", "".join(analysis["forbidden_claims"]))
        for needle in ("power_impl", "archive/legacy", "import b3_power_attribution"):
            self.assertNotIn(needle, TOOL_SOURCE)
        self.assertEqual(len(analysis["findings"]), 5)
        self.assertEqual(len(analysis["forbidden_claims"]), 5)

    def test_report_documents_reading_level_audit_and_renumbered_review(self) -> None:
        text = REPORT.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        self.assertIn("## 8. 读数级审计", text)
        self.assertIn("## 9. 复核", text)
        self.assertIn("b3_power_meter_audit.py", text)
        self.assertIn("delta_mAh", text)
        self.assertIn("反序对", text)
        self.assertEqual(text.count("## 8. 复核"), 0)



    def test_audit_fails_closed_on_malformed_readings(self) -> None:
        payload = json.loads(OBSERVATIONS.read_text(encoding="utf-8"))
        healthy = payload["observations"]
        audit.build_audit(
            healthy, sigma_pair_mw=SAME_CONFIG_REPEATABILITY_MW, effects_mw=EFFECTS_MW
        )
        cases = [
            (lambda w: w.__setitem__("readings", w["readings"][:1]), "readings"),
            (lambda w: w.__setitem__("delta_mWh", int(w["delta_mWh"]) + 1), "delta_mWh"),
            (lambda w: w["readings"].__setitem__(1, list(w["readings"][0])), "段时长"),
            (lambda w: w.__setitem__("mode", "b3_unknown"), "五窗口"),
        ]
        for mutate, needle in cases:
            broken = json.loads(json.dumps(healthy))
            target = next(w for w in broken if w["mode"] == "b3_idle")
            mutate(target)
            with self.assertRaises(audit.AuditInputError) as ctx:
                audit.build_audit(
                    broken, sigma_pair_mw=SAME_CONFIG_REPEATABILITY_MW, effects_mw=EFFECTS_MW
                )
            self.assertIn(needle, str(ctx.exception))



if __name__ == "__main__":
    unittest.main()
"""B3-POWER 合同：保留历史三模式报告，并冻结 CP8 四态与 B10 仪器口径。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from b3_mvp_report import (
    POWER_CONTRACT_FIELDS,
    POWER_MODES,
    build_power_report,
    forbid_vivado_as_board_power,
    load_power_contract,
    record_from_artifacts,
)


def _probe(execute: int, skip: int, cycles: int) -> str:
    return "\n".join([
        "B2_NPU_RUNTIME_STATUS=1",
        "B2_NPU_ACTIVE_MASK_EPOCH=1",
        "B2_NPU_PENDING_MASK_EPOCH=0",
        f"B2_NPU_LAST_COMPUTE_CYCLES={cycles}",
        "B2_NPU_PROTOCOL_ERROR_COUNT=0",
        f"B2_NPU_EXECUTE_GROUP_COUNT={execute}",
        f"B2_NPU_SKIP_GROUP_COUNT={skip}",
    ])


def _row(mode: str, *, cycles: int, execute: int, skip: int, logits: tuple[int, ...], source: str) -> dict[str, object]:
    return record_from_artifacts(
        mode=mode,
        run_manifest={"status": "PASS", "elf_sha256": "e", "bitstream_sha256": "b"},
        probe_text=_probe(execute, skip, cycles),
        logits=logits,
        decision_source=source,
    )


def _open_contract() -> dict[str, object]:
    return {
        "schema": "eneuron_b3_power_instrument_contract_v1",
        "status": "POWER_NOT_MEASURED",
        "仪器": None,
        "测点": None,
        "采样率": None,
        "空闲基线": None,
        "负载同步": None,
        "积分窗口": None,
    }


def _power_rows() -> dict[str, dict[str, object]]:
    return {
        "b3_dense": _row(
            "b3_dense", cycles=2494, execute=592, skip=0,
            logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
            source="none_full_open_or_dense",
        ),
        "b3_static_mixed": _row(
            "b3_static_mixed", cycles=1606, execute=296, skip=296,
            logits=(74, -18, 14, 0, 0, 0, 0, 0, 0, 114),
            source="host_replay_static_mixed",
        ),
        "b3_live_eneuron": _row(
            "b3_live_eneuron", cycles=1606, execute=296, skip=296,
            logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
            source="live_eneuron_s2",
        ),
    }


class B3PowerReportContractTests(unittest.TestCase):
    def test_current_docs_separate_power_measurement_from_goal_gate(self) -> None:
        root = Path(__file__).resolve().parent
        todo = (root / "docs/planning/TODO.md").read_text(encoding="utf-8")
        current = (root / "docs/CURRENT_STATUS.md").read_text(encoding="utf-8")
        self.assertIn("- [ ] B3-POWER-MEASURED", todo)
        self.assertIn("- [ ] B3-POWER-GATE", todo)
        self.assertIn("B3-POWER-MEASURED", current)
        self.assertIn("B3-POWER-GATE", current)
        self.assertNotIn("B3_POWER_PASS", current)

    def test_committed_power_report_stays_not_measured(self) -> None:
        path = Path(__file__).resolve().parent / "artifacts/logs/b3_power_20260913_be84596/b3_power_report.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "POWER_NOT_MEASURED")
        self.assertEqual(data["power_goal_status"], "NOT_PROVEN")
        self.assertEqual(data["power_gate"], "OPEN")
        self.assertEqual(data["modes"], list(POWER_MODES))
        forbid_vivado_as_board_power(data)
        rows = {row["mode"]: row for row in data["rows"]}
        self.assertNotEqual(rows["b3_live_eneuron"]["decision_source"], rows["b3_static_mixed"]["decision_source"])
        for field in POWER_CONTRACT_FIELDS:
            self.assertIn(field, data["contract"])

    def test_shipped_contract_names_six_fields_verbatim(self) -> None:
        path = Path(__file__).resolve().parent / "tools/repro/b3_power_instrument_contract.json"
        contract = load_power_contract(path)
        self.assertEqual(contract["schema"], "eneuron_b3_power_instrument_contract_v1")
        for field in POWER_CONTRACT_FIELDS:
            self.assertIn(field, contract)
        self.assertEqual(POWER_CONTRACT_FIELDS, ("仪器", "测点", "采样率", "空闲基线", "负载同步", "积分窗口"))
        self.assertEqual(contract["status"], "POWER_NOT_MEASURED")

    def test_cp8_contract_freezes_b10_instrument_and_four_states(self) -> None:
        path = Path(__file__).resolve().parent / "tools/repro/b3_power_instrument_contract.json"
        contract = load_power_contract(path)
        self.assertEqual(contract["status"], "POWER_NOT_MEASURED")
        self.assertEqual(contract["measurement_status"], "MEASUREMENT_OPEN")
        self.assertIn("B10", contract["instrument"]["name"])
        self.assertLessEqual(contract["instrument"]["accuracy_percent_max"], 0.2)
        self.assertIn("Type-C", contract["measurement_point"]["location"])
        self.assertIn("not pure NPU", contract["measurement_point"]["scope"])
        self.assertEqual(
            contract["cp8_states"],
            [
                "dense_idle",
                "dense_continuous_full",
                "lossless_idle",
                "lossless_continuous_full",
            ],
        )
        self.assertEqual(contract["paired_rounds_min"], 5)
        self.assertEqual(contract["paired_order"], "alternating")
        self.assertIn("identical", contract["jtag_ps_state"])
        self.assertIn("CP5b", contract["full_load"]["replay"])
        self.assertEqual(contract["full_load"]["warmup_samples"], 1000)
        self.assertFalse(contract["full_load"]["ps_per_sample_decision"])
        for metric in (
            "whole_board_average_power_w",
            "mode_matched_idle_to_full_incremental_power_w",
            "whole_board_energy_per_correct_inference_j",
            "mode_matched_incremental_energy_per_correct_inference_j",
            "instrument_resolvability",
        ):
            self.assertIn(metric, contract["metrics"])
        self.assertIn("pure NPU power", contract["forbidden_attribution"])
        self.assertNotIn("b3_static_mixed", contract["cp8_states"])
        self.assertNotIn("b3_live_eneuron", contract["cp8_states"])
        self.assertIn("photo/manual-observation manifest", contract["close_boundary"])

        power_contract = (
            Path(__file__).resolve().parent
            / "docs/planning/NPU_B3_POWER_INSTRUMENT_CONTRACT_V1.md"
        ).read_text(encoding="utf-8")
        self.assertIn("整板总能耗/正确推理", power_contract)
        self.assertIn("mode-matched 增量能耗/正确推理", power_contract)

        nexus = json.loads(
            (
                Path(__file__).resolve().parent
                / ".nexus-map/concepts/b2_packet_npu.json"
            ).read_text(encoding="utf-8")
        )
        optimization = nexus["b3_goal_optimization_line"]
        self.assertIn("HISTORICAL_PRE_CP5B", optimization["scope"])
        self.assertIn("dense idle/full and lossless idle/full", optimization["items"]["B3-21"])
        self.assertNotIn("idle/dense/static/live", optimization["items"]["B3-21"])

    def test_missing_contract_field_is_rejected(self) -> None:
        contract = _open_contract()
        del contract["测点"]
        with self.assertRaises(ValueError) as ctx:
            build_power_report(_power_rows(), contract)
        self.assertIn("测点", str(ctx.exception))

    def test_dense_static_live_stay_on_separate_rows(self) -> None:
        report = build_power_report(_power_rows(), _open_contract())
        self.assertEqual(report["modes"], list(POWER_MODES))
        self.assertEqual([row["mode"] for row in report["rows"]], list(POWER_MODES))
        rows = {row["mode"]: row for row in report["rows"]}
        self.assertEqual(rows["b3_live_eneuron"]["decision_source"], "live_eneuron_s2")
        self.assertEqual(rows["b3_static_mixed"]["decision_source"], "host_replay_static_mixed")
        self.assertNotEqual(
            rows["b3_live_eneuron"]["decision_source"],
            rows["b3_static_mixed"]["decision_source"],
        )
        self.assertEqual(report["status"], "POWER_NOT_MEASURED")
        self.assertEqual(report["power_goal_status"], "NOT_PROVEN")
        self.assertEqual(report["power_gate"], "OPEN")

    def test_live_must_not_collapse_into_static(self) -> None:
        rows = _power_rows()
        rows["b3_live_eneuron"]["decision_source"] = "host_replay_static_mixed"
        with self.assertRaises(ValueError):
            build_power_report(rows, _open_contract())

    def test_vivado_estimate_is_not_board_power(self) -> None:
        report = {
            "status": "MEASURED",
            "power_source": "vivado",
            "on_chip_power_w": 0.112,
        }
        with self.assertRaises(ValueError) as ctx:
            forbid_vivado_as_board_power(report)
        self.assertIn("vivado", str(ctx.exception).lower())
        rows = _power_rows()
        rows["b3_dense"]["power_source"] = "vivado_estimate"
        rows["b3_dense"]["external_power_w"] = 0.2
        rows["b3_static_mixed"]["external_power_w"] = 0.1
        rows["b3_live_eneuron"]["external_power_w"] = 0.1
        contract = _open_contract()
        contract["status"] = "MEASURED"
        contract["仪器"] = "fake"
        with self.assertRaises(ValueError):
            build_power_report(rows, contract)

    def test_cannot_close_power_without_traces_or_not_measured(self) -> None:
        contract = _open_contract()
        contract["status"] = "PASS"
        with self.assertRaises(ValueError) as ctx:
            build_power_report(_power_rows(), contract)
        self.assertIn("POWER_NOT_MEASURED", str(ctx.exception))
        measured = _open_contract()
        measured["status"] = "MEASURED"
        measured["仪器"] = "meter"
        measured["测点"] = "J1"
        measured["采样率"] = "1 kS/s"
        measured["空闲基线"] = "10 s idle"
        measured["负载同步"] = "UART B2_PACKET_BEGIN"
        measured["积分窗口"] = "sample window"
        with self.assertRaises(ValueError) as missing:
            build_power_report(_power_rows(), measured)
        self.assertIn("external_power_w", str(missing.exception))

    def test_measured_requires_populated_instrument_contract(self) -> None:
        measured = _open_contract()
        measured["status"] = "MEASURED"
        rows = _power_rows()
        for row in rows.values():
            row["external_power_w"] = 1.0
            row["power_source"] = "external_meter"
            row["external_trace"] = "trace.csv"
        with self.assertRaises(ValueError) as ctx:
            build_power_report(rows, measured)
        self.assertIn("仪器", str(ctx.exception))

    def test_measured_requires_external_source_and_trace_for_every_mode(self) -> None:
        measured = _open_contract()
        measured.update({
            "status": "MEASURED",
            "仪器": "meter",
            "测点": "board input",
            "采样率": "1 kS/s",
            "空闲基线": "10 s idle",
            "负载同步": "GPIO marker",
            "积分窗口": "100 samples",
        })
        rows = _power_rows()
        for row in rows.values():
            row["external_power_w"] = 1.0
            row["power_source"] = "external_meter"
            row["external_trace"] = "trace.csv"
        del rows["b3_live_eneuron"]["external_trace"]
        with self.assertRaises(ValueError) as ctx:
            build_power_report(rows, measured)
        self.assertIn("external_trace", str(ctx.exception))

    def test_measured_data_does_not_by_itself_close_power_goal(self) -> None:
        measured = _open_contract()
        measured.update({
            "status": "MEASURED",
            "仪器": "meter",
            "测点": "board input",
            "采样率": "1 kS/s",
            "空闲基线": "10 s idle",
            "负载同步": "GPIO marker",
            "积分窗口": "100 samples",
        })
        rows = _power_rows()
        for mode, power_w in (
            ("b3_dense", 1.0),
            ("b3_static_mixed", 0.9),
            ("b3_live_eneuron", 1.1),
        ):
            rows[mode]["external_power_w"] = power_w
            rows[mode]["power_source"] = "external_meter"
            rows[mode]["external_trace"] = f"{mode}.csv"

        report = build_power_report(rows, measured)

        self.assertEqual(report["status"], "MEASURED")
        self.assertEqual(report["power_goal_status"], "NOT_PROVEN")
        self.assertEqual(report["power_gate"], "OPEN")


if __name__ == "__main__":
    unittest.main()

"""B3-POWER 合同：六字段仪器合同、dense/static/live 分行，禁止 Vivado 冒充板上功耗。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from b3_mvp_report import (
    POWER_CONTRACT_FIELDS,
    POWER_MODES,
    build_manual_power_report,
    build_power_report,
    calculate_manual_power_window,
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


def _manual_window(mode: str, round_index: int) -> dict[str, object]:
    delta_by_mode = {
        "b3_idle": 250,
        "b3_dense": 300,
        "b3_static_mixed": 270,
        "b3_live_eneuron": 260,
    }
    valid_by_mode = {
        "b3_idle": 0,
        "b3_dense": 12000,
        "b3_static_mixed": 15000,
        "b3_live_eneuron": 14000,
    }
    start_mwh = 1000 + round_index * 2000
    return {
        "mode": mode,
        "round": round_index,
        "duration_seconds": 600,
        "start_mwh": start_mwh,
        "end_mwh": start_mwh + delta_by_mode[mode],
        "start_mah": 200,
        "end_mah": 260,
        "voltage_start_v": 5.0,
        "voltage_end_v": 5.0,
        "valid_inferences": valid_by_mode[mode],
        "protocol_error_count": 0,
        "jtag_physically_connected": True,
        "xsct_active_during_window": False,
        "hw_server_active_during_window": False,
        "start_photo": f"round{round_index}-{mode}-start.jpg",
        "end_photo": f"round{round_index}-{mode}-end.jpg",
        "manual_observation_csv": f"round{round_index}-{mode}.csv",
    }


class B3PowerReportContractTests(unittest.TestCase):
    def test_manual_report_requires_five_complete_rounds_and_keeps_goal_open(self) -> None:
        root = Path(__file__).resolve().parent
        contract = load_power_contract(root / "tools/repro/b3_power_instrument_contract.json")
        contract["status"] = "MEASURED"
        forward = ("b3_idle", "b3_dense", "b3_static_mixed", "b3_live_eneuron")
        windows = []
        for round_index in range(1, 6):
            order = forward if round_index % 2 else tuple(reversed(forward))
            windows.extend(_manual_window(mode, round_index) for mode in order)

        report = build_manual_power_report(windows, contract)

        self.assertEqual(report["schema"], "eneuron_b3_manual_power_report_v2")
        self.assertEqual(report["round_count"], 5)
        self.assertEqual(report["status"], "MEASURED")
        self.assertEqual(report["power_goal_status"], "NOT_PROVEN")
        self.assertEqual(report["power_gate"], "OPEN")
        self.assertEqual(report["summaries"]["b3_dense"]["median_average_power_w"], 1.8)
        self.assertEqual(report["summaries"]["b3_live_eneuron"]["median_energy_per_inference_mj"], 66.85714285714286)

    def test_manual_report_rejects_non_alternating_round_order(self) -> None:
        root = Path(__file__).resolve().parent
        contract = load_power_contract(root / "tools/repro/b3_power_instrument_contract.json")
        contract["status"] = "MEASURED"
        windows = [
            _manual_window(mode, round_index)
            for round_index in range(1, 6)
            for mode in ("b3_idle", "b3_dense", "b3_static_mixed", "b3_live_eneuron")
        ]
        with self.assertRaisesRegex(ValueError, "alternating mode order"):
            build_manual_power_report(windows, contract)

    def test_manual_cumulative_window_calculates_board_power_and_energy(self) -> None:
        result = calculate_manual_power_window({
            "mode": "b3_dense",
            "round": 1,
            "duration_seconds": 600,
            "start_mwh": 1000,
            "end_mwh": 1300,
            "start_mah": 200,
            "end_mah": 260,
            "voltage_start_v": 5.0,
            "voltage_end_v": 5.0,
            "valid_inferences": 12000,
            "protocol_error_count": 0,
            "jtag_physically_connected": True,
            "xsct_active_during_window": False,
            "hw_server_active_during_window": False,
            "start_photo": "round1-dense-start.jpg",
            "end_photo": "round1-dense-end.jpg",
            "manual_observation_csv": "round1-dense.csv",
        })

        self.assertEqual(result["delta_mwh"], 300)
        self.assertEqual(result["average_power_w"], 1.8)
        self.assertEqual(result["energy_per_inference_mj"], 90.0)
        self.assertEqual(result["power_source"], "manual_cumulative_meter")

        too_short = dict(result)
        too_short["start_mwh"] = 1000
        too_short["end_mwh"] = 1199
        with self.assertRaisesRegex(ValueError, "200 mWh"):
            calculate_manual_power_window(too_short)

    def test_current_docs_separate_power_measurement_from_goal_gate(self) -> None:
        root = Path(__file__).resolve().parent
        todo = (root / "docs/planning/TODO.md").read_text(encoding="utf-8")
        current = (root / "docs/CURRENT_STATUS.md").read_text(encoding="utf-8")
        contract = root / "docs/planning/NPU_B3_POWER_INSTRUMENT_CONTRACT_V2.md"
        self.assertIn("- [ ] B3-POWER-MEASURED", todo)
        self.assertIn("- [ ] B3-POWER-GATE", todo)
        self.assertIn("NPU_B3_POWER_INSTRUMENT_CONTRACT_V2.md", todo)
        self.assertNotIn("B3-POWER-GATE：测量前补冻重复次数", todo)
        self.assertIn("B3-POWER-MEASURED", current)
        self.assertIn("B3-POWER-GATE", current)
        self.assertNotIn("B3_POWER_PASS", current)
        self.assertTrue(contract.is_file())
        self.assertIn("run_b3_power_manual.ps1", contract.read_text(encoding="utf-8"))

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
        self.assertEqual(contract["schema"], "eneuron_b3_power_instrument_contract_v2")
        for field in POWER_CONTRACT_FIELDS:
            self.assertIn(field, contract)
        self.assertEqual(POWER_CONTRACT_FIELDS, ("仪器", "测点", "采样率", "空闲基线", "负载同步", "积分窗口"))
        self.assertEqual(contract["measurement_method"], "manual_cumulative_meter")
        self.assertEqual(contract["display_resolution"]["mwh"], 1)
        self.assertEqual(contract["display_resolution"]["mah"], 1)
        self.assertEqual(contract["display_resolution"]["voltage_v"], 0.00001)
        self.assertEqual(contract["minimum_delta_mwh"], 200)
        self.assertEqual(contract["minimum_duration_seconds"], 300)
        self.assertEqual(contract["minimum_rounds"], 5)
        self.assertEqual(
            contract["round_order"]["odd"],
            ["b3_idle", "b3_dense", "b3_static_mixed", "b3_live_eneuron"],
        )
        self.assertEqual(
            contract["round_order"]["even"],
            ["b3_live_eneuron", "b3_static_mixed", "b3_dense", "b3_idle"],
        )
        self.assertFalse(contract["jtag_window_state"]["xsct_active"])
        self.assertFalse(contract["jtag_window_state"]["hw_server_active"])
        self.assertEqual(contract["status"], "POWER_NOT_MEASURED")

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

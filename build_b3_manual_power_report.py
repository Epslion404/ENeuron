"""从人工抄录的累计功率计 CSV 生成 B3 功耗报告。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from b3_mvp_report import build_manual_power_report, load_power_contract


INTEGER_FIELDS = (
    "round",
    "duration_seconds",
    "start_mwh",
    "end_mwh",
    "start_mah",
    "end_mah",
    "valid_inferences",
    "protocol_error_count",
)
FLOAT_FIELDS = (
    "voltage_start_v",
    "voltage_end_v",
    "current_start_a",
    "current_end_a",
    "power_start_w",
    "power_end_w",
)
BOOLEAN_FIELDS = (
    "jtag_physically_connected",
    "xsct_active_during_window",
    "hw_server_active_during_window",
)
TEXT_FIELDS = (
    "mode",
    "start_photo",
    "end_photo",
    "meter_trace_csv",
    "board_result_manifest",
    "instrument_model",
    "instrument_accuracy",
    "power_source_description",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_bool(value: str, field: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{field} must be true or false")


def load_windows(path: Path) -> list[dict[str, object]]:
    windows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = set(INTEGER_FIELDS + FLOAT_FIELDS + BOOLEAN_FIELDS + TEXT_FIELDS)
        missing = sorted(required - set(reader.fieldnames or ()))
        if missing:
            raise ValueError(f"manual power CSV missing columns: {missing}")
        for line_number, raw in enumerate(reader, start=2):
            try:
                row: dict[str, object] = {field: int(raw[field]) for field in INTEGER_FIELDS}
                row.update({field: float(raw[field]) for field in FLOAT_FIELDS})
                row.update({field: parse_bool(raw[field], field) for field in BOOLEAN_FIELDS})
                row.update({field: raw[field].strip() for field in TEXT_FIELDS})
                for evidence_field in (
                    "start_photo",
                    "end_photo",
                    "meter_trace_csv",
                    "board_result_manifest",
                ):
                    evidence_path = Path(str(row[evidence_field]))
                    if not evidence_path.is_absolute():
                        evidence_path = path.parent / evidence_path
                    if not evidence_path.is_file():
                        raise ValueError(f"missing {evidence_field}: {evidence_path}")
                    row[evidence_field] = str(evidence_path.resolve())
                    row[f"{evidence_field}_sha256"] = sha256_file(evidence_path)

                manifest = json.loads(Path(str(row["board_result_manifest"])).read_text(encoding="utf-8-sig"))
                if (
                    manifest.get("status") != "PASS"
                    or int(manifest.get("round", -1)) != int(row["round"])
                    or manifest.get("mode") != row["mode"]
                ):
                    raise ValueError("board_result_manifest does not match a passing window")

                with Path(str(row["meter_trace_csv"])).open(
                    "r", encoding="utf-8-sig", newline=""
                ) as trace_handle:
                    trace_rows = list(csv.DictReader(trace_handle))
                expected_schedule = list(range(0, int(row["duration_seconds"]), 60))
                expected_schedule.append(int(row["duration_seconds"]))
                observed_schedule = [int(trace["scheduled_elapsed_seconds"]) for trace in trace_rows]
                if observed_schedule != expected_schedule:
                    raise ValueError("meter_trace_csv must contain start, every minute, and end")
                if trace_rows[0].get("kind") != "start" or trace_rows[-1].get("kind") != "end":
                    raise ValueError("meter_trace_csv start/end markers are invalid")
                row["manual_observation_csv"] = str(path.resolve())
                windows.append(row)
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"manual power CSV line {line_number}: {error}") from error
    return windows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="人工窗口 CSV")
    parser.add_argument("--output", type=Path, required=True, help="输出 JSON")
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path(__file__).resolve().parent / "tools/repro/b3_power_instrument_contract.json",
    )
    arguments = parser.parse_args()

    input_path = arguments.input.resolve()
    contract_path = arguments.contract.resolve()
    contract = load_power_contract(contract_path)
    measurement_contract = dict(contract)
    measurement_contract["status"] = "MEASURED"
    report = build_manual_power_report(load_windows(input_path), measurement_contract)
    report["source_csv"] = str(input_path)
    report["source_csv_sha256"] = sha256_file(input_path)
    report["contract"] = contract
    report["contract_sha256"] = sha256_file(contract_path)
    report["measurement_contract_status"] = measurement_contract["status"]
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"B3_MANUAL_POWER_REPORT={arguments.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

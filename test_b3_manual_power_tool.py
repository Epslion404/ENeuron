from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class B3ManualPowerToolTests(unittest.TestCase):
    def test_cli_builds_hashed_report_from_five_complete_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            csv_path = temp / "manual_power.csv"
            output_path = temp / "report.json"
            fieldnames = (
                "round", "mode", "duration_seconds", "start_mwh", "end_mwh",
                "start_mah", "end_mah", "voltage_start_v", "voltage_end_v",
                "current_start_a", "current_end_a", "power_start_w", "power_end_w",
                "valid_inferences", "protocol_error_count", "jtag_physically_connected",
                "xsct_active_during_window", "hw_server_active_during_window",
                "start_photo", "end_photo", "meter_trace_csv", "board_result_manifest",
                "instrument_model", "instrument_accuracy", "power_source_description",
            )
            rows: list[dict[str, object]] = []
            deltas = {
                "b3_idle": 250,
                "b3_dense": 300,
                "b3_static_mixed": 270,
                "b3_live_eneuron": 260,
            }
            valid = {
                "b3_idle": 0,
                "b3_dense": 12000,
                "b3_static_mixed": 15000,
                "b3_live_eneuron": 14000,
            }
            for round_index in range(1, 6):
                order = tuple(deltas) if round_index % 2 else tuple(reversed(tuple(deltas)))
                for mode in order:
                    delta_mwh = deltas[mode]
                    start_photo = temp / f"r{round_index}-{mode}-start.jpg"
                    end_photo = temp / f"r{round_index}-{mode}-end.jpg"
                    meter_trace = temp / f"r{round_index}-{mode}-trace.csv"
                    board_manifest = temp / f"r{round_index}-{mode}-manifest.json"
                    start_photo.write_bytes(b"start-photo")
                    end_photo.write_bytes(b"end-photo")
                    meter_trace.write_text(
                        "kind,scheduled_elapsed_seconds,voltage_v,current_a,power_w,mah,mwh,photo\n"
                        "start,0,5.00000,0.50000,2.50000,200,1000,start.jpg\n"
                        "minute,60,5.00000,0.50000,2.50000,,,\n"
                        "minute,120,5.00000,0.50000,2.50000,,,\n"
                        "minute,180,5.00000,0.50000,2.50000,,,\n"
                        "minute,240,5.00000,0.50000,2.50000,,,\n"
                        "minute,300,5.00000,0.50000,2.50000,,,\n"
                        "minute,360,5.00000,0.50000,2.50000,,,\n"
                        "minute,420,5.00000,0.50000,2.50000,,,\n"
                        "minute,480,5.00000,0.50000,2.50000,,,\n"
                        "minute,540,5.00000,0.50000,2.50000,,,\n"
                        f"end,600,5.00000,0.50000,2.50000,260,{1000 + delta_mwh},end.jpg\n",
                        encoding="utf-8",
                    )
                    board_manifest.write_text(
                        json.dumps({"status": "PASS", "round": round_index, "mode": mode}),
                        encoding="utf-8",
                    )
                    rows.append({
                        "round": round_index,
                        "mode": mode,
                        "duration_seconds": 600,
                        "start_mwh": 1000,
                        "end_mwh": 1000 + delta_mwh,
                        "start_mah": 200,
                        "end_mah": 260,
                        "voltage_start_v": 5.0,
                        "voltage_end_v": 5.0,
                        "current_start_a": 0.5,
                        "current_end_a": 0.5,
                        "power_start_w": 2.5,
                        "power_end_w": 2.5,
                        "valid_inferences": valid[mode],
                        "protocol_error_count": 0,
                        "jtag_physically_connected": "true",
                        "xsct_active_during_window": "false",
                        "hw_server_active_during_window": "false",
                        "start_photo": start_photo.name,
                        "end_photo": end_photo.name,
                        "meter_trace_csv": meter_trace.name,
                        "board_result_manifest": board_manifest.name,
                        "instrument_model": "manual-meter",
                        "instrument_accuracy": "manufacturer specification",
                        "power_source_description": "fixed 5 V Type-C source",
                    })
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "build_b3_manual_power_report.py"),
                    "--input",
                    str(csv_path),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "MEASURED")
            self.assertEqual(report["measurement_contract_status"], "MEASURED")
            self.assertEqual(report["contract"]["status"], "POWER_NOT_MEASURED")
            self.assertEqual(len(report["contract_sha256"]), 64)
            self.assertEqual(report["round_count"], 5)
            self.assertEqual(len(report["source_csv_sha256"]), 64)
            self.assertEqual(len(report["windows"][0]["start_photo_sha256"]), 64)
            self.assertEqual(len(report["windows"][0]["meter_trace_csv_sha256"]), 64)
            self.assertEqual(len(report["windows"][0]["board_result_manifest_sha256"]), 64)
            self.assertEqual(report["power_gate"], "OPEN")


if __name__ == "__main__":
    unittest.main()

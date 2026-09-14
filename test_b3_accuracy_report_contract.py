from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from b3_accuracy_report import build_accuracy_report, load_accuracy_input, load_samples


def _samples(count: int = 1000, disagreement: int = 0) -> list[dict[str, object]]:
    rows = []
    for index in range(count):
        dense = [10, 1, 0]
        live = [10, 1, 0]
        if index < disagreement:
            live = [1, 10, 0]
        rows.append({
            "sample_id": f"sample-{index}",
            "input_identity": f"input-{index}",
            "mask_epoch": index + 1,
            "protocol_errors": 0,
            "result_crc_match": True,
            "input_match": True,
            "label": 0,
            "dense_logits": dense,
            "live_logits": live,
        })
    return rows


IDENTITY = {
    "model": "model-3",
    "preprocess": "uint4-nibble-v1",
    "bitstream_sha256": "bit",
    "xsa_sha256": "xsa",
    "elf_sha256": "elf",
}


class B3AccuracyReportContractTests(unittest.TestCase):
    def test_pass_requires_one_thousand_samples_and_reports_ci(self) -> None:
        report = build_accuracy_report(_samples(), identity=IDENTITY)
        self.assertEqual(report["schema"], "eneuron_b3_accuracy_report_v1")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["accuracy_gate"], "ACCURACY_NEAR_DENSE")
        self.assertEqual(report["sample_count"], 1000)
        self.assertEqual(report["prediction_agreement"], 1.0)
        self.assertEqual(report["logit_exact_match_rate"], 1.0)
        self.assertEqual(report["logit_exact_match_count"], 1000)
        self.assertEqual(report["accuracy_drop_pp"], 0.0)
        self.assertEqual(report["accuracy_drop_ci95_pp"], [0.0, 0.0])
        self.assertEqual(len(report["prediction_agreement_ci95"]), 2)
        self.assertIn("p95", report["logit_error"]["max_abs"])
        self.assertEqual(report["per_class_recall"]["0"]["live_recall"], 1.0)

    def test_threshold_failures_are_explicit(self) -> None:
        report = build_accuracy_report(_samples(999), identity=IDENTITY)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("sample_count<1000", report["failed_checks"])
        report = build_accuracy_report(_samples(disagreement=11), identity=IDENTITY)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("prediction_agreement_below_threshold", report["failed_checks"])

    def test_confidence_bounds_are_part_of_the_gate(self) -> None:
        report = build_accuracy_report(_samples(disagreement=4), identity=IDENTITY)
        self.assertEqual(report["prediction_agreement"], 0.996)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("prediction_agreement_ci95_lower_below_threshold", report["failed_checks"])

        report = build_accuracy_report(
            _samples(disagreement=6),
            identity=IDENTITY,
            agreement_threshold=0.0,
        )
        self.assertAlmostEqual(report["accuracy_drop_pp"], 0.6)
        self.assertIn("accuracy_drop_ci95_upper_above_threshold", report["failed_checks"])

    def test_bad_protocol_or_result_cannot_be_masked_by_good_accuracy(self) -> None:
        rows = _samples()
        rows[0]["protocol_errors"] = 1
        with self.assertRaises(ValueError):
            build_accuracy_report(rows, identity=IDENTITY)
        rows = _samples()
        rows[0]["result_crc_match"] = False
        with self.assertRaises(ValueError):
            build_accuracy_report(rows, identity=IDENTITY)

    def test_duplicate_and_prediction_mismatch_are_rejected(self) -> None:
        rows = _samples()
        rows[1]["sample_id"] = rows[0]["sample_id"]
        with self.assertRaises(ValueError):
            build_accuracy_report(rows, identity=IDENTITY)
        rows = _samples()
        rows[0]["dense_pred"] = 1
        with self.assertRaises(ValueError):
            build_accuracy_report(rows, identity=IDENTITY)

    def test_jsonl_loader_and_cli(self) -> None:
        rows = _samples(3)
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "samples.jsonl"
            report_path = Path(temp) / "report.json"
            source.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            self.assertEqual(len(load_samples(source)), 3)
            rows = _samples()
            source.write_text(json.dumps({"identity": IDENTITY, "samples": rows}), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "b3_accuracy_report.py", str(source), "-o", str(report_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["status"], "PASS")

    def test_identity_is_required_for_a_gate_pass(self) -> None:
        report = build_accuracy_report(_samples())
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any(item.startswith("identity_missing:") for item in report["failed_checks"]))


if __name__ == "__main__":
    unittest.main()

"""验证 HelloZynq B0 第一次正式下载证据的身份和不可覆盖边界。"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SUMMARY_PATH = ROOT / "artifacts" / "results" / "hellozynq_b0_smoke_summary.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class HelloZynqB0EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        current_run = self.summary["program_runs"][-1]
        self.current_run = current_run
        self.archive_dir = ROOT / current_run["machine_evidence_archive"]
        self.archive = json.loads(
            (self.archive_dir / "archive_manifest.json").read_text(encoding="utf-8-sig")
        )

    def test_current_run_identity_matches_archive(self) -> None:
        self.assertEqual(
            self.summary["build"]["bitstream_sha256"],
            self.current_run["bitstream_sha256"],
        )
        self.assertEqual(self.current_run["bitstream_sha256"], self.archive["bitstream_sha256"])
        self.assertEqual(self.current_run["program_log_sha256"], self.archive["program_log_sha256"])

    def test_archived_files_match_manifest(self) -> None:
        expected = {
            "program_result_sha256": "program_result.txt",
            "program_log_sha256": "program_run.txt",
            "build_manifest_sha256": "build_manifest.json",
        }
        for field, filename in expected.items():
            with self.subTest(field=field):
                self.assertEqual(self.archive[field], sha256(self.archive_dir / filename))

    def test_field_gate_remains_pending(self) -> None:
        self.assertEqual("PERIOD_QUANTIFICATION_PENDING", self.current_run["observation_status"])
        self.assertEqual("PERIOD_QUANTIFICATION_PENDING", self.archive["observation_status"])
        self.assertIn("PENDING", self.summary["status"])

    def test_field_observation_records_stable_blink_without_inventing_period(self) -> None:
        observation_path = ROOT / self.current_run["field_observation"]
        observation = json.loads(observation_path.read_text(encoding="utf-8"))
        self.assertEqual(self.archive["field_observation_sha256"], sha256(observation_path))
        self.assertTrue(observation["stable_blinking_confirmed"])
        self.assertEqual(1.0, observation["observed_complete_period_seconds"])
        self.assertTrue(observation["observed_complete_period_is_approximate"])
        self.assertIsNone(observation["observed_toggle_interval_seconds"])
        self.assertEqual(12.6, observation["timed_10_period_acceptance_min_seconds"])
        self.assertEqual(14.2, observation["timed_10_period_acceptance_max_seconds"])
        self.assertIsNone(observation["timed_10_period_observed_seconds"])
        self.assertEqual("PERIOD_QUANTIFICATION_PENDING", observation["status"])

    def test_archive_script_rejects_existing_run_directory(self) -> None:
        script = (
            ROOT / "boards" / "hellozynq" / "b0_smoke" / "archive_b0_program_run.ps1"
        ).read_text(encoding="utf-8-sig")
        self.assertIn("will not be overwritten", script)
        self.assertIn("B0_PROGRAM_COMMAND=PASS", script)
        self.assertIn("B0_PROGRAM_PASS", script)


if __name__ == "__main__":
    unittest.main()

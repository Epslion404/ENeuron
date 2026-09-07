"""验证 HelloZynq B0 双运行、完整断电和现场观察证据。"""

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


def canonical_lf_sha256(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


class HelloZynqB0EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        self.current_runs = [
            run
            for run in self.summary["program_runs"]
            if run.get("bitstream_sha256") == self.summary["build"]["bitstream_sha256"]
        ]
        current_run = self.current_runs[-1]
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
            "program_result_canonical_lf_sha256": "program_result.txt",
            "program_log_canonical_lf_sha256": "program_run.txt",
            "build_manifest_canonical_lf_sha256": "build_manifest.json",
        }
        for field, filename in expected.items():
            with self.subTest(field=field):
                self.assertEqual(
                    self.archive[field], canonical_lf_sha256(self.archive_dir / filename)
                )

    def test_b0_gate_is_complete(self) -> None:
        self.assertEqual("PASS", self.current_run["observation_status"])
        self.assertEqual("PASS", self.archive["observation_status"])
        self.assertEqual("B0_COMPLETE", self.summary["status"])
        self.assertEqual([], self.summary["pending"])

    def test_run2_field_observation_records_cold_restart_measurement(self) -> None:
        observation_path = ROOT / self.current_run["field_observation"]
        observation = json.loads(observation_path.read_text(encoding="utf-8"))
        self.assertEqual(
            self.archive["field_observation_canonical_lf_sha256"],
            canonical_lf_sha256(observation_path),
        )
        self.assertTrue(observation["stable_blinking_confirmed"])
        self.assertEqual(1.34, observation["observed_complete_period_seconds"])
        self.assertFalse(observation["observed_complete_period_is_approximate"])
        self.assertEqual(0.67, observation["observed_toggle_interval_seconds"])
        self.assertEqual(12.6, observation["timed_10_period_acceptance_min_seconds"])
        self.assertEqual(14.2, observation["timed_10_period_acceptance_max_seconds"])
        self.assertEqual(13.4, observation["timed_10_period_observed_seconds"])
        self.assertTrue(observation["timed_10_period_within_acceptance_window"])
        self.assertEqual("PASS", observation["status"])

    def test_two_current_bitstream_runs_span_the_complete_power_cycle(self) -> None:
        self.assertEqual(2, len(self.current_runs))
        self.assertEqual([13.42, 13.4], [
            run["timed_10_period_observed_seconds"] for run in self.current_runs
        ])
        self.assertTrue(self.summary["power_cycle"]["user_confirmed_complete_power_off"])
        self.assertEqual(
            "PASS", self.summary["power_cycle"]["second_program_after_complete_power_off"]
        )
        self.assertEqual("PASS", self.summary["power_cycle"]["second_field_observation"])

    def test_archive_script_rejects_existing_run_directory(self) -> None:
        script = (
            ROOT / "boards" / "hellozynq" / "b0_smoke" / "archive_b0_program_run.ps1"
        ).read_text(encoding="utf-8-sig")
        self.assertIn("will not be overwritten", script)
        self.assertIn("B0_PROGRAM_COMMAND=PASS", script)
        self.assertIn("B0_PROGRAM_PASS", script)

    def test_complete_power_off_probe_is_archived_and_hashed(self) -> None:
        power_cycle = self.summary["power_cycle"]
        evidence_dir = ROOT / power_cycle["evidence_archive"]
        manifest = json.loads(
            (evidence_dir / "power_off_probe_manifest.json").read_text(encoding="utf-8-sig")
        )
        self.assertTrue(power_cycle["user_confirmed_complete_power_off"])
        self.assertEqual(1, power_cycle["matching_cable_target_count"])
        self.assertEqual(0, power_cycle["accessible_device_count"])
        self.assertEqual("PASS", power_cycle["jtag_inaccessible_result"])
        self.assertEqual("PASS", manifest["result"])
        self.assertEqual(0, manifest["accessible_device_count"])
        self.assertEqual(
            manifest["result_canonical_lf_sha256"],
            canonical_lf_sha256(evidence_dir / "power_off_probe_result.txt"),
        )
        self.assertEqual(
            manifest["transcript_canonical_lf_sha256"],
            canonical_lf_sha256(evidence_dir / "power_off_probe_run.txt"),
        )
        self.assertEqual(
            manifest["tcl_sha256"],
            sha256(ROOT / "boards" / "hellozynq" / "b0_smoke" / "probe_b0_power_off.tcl"),
        )
        self.assertEqual(
            manifest["runner_sha256"],
            sha256(
                ROOT
                / "boards"
                / "hellozynq"
                / "b0_smoke"
                / "run_b0_power_off_probe.ps1"
            ),
        )
        transcript = (evidence_dir / "power_off_probe_run.txt").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("No devices detected", transcript)
        self.assertIn("B0_COMPLETE_POWER_OFF_JTAG_INACCESSIBLE=PASS", transcript)
        runner = (
            ROOT / "boards" / "hellozynq" / "b0_smoke" / "run_b0_power_off_probe.ps1"
        ).read_text(encoding="utf-8-sig")
        self.assertIn("will not be overwritten", runner)
        self.assertIn("B0_POWER_OFF_MATCHING_TARGET_COUNT=1", runner)
        self.assertIn("B0_POWER_OFF_ACCESSIBLE_DEVICE_COUNT=0", runner)


if __name__ == "__main__":
    unittest.main()

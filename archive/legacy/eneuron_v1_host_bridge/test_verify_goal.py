"""T0 Tile Vivado 证据门的测试先行合同。"""

from __future__ import annotations

import os
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import verify_goal


SOURCE_NAMES = (
    "digital_lif_engine.sv",
    "digital_snn_tile_4x2x2.sv",
    "vivado_tile_synth.tcl",
    "run_vivado_tile_synth.ps1",
)

REPORT_NAMES = (
    "signoff_summary.txt",
    "timing_impl.rpt",
    "utilization_impl.rpt",
    "route_status_impl.rpt",
    "drc_impl.rpt",
    "methodology_impl.rpt",
    "power_impl.rpt",
    "digital_snn_tile_4x2x2_impl.dcp",
    "vivado_run.log",
)


GOOD_SUMMARY = """\
RESULT=PASS
VIVADO_VERSION=2024.1
PART=xc7a35tcpg236-1
TOP=digital_snn_tile_4x2x2
MODE=OUT_OF_CONTEXT
CLOCK_MHZ=100.000
WNS_NS=0.213
TNS_NS=0.000
SETUP_VIOLATIONS=0
WHS_NS=0.026
THS_NS=0.000
HOLD_VIOLATIONS=0
ROUTE_ERRORS=0
FULLY_ROUTED_NETS=4420
DRC_ERRORS=0
DRC_CRITICAL_WARNINGS=0
DRC_CFGBVS1_WARNINGS=1
METHODOLOGY_ERRORS=0
METHODOLOGY_CRITICAL_WARNINGS=0
METHODOLOGY_TIMING18_WARNINGS=180
LUT=3152
FF=1972
BRAM36=0
BRAM18=0
DSP=0
POWER_W=0.103
POWER_CONFIDENCE=Medium
POWER_ACTIVITY_FILE=NONE
"""

GOOD_TIMING = """\
| Tool Version : Vivado v.2024.1 (win64)
| Design       : digital_snn_tile_4x2x2
| Device       : xc7a35tcpg236-1
| Design State : Routed
| Design Timing Summary
    WNS(ns) TNS(ns) TNS Failing Endpoints TNS Total Endpoints WHS(ns) THS(ns) THS Failing Endpoints THS Total Endpoints
      0.213   0.000                     0                3861   0.026   0.000                     0                3861
All user specified timing constraints are met.
Setup : 0 Failing Endpoints, Worst Slack 0.213ns, Total Violation 0.000ns
Hold  : 0 Failing Endpoints, Worst Slack 0.026ns, Total Violation 0.000ns
"""

GOOD_UTILIZATION = """\
| Tool Version : Vivado v.2024.1 (win64)
| Design       : digital_snn_tile_4x2x2
| Device       : xc7a35tcpg236-1
| Design State : Routed
| Slice LUTs              | 3152 | 0 | 0 | 20800 | 15.15 |
| Slice Registers         | 1972 | 0 | 0 | 41600 | 4.74 |
| Block RAM Tile          | 0    | 0 | 0 | 50    | 0.00 |
| RAMB36/FIFO*            | 0    | 0 | 0 | 50    | 0.00 |
| RAMB18                  | 0    | 0 | 0 | 100   | 0.00 |
| DSPs                    | 0    | 0 | 0 | 90    | 0.00 |
"""

GOOD_ROUTE = """\
Design Route Status
    # of logical nets.......................... :        7781 :
    # of fully routed nets..................... :        4420 :
    # of nets with routing errors.............. :           0 :
"""

GOOD_DRC = """\
| Tool Version : Vivado v.2024.1 (win64)
| Design       : digital_snn_tile_4x2x2
| Device       : xc7a35tcpg236-1
| Design State : Fully Routed
Violations found: 1
| Rule     | Severity | Description | Violations |
| CFGBVS-1 | Warning  | Missing configuration voltage properties | 1 |
"""

GOOD_METHODOLOGY = """\
| Tool Version : Vivado v.2024.1 (win64)
| Design       : digital_snn_tile_4x2x2
| Device       : xc7a35tcpg236-1
| Design State : Fully Routed
Violations found: 180
| Rule      | Severity | Description | Violations |
| TIMING-18 | Warning  | Missing input or output delay | 180 |
"""

GOOD_POWER = """\
| Tool Version             : Vivado v.2024.1 (win64)
| Design                   : digital_snn_tile_4x2x2
| Device                   : xc7a35tcpg236-1
| Design State             : routed
| Total On-Chip Power (W)  | 0.103  |
| Dynamic (W)              | 0.035  |
| Device Static (W)        | 0.068  |
| Confidence Level         | Medium |
| Simulation Activity File | ---    |
| Overall confidence level | Medium |
"""


class ReadKeyValuesTests(unittest.TestCase):
    def write_summary(self, text: str) -> Path:
        directory = tempfile.TemporaryDirectory(prefix="eneuron_key_values_")
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "summary.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def test_parses_strict_key_value_lines_and_ignores_blank_lines(self) -> None:
        path = self.write_summary("RESULT=PASS\n\nPART = xc7a35tcpg236-1\n")

        self.assertEqual(
            verify_goal.read_key_values(path),
            {"RESULT": "PASS", "PART": "xc7a35tcpg236-1"},
        )

    def test_rejects_duplicate_keys_after_whitespace_normalization(self) -> None:
        path = self.write_summary("RESULT=PASS\n RESULT = FAIL\n")

        with self.assertRaisesRegex(AssertionError, "重复|duplicate|RESULT"):
            verify_goal.read_key_values(path)

    def test_rejects_nonempty_lines_without_equals(self) -> None:
        path = self.write_summary("RESULT=PASS\nthis is not a field\n")

        with self.assertRaisesRegex(AssertionError, "格式|format|line|行"):
            verify_goal.read_key_values(path)

    def test_rejects_empty_keys_or_values(self) -> None:
        for text in ("=PASS\n", "RESULT=\n"):
            with self.subTest(text=text):
                path = self.write_summary(text)
                with self.assertRaisesRegex(AssertionError, "格式|format|empty|空"):
                    verify_goal.read_key_values(path)


class XpmSummaryParsingTests(unittest.TestCase):
    def write_summary(self, text: str) -> Path:
        directory = tempfile.TemporaryDirectory(prefix="eneuron_xpm_summary_")
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "vivado_xpm_wrapper_summary.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def test_accepts_fixed_marker_then_strict_key_value_lines(self) -> None:
        path = self.write_summary(
            "VIVADO_XPM_WRAPPER_PASS\n"
            "vivado_version=2024.1\n"
            "part=xc7a35tcpg236-1\n"
        )

        self.assertEqual(
            verify_goal.read_xpm_summary(path),
            {
                "vivado_version": "2024.1",
                "part": "xc7a35tcpg236-1",
            },
        )

    def test_rejects_missing_or_wrong_first_line_marker(self) -> None:
        for first_line in (
            "vivado_version=2024.1",
            "VIVADO_XPM_WRAPPER_FAIL",
            " VIVADO_XPM_WRAPPER_PASS",
        ):
            with self.subTest(first_line=first_line):
                path = self.write_summary(first_line + "\npart=xc7a35tcpg236-1\n")
                with self.assertRaisesRegex(AssertionError, "marker|首行|VIVADO_XPM_WRAPPER_PASS"):
                    verify_goal.read_xpm_summary(path)

    def test_rejects_bare_lines_after_valid_marker(self) -> None:
        path = self.write_summary(
            "VIVADO_XPM_WRAPPER_PASS\n"
            "vivado_version=2024.1\n"
            "unexpected bare line\n"
        )

        with self.assertRaisesRegex(AssertionError, "格式|format|line|行"):
            verify_goal.read_xpm_summary(path)


class SystemCdcSummaryParsingTests(unittest.TestCase):
    def write_summary(self, text: str) -> Path:
        directory = tempfile.TemporaryDirectory(prefix="eneuron_system_cdc_summary_")
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "cdc_classification.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def test_accepts_fixed_marker_then_strict_key_value_lines(self) -> None:
        path = self.write_summary(
            "CDC_CLASSIFICATION\n"
            "XPM_SCOPE=host_bridge/command_fifo,host_bridge/response_fifo\n"
            "XPM_CRITICAL_LINES=0\n"
        )

        self.assertEqual(
            verify_goal.read_system_cdc_summary(path),
            {
                "XPM_SCOPE": "host_bridge/command_fifo,host_bridge/response_fifo",
                "XPM_CRITICAL_LINES": "0",
            },
        )

    def test_rejects_missing_wrong_or_indented_marker(self) -> None:
        for text in (
            "XPM_SCOPE=host_bridge/command_fifo\n",
            "CDC_CLASSIFICATION_FAIL\nXPM_CRITICAL_LINES=0\n",
            " CDC_CLASSIFICATION\nXPM_CRITICAL_LINES=0\n",
            "",
        ):
            with self.subTest(text=text):
                path = self.write_summary(text)
                with self.assertRaisesRegex(
                    AssertionError,
                    "marker|first|CDC_CLASSIFICATION|首行",
                ):
                    verify_goal.read_system_cdc_summary(path)

    def test_rejects_bare_lines_after_valid_marker(self) -> None:
        path = self.write_summary(
            "CDC_CLASSIFICATION\n"
            "XPM_CRITICAL_LINES=0\n"
            "unexpected bare line\n"
        )

        with self.assertRaisesRegex(AssertionError, "格式|format|line|行"):
            verify_goal.read_system_cdc_summary(path)


class TileVivadoReportTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="eneuron_tile_signoff_")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.reports = self.root / "vivado_tile_reports"
        self.reports.mkdir()

        for name in SOURCE_NAMES:
            (self.root / name).write_text(f"fixture for {name}\n", encoding="utf-8")

        report_contents = {
            "signoff_summary.txt": GOOD_SUMMARY,
            "timing_impl.rpt": GOOD_TIMING,
            "utilization_impl.rpt": GOOD_UTILIZATION,
            "route_status_impl.rpt": GOOD_ROUTE,
            "drc_impl.rpt": GOOD_DRC,
            "methodology_impl.rpt": GOOD_METHODOLOGY,
            "power_impl.rpt": GOOD_POWER,
            "digital_snn_tile_4x2x2_impl.dcp": "fixture checkpoint\n",
            "vivado_run.log": (
                "****** Vivado v2024.1 (64-bit)\n"
                "route_design completed successfully\n"
                "VIVADO_ENEURON_TILE_PASS part=xc7a35tcpg236-1 "
                "top=digital_snn_tile_4x2x2 setup_slack=0.213 hold_slack=0.026\n"
            ),
        }
        for name, content in report_contents.items():
            (self.reports / name).write_text(content, encoding="utf-8")

        self.source_time = 1_700_000_000
        self.report_time = self.source_time + 60
        for name in SOURCE_NAMES:
            os.utime(self.root / name, (self.source_time, self.source_time))
        for name in REPORT_NAMES:
            os.utime(self.reports / name, (self.report_time, self.report_time))

        root_patch = mock.patch.object(verify_goal, "ROOT", self.root)
        reports_patch = mock.patch.object(
            verify_goal,
            "TILE_REPORTS",
            self.reports,
            create=True,
        )
        root_patch.start()
        reports_patch.start()
        self.addCleanup(root_patch.stop)
        self.addCleanup(reports_patch.stop)

    def verify(self) -> None:
        verifier = getattr(verify_goal, "verify_tile_reports", None)
        self.assertIsNotNone(verifier, "verify_goal.py 尚未实现 verify_tile_reports()")
        verifier()

    def replace_report(self, name: str, old: str, new: str) -> None:
        path = self.reports / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding="utf-8")
        os.utime(path, (self.report_time, self.report_time))

    def test_accepts_current_tile_ooc_evidence(self) -> None:
        self.verify()

    def test_rejects_wrong_tile_summary_identity_or_result(self) -> None:
        mutations = (
            ("RESULT=PASS", "RESULT=FAIL"),
            ("VIVADO_VERSION=2024.1", "VIVADO_VERSION=2023.2"),
            ("PART=xc7a35tcpg236-1", "PART=xc7a100tcsg324-1"),
            ("TOP=digital_snn_tile_4x2x2", "TOP=wrong_top"),
            ("MODE=OUT_OF_CONTEXT", "MODE=DEFAULT"),
            ("CLOCK_MHZ=100.000", "CLOCK_MHZ=99.000"),
        )
        summary_path = self.reports / "signoff_summary.txt"
        original = summary_path.read_text(encoding="utf-8")
        for old, new in mutations:
            with self.subTest(new=new):
                summary_path.write_text(original.replace(old, new), encoding="utf-8")
                os.utime(summary_path, (self.report_time, self.report_time))
                with self.assertRaisesRegex(
                    AssertionError,
                    "摘要|summary|RESULT|VIVADO|PART|TOP|MODE|CLOCK",
                ):
                    self.verify()
        summary_path.write_text(original, encoding="utf-8")

    def test_rejects_summary_values_that_disagree_with_raw_reports(self) -> None:
        mutations = (
            ("WNS_NS=0.213", "WNS_NS=0.214"),
            ("WHS_NS=0.026", "WHS_NS=0.027"),
            ("FULLY_ROUTED_NETS=4420", "FULLY_ROUTED_NETS=4419"),
            ("LUT=3152", "LUT=3151"),
            ("FF=1972", "FF=1971"),
            ("POWER_W=0.103", "POWER_W=0.104"),
        )
        summary_path = self.reports / "signoff_summary.txt"
        original = summary_path.read_text(encoding="utf-8")
        for old, new in mutations:
            with self.subTest(new=new):
                summary_path.write_text(original.replace(old, new), encoding="utf-8")
                os.utime(summary_path, (self.report_time, self.report_time))
                with self.assertRaisesRegex(
                    AssertionError,
                    "摘要|summary|不一致|WNS|WHS|route|LUT|FF|power",
                ):
                    self.verify()
        summary_path.write_text(original, encoding="utf-8")

    def test_requires_every_report_and_generated_artifact(self) -> None:
        for name in REPORT_NAMES:
            with self.subTest(name=name):
                path = self.reports / name
                original = path.read_bytes()
                path.unlink()
                try:
                    with self.assertRaisesRegex(AssertionError, "缺少|missing"):
                        self.verify()
                finally:
                    path.write_bytes(original)
                    os.utime(path, (self.report_time, self.report_time))

    def test_all_reports_must_be_newer_than_every_tile_build_dependency(self) -> None:
        for source_name in SOURCE_NAMES:
            with self.subTest(source_name=source_name):
                source = self.root / source_name
                os.utime(source, (self.report_time + 1, self.report_time + 1))
                try:
                    with self.assertRaisesRegex(AssertionError, "早于|stale|新鲜"):
                        self.verify()
                finally:
                    os.utime(source, (self.source_time, self.source_time))

    def test_rejects_timing_failures_from_raw_report(self) -> None:
        mutations = (
            ("0.213   0.000", "-0.001   0.000"),
            ("0.213   0.000", "0.213   -0.001"),
            ("0.026   0.000", "-0.001   0.000"),
            ("0.026   0.000", "0.026   -0.001"),
            ("Setup : 0 Failing Endpoints", "Setup : 1 Failing Endpoints"),
            ("Hold  : 0 Failing Endpoints", "Hold  : 1 Failing Endpoints"),
        )
        timing_path = self.reports / "timing_impl.rpt"
        original = timing_path.read_text(encoding="utf-8")
        for old, new in mutations:
            with self.subTest(new=new):
                timing_path.write_text(original.replace(old, new, 1), encoding="utf-8")
                os.utime(timing_path, (self.report_time, self.report_time))
                with self.assertRaisesRegex(AssertionError, "时序|timing|WNS|WHS|TNS|THS"):
                    self.verify()
        timing_path.write_text(original, encoding="utf-8")

    def test_rejects_incomplete_or_error_routing(self) -> None:
        mutations = (
            ("fully routed nets..................... :        4420", "fully routed nets..................... :           0"),
            ("nets with routing errors.............. :           0", "nets with routing errors.............. :           1"),
        )
        route_path = self.reports / "route_status_impl.rpt"
        original = route_path.read_text(encoding="utf-8")
        for old, new in mutations:
            with self.subTest(new=new):
                route_path.write_text(original.replace(old, new), encoding="utf-8")
                os.utime(route_path, (self.report_time, self.report_time))
                with self.assertRaisesRegex(AssertionError, "路由|route|routed"):
                    self.verify()
        route_path.write_text(original, encoding="utf-8")

    def test_rejects_new_or_changed_drc_warning_classes(self) -> None:
        self.replace_report("drc_impl.rpt", "CFGBVS-1", "NSTD-1")

        with self.assertRaisesRegex(AssertionError, "DRC|CFGBVS|白名单|warning"):
            self.verify()

    def test_rejects_new_or_changed_methodology_warning_classes(self) -> None:
        self.replace_report("methodology_impl.rpt", "TIMING-18", "TIMING-17")

        with self.assertRaisesRegex(AssertionError, "methodology|TIMING-18|白名单|warning"):
            self.verify()

    def test_rejects_drc_or_methodology_errors_and_critical_warnings(self) -> None:
        mutations = (
            ("drc_impl.rpt", "Warning", "Critical Warning"),
            ("methodology_impl.rpt", "Warning", "Error"),
        )
        for name, old, new in mutations:
            with self.subTest(name=name, severity=new):
                path = self.reports / name
                original = path.read_text(encoding="utf-8")
                path.write_text(original.replace(old, new), encoding="utf-8")
                os.utime(path, (self.report_time, self.report_time))
                try:
                    with self.assertRaisesRegex(AssertionError, "DRC|methodology|Error|Critical"):
                        self.verify()
                finally:
                    path.write_text(original, encoding="utf-8")
                    os.utime(path, (self.report_time, self.report_time))

    def test_enforces_tile_resource_budget(self) -> None:
        mutations = (
            ("Slice LUTs              | 3152", "Slice LUTs              | 3201"),
            ("Slice Registers         | 1972", "Slice Registers         | 2001"),
            ("RAMB36/FIFO*            | 0", "RAMB36/FIFO*            | 1"),
            ("RAMB18                  | 0", "RAMB18                  | 1"),
            ("DSPs                    | 0", "DSPs                    | 1"),
        )
        utilization_path = self.reports / "utilization_impl.rpt"
        original = utilization_path.read_text(encoding="utf-8")
        for old, new in mutations:
            with self.subTest(new=new):
                utilization_path.write_text(original.replace(old, new), encoding="utf-8")
                os.utime(utilization_path, (self.report_time, self.report_time))
                with self.assertRaisesRegex(AssertionError, "资源|resource|LUT|FF|BRAM|DSP"):
                    self.verify()
        utilization_path.write_text(original, encoding="utf-8")

    def test_requires_positive_vectorless_power_with_at_least_medium_confidence(self) -> None:
        mutations = (
            ("0.103", "0.000"),
            ("Medium", "Low"),
            ("Simulation Activity File | ---", "Simulation Activity File | fixture.saif"),
        )
        power_path = self.reports / "power_impl.rpt"
        original = power_path.read_text(encoding="utf-8")
        for old, new in mutations:
            with self.subTest(new=new):
                power_path.write_text(original.replace(old, new), encoding="utf-8")
                os.utime(power_path, (self.report_time, self.report_time))
                with self.assertRaisesRegex(AssertionError, "功耗|power|confidence|activity"):
                    self.verify()
        power_path.write_text(original, encoding="utf-8")


class VivadoRerunOrderTests(unittest.TestCase):
    def test_rerun_vivado_runs_tile_before_xpm_and_system(self) -> None:
        rerun = getattr(verify_goal, "rerun_vivado", None)
        self.assertIsNotNone(rerun, "verify_goal.py 尚未实现可测试的 rerun_vivado()")
        calls: list[str] = []

        def record(command: list[str], _description: str) -> None:
            calls.append(Path(command[-1]).name)

        with mock.patch.object(verify_goal, "run_command", side_effect=record):
            rerun()

        self.assertEqual(
            calls,
            [
                "run_vivado_tile_synth.ps1",
                "run_vivado_xpm_wrapper_sim.ps1",
                "run_vivado_host_bridge_system_ooc.ps1",
            ],
        )

    def test_rerun_vivado_stops_immediately_when_tile_signoff_fails(self) -> None:
        rerun = getattr(verify_goal, "rerun_vivado", None)
        self.assertIsNotNone(rerun, "verify_goal.py 尚未实现可测试的 rerun_vivado()")
        calls: list[str] = []

        def fail_tile(command: list[str], _description: str) -> None:
            calls.append(Path(command[-1]).name)
            raise AssertionError("tile failed")

        with mock.patch.object(verify_goal, "run_command", side_effect=fail_tile):
            with self.assertRaisesRegex(AssertionError, "tile failed"):
                rerun()

        self.assertEqual(calls, ["run_vivado_tile_synth.ps1"])


class T0HandoffSummaryTests(unittest.TestCase):
    def test_t0_summary_binds_current_sources_and_document_values(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="eneuron_t0_handoff_")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        tile_reports = root / "vivado_tile_reports"
        tile_reports.mkdir()

        files = {
            "digital_lif_engine.sv": "engine\n",
            "digital_snn_tile_4x2x2.sv": "tile\n",
            "vivado_tile_synth.tcl": "tcl\n",
            "run_vivado_tile_synth.ps1": "runner\n",
            "verify_goal.py": "verifier\n",
            "README.md": "| 4->2->2 Tile | 3152 | 1972 | 0 | 0 | +0.213 ns | +0.026 ns |\n",
            "docs/verification/goal_audit.md": "`3152 LUT / 1972 FF / 0 BRAM / 0 DSP` WNS `+0.213 ns`\n",
            "docs/design/recommended_design.md": "`3152 LUT / 1972 FF` WNS `+0.213 ns`\n",
        }
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        tile_summary = tile_reports / "signoff_summary.txt"
        tile_summary.write_text(GOOD_SUMMARY, encoding="utf-8")

        with mock.patch.object(verify_goal, "ROOT", root), mock.patch.object(
            verify_goal, "TILE_REPORTS", tile_reports
        ):
            verify_goal.write_t0_signoff_summary()

        values = verify_goal.read_key_values(root / "t0_signoff_summary.txt")
        self.assertEqual(values["RESULT"], "PASS")
        self.assertEqual(values["SCHEMA"], "T0_TILE_SIGNOFF_V1")
        self.assertEqual(values["TILE_RESULT"], "PASS")
        self.assertEqual(values["DOCUMENT_VALUES_MATCH"], "1")
        self.assertEqual(
            values["TILE_SUMMARY_SHA256"],
            hashlib.sha256(tile_summary.read_bytes()).hexdigest().upper(),
        )

    def test_t0_summary_rejects_stale_document_values(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="eneuron_t0_docs_")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        tile_reports = root / "vivado_tile_reports"
        tile_reports.mkdir()
        (tile_reports / "signoff_summary.txt").write_text(GOOD_SUMMARY, encoding="utf-8")
        for name in (
            "digital_lif_engine.sv",
            "digital_snn_tile_4x2x2.sv",
            "vivado_tile_synth.tcl",
            "run_vivado_tile_synth.ps1",
            "verify_goal.py",
        ):
            (root / name).write_text(name, encoding="utf-8")
        for name in ("README.md", "docs/verification/goal_audit.md", "docs/design/recommended_design.md"):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("old Tile values\n", encoding="utf-8")

        with mock.patch.object(verify_goal, "ROOT", root), mock.patch.object(
            verify_goal, "TILE_REPORTS", tile_reports
        ), self.assertRaisesRegex(AssertionError, "文档|document|README"):
            verify_goal.write_t0_signoff_summary()


if __name__ == "__main__":
    unittest.main()

"""B3纯PL NPU post-route SAIF功耗分析合同。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools" / "repro"))

from b3_npu_saif_power_summary import summarize  # noqa: E402


GENERATOR = ROOT / "tools" / "repro" / "b3_npu_saif_fixture.py"
MANIFEST = ROOT / "tools" / "repro" / "b3_qat_model_manifest.json"
DIAGNOSTIC = ROOT / "artifacts" / "results" / "b3_qat_pruning_diagnostic.json"
TB = ROOT / "tb_b3_npu_saif_power.sv"
FLOW_TCL = ROOT / "tools" / "repro" / "b3_npu_saif_power.tcl"
RUNNER = ROOT / "tools" / "repro" / "run_b3_npu_saif_power.ps1"


class B3NpuSaifPowerContractTests(unittest.TestCase):
    def test_fixture_is_qat_v3_strict_2of4_and_reproducible(self) -> None:
        with tempfile.TemporaryDirectory(prefix="b3_saif_fixture_") as temp:
            output = Path(temp)
            ran = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    "--manifest",
                    str(MANIFEST),
                    "--diagnostic",
                    str(DIAGNOSTIC),
                    "--output-dir",
                    str(output),
                    "--sample-count",
                    "64",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(ran.returncode, 0, ran.stderr)
            fixture = json.loads((output / "fixture.json").read_text(encoding="utf-8"))
            self.assertEqual(fixture["schema"], "eneuron_b3_npu_saif_fixture_v1")
            self.assertEqual(fixture["part"], "xc7z020clg484-2")
            self.assertEqual(fixture["clock_mhz"], 200.0)
            self.assertEqual(fixture["sample_count"], 64)
            self.assertEqual(fixture["model_word_count"], 634)
            self.assertEqual(fixture["sample_beat_count"], 512)
            self.assertEqual(fixture["gated_enabled_groups"], 296)
            self.assertEqual(fixture["gated_disabled_groups"], 296)
            self.assertEqual(fixture["packed_words_sha256"], "4bc51712ad5502a4a19fe73862946d53be79055c1467204a857e7b25ccdf97be")
            self.assertEqual(set(fixture["generated_sha256"]), {"model.mem", "samples.mem", "gated_mask.mem"})
            for name, expected_lines in (("model.mem", 634), ("samples.mem", 512), ("gated_mask.mem", 19)):
                lines = (output / name).read_text(encoding="ascii").splitlines()
                self.assertEqual(len(lines), expected_lines)
                self.assertEqual(fixture["generated_sha256"][name], __import__("hashlib").sha256((output / name).read_bytes()).hexdigest())

    def test_summary_separates_dynamic_and_device_static_energy(self) -> None:
        report_template = """\
| Device           : xc7z020clg484-2
| Design State     : routed
| Total On-Chip Power (W)  | {total:.3f} |
| Dynamic (W)              | {dynamic:.3f} |
| Device Static (W)        | {static:.3f} |
| Confidence Level         | High |
| Simulation Activity File | {saif} |
| Design Nets Matched      | 68%   (3229/4716) |
| Overall confidence level | High | |
| clk   | clk    |             5.0 |
"""
        with tempfile.TemporaryDirectory(prefix="b3_saif_summary_") as temp:
            output = Path(temp)
            dense_report = output / "dense_power_post_route.rpt"
            gated_report = output / "gated_power_post_route.rpt"
            dense_saif = output / "dense.saif"
            gated_saif = output / "gated.saif"
            dcp = output / "npu_impl.dcp"
            timing = output / "timing_post_route.rpt"
            route = output / "route_status_post_route.rpt"
            drc = output / "drc_post_route.rpt"
            rtl = output / "npu.sv"
            testbench = output / "tb.sv"
            fixture = output / "fixture.json"
            netlist = output / "post_route_funcsim.v"
            dense_report.write_text(report_template.format(total=0.143, dynamic=0.040, static=0.103, saif="dense.saif"), encoding="utf-8")
            gated_report.write_text(report_template.format(total=0.123, dynamic=0.020, static=0.103, saif="gated.saif"), encoding="utf-8")
            dense_saif.write_text("dense", encoding="ascii")
            gated_saif.write_text("gated", encoding="ascii")
            dcp.write_text("checkpoint", encoding="ascii")
            timing.write_text(
                "Design Timing Summary\n"
                "WNS(ns) TNS(ns) TNS Failing Endpoints TNS Total Endpoints WHS(ns) THS(ns) THS Failing Endpoints\n"
                "------- ------- --------------------- ------------------- ------- ------- ---------------------\n"
                "0.227 0.000 0 8170 0.029 0.000 0 8170\n"
                "All user specified timing constraints are met.\n",
                encoding="utf-8",
            )
            route.write_text("# of nets with routing errors.......... : 0 :\n", encoding="utf-8")
            drc.write_text(
                "Violations found: 11\n"
                "| Rule | Severity | Description | Violations |\n"
                "| DPIP-1 | Warning | Input pipelining | 11 |\n",
                encoding="utf-8",
            )
            for path in (rtl, testbench, fixture, netlist):
                path.write_text(path.name, encoding="utf-8")

            summary = summarize(
                dense_report=dense_report,
                gated_report=gated_report,
                dense_saif=dense_saif,
                gated_saif=gated_saif,
                dcp=dcp,
                timing_report=timing,
                route_status_report=route,
                drc_report=drc,
                rtl=rtl,
                testbench=testbench,
                fixture=fixture,
                post_route_netlist=netlist,
                clock_mhz=200.0,
                dense_cycles=2494,
                gated_cycles=1606,
            )

            self.assertEqual(summary["status"], "PASS")
            self.assertEqual(summary["part"], "xc7z020clg484-2")
            self.assertAlmostEqual(summary["modes"]["dense"]["dynamic_power_w"], 0.040)
            self.assertAlmostEqual(summary["modes"]["dense"]["device_static_power_w"], 0.103)
            self.assertAlmostEqual(summary["modes"]["dense"]["dynamic_energy_nj"], 498.8)
            self.assertAlmostEqual(summary["modes"]["gated"]["dynamic_energy_nj"], 160.6)
            self.assertAlmostEqual(summary["modes"]["gated"]["device_static_window_energy_nj"], 827.09)
            self.assertEqual(summary["boundary"], "Device static is a whole-device baseline, not NPU-attributable power.")
            self.assertIn("dcp", summary["sha256"])
            self.assertEqual(summary["saif_quality_gate"]["minimum_direct_match_percent"], 50.0)
            self.assertEqual(summary["implementation"]["timing"]["wns_ns"], 0.227)
            self.assertEqual(summary["implementation"]["timing"]["whs_ns"], 0.029)
            self.assertEqual(summary["implementation"]["route_errors"], 0)
            self.assertEqual(summary["implementation"]["drc"]["error_count"], 0)
            self.assertEqual(summary["implementation"]["drc"]["warning_count"], 11)
            self.assertIn("rtl", summary["sha256"])
            self.assertIn("post_route_netlist", summary["sha256"])

    def test_flow_freezes_200mhz_post_route_saif_contract(self) -> None:
        tb = TB.read_text(encoding="utf-8")
        flow = FLOW_TCL.read_text(encoding="utf-8")
        runner = RUNNER.read_text(encoding="utf-8")
        self.assertIn("always #2.5 clk", tb)
        self.assertIn("saif_active", tb)
        self.assertIn("B3_NPU_SAIF_PASS", tb)
        self.assertIn("last_compute_cycles", tb)
        self.assertIn("execute_group_count", tb)
        self.assertIn("skip_group_count", tb)
        self.assertIn("xc7z020clg484-2", flow)
        self.assertIn("create_clock -name clk -period 5.000", flow)
        self.assertIn("route_design", flow)
        self.assertIn("read_saif", flow)
        self.assertIn("report_power", flow)
        self.assertIn("dense.saif", runner)
        self.assertIn("gated.saif", runner)
        self.assertIn("b3_npu_saif_power_summary.py", runner)


if __name__ == "__main__":
    unittest.main()

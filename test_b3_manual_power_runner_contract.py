from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SW_ROOT = ROOT / "boards/hellozynq/b2_sw"


class B3ManualPowerRunnerContractTests(unittest.TestCase):
    def test_xsct_start_and_result_scripts_leave_measurement_window_disconnected(self) -> None:
        start = (SW_ROOT / "start_b3_power_window.tcl").read_text(encoding="utf-8")
        result = (SW_ROOT / "probe_b3_power_result.tcl").read_text(encoding="utf-8")

        for token in (
            "0x01008500",
            "0x01008600",
            "B3_POWER_READY_PASS",
            "B3_POWER_GO_WRITE_PASS",
            "mwr",
            "mrd -value",
            "disconnect",
        ):
            self.assertIn(token, start)
        self.assertLess(start.index("mwr 0x01008500"), start.index("\ncon\n"))
        self.assertLess(start.index("B3_POWER_READY_PASS"), start.index("B3_POWER_GO_WRITE_PASS"))
        self.assertLess(start.index("B3_POWER_GO_WRITE_PASS"), start.index("disconnect"))

        for token in (
            "B3_POWER_RESULT_MAGIC",
            "B3_POWER_RESULT_STATUS",
            "B3_POWER_VALID_INFERENCES",
            "B3_POWER_PROTOCOL_ERROR_COUNT",
            "B3_POWER_ERROR_CODE",
            "disconnect",
        ):
            self.assertIn(token, result)

    def test_manual_runner_enforces_frozen_meter_and_jtag_contract(self) -> None:
        source = (SW_ROOT / "run_b3_power_manual.ps1").read_text(encoding="utf-8")
        for token in (
            "b3_idle",
            "b3_dense",
            "b3_static_mixed",
            "b3_live_eneuron",
            "300",
            "10000",
            "200",
            "Get-Process -Name 'xsct','hw_server'",
            "$ownedHwServer",
            "Stop-Process -Id $ownedHwServer.Id",
            "Confirm-JtagPhysicalConnection",
            "Read-MeterObservation",
            "voltage_v",
            "current_a",
            "power_w",
            "start_mah",
            "end_mah",
            "start_mwh",
            "end_mwh",
            "meter_trace_csv",
            "manual_power.csv",
            "run_manifest.json",
            "Get-FileHash -Algorithm SHA256",
            "start_b3_power_window.tcl",
            "probe_b3_power_result.tcl",
        ):
            self.assertIn(token, source)
        self.assertNotIn("uart", source.lower())
        self.assertIn("Get-Content -LiteralPath $contractPath -Raw -Encoding UTF8", source)
        self.assertIn("Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8", source)
        self.assertIn("@('b3_idle', 'b3_dense', 'b3_static_mixed', 'b3_live_eneuron')", source)
        self.assertIn("@('b3_live_eneuron', 'b3_static_mixed', 'b3_dense', 'b3_idle')", source)
        self.assertIn("$env:HW_SERVER_FTDIMGR_DISABLE = '0'", source)
        self.assertIn("$env:HW_SERVER_DJTG_DISABLE = '0'", source)
        self.assertIn("$startInfo.EnvironmentVariables['HW_SERVER_FTDIMGR_DISABLE'] = '0'", source)
        self.assertIn("$startInfo.EnvironmentVariables['HW_SERVER_DJTG_DISABLE'] = '0'", source)
        self.assertIn("$process.Refresh()", source)

    def test_manual_runner_is_valid_powershell(self) -> None:
        script = SW_ROOT / "run_b3_power_manual.ps1"
        command = (
            "$errors=$null; "
            f"[void][System.Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$null,[ref]$errors); "
            "if($errors.Count){$errors | ForEach-Object { Write-Error $_ }; exit 1}"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_power_benchmark_has_unreachable_return_for_arm_gcc(self) -> None:
        source = (SW_ROOT / "src/packet_main.c").read_text(encoding="utf-8")
        start = source.index("static int run_power_benchmark(void)")
        end = source.index("#endif", start)
        function = source[start:end]
        self.assertIn("while (1) sleep(1U);\n    return XST_SUCCESS;", function)

    def test_owned_hw_server_start_cleans_up_on_startup_failure(self) -> None:
        source = (SW_ROOT / "run_b3_power_manual.ps1").read_text(encoding="utf-8")
        start = source.index("function Start-OwnedHwServer")
        end = source.index("function Stop-OwnedHwServer", start)
        function = source[start:end]
        self.assertIn("try {", function)
        self.assertIn("catch {", function)
        self.assertIn("Stop-Process -Id $ownedHwServer.Id -Force", function)


if __name__ == "__main__":
    unittest.main()

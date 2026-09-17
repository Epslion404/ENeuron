"""核对无损零组跳过 OOC 摘要与最终 Vivado 报告一致。"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RESULT = ROOT / "artifacts/results/b3_qat_lossless_zero_group_ooc.json"


def parse_timing(report: Path) -> dict[str, float | int]:
    text = report.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r"^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+\d+\s+"
        r"(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+\d+",
        text,
        re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f"无法解析时序摘要: {report}")
    return {
        "wns_ns": float(match.group(1)),
        "tns_ns": float(match.group(2)),
        "failing_setup_endpoints": int(match.group(3)),
        "whs_ns": float(match.group(4)),
        "ths_ns": float(match.group(5)),
        "failing_hold_endpoints": int(match.group(6)),
    }


def parse_utilization(report: Path) -> dict[str, int]:
    text = report.read_text(encoding="utf-8", errors="replace")
    match = re.search(
            r"\| npu_eneuron_single_clock_skeleton\s+\|\s+\(top\)\s+\|"
        r"\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|\s+\d+\s+\|"
        r"\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|",
        text,
    )
    if match is None:
        raise AssertionError(f"无法解析资源摘要: {report}")
    return {
        "lut_total": int(match.group(1)),
        "lut_logic": int(match.group(2)),
        "lutram": int(match.group(3)),
        "ff": int(match.group(4)),
        "bram36": int(match.group(5)),
        "bram18": int(match.group(6)),
        "dsp48e1": int(match.group(7)),
    }


class B3QatLosslessZeroGroupOocContractTests(unittest.TestCase):
    def test_summary_matches_each_final_post_route_report(self) -> None:
        data = json.loads(RESULT.read_text(encoding="utf-8"))
        self.assertEqual("OOC_PASS_TIMING", data["status"])
        self.assertEqual("repaired", data["current_attempt"])

        attempts = {attempt["label"]: attempt for attempt in data["attempts"]}
        for label, attempt in attempts.items():
            directory = ROOT / attempt["directory"]
            self.assertEqual(
                parse_timing(directory / "timing_post_route.rpt"),
                attempt["timing"],
            )
            self.assertEqual(
                parse_utilization(directory / "utilization_post_route.rpt"),
                attempt["resources"],
            )

        current_timing = {
            key: data["timing"][key] for key in attempts["repaired"]["timing"]
        }
        self.assertEqual(attempts["repaired"]["timing"], current_timing)
        self.assertEqual(attempts["repaired"]["resources"], data["resources"])


if __name__ == "__main__":
    unittest.main()

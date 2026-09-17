"""解析Vivado post-route SAIF功耗报告并按同一频率计算推理能量。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


EXPECTED_PART = "xc7z020clg484-2"
MIN_DIRECT_SAIF_MATCH_PERCENT = 50.0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _field(text: str, name: str) -> str:
    match = re.search(rf"^\|\s*{re.escape(name)}\s*(?::|\|)\s*([^|\r\n]+)", text, re.MULTILINE | re.IGNORECASE)
    if not match:
        raise ValueError(f"missing power report field: {name}")
    return match.group(1).strip()


def _clock_period_ns(text: str) -> float:
    match = re.search(r"^\|\s*clk\s*\|\s*clk\s*\|\s*([0-9.]+)\s*\|", text, re.MULTILINE)
    if not match:
        raise ValueError("missing clk constraint row")
    return float(match.group(1))


def parse_report(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    matched = _field(text, "Design Nets Matched")
    matched_number = re.search(r"[0-9.]+", matched)
    return {
        "device": _field(text, "Device"),
        "design_state": _field(text, "Design State").lower(),
        "total_on_chip_power_w": float(_field(text, "Total On-Chip Power (W)")),
        "dynamic_power_w": float(_field(text, "Dynamic (W)")),
        "device_static_power_w": float(_field(text, "Device Static (W)")),
        "confidence": _field(text, "Confidence Level"),
        "simulation_activity_file": _field(text, "Simulation Activity File"),
        "design_nets_matched": matched,
        "design_nets_matched_percent": float(matched_number.group(0)) if matched_number else None,
        "clock_period_ns": _clock_period_ns(text),
    }


def parse_timing_report(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    summary = text.split("Design Timing Summary", maxsplit=1)
    if len(summary) != 2:
        raise ValueError("missing Design Timing Summary")
    row = re.search(
        r"^\s*(-?[0-9.]+)\s+(-?[0-9.]+)\s+(\d+)\s+\d+\s+"
        r"(-?[0-9.]+)\s+(-?[0-9.]+)\s+(\d+)\s+\d+",
        summary[1],
        re.MULTILINE,
    )
    if not row:
        raise ValueError("missing timing summary data row")
    return {
        "wns_ns": float(row.group(1)),
        "tns_ns": float(row.group(2)),
        "setup_failing_endpoints": int(row.group(3)),
        "whs_ns": float(row.group(4)),
        "ths_ns": float(row.group(5)),
        "hold_failing_endpoints": int(row.group(6)),
    }


def parse_route_status(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"# of nets with routing errors\.+\s*:\s*(\d+)\s*:", text)
    if not match:
        raise ValueError("missing routing error count")
    return int(match.group(1))


def parse_drc_report(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    violations = re.search(r"Violations found:\s*(\d+)", text)
    if not violations:
        raise ValueError("missing DRC violation count")
    counts = {"error": 0, "critical_warning": 0, "warning": 0}
    for severity, count in re.findall(
        r"^\|\s*[^|]+\|\s*(Error|Critical Warning|Warning)\s*\|[^|]*\|\s*(\d+)\s*\|",
        text,
        re.MULTILINE | re.IGNORECASE,
    ):
        counts[severity.lower().replace(" ", "_")] += int(count)
    return {"violation_count": int(violations.group(1)), **{f"{key}_count": value for key, value in counts.items()}}


def _mode(report: dict, cycles: int, clock_mhz: float) -> dict:
    inference_seconds = cycles / (clock_mhz * 1_000_000.0)
    return {
        "cycles": cycles,
        "inference_time_us": inference_seconds * 1_000_000.0,
        "dynamic_power_w": report["dynamic_power_w"],
        "device_static_power_w": report["device_static_power_w"],
        "total_on_chip_power_w": report["total_on_chip_power_w"],
        "dynamic_energy_nj": report["dynamic_power_w"] * inference_seconds * 1_000_000_000.0,
        "device_static_window_energy_nj": report["device_static_power_w"] * inference_seconds * 1_000_000_000.0,
        "total_on_chip_window_energy_nj": report["total_on_chip_power_w"] * inference_seconds * 1_000_000_000.0,
        "confidence": report["confidence"],
        "simulation_activity_file": report["simulation_activity_file"],
        "design_nets_matched": report["design_nets_matched"],
        "design_nets_matched_percent": report["design_nets_matched_percent"],
    }


def summarize(
    *,
    dense_report: Path,
    gated_report: Path,
    dense_saif: Path,
    gated_saif: Path,
    dcp: Path,
    timing_report: Path,
    route_status_report: Path,
    drc_report: Path,
    rtl: Path,
    testbench: Path,
    fixture: Path,
    post_route_netlist: Path,
    clock_mhz: float,
    dense_cycles: int,
    gated_cycles: int,
) -> dict:
    reports = {"dense": parse_report(dense_report), "gated": parse_report(gated_report)}
    expected_period = 1000.0 / clock_mhz
    problems: list[str] = []
    for name, report in reports.items():
        if report["device"] != EXPECTED_PART:
            problems.append(f"{name}: unexpected device {report['device']}")
        if report["design_state"] != "routed":
            problems.append(f"{name}: design is not routed")
        if abs(report["clock_period_ns"] - expected_period) > 1e-6:
            problems.append(f"{name}: clock period is not {expected_period:.3f} ns")
        if report["simulation_activity_file"] in {"---", ""}:
            problems.append(f"{name}: SAIF is not attached")
        if report["design_nets_matched_percent"] is None or report["design_nets_matched_percent"] < MIN_DIRECT_SAIF_MATCH_PERCENT:
            problems.append(f"{name}: SAIF design-net match is below {MIN_DIRECT_SAIF_MATCH_PERCENT:.0f}%")
        if report["confidence"].lower() != "high":
            problems.append(f"{name}: overall power confidence is not High")

    timing = parse_timing_report(timing_report)
    route_errors = parse_route_status(route_status_report)
    drc = parse_drc_report(drc_report)
    if timing["wns_ns"] < 0.0 or timing["tns_ns"] != 0.0 or timing["setup_failing_endpoints"] != 0:
        problems.append("post-route setup timing is not met")
    if timing["whs_ns"] < 0.0 or timing["ths_ns"] != 0.0 or timing["hold_failing_endpoints"] != 0:
        problems.append("post-route hold timing is not met")
    if route_errors != 0:
        problems.append("post-route design has routing errors")
    if drc["error_count"] != 0:
        problems.append("post-route DRC has Error violations")

    modes = {
        "dense": _mode(reports["dense"], dense_cycles, clock_mhz),
        "gated": _mode(reports["gated"], gated_cycles, clock_mhz),
    }
    return {
        "schema": "eneuron_b3_npu_saif_power_v1",
        "status": "PASS" if not problems else "FAIL",
        "problems": problems,
        "part": EXPECTED_PART,
        "clock_mhz": clock_mhz,
        "analysis": "post_route_saif_ooc_core",
        "saif_quality_gate": {
            "minimum_direct_match_percent": MIN_DIRECT_SAIF_MATCH_PERCENT,
            "required_vivado_confidence": "High",
            "rationale": "Post-route gate-level SAIF must cover at least half of design nets and Vivado must rate overall confidence High.",
        },
        "implementation": {"timing": timing, "route_errors": route_errors, "drc": drc},
        "modes": modes,
        "comparison": {
            "core_cycle_speedup": dense_cycles / gated_cycles,
            "dynamic_power_reduction_percent": (1.0 - modes["gated"]["dynamic_power_w"] / modes["dense"]["dynamic_power_w"]) * 100.0,
            "dynamic_energy_reduction_percent": (1.0 - modes["gated"]["dynamic_energy_nj"] / modes["dense"]["dynamic_energy_nj"]) * 100.0,
        },
        "sha256": {
            "dcp": sha256(dcp),
            "dense_saif": sha256(dense_saif),
            "gated_saif": sha256(gated_saif),
            "dense_power_report": sha256(dense_report),
            "gated_power_report": sha256(gated_report),
            "timing_report": sha256(timing_report),
            "route_status_report": sha256(route_status_report),
            "drc_report": sha256(drc_report),
            "rtl": sha256(rtl),
            "testbench": sha256(testbench),
            "fixture": sha256(fixture),
            "post_route_netlist": sha256(post_route_netlist),
        },
        "boundary": "Device static is a whole-device baseline, not NPU-attributable power.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="汇总B3 NPU post-route SAIF功耗")
    parser.add_argument("--dense-report", type=Path, required=True)
    parser.add_argument("--gated-report", type=Path, required=True)
    parser.add_argument("--dense-saif", type=Path, required=True)
    parser.add_argument("--gated-saif", type=Path, required=True)
    parser.add_argument("--dcp", type=Path, required=True)
    parser.add_argument("--timing-report", type=Path, required=True)
    parser.add_argument("--route-status-report", type=Path, required=True)
    parser.add_argument("--drc-report", type=Path, required=True)
    parser.add_argument("--rtl", type=Path, required=True)
    parser.add_argument("--testbench", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--post-route-netlist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clock-mhz", type=float, default=200.0)
    parser.add_argument("--dense-cycles", type=int, default=2494)
    parser.add_argument("--gated-cycles", type=int, default=1606)
    args = parser.parse_args()
    summary = summarize(
        dense_report=args.dense_report,
        gated_report=args.gated_report,
        dense_saif=args.dense_saif,
        gated_saif=args.gated_saif,
        dcp=args.dcp,
        timing_report=args.timing_report,
        route_status_report=args.route_status_report,
        drc_report=args.drc_report,
        rtl=args.rtl,
        testbench=args.testbench,
        fixture=args.fixture,
        post_route_netlist=args.post_route_netlist,
        clock_mhz=args.clock_mhz,
        dense_cycles=args.dense_cycles,
        gated_cycles=args.gated_cycles,
    )
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "output": str(args.output)}, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

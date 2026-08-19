"""Pulse-Mini 物理签核摘要审计。"""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_summary(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def verify(path: Path) -> dict[str, object]:
    values = parse_summary(path)
    required = ("PART", "TOP", "LUT", "FF", "BRAM36", "BRAM18", "DSP", "WNS_NS", "TNS_NS", "WHS_NS", "THS_NS")
    missing = [key for key in required if key not in values]
    if missing:
        raise AssertionError(f"missing summary keys: {missing}")
    lut = int(values["LUT"])
    ff = int(values["FF"])
    bram = int(values["BRAM36"]) + int(values["BRAM18"])
    dsp = int(values["DSP"])
    wns = float(values["WNS_NS"])
    tns = float(values["TNS_NS"])
    whs = float(values["WHS_NS"])
    ths = float(values["THS_NS"])
    checks = {
        "part": values["PART"] == "xc7z020clg400-1",
        "top": values["TOP"] == "pulse_mini_core",
        "lut_hard": lut <= 260,
        "ff_hard": ff <= 140,
        "bram_zero": bram == 0,
        "dsp_zero": dsp == 0,
        "wns_nonnegative": wns >= 0,
        "tns_zero": tns == 0,
        "whs_nonnegative": whs >= 0,
        "ths_zero": ths == 0,
    }
    result = {"summary": values, "checks": checks, "pass": all(checks.values())}
    print(f"PULSE_MINI_VIVADO_AUDIT pass={result['pass']} lut={lut} ff={ff} bram={bram} dsp={dsp} wns={wns} tns={tns}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary", nargs="?", default="vivado_pulse_mini_reports/signoff_summary.txt")
    args = parser.parse_args()
    result = verify(Path(args.summary))
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

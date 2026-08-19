"""P7 阵列资源与时序摘要审计。"""

from __future__ import annotations

from pathlib import Path


def parse(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line)


def main() -> None:
    root = Path("vivado_pulse_mini_array_reports")
    rows = []
    for n in (32, 64, 128):
        values = parse(root / f"n{n}" / "summary.txt")
        row = {key: float(values[key]) if key in {"LUT", "FF", "BRAM", "DSP", "WNS_NS", "TNS_NS"} else values[key] for key in values}
        rows.append(row)
        assert row["BRAM"] == 0 and row["DSP"] == 0
    hard_gate = all(row["WNS_NS"] >= 0 and row["TNS_NS"] == 0 for row in rows)
    print(f"PULSE_MINI_ARRAY_RESOURCE_REPORT_PASS timing_all_pass={hard_gate}")
    for row in rows:
        print(f"N={int(row['N_CORES'])} LUT={int(row['LUT'])} FF={int(row['FF'])} WNS={row['WNS_NS']} TNS={row['TNS_NS']}")
    if not hard_gate:
        print("P7_CAPACITY_CLAIM=NOT_PROVEN simple_broadcast_fanout_timing_failed")


if __name__ == "__main__":
    main()

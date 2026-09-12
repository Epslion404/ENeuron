"""B3-14 四种模式的局部周期比较表。

读取各模式的 run manifest 与 JTAG probe 日志，抽出 0x5C 周期和 execute/skip。
不把静态 mixed 与 live-ENeuron 合成一行，也不把理论稀疏率当成硬件计数。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping


REQUIRED_MODES = (
    "b3_dense",
    "b3_full_open",
    "b3_static_mixed",
    "b3_live_eneuron",
)

REQUIRED_FIELDS = (
    "mode",
    "sample_count",
    "logits",
    "decision_source",
    "mask_granularity",
    "last_compute_cycles",
    "execute_group_count",
    "skip_group_count",
    "active_mask_epoch",
    "pending_mask_epoch",
    "protocol_error_count",
    "runtime_status",
)

# B3-SPEED 墙钟分段：NPU 周期 + PS 调度 + DMA 往返 + Host UART 收发。
SPEED_SEGMENT_FIELDS = (
    "last_compute_cycles",
    "ps_schedule_us",
    "dma_roundtrip_us",
    "host_uart_us",
)
NPU_CLOCK_HZ = 200_000_000

# B3-POWER 仪器合同字段必须与 TODO 原文一致。
POWER_CONTRACT_FIELDS = (
    "仪器",
    "测点",
    "采样率",
    "空闲基线",
    "负载同步",
    "积分窗口",
)
POWER_MODES = (
    "b3_dense",
    "b3_static_mixed",
    "b3_live_eneuron",
)
FORBIDDEN_POWER_SOURCES = (
    "vivado",
    "vivado_estimate",
    "vectorless",
    "saif_estimate",
)
DEFAULT_POWER_CONTRACT = Path(__file__).resolve().parent / "tools/repro/b3_power_instrument_contract.json"


def parse_probe_u32(text: str, key: str) -> int:
    """从 probe_b2_state.tcl 输出解析一个无符号计数。"""
    prefix = f"{key}="
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(prefix):
            value = line[len(prefix):].strip()
            if value.lower().startswith("0x"):
                return int(value, 16)
            return int(value, 10)
    raise ValueError(f"probe log missing {key}")


def record_from_artifacts(
    *,
    mode: str,
    run_manifest: Mapping[str, object],
    probe_text: str,
    logits: tuple[int, ...],
    decision_source: str,
    mask_granularity: str = "group_4way",
    sample_count: int = 1,
    speed: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """用已提交的 probe 解析器从真实 JTAG 文本生成一行 B3-14 记录。"""
    if mode not in REQUIRED_MODES:
        raise ValueError(f"unsupported B3-MVP mode {mode}")
    if run_manifest.get("status") != "PASS":
        raise ValueError(f"{mode} run status is not PASS")
    record = {
        "mode": mode,
        "sample_count": int(sample_count),
        "logits": [int(value) for value in logits],
        "decision_source": decision_source,
        "mask_granularity": mask_granularity,
        "last_compute_cycles": parse_probe_u32(probe_text, "B2_NPU_LAST_COMPUTE_CYCLES"),
        "execute_group_count": parse_probe_u32(probe_text, "B2_NPU_EXECUTE_GROUP_COUNT"),
        "skip_group_count": parse_probe_u32(probe_text, "B2_NPU_SKIP_GROUP_COUNT"),
        "active_mask_epoch": parse_probe_u32(probe_text, "B2_NPU_ACTIVE_MASK_EPOCH"),
        "pending_mask_epoch": parse_probe_u32(probe_text, "B2_NPU_PENDING_MASK_EPOCH"),
        "protocol_error_count": parse_probe_u32(probe_text, "B2_NPU_PROTOCOL_ERROR_COUNT"),
        "runtime_status": parse_probe_u32(probe_text, "B2_NPU_RUNTIME_STATUS"),
        "run_status": run_manifest.get("status"),
        "elf_sha256": run_manifest.get("elf_sha256"),
        "bitstream_sha256": run_manifest.get("bitstream_sha256"),
    }
    if speed is not None:
        for field in ("ps_schedule_us", "dma_roundtrip_us", "host_uart_us"):
            if field not in speed:
                raise ValueError(f"missing B3-SPEED field {field}")
            record[field] = int(speed[field])
        if "host_uart_us" in run_manifest and record["host_uart_us"] != int(run_manifest["host_uart_us"]):
            raise ValueError("host_uart_us must match run_manifest")
    for field in REQUIRED_FIELDS:
        if field not in record:
            raise ValueError(f"missing B3-14 field {field}")
    return record


def build_comparison(records: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    """四种模式必须分行；live 不得复用 static 的 decision_source。"""
    missing = [mode for mode in REQUIRED_MODES if mode not in records]
    if missing:
        raise ValueError(f"B3-14 comparison missing modes: {missing}")
    rows = []
    for mode in REQUIRED_MODES:
        row = dict(records[mode])
        if row.get("mode") != mode:
            raise ValueError(f"record mode mismatch for {mode}")
        rows.append(row)
    live = records["b3_live_eneuron"]
    static = records["b3_static_mixed"]
    if live.get("decision_source") == static.get("decision_source"):
        raise ValueError("live-ENeuron must not collapse into the static mixed row")
    if live.get("decision_source") != "live_eneuron_s2":
        raise ValueError("live-ENeuron decision_source must be live_eneuron_s2")
    if static.get("decision_source") != "host_replay_static_mixed":
        raise ValueError("static mixed decision_source must be host_replay_static_mixed")
    return {
        "schema": "eneuron_b3_14_comparison_v1",
        "modes": REQUIRED_MODES,
        "rows": rows,
    }


def write_comparison(path: Path, comparison: Mapping[str, object]) -> None:
    path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")


def parse_speed_split_from_uart(text: str) -> dict[str, int]:
    """从板端 UART 的 B3_SPEED_SPLIT 行解析 PS/DMA 微秒，不重算黄金值。"""
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("B3_SPEED_SPLIT"):
            continue
        parts = {item.split("=", 1)[0]: item.split("=", 1)[1] for item in line.split() if "=" in item}
        if "ps_us" not in parts or "dma_us" not in parts:
            raise ValueError("B3_SPEED_SPLIT missing ps_us or dma_us")
        return {
            "ps_schedule_us": int(parts["ps_us"], 10),
            "dma_roundtrip_us": int(parts["dma_us"], 10),
        }
    raise ValueError("UART log missing B3_SPEED_SPLIT")


def npu_cycles_to_us(cycles: int) -> float:
    """200 MHz FCLK0 下把 NPU 周期换成微秒，只用于对照，不是墙钟。"""
    return float(cycles) * 1e6 / float(NPU_CLOCK_HZ)


def load_power_contract(path: Path) -> dict[str, object]:
    """读取已冻结的 B3-POWER 仪器合同，不补默认测点。"""
    contract = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if contract.get("schema") != "eneuron_b3_power_instrument_contract_v1":
        raise ValueError("power contract schema mismatch")
    missing = [field for field in POWER_CONTRACT_FIELDS if field not in contract]
    if missing:
        raise ValueError(f"power contract missing {missing}")
    return contract


def forbid_vivado_as_board_power(report: Mapping[str, object]) -> None:
    """禁止把 Vivado 功耗估算写成板上功耗。"""
    source = str(report.get("power_source", "")).lower()
    if source in FORBIDDEN_POWER_SOURCES or "vivado" in source:
        raise ValueError("must not treat Vivado power estimate as board power")
    for row in report.get("rows", ()):
        row_source = str(row.get("power_source", "")).lower()
        if row_source in FORBIDDEN_POWER_SOURCES or "vivado" in row_source:
            raise ValueError("must not treat Vivado power estimate as board power")


def build_power_report(
    records: Mapping[str, Mapping[str, object]],
    contract: Mapping[str, object],
) -> dict[str, object]:
    """B3-POWER：dense/static/live 分行；无外部 traces 只能是 POWER_NOT_MEASURED。"""
    missing_fields = [field for field in POWER_CONTRACT_FIELDS if field not in contract]
    if missing_fields:
        raise ValueError(f"B3-POWER missing {missing_fields[0]}")
    missing_modes = [mode for mode in POWER_MODES if mode not in records]
    if missing_modes:
        raise ValueError(f"B3-POWER comparison missing modes: {missing_modes}")
    rows = []
    for mode in POWER_MODES:
        row = dict(records[mode])
        if row.get("mode") != mode:
            raise ValueError(f"record mode mismatch for {mode}")
        rows.append(row)
    live = records["b3_live_eneuron"]
    static = records["b3_static_mixed"]
    if live.get("decision_source") == static.get("decision_source"):
        raise ValueError("live-ENeuron must not collapse into the static mixed row")
    if live.get("decision_source") != "live_eneuron_s2":
        raise ValueError("live-ENeuron decision_source must be live_eneuron_s2")
    if static.get("decision_source") != "host_replay_static_mixed":
        raise ValueError("static mixed decision_source must be host_replay_static_mixed")
    report = {
        "schema": "eneuron_b3_power_report_v1",
        "modes": list(POWER_MODES),
        "rows": rows,
        "contract": {field: contract.get(field) for field in POWER_CONTRACT_FIELDS},
    }
    forbid_vivado_as_board_power(report)
    status = contract.get("status")
    if status == "POWER_NOT_MEASURED":
        report["status"] = "POWER_NOT_MEASURED"
        report["power_gate"] = "OPEN"
        return report
    if status == "MEASURED":
        for row in rows:
            if "external_power_w" not in row:
                raise ValueError("MEASURED B3-POWER missing external_power_w")
            if type(row["external_power_w"]) not in (int, float):
                raise ValueError("external_power_w must be numeric")
            row_source = str(row.get("power_source", "external"))
            if row_source.lower() in FORBIDDEN_POWER_SOURCES or "vivado" in row_source.lower():
                raise ValueError("must not treat Vivado power estimate as board power")
        report["status"] = "MEASURED"
        report["power_gate"] = "PASS"
        return report
    raise ValueError("B3-POWER status must be MEASURED or POWER_NOT_MEASURED")


def forbid_end_to_end_from_npu_cycles(comparison: Mapping[str, object]) -> None:
    """禁止把局部 NPU 周期差写成端到端加速。"""
    claim = comparison.get("claim")
    if comparison.get("end_to_end_accelerated") is True or claim in {
        "end_to_end_acceleration",
        "e2e_from_888",
        "end_to_end_accelerated_from_npu_cycles",
    }:
        raise ValueError("must not treat NPU cycle delta as end-to-end acceleration")


def build_speed_comparison(records: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    """B3-SPEED：四种模式分行，每行必须有四段墙钟。"""
    comparison = build_comparison(records)
    for row in comparison["rows"]:
        for field in SPEED_SEGMENT_FIELDS:
            if field not in row:
                raise ValueError(f"B3-SPEED missing {field} for {row.get('mode')}")
            value = row[field]
            if type(value) is not int or value < 0:
                raise ValueError(f"B3-SPEED {field} must be a non-negative int")
        npu_us = npu_cycles_to_us(int(row["last_compute_cycles"]))
        if row["host_uart_us"] == int(npu_us) and row["dma_roundtrip_us"] == int(npu_us):
            raise ValueError("wall-clock segments must not be copies of NPU cycle time")
    dense_cycles = int(records["b3_dense"]["last_compute_cycles"])
    gated_cycles = int(records["b3_static_mixed"]["last_compute_cycles"])
    comparison["schema"] = "eneuron_b3_speed_comparison_v1"
    comparison["claim"] = "local_npu_cycle_delta_only"
    comparison["end_to_end_accelerated"] = False
    comparison["npu_cycle_delta"] = dense_cycles - gated_cycles
    comparison["npu_clock_hz"] = NPU_CLOCK_HZ
    forbid_end_to_end_from_npu_cycles(comparison)
    return comparison


DECISION_SOURCE_BY_MODE = {
    "b3_dense": "none_full_open_or_dense",
    "b3_full_open": "host_full_open_mask",
    "b3_static_mixed": "host_replay_static_mixed",
    "b3_live_eneuron": "live_eneuron_s2",
}


def parse_logits_from_uart(text: str) -> tuple[int, ...]:
    """从实板 UART PASS 行解析 logits= 列表，不重算黄金值。"""
    for raw in text.splitlines():
        line = raw.strip()
        if "_PASS" not in line or "logits=" not in line:
            continue
        marker = "logits="
        start = line.find(marker)
        if start < 0:
            continue
        payload = line[start + len(marker):].split()[0]
        values = tuple(int(part) for part in payload.split(",") if part != "")
        if len(values) != 10:
            raise ValueError(f"UART logits length {len(values)} != 10")
        return values
    raise ValueError("UART log missing logits= PASS line")


def record_from_run_dir(run_dir: Path, mode: str, *, require_speed: bool = False) -> dict[str, object]:
    """从一次 packet board run 目录生成 B3-14 行。"""
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8-sig"))
    probe_path = run_dir / "post_pass_probe.log"
    if not probe_path.is_file():
        raise ValueError(f"{run_dir} missing post_pass_probe.log")
    uart_path = run_dir / "uart.log"
    if not uart_path.is_file():
        raise ValueError(f"{run_dir} missing uart.log")
    probe_text = probe_path.read_text(encoding="utf-8-sig")
    uart_text = uart_path.read_text(encoding="utf-8-sig")
    if mode == "b3_live_eneuron" and "decision_source=live_eneuron_s2" not in uart_text:
        raise ValueError("live-ENeuron UART must name live_eneuron_s2")
    if mode == "b3_static_mixed" and "B3_LIVE_ENEURON" in uart_text:
        raise ValueError("static mixed UART must not use the live-ENeuron marker")
    speed = None
    if require_speed:
        split = parse_speed_split_from_uart(uart_text)
        if "host_uart_us" not in manifest:
            raise ValueError("run_manifest missing host_uart_us")
        speed = {
            "ps_schedule_us": split["ps_schedule_us"],
            "dma_roundtrip_us": split["dma_roundtrip_us"],
            "host_uart_us": int(manifest["host_uart_us"]),
        }
    return record_from_artifacts(
        mode=mode,
        run_manifest=manifest,
        probe_text=probe_text,
        logits=parse_logits_from_uart(uart_text),
        decision_source=DECISION_SOURCE_BY_MODE[mode],
        speed=speed,
    )


def comparison_from_run_dirs(run_dirs: Mapping[str, Path], *, require_speed: bool = False) -> dict[str, object]:
    records = {
        mode: record_from_run_dir(Path(run_dirs[mode]), mode, require_speed=require_speed)
        for mode in REQUIRED_MODES
    }
    if require_speed:
        return build_speed_comparison(records)
    return build_comparison(records)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build B3-14 comparison from four packet board runs")
    parser.add_argument("--dense", type=Path, required=True)
    parser.add_argument("--full-open", type=Path, required=True)
    parser.add_argument("--static-mixed", type=Path, required=True)
    parser.add_argument("--live-eneuron", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--speed", action="store_true", help="Build B3-SPEED wall-clock comparison")
    args = parser.parse_args()
    comparison = comparison_from_run_dirs({
        "b3_dense": args.dense,
        "b3_full_open": args.full_open,
        "b3_static_mixed": args.static_mixed,
        "b3_live_eneuron": args.live_eneuron,
    }, require_speed=bool(args.speed))
    write_comparison(args.out, comparison)
    if args.speed:
        print(f"B3_SPEED_COMPARISON={args.out}")
    else:
        print(f"B3_14_COMPARISON={args.out}")

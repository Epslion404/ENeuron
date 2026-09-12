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

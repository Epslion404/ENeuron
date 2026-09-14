"""B3 剪枝前后整板功率归因分析：只读、fail-closed，不关闭任何门。

默认输入是主线已归档的 B10 人工读数与 B3-POWER 报告：

- `artifacts/logs/b3_power_20260913_be84596/manual_meter_observations_20260913.json`
- `artifacts/logs/b3_power_20260913_be84596/b3_power_report.json`

主线 rollup 只有 live 窗口带 `valid_inferences`，所以吞吐、每次正确推理能耗和 NPU 占空比
默认只对 live 可算。其它窗口的计数必须经 `--extra-counts` 显式提供，且每条都要绑定来源
ref 与 canonical-LF SHA-256；本工具不给缺失计数猜值，也不读取 Vivado 功耗报告：
Vivado 估算不能冒充板上实测（`docs/planning/NPU_B3_POWER_INSTRUMENT_CONTRACT_V1.md`）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parent
DEFAULT_OBSERVATIONS = ROOT / "artifacts/logs/b3_power_20260913_be84596/manual_meter_observations_20260913.json"
DEFAULT_POWER_REPORT = ROOT / "artifacts/logs/b3_power_20260913_be84596/b3_power_report.json"
DEFAULT_CLOCK_HZ = 200_000_000.0
IDLE_MODE = "b3_idle"
DENSE_MODES = ("b3_dense_round_1", "b3_dense_round_2")
PRUNED_MODES = ("b3_static_mixed", "b3_live_eneuron")
MWH_TO_J = 3.6
POWER_TOLERANCE_W = 0.0005


def canonical_lf_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_observations(path: Path) -> tuple[list[dict[str, object]], float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    instrument = payload.get("instrument") or {}
    accuracy = instrument.get("accuracy_percent")
    if not isinstance(accuracy, (int, float)) or accuracy <= 0:
        raise ValueError("仪器准确度缺失或非正数，无法给功率差值定不确定度")
    windows: list[dict[str, object]] = []
    for item in payload.get("observations") or []:
        for field in ("mode", "duration_s", "delta_mWh", "average_power_w"):
            if field not in item:
                raise ValueError(f"窗口 {item.get('mode')} 缺字段 {field}")
        duration = item["duration_s"]
        delta_mwh = item["delta_mWh"]
        if duration <= 0 or delta_mwh <= 0:
            raise ValueError(f"窗口 {item['mode']} 的时长或能量增量非正")
        recomputed = delta_mwh * MWH_TO_J / duration
        if abs(recomputed - item["average_power_w"]) > POWER_TOLERANCE_W:
            raise ValueError(
                f"窗口 {item['mode']} 平均功率自洽失败：记录 {item['average_power_w']} vs 复算 {recomputed:.8f}"
            )
        windows.append(
            {
                "mode": item["mode"],
                "duration_s": duration,
                "delta_mwh": delta_mwh,
                "average_power_w": item["average_power_w"],
                "valid_inferences": item.get("valid_inferences"),
                "recomputed_average_power_w": round(recomputed, 8),
            }
        )
    if not any(w["mode"] == IDLE_MODE for w in windows):
        raise ValueError("缺 idle 基线，无法区分负载功率与整板静态")
    return windows, float(accuracy)


def cycles_by_mode(power_report: Mapping[str, object]) -> dict[str, int]:
    rows: dict[str, int] = {}
    for row in power_report.get("rows") or []:  # type: ignore[union-attr]
        mode = row.get("mode")
        cycles = row.get("last_compute_cycles")
        if isinstance(mode, str) and isinstance(cycles, int) and cycles > 0:
            rows[mode] = cycles
    if not rows:
        raise ValueError("B3-POWER 报告里没有可用的 last_compute_cycles")
    return rows


def load_extra_counts(path: Path | None) -> tuple[dict[str, object], list[dict[str, object]]]:
    if path is None:
        return {}, []
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("inferences")
    if not isinstance(entries, list):
        raise ValueError("--extra-counts 需要 inferences 列表（裸 mode->计数 映射缺来源绑定，不接受）")
    counts: dict[str, object] = {}
    sources: list[dict[str, object]] = []
    for item in entries:
        mode = item.get("mode")
        value = item.get("valid_inferences")
        ref = item.get("source_ref")
        digest = item.get("source_canonical_lf_sha256")
        if not isinstance(mode, str) or not isinstance(value, (int, float)):
            raise ValueError("计数条目缺 mode 或非数值的 valid_inferences")
        if value < 0 or math.isnan(float(value)):
            raise ValueError(f"窗口 {mode} 的 valid_inferences 非法")
        if not isinstance(ref, str) or not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"窗口 {mode} 的计数缺 source_ref/canonical-LF SHA-256 绑定")
        counts[mode] = value
        sources.append(
            {
                "mode": mode,
                "valid_inferences": value,
                "source_ref": ref,
                "source_blob_sha1": item.get("source_blob_sha1"),
                "source_canonical_lf_sha256": digest,
            }
        )
    return counts, sources


def build_analysis(
    windows: list[dict[str, object]],
    cycles: Mapping[str, int],
    *,
    accuracy_percent: float,
    clock_hz: float = DEFAULT_CLOCK_HZ,
    extra_counts: Mapping[str, object] | None = None,
    count_sources: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    counts = dict(extra_counts or {})
    idle = next(w for w in windows if w["mode"] == IDLE_MODE)
    dense = [w for w in windows if w["mode"] in DENSE_MODES]
    if not dense:
        raise ValueError("缺 dense 窗口，无法与剪枝模式比较")
    p_idle = float(idle["average_power_w"])
    p_dense = sum(float(w["average_power_w"]) for w in dense) / len(dense)

    cycles_for = {
        "b3_dense_round_1": cycles.get("b3_dense"),
        "b3_dense_round_2": cycles.get("b3_dense"),
        "b3_static_mixed": cycles.get("b3_static_mixed"),
        "b3_live_eneuron": cycles.get("b3_live_eneuron"),
        "b3_idle": 0,
    }
    rows: list[dict[str, object]] = []
    for window in windows:
        mode = str(window["mode"])
        valid = window["valid_inferences"]
        origin = "rollup" if valid is not None else None
        if valid is None:
            valid = counts.get(mode)
            origin = "extra_counts" if valid is not None else None
        throughput = None
        energy_mj = None
        duty_percent = None
        cycles_used = cycles_for.get(mode)
        if isinstance(valid, (int, float)) and valid > 0:
            throughput = float(valid) / float(window["duration_s"])
            energy_mj = float(window["delta_mwh"]) * MWH_TO_J / float(valid) * 1000.0
            if isinstance(cycles_used, int):
                duty_percent = throughput * cycles_used / clock_hz * 100.0
        rows.append(
            {
                "mode": mode,
                "duration_s": window["duration_s"],
                "delta_mwh": window["delta_mwh"],
                "average_power_w": window["average_power_w"],
                "valid_inferences": valid,
                "valid_inference_origin": origin,
                "inferences_per_second": None if throughput is None else round(throughput, 3),
                "energy_per_valid_inference_mj": None if energy_mj is None else round(energy_mj, 7),
                "npu_compute_cycles": cycles_used,
                "npu_duty_percent": None if duty_percent is None else round(duty_percent, 4),
                "delta_power_vs_idle_percent": round((float(window["average_power_w"]) - p_idle) / p_idle * 100, 4),
                "delta_power_vs_dense_mean_percent": (
                    None
                    if mode in DENSE_MODES or mode == IDLE_MODE
                    else round((float(window["average_power_w"]) - p_dense) / p_dense * 100, 4)
                ),
            }
        )

    dense_powers = [float(w["average_power_w"]) for w in dense]
    scatter = max(dense_powers) - min(dense_powers) if len(dense_powers) >= 2 else None
    uncertainty_w = accuracy_percent / 100.0 * p_idle
    by_mode = {str(r["mode"]): r for r in rows}
    gaps: dict[str, object] = {}
    for label, mode in (("live", "b3_live_eneuron"), ("static_mixed", "b3_static_mixed")):
        if mode in by_mode:
            delta = float(by_mode[mode]["average_power_w"]) - p_dense
            gaps[label] = {
                "delta_power_w": round(delta, 8),
                "delta_power_percent": round(delta / p_dense * 100, 4),
                "exceeds_instrument_uncertainty": abs(delta) > uncertainty_w,
                "exceeds_same_config_repeatability": None if scatter is None else abs(delta) > scatter,
            }
    dense_energy = [
        by_mode[m]["energy_per_valid_inference_mj"]
        for m in DENSE_MODES
        if by_mode.get(m) is not None and by_mode[m]["energy_per_valid_inference_mj"]
    ]
    energy_gaps: dict[str, object] = {}
    for label, mode in (("live", "b3_live_eneuron"), ("static_mixed", "b3_static_mixed")):
        value = by_mode[mode]["energy_per_valid_inference_mj"]
        if dense_energy and isinstance(value, float):
            base = sum(dense_energy) / len(dense_energy)
            energy_gaps[label] = {
                "energy_per_valid_inference_mj": value,
                "delta_vs_dense_mean_percent": round((value - base) / base * 100, 4),
            }
    inverted = [str(r["mode"]) for r in rows if r["mode"] != IDLE_MODE and float(r["average_power_w"]) < p_idle]
    resolvable = [v["exceeds_same_config_repeatability"] for v in gaps.values()]
    return {
        "schema": "eneuron_b3_power_attribution_v1",
        "status": "POWER_ATTRIBUTION_NOT_ESTABLISHED",
        "power_gate": "OPEN",
        "power_goal_status": "NOT_PROVEN",
        "b3_power_measured": "POWER_NOT_MEASURED",
        "instrument_accuracy_percent": accuracy_percent,
        "instrument_uncertainty_w": round(uncertainty_w, 8),
        "same_config_repeatability_w": None if scatter is None else round(scatter, 8),
        "idle_baseline_w": p_idle,
        "dense_mean_power_w": round(p_dense, 8),
        "clock_hz": clock_hz,
        "windows": rows,
        "valid_inference_sources": count_sources or [],
        "counts_from_mainline_rollup_only": not bool(count_sources),
        "delta_vs_dense": gaps,
        "energy_per_valid_inference": energy_gaps,
        "idle_inverted_load_windows": inverted,
        "verdict_rules": {
            "idle_is_lowest_window": not inverted,
            "gap_exceeds_same_config_repeatability": (
                all(flag is True for flag in resolvable) if scatter is not None and resolvable else None
            ),
            "rounds_per_mode": {"dense": len(dense_powers), "pruned": sum(1 for m in PRUNED_MODES if m in by_mode)},
        },
        "claim_boundary": {
            "measurement_point": "Type-C 整板输入，非 PL 轨",
            "evidence_class": "engineering_observation",
            "vivado_estimate_used_as_board_power": False,
            "pruning_power_benefit_proven": False,
            "gate_closure_authority": "none",
        },
        "forbidden_claims": [
            "剪枝已降低板上功耗",
            "power_gate=PASS",
            "B3-POWER-MEASURED 已完成",
            "Vivado 估算等于板上实测",
        ],
    }


def write_analysis(path: Path, analysis: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def analyze(
    observations: Path,
    power_report: Path,
    *,
    extra_counts: Path | None = None,
    clock_hz: float = DEFAULT_CLOCK_HZ,
) -> dict[str, object]:
    windows, accuracy = load_observations(observations)
    counts, sources = load_extra_counts(extra_counts)
    analysis = build_analysis(
        windows,
        cycles_by_mode(json.loads(power_report.read_text(encoding="utf-8"))),
        accuracy_percent=accuracy,
        clock_hz=clock_hz,
        extra_counts=counts,
        count_sources=sources,
    )
    analysis["input_bindings"] = {
        "observations_canonical_lf_sha256": canonical_lf_sha256(observations),
        "power_report_canonical_lf_sha256": canonical_lf_sha256(power_report),
    }
    if extra_counts is not None:
        analysis["input_bindings"]["valid_inference_inputs_canonical_lf_sha256"] = canonical_lf_sha256(extra_counts)
    return analysis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="分析剪枝后的整板功率变化（只读，fail-closed）")
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument("--power-report", type=Path, default=DEFAULT_POWER_REPORT)
    parser.add_argument("--extra-counts", type=Path)
    parser.add_argument("--clock-hz", type=float, default=DEFAULT_CLOCK_HZ)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args(argv)
    analysis = analyze(
        args.observations,
        args.power_report,
        extra_counts=args.extra_counts,
        clock_hz=args.clock_hz,
    )
    if args.output:
        write_analysis(args.output, analysis)
    print(json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

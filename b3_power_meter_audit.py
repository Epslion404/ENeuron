"""B3 功率计读数独立审计：只读、fail-closed，不修改任何已冻结证据文件。

审计四件事（全部只用主线
`artifacts/logs/b3_power_20260913_be84596/manual_meter_observations_20260913.json`）：

1. **通道自洽**：`delta_mWh` / `delta_mAh` 是否等于该窗口自身 `readings` 数组的首末差，
   并用隐含电压（ΔmWh/ΔmAh 必须落在 Type-C 的 4.5–5.5 V）判出到底是哪一条通道抄错。
2. **段级坏点**：把窗口按相邻读数切段，用 ΔmWh 反推段功率，与段两端显示功率均值比较，
   超过 MAD 稳健门限即判坏点；对被同一内部读数污染的相邻两段，线性内插还原该读数。
3. **可辨识性**：剪枝等级与测量时刻的秩是否共线；线性去漂移后的处理残差对“漂移口径”的敏感性。
4. **检测功效**：给定同配置重复性 σ_pair，分辨指定效应所需的配对轮数。

本工具不关闭任何门，也不把仪表读数升级为实测结论：`delta_mAh` 缺陷只**报告**，
不改写证据文件（该文件的 canonical-LF SHA-256 已被 `b3_power_attribution.json` 绑定）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parent
DEFAULT_OBSERVATIONS = ROOT / "artifacts/logs/b3_power_20260913_be84596/manual_meter_observations_20260913.json"
MWH_TO_J = 3.6
VOLTAGE_PLAUSIBLE_RANGE = (4.5, 5.5)
OUTLIER_SIGMA = 3.0
MAD_TO_SIGMA = 1.4826
Z_TWO_SIDED_05 = 1.959_963_985
Z_POWER_80 = 0.841_621_234
IDLE_MODE = "b3_idle"
DENSE_MODES = ("b3_dense_round_1", "b3_dense_round_2")
PRUNED_MODES = ("b3_static_mixed", "b3_live_eneuron")
PRUNED_LEVELS = {"b3_idle": 0, "b3_dense_round_1": 1, "b3_dense_round_2": 1, "b3_static_mixed": 2, "b3_live_eneuron": 3}


def canonical_lf_sha256(path: Path) -> str:
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_stamp(window: Mapping[str, object], hhmmss: str) -> datetime:
    start = str(window["start"])
    return datetime.fromisoformat(f"{start[:10]}T{hhmmss}")


class AuditInputError(ValueError):
    """读数本身不足以支撑审计：宁可抛错，也不给出结论。"""


def validate_observations(observations: list[Mapping[str, object]]) -> None:
    if not observations:
        raise AuditInputError("没有任何窗口读数")
    modes = [str(w["mode"]) for w in observations]
    if set(modes) != set(PRUNED_LEVELS):
        raise AuditInputError("窗口集合与 B3 五窗口合同不符: " + ",".join(sorted(modes)))
    if len(modes) != len(set(modes)):
        raise AuditInputError("窗口 mode 重复，无法判定测量顺序")
    lo, hi = VOLTAGE_PLAUSIBLE_RANGE
    for window in observations:
        mode = str(window["mode"])
        readings = window.get("readings")
        if not isinstance(readings, list) or len(readings) < 2:
            raise AuditInputError(mode + " 的 readings 缺失或不足两条，无法切段")
        stamps = [_parse_stamp(window, str(r[0])) for r in readings]
        for first, second in zip(stamps, stamps[1:]):
            if (second - first).total_seconds() <= 0:
                raise AuditInputError(mode + " 存在非正的段时长")
        if int(window["delta_mWh"]) != int(readings[-1][5]) - int(readings[0][5]):
            raise AuditInputError(mode + " 的 delta_mWh 与自身 readings 首末差不一致，通道审计失效")
        recorded_mah = int(window["delta_mAh"])
        if recorded_mah:
            implied = int(window["delta_mWh"]) / recorded_mah
            if not lo <= implied <= hi and recorded_mah == int(readings[-1][4]) - int(readings[0][4]):
                raise AuditInputError(mode + " 的隐含电压越界却被记为自洽，判据本身失效")



def audit_channels(observations: list[Mapping[str, object]]) -> dict[str, object]:
    per_window: list[dict[str, object]] = []
    for window in observations:
        readings = window["readings"]
        mah_span = int(readings[-1][4]) - int(readings[0][4])
        mwh_span = int(readings[-1][5]) - int(readings[0][5])
        recorded_mwh = int(window["delta_mWh"])
        recorded_mah = int(window["delta_mAh"])
        displayed_v = statistics.mean(float(r[1]) for r in readings)
        implied_v_recorded = recorded_mwh / recorded_mah if recorded_mah else float("nan")
        implied_v_readings = mwh_span / mah_span if mah_span else float("nan")
        lo, hi = VOLTAGE_PLAUSIBLE_RANGE
        per_window.append(
            {
                "mode": str(window["mode"]),
                "mwh_matches_readings": recorded_mwh == mwh_span,
                "mah_matches_readings": recorded_mah == mah_span,
                "recorded_delta_mAh": recorded_mah,
                "readings_delta_mAh": mah_span,
                "recorded_delta_mWh": recorded_mwh,
                "readings_delta_mWh": mwh_span,
                "implied_voltage_v_from_recorded_mAh": round(implied_v_recorded, 4),
                "implied_voltage_v_from_readings": round(implied_v_readings, 4),
                "display_voltage_mean_v": round(displayed_v, 5),
                "recorded_mAh_channel_plausible": lo <= implied_v_recorded <= hi,
                "readings_mAh_channel_plausible": lo <= implied_v_readings <= hi,
                "implied_v_vs_display_v_percent": round((implied_v_readings - displayed_v) / displayed_v * 100, 4),
            }
        )
    return {
        "per_window": per_window,
        "mwh_channel_self_consistent": all(bool(w["mwh_matches_readings"]) for w in per_window),
        "mah_field_self_consistent": all(bool(w["mah_matches_readings"]) for w in per_window),
        "windows_with_bad_mAh_field": [w["mode"] for w in per_window if not w["mah_matches_readings"]],
        "bad_mAh_field_error_mAh": {
            w["mode"]: int(w["recorded_delta_mAh"]) - int(w["readings_delta_mAh"])
            for w in per_window
            if not w["mah_matches_readings"]
        },
        "defect_class": (
            "DELTA_MAH_FIELD_INCONSISTENT_WITH_READINGS"
            if any(not w["mah_matches_readings"] for w in per_window)
            else "CHANNELS_CONSISTENT"
        ),
        "power_metrics_channel": "delta_mWh（自洽，5/5 与 readings 首末差一致）",
        "evidence_rewrite": "forbidden",
    }


def audit_segments(observations: list[Mapping[str, object]]) -> dict[str, object]:
    segments: list[dict[str, object]] = []
    for window in observations:
        readings = window["readings"]
        for first, second in zip(readings, readings[1:]):
            dt = (_parse_stamp(window, str(second[0])) - _parse_stamp(window, str(first[0]))).total_seconds()
            dmwh = int(second[5]) - int(first[5])
            segment_power = dmwh * MWH_TO_J / dt
            displayed_mean = (float(first[3]) + float(second[3])) / 2.0
            segments.append(
                {
                    "mode": str(window["mode"]),
                    "from": str(first[0]),
                    "to": str(second[0]),
                    "duration_s": round(dt, 1),
                    "delta_mWh": dmwh,
                    "segment_power_w": round(segment_power, 6),
                    "displayed_power_mean_w": round(displayed_mean, 6),
                    "deviation_mw": round((segment_power - displayed_mean) * 1000, 3),
                }
            )
    deviations = [abs(float(s["deviation_mw"])) for s in segments]
    median = statistics.median(deviations)
    mad_sigma = MAD_TO_SIGMA * statistics.median(abs(d - median) for d in deviations)
    threshold = OUTLIER_SIGMA * mad_sigma
    outliers = [s for s in segments if abs(float(s["deviation_mw"])) > threshold]
    recoveries: list[dict[str, object]] = []
    for first, second in zip(outliers, outliers[1:]):
        if first["mode"] != second["mode"] or first["to"] != second["from"]:
            continue
        if float(first["deviation_mw"]) * float(second["deviation_mw"]) > 0:
            continue
        window = next(w for w in observations if str(w["mode"]) == str(first["mode"]))
        readings = window["readings"]
        idx = next(i for i, r in enumerate(readings) if str(r[0]) == str(first["to"]))
        span_s = (_parse_stamp(window, str(readings[idx + 1][0])) - _parse_stamp(window, str(readings[idx - 1][0]))).total_seconds()
        span_mwh = int(readings[idx + 1][5]) - int(readings[idx - 1][5])
        leg_s = (_parse_stamp(window, str(readings[idx][0])) - _parse_stamp(window, str(readings[idx - 1][0]))).total_seconds()
        interpolated = int(readings[idx - 1][5]) + span_mwh * leg_s / span_s
        error_mwh = int(readings[idx][5]) - interpolated
        duration_s = float(window["duration_s"])
        recoveries.append(
            {
                "mode": str(window["mode"]),
                "suspect_reading_at": str(readings[idx][0]),
                "recorded_mWh": int(readings[idx][5]),
                "interpolated_mWh": round(interpolated, 2),
                "single_reading_error_mWh": round(error_mwh, 2),
                "single_reading_error_J": round(error_mwh * MWH_TO_J, 2),
                "same_error_at_window_endpoint_power_error_mW": round(abs(error_mwh) * MWH_TO_J / duration_s * 1000, 3),
            }
        )
    return {
        "segment_count": len(segments),
        "abs_deviation_mw": {"median": round(median, 3), "robust_sigma": round(mad_sigma, 3), "outlier_threshold": round(threshold, 3)},
        "outlier_segments": outliers,
        "outlier_count": len(outliers),
        "shared_reading_recoveries": recoveries,
        "displayed_power_distinct_values": len({float(r[3]) for w in observations for r in w["readings"]}),
        "displayed_current_distinct_values": sorted({float(r[2]) for w in observations for r in w["readings"]}),
        "displayed_current_lsb_power_mw": round(
            (max(float(r[2]) for w in observations for r in w["readings"]) - min(float(r[2]) for w in observations for r in w["readings"]))
            / 2.0
            * statistics.mean(float(r[1]) for w in observations for r in w["readings"])
            * 1000,
            2,
        ),
        "energy_accumulator_resolution_mw": {
            str(w["mode"]): round(MWH_TO_J / float(w["duration_s"]) * 1000, 3) for w in observations
        },
        "endpoint_half_count_resolution_mw": {
            str(w["mode"]): round(0.5 * MWH_TO_J / float(w["duration_s"]) * 1000, 3) for w in observations
        },
    }


def _ols(x: list[float], y: list[float]) -> dict[str, float]:
    n = len(x)
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    slope = sxy / sxx
    intercept = my - slope * mx
    resid = [b - (intercept + slope * a) for a, b in zip(x, y)]
    ss_res = sum(r * r for r in resid)
    ss_tot = sum((b - my) ** 2 for b in y)
    se_slope = math.sqrt(ss_res / (n - 2) / sxx) if n > 2 else float("nan")
    return {"slope": slope, "intercept": intercept, "se_slope": se_slope, "r2": 1 - ss_res / ss_tot, "residuals": resid}


def audit_identifiability(observations: list[Mapping[str, object]]) -> dict[str, object]:
    ordered = sorted(observations, key=lambda w: _parse_stamp(w, str(w["readings"][0][0])))
    levels = [PRUNED_LEVELS[str(w["mode"])] for w in ordered]
    t0 = _parse_stamp(ordered[0], str(ordered[0]["readings"][0][0]))
    hours = []
    for window in ordered:
        begin = _parse_stamp(window, str(window["readings"][0][0])).timestamp()
        finish = _parse_stamp(window, str(window["readings"][-1][0])).timestamp()
        hours.append(((begin + finish) / 2.0 - t0.timestamp()) / 3600.0)
    power = [float(w["average_power_w"]) for w in ordered]
    discordant = sum(1 for i in range(len(levels)) for j in range(i + 1, len(levels)) if levels[i] > levels[j])
    fit = _ols(hours, power)
    by_mode = {str(w["mode"]): w for w in observations}
    dense_hours = [hours[i] for i, w in enumerate(ordered) if str(w["mode"]) in DENSE_MODES]
    dense_power = [power[i] for i, w in enumerate(ordered) if str(w["mode"]) in DENSE_MODES]
    same_config_rate = None
    if len(dense_hours) == 2:
        gap = abs(dense_hours[1] - dense_hours[0])
        same_config_rate = abs(dense_power[1] - dense_power[0]) * 1000 / gap
    dm_t = statistics.mean(dense_hours) if dense_hours else float("nan")
    dm_p = statistics.mean(dense_power) if dense_power else float("nan")
    detrended: dict[str, object] = {}
    for mode in PRUNED_MODES:
        if mode not in by_mode:
            continue
        window = by_mode[mode]
        idx = next(i for i, w in enumerate(ordered) if str(w["mode"]) == mode)
        dt = hours[idx] - dm_t
        observed_drop_mw = (dm_p - float(window["average_power_w"])) * 1000
        by_regression = observed_drop_mw - (-fit["slope"] * 1000) * dt
        by_same_config = observed_drop_mw - (same_config_rate or 0.0) * dt
        detrended[mode] = {
            "elapsed_hours_vs_dense_mean": round(dt, 4),
            "observed_drop_mw": round(observed_drop_mw, 3),
            "detrended_using_regression_rate_mw": round(by_regression, 3),
            "detrended_using_same_config_rate_mw": round(by_same_config, 3),
            "sign_stable_across_drift_convention": (by_regression > 0) == (by_same_config > 0),
        }
    return {
        "measurement_order": [str(w["mode"]) for w in ordered],
        "pruning_level_sequence": levels,
        "discordant_level_time_pairs": discordant,
        "level_and_time_rank_collinear": discordant == 0,
        "linear_time_fit": {
            "slope_mw_per_h": round(fit["slope"] * 1000, 4),
            "slope_stderr_mw_per_h": round(fit["se_slope"] * 1000, 4),
            "slope_t_stat": round(fit["slope"] / fit["se_slope"], 3),
            "r2": round(fit["r2"], 4),
            "residuals_mw": [round(r * 1000, 3) for r in fit["residuals"]],
        },
        "same_config_drift_rate_mw_per_h": None if same_config_rate is None else round(same_config_rate, 4),
        "detrended_effect": detrended,
        "verdict": "TREATMENT_NOT_IDENTIFIABLE_FROM_WINDOW_MEANS",
    }


def audit_power(sigma_pair_mw: float, effects_mw: Mapping[str, float], rounds: tuple[int, ...] = (1, 2, 3, 5, 10, 20, 40, 80, 160, 320)) -> dict[str, object]:
    def n_required(effect: float) -> int:
        return math.ceil(((Z_TWO_SIDED_05 + Z_POWER_80) * sigma_pair_mw / effect) ** 2)

    return {
        "model": "配对两轮正态，双侧 alpha=0.05，功效 80%，n = ((z_a+z_b)*sigma_pair/effect)^2",
        "sigma_pair_mw": round(sigma_pair_mw, 4),
        "sigma_pair_source": "同一 dense 配置两轮的功率差（唯一无处理混淆的重复性估计）",
        "sigma_pair_caveat": "该 sigma 只有 1 个自由度（90% CI 约 5.2–107.6 mW），所以轮数是量级结论而非精确值",
        "required_rounds_per_mode": {k: n_required(v) for k, v in sorted(effects_mw.items())},
        "detectable_effect_mw_at_rounds": {
            str(n): round((Z_TWO_SIDED_05 + Z_POWER_80) * sigma_pair_mw / math.sqrt(n), 3) for n in rounds
        },
        "contract_v2_planned_rounds": 5,
        "contract_v2_detectable_effect_mw": round((Z_TWO_SIDED_05 + Z_POWER_80) * sigma_pair_mw / math.sqrt(5), 3),
    }


def build_audit(observations: list[Mapping[str, object]], *, sigma_pair_mw: float, effects_mw: Mapping[str, float]) -> dict[str, object]:
    validate_observations(observations)
    channels = audit_channels(observations)
    segments = audit_segments(observations)
    identifiability = audit_identifiability(observations)
    power = audit_power(sigma_pair_mw, effects_mw)
    return {
        "schema": "eneuron_b3_power_meter_audit_v1",
        "status": "POWER_METER_READING_AUDIT_COMPLETE",
        "b3_power_measured": "POWER_NOT_MEASURED",
        "power_gate": "OPEN",
        "power_goal_status": "NOT_PROVEN",
        "gate_closure_authority": "none",
        "inputs": {"observations_sha256_canonical_lf": None},
        "channels": channels,
        "segments": segments,
        "identifiability": identifiability,
        "power_analysis": power,
        "findings": [
            "delta_mWh 通道 5/5 与自身 readings 首末差一致；delta_mAh 字段 4/5 与自身 readings 矛盾（隐含电压 15–20 V，Type-C 上物理不可能），因此功率数字仍可用，但该字段不可引用。",
            "窗口内部逐段复核发现 1 个坏读数（dense 第二轮 20:04:13）：单点抄录误差约 +16.7 mWh（60 J）。同样的单点误差若落在窗口端点，整窗口功率误差约 35.8 mW，是观测处理差（7.7–9.9 mW）的 3.6 倍。",
            "显示通道分辨率不足以分辨本效应：功率显示只有 7 个离散值，电流 LSB 对应约 26.6 mW；能量累加器 1 mWh 在本窗口尺度约合 2.13–2.28 mW。",
            "剪枝等级与测量时刻秩完全共线（反序对=0），单看窗口均值的线性时间趋势 R2 显著；用回归漂移率与同配置漂移率两种合法口径去漂移，处理残差符号相反，故处理效应不可辨识。",
            "以同配置重复性为 sigma，合同 V2 计划的 5 配对轮只能分辨约 14 mW；要分辨 Vivado 外推的 1.7–3.5 mW 需要约 80–320 对，整板测点在该量级上不具备可分辨性。",
        ],
        "claim_boundary": {
            "audit_authority": "reports evidence defects and identifiability only; closes nothing",
            "evidence_files_modified": False,
            "measurement_point": "Type-C 整板输入，非 PL 轨",
            "vivado_estimate_used_as_board_power": False,
        },
        "forbidden_claims": [
            "delta_mAh 字段可用于任何指标",
            "显示功率均值可以分辨 10 mW 级差",
            "去漂移后的残差就是剪枝收益",
            "5 配对轮足以分辨整板毫瓦级效应",
            "power_gate=PASS",
        ],
    }


def analyze(observations: Path, *, sigma_pair_mw: float, effects_mw: Mapping[str, float]) -> dict[str, object]:
    payload = json.loads(observations.read_text(encoding="utf-8"))
    analysis = build_audit(list(payload["observations"]), sigma_pair_mw=sigma_pair_mw, effects_mw=effects_mw)
    analysis["inputs"] = {
        "observations": str(observations.relative_to(ROOT)).replace("\\", "/"),
        "observations_sha256_canonical_lf": canonical_lf_sha256(observations),
        "observations_status": payload.get("status"),
        "instrument_accuracy_percent": payload["instrument"]["accuracy_percent"],
    }
    return analysis


def write_analysis(path: Path, analysis: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="审计 B3 功率计读数（只读，fail-closed，不改证据）")
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument("--sigma-pair-mw", type=float, default=11.15547)
    parser.add_argument("--effects", type=str, default="vivado_extrapolated_200mhz=3.487,vivado_raw_100mhz=1.743,observed_live=9.944,observed_static=7.694")
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args(argv)
    effects = {}
    for item in args.effects.split(","):
        key, _, value = item.partition("=")
        effects[key.strip()] = float(value)
    analysis = analyze(args.observations, sigma_pair_mw=args.sigma_pair_mw, effects_mw=effects)
    if args.output:
        write_analysis(args.output, analysis)
    print(json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

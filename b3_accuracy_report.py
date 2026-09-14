"""B3-ACCURACY：dense/live 逐样本精度对照与门判定。

输入是 JSON 或 JSONL。JSON 对象应包含 ``samples`` 数组；JSONL 每行一个样本
对象。脚本只统计已经完成协议校验的同一输入对照，不从固定向量外推通用精度。
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence


SCHEMA = "eneuron_b3_accuracy_report_v1"
MIN_SAMPLES = 1000
AGREEMENT_THRESHOLD = 0.99
ACCURACY_DROP_THRESHOLD_PP = 1.0
# 点估计只能描述观测到的样本；关闭精度门时还要求 95% 区间仍在门限内。
AGREEMENT_CI_LOWER_THRESHOLD = AGREEMENT_THRESHOLD
ACCURACY_DROP_CI_UPPER_THRESHOLD_PP = ACCURACY_DROP_THRESHOLD_PP


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _argmax(values: Sequence[float]) -> int:
    if not values:
        raise ValueError("logits must not be empty")
    return max(range(len(values)), key=lambda index: values[index])


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float | None]:
    if total <= 0:
        return [None, None]
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    half = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total) / denominator
    return [max(0.0, centre - half), min(1.0, centre + half)]


def _quantiles(values: Iterable[float]) -> dict[str, float | None]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {key: None for key in ("p50", "p95", "p99", "max")}

    def percentile(q: float) -> float:
        position = (len(ordered) - 1) * q
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return ordered[lower]
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    return {
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "p99": percentile(0.99),
        "max": ordered[-1],
    }


def _paired_difference_ci(values: Sequence[float]) -> list[float | None]:
    """对同一输入的 dense/live 正确性差值给出 95% Wald 区间。"""
    if not values:
        return [None, None]
    mean = statistics.fmean(values)
    if len(values) == 1:
        return [mean, mean]
    standard_error = statistics.stdev(values) / math.sqrt(len(values))
    margin = 1.959963984540054 * standard_error
    return [mean - margin, mean + margin]


def load_accuracy_input(path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    """读取 JSON/JSONL，并保留用于证明同源构建的顶层 identity。"""
    text = path.read_text(encoding="utf-8-sig")
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        samples: list[dict[str, object]] = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL line {line_number} must be an object")
            samples.append(dict(value))
        if not samples:
            raise ValueError("accuracy input contains no samples")
        return {}, samples
    if isinstance(document, dict):
        raw_samples = document.get("samples")
        metadata = document.get("identity", {})
        if not isinstance(metadata, dict):
            raise ValueError("accuracy input identity must be an object")
    else:
        raw_samples = document
        metadata = {}
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("accuracy input must contain a non-empty samples array")
    if any(not isinstance(item, dict) for item in raw_samples):
        raise ValueError("each accuracy sample must be an object")
    return dict(metadata), [dict(item) for item in raw_samples]


def load_samples(path: Path) -> list[dict[str, object]]:
    """兼容读取器；正式 CLI 使用 ``load_accuracy_input`` 保留 identity。"""
    return load_accuracy_input(path)[1]


def _validate_sample(sample: Mapping[str, object], index: int) -> dict[str, object]:
    sample_id = sample.get("sample_id")
    if sample_id is None or not str(sample_id).strip():
        raise ValueError(f"sample {index} missing sample_id")
    if sample.get("input_identity") is None and sample.get("input_sha256") is None:
        raise ValueError(f"sample {sample_id} missing input_identity/input_sha256")
    if sample.get("mask_epoch") is None:
        raise ValueError(f"sample {sample_id} missing mask_epoch")
    protocol_errors = int(_number(sample.get("protocol_errors", 0), "protocol_errors"))
    if protocol_errors != 0:
        raise ValueError(f"sample {sample_id} has protocol_errors={protocol_errors}")
    for field in ("result_crc_match", "input_match"):
        if field in sample and sample[field] is not True:
            raise ValueError(f"sample {sample_id} failed {field}")

    dense = sample.get("dense_logits")
    live = sample.get("live_logits")
    if not isinstance(dense, Sequence) or isinstance(dense, (str, bytes)):
        raise ValueError(f"sample {sample_id} missing dense_logits")
    if not isinstance(live, Sequence) or isinstance(live, (str, bytes)):
        raise ValueError(f"sample {sample_id} missing live_logits")
    if len(dense) != len(live) or not dense:
        raise ValueError(f"sample {sample_id} dense/live logits shape mismatch")
    dense_values = [_number(value, "dense_logit") for value in dense]
    live_values = [_number(value, "live_logit") for value in live]
    label = sample.get("label")
    if isinstance(label, bool) or not isinstance(label, int) or not 0 <= label < len(dense_values):
        raise ValueError(f"sample {sample_id} label is outside logits range")
    dense_pred = _argmax(dense_values)
    live_pred = _argmax(live_values)
    if "dense_pred" in sample and int(sample["dense_pred"]) != dense_pred:
        raise ValueError(f"sample {sample_id} dense_pred mismatch")
    if "live_pred" in sample and int(sample["live_pred"]) != live_pred:
        raise ValueError(f"sample {sample_id} live_pred mismatch")
    abs_errors = [abs(left - right) for left, right in zip(dense_values, live_values)]
    scale = max(max(abs(value) for value in dense_values), 1.0)
    return {
        "sample_id": str(sample_id),
        "label": label,
        "dense_pred": dense_pred,
        "live_pred": live_pred,
        "dense_correct": dense_pred == label,
        "live_correct": live_pred == label,
        "prediction_agree": dense_pred == live_pred,
        "logits_exact_match": dense_values == live_values,
        "max_abs_logit_error": max(abs_errors),
        "mean_abs_logit_error": statistics.fmean(abs_errors),
        "max_relative_logit_error": max(abs_error / scale for abs_error in abs_errors),
    }


def build_accuracy_report(
    samples: Sequence[Mapping[str, object]],
    *,
    identity: Mapping[str, object] | None = None,
    min_samples: int = MIN_SAMPLES,
    agreement_threshold: float = AGREEMENT_THRESHOLD,
    accuracy_drop_threshold_pp: float = ACCURACY_DROP_THRESHOLD_PP,
) -> dict[str, object]:
    """生成可审计报告；``status=PASS`` 才能关闭精度门。"""
    if min_samples <= 0:
        raise ValueError("min_samples must be positive")
    normalized = [_validate_sample(sample, index) for index, sample in enumerate(samples)]
    ids = [str(item["sample_id"]) for item in normalized]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate sample_id")
    total = len(normalized)
    agreement_count = sum(bool(item["prediction_agree"]) for item in normalized)
    exact_match_count = sum(bool(item["logits_exact_match"]) for item in normalized)
    dense_correct = sum(bool(item["dense_correct"]) for item in normalized)
    live_correct = sum(bool(item["live_correct"]) for item in normalized)
    agreement = agreement_count / total
    dense_accuracy = dense_correct / total
    live_accuracy = live_correct / total
    accuracy_drop_pp = (dense_accuracy - live_accuracy) * 100.0
    paired_differences = [
        float(bool(item["dense_correct"]) - bool(item["live_correct"]))
        for item in normalized
    ]

    class_counts: dict[int, dict[str, int]] = defaultdict(lambda: {"dense_tp": 0, "live_tp": 0, "support": 0})
    for item in normalized:
        label = int(item["label"])
        class_counts[label]["support"] += 1
        if item["dense_correct"]:
            class_counts[label]["dense_tp"] += 1
        if item["live_correct"]:
            class_counts[label]["live_tp"] += 1
    per_class = {
        str(label): {
            "support": values["support"],
            "dense_recall": values["dense_tp"] / values["support"],
            "live_recall": values["live_tp"] / values["support"],
        }
        for label, values in sorted(class_counts.items())
    }
    report: dict[str, object] = {
        "schema": SCHEMA,
        "identity": dict(identity or {}),
        "sample_count": total,
        "thresholds": {
            "minimum_samples": min_samples,
            "prediction_agreement_min": agreement_threshold,
            "prediction_agreement_ci95_lower_min": agreement_threshold,
            "accuracy_drop_max_pp": accuracy_drop_threshold_pp,
            "accuracy_drop_ci95_upper_max_pp": accuracy_drop_threshold_pp,
        },
        "prediction_agreement": agreement,
        "prediction_agreement_ci95": _wilson(agreement_count, total),
        "logit_exact_match_count": exact_match_count,
        "logit_exact_match_rate": exact_match_count / total,
        "logit_exact_match_ci95": _wilson(exact_match_count, total),
        "dense_accuracy": dense_accuracy,
        "dense_accuracy_ci95": _wilson(dense_correct, total),
        "live_accuracy": live_accuracy,
        "live_accuracy_ci95": _wilson(live_correct, total),
        "accuracy_drop_pp": accuracy_drop_pp,
        "accuracy_drop_ci95_pp": [100.0 * value for value in _paired_difference_ci(paired_differences)],
        "logit_error": {
            "max_abs": _quantiles(item["max_abs_logit_error"] for item in normalized),
            "mean_abs": _quantiles(item["mean_abs_logit_error"] for item in normalized),
            "max_relative": _quantiles(item["max_relative_logit_error"] for item in normalized),
        },
        "per_class_recall": per_class,
        "failed_checks": [],
    }
    failures = report["failed_checks"]
    assert isinstance(failures, list)
    required_identity = ("model", "preprocess", "bitstream_sha256", "xsa_sha256", "elf_sha256")
    missing_identity = [field for field in required_identity if not str((identity or {}).get(field, "")).strip()]
    if missing_identity:
        failures.append("identity_missing:" + ",".join(missing_identity))
    if total < min_samples:
        failures.append(f"sample_count<{min_samples}")
    if agreement < agreement_threshold:
        failures.append("prediction_agreement_below_threshold")
    agreement_ci95 = report["prediction_agreement_ci95"]
    assert isinstance(agreement_ci95, list)
    agreement_ci_lower = agreement_ci95[0]
    if agreement_ci_lower is None or agreement_ci_lower < agreement_threshold:
        failures.append("prediction_agreement_ci95_lower_below_threshold")
    if accuracy_drop_pp > accuracy_drop_threshold_pp:
        failures.append("accuracy_drop_above_threshold")
    accuracy_drop_ci95 = report["accuracy_drop_ci95_pp"]
    assert isinstance(accuracy_drop_ci95, list)
    accuracy_drop_ci_upper = accuracy_drop_ci95[1]
    if accuracy_drop_ci_upper is None or accuracy_drop_ci_upper > accuracy_drop_threshold_pp:
        failures.append("accuracy_drop_ci95_upper_above_threshold")
    report["status"] = "PASS" if not failures else "FAIL"
    report["accuracy_gate"] = "ACCURACY_NEAR_DENSE" if report["status"] == "PASS" else "OPEN"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="汇总 B3 dense/live 精度对照")
    parser.add_argument("input", type=Path, help="JSON 或 JSONL 样本文件")
    parser.add_argument("-o", "--output", type=Path, help="报告 JSON 输出路径")
    parser.add_argument("--min-samples", type=int, default=MIN_SAMPLES)
    args = parser.parse_args()
    identity, samples = load_accuracy_input(args.input)
    report = build_accuracy_report(samples, identity=identity, min_samples=args.min_samples)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

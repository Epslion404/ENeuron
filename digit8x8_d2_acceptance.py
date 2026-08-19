"""D2 图像实验的独立验收门。

本模块不运行神经元，也不修改训练状态。它把 D2 的结论约束写成可复用
的纯函数，避免实验脚本通过只报告条件准确率、单个随机种子或空覆盖来
制造虚假的通过。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


LABEL_COUNT = 10
CHANCE_BALANCED_ACCURACY = 1.0 / LABEL_COUNT
MIN_CLEAN_COVERAGE = 0.90
MIN_CLEAN_BALANCED_ACCURACY = 0.70
MIN_BASELINE_GAIN = 0.10
MAX_ROBUSTNESS_DROP = 0.15
MIN_SEED_PASS_RATE = 0.80


class AcceptanceError(AssertionError):
    """验收输入或门槛失败。"""


@dataclass(frozen=True)
class SeedAggregate:
    """多个随机种子的最小、平均和通过数量。"""

    seed_count: int
    passed_count: int
    pass_rate: float
    mean_balanced_accuracy: float
    min_balanced_accuracy: float
    mean_coverage: float
    min_coverage: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "seed_count": self.seed_count,
            "passed_count": self.passed_count,
            "pass_rate": self.pass_rate,
            "mean_balanced_accuracy": self.mean_balanced_accuracy,
            "min_balanced_accuracy": self.min_balanced_accuracy,
            "mean_coverage": self.mean_coverage,
            "min_coverage": self.min_coverage,
        }


def _number(metrics: Mapping[str, Any], name: str) -> float:
    try:
        value = float(metrics[name])
    except (KeyError, TypeError, ValueError) as exc:
        raise AcceptanceError(f"missing or non-numeric metric: {name}") from exc
    if value < 0.0 or value > 1.0:
        raise AcceptanceError(f"metric {name} must be within [0, 1], got {value}")
    return value


def validate_metrics(metrics: Mapping[str, Any], *, require_confusion: bool = True) -> None:
    """检查 D1/D2 统一分类指标格式和十分类混淆矩阵。"""

    required = ("sample_count", "balanced_accuracy", "accuracy", "macro_f1", "coverage", "abstain_rate")
    missing = [name for name in required if name not in metrics]
    if missing:
        raise AcceptanceError(f"metrics missing fields: {', '.join(missing)}")
    sample_count = int(metrics["sample_count"])
    if sample_count <= 0:
        raise AcceptanceError("sample_count must be positive")
    coverage = _number(metrics, "coverage")
    abstain_rate = _number(metrics, "abstain_rate")
    if abs((coverage + abstain_rate) - 1.0) > 1e-9:
        raise AcceptanceError("coverage + abstain_rate must equal 1")
    for name in ("balanced_accuracy", "accuracy", "macro_f1"):
        _number(metrics, name)
    if not require_confusion:
        return
    confusion = metrics.get("confusion")
    if not isinstance(confusion, Sequence) or len(confusion) != LABEL_COUNT:
        raise AcceptanceError("confusion must have ten rows")
    row_total = 0
    for row in confusion:
        if not isinstance(row, Sequence) or len(row) != LABEL_COUNT:
            raise AcceptanceError("confusion must be a 10x10 matrix")
        if any(int(value) < 0 for value in row):
            raise AcceptanceError("confusion entries must be non-negative")
        row_total += sum(int(value) for value in row)
    expected_covered = round(sample_count * coverage)
    if row_total != expected_covered:
        raise AcceptanceError("confusion total must equal covered sample count")


def passes_clean_gate(
    metrics: Mapping[str, Any],
    *,
    no_learning_balanced_accuracy: float | None = None,
    min_balanced_accuracy: float = MIN_CLEAN_BALANCED_ACCURACY,
    min_coverage: float = MIN_CLEAN_COVERAGE,
    min_baseline_gain: float = MIN_BASELINE_GAIN,
) -> bool:
    """D2 clean test 门：绝对性能、覆盖率和相对无学习基线同时满足。"""

    validate_metrics(metrics)
    balanced_accuracy = _number(metrics, "balanced_accuracy")
    coverage = _number(metrics, "coverage")
    if balanced_accuracy < min_balanced_accuracy or coverage < min_coverage:
        return False
    if no_learning_balanced_accuracy is not None:
        if not 0.0 <= no_learning_balanced_accuracy <= 1.0:
            raise AcceptanceError("no-learning baseline must be within [0, 1]")
        if balanced_accuracy - no_learning_balanced_accuracy < min_baseline_gain:
            return False
    return True


def aggregate_seeds(
    metrics_by_seed: Sequence[Mapping[str, Any]],
    *,
    min_balanced_accuracy: float = MIN_CLEAN_BALANCED_ACCURACY,
    min_coverage: float = MIN_CLEAN_COVERAGE,
) -> SeedAggregate:
    """按 validation 指标统计随机种子门槛，默认要求至少 8/10 通过。"""

    if not metrics_by_seed:
        raise AcceptanceError("at least one seed is required")
    for metrics in metrics_by_seed:
        validate_metrics(metrics)
    bas = [_number(metrics, "balanced_accuracy") for metrics in metrics_by_seed]
    coverages = [_number(metrics, "coverage") for metrics in metrics_by_seed]
    passed = sum(ba >= min_balanced_accuracy and cov >= min_coverage for ba, cov in zip(bas, coverages))
    count = len(metrics_by_seed)
    return SeedAggregate(
        seed_count=count,
        passed_count=passed,
        pass_rate=passed / count,
        mean_balanced_accuracy=sum(bas) / count,
        min_balanced_accuracy=min(bas),
        mean_coverage=sum(coverages) / count,
        min_coverage=min(coverages),
    )


def passes_seed_gate(aggregate: SeedAggregate, *, min_pass_rate: float = MIN_SEED_PASS_RATE) -> bool:
    """检查多种子通过率，禁止只凭单个幸运种子签核。"""

    if aggregate.seed_count <= 0:
        raise AcceptanceError("seed_count must be positive")
    if not 0.0 <= min_pass_rate <= 1.0:
        raise AcceptanceError("min_pass_rate must be within [0, 1]")
    return aggregate.pass_rate >= min_pass_rate


def passes_label_shuffle_negative_control(
    metrics: Mapping[str, Any],
    *,
    max_balanced_accuracy: float = CHANCE_BALANCED_ACCURACY + 0.10,
    min_coverage: float = MIN_CLEAN_COVERAGE,
) -> bool:
    """标签打乱负对照：接近机会水平，同时保持足够覆盖，防止 abstain 作弊。"""

    validate_metrics(metrics)
    return (
        _number(metrics, "balanced_accuracy") <= max_balanced_accuracy
        and _number(metrics, "coverage") >= min_coverage
    )


def passes_fixed_weight_negative_control(
    trained_metrics: Mapping[str, Any],
    fixed_metrics: Mapping[str, Any],
    *,
    max_gain: float = MIN_BASELINE_GAIN,
) -> bool:
    """固定权重对照：训练请求不得带来超过小容差的性能变化。"""

    validate_metrics(trained_metrics)
    validate_metrics(fixed_metrics)
    if max_gain < 0:
        raise AcceptanceError("max_gain must be non-negative")
    return _number(trained_metrics, "balanced_accuracy") - _number(fixed_metrics, "balanced_accuracy") <= max_gain


def robustness_drop(clean: Mapping[str, Any], perturbed: Mapping[str, Any]) -> float:
    """返回扰动后 balanced accuracy 相对 clean 的下降量。"""

    validate_metrics(clean)
    validate_metrics(perturbed)
    return _number(clean, "balanced_accuracy") - _number(perturbed, "balanced_accuracy")


def passes_robustness_gate(
    clean: Mapping[str, Any],
    perturbed: Mapping[str, Any],
    *,
    max_drop: float = MAX_ROBUSTNESS_DROP,
    min_coverage: float = MIN_CLEAN_COVERAGE,
) -> bool:
    """扰动鲁棒性门：性能下降和覆盖率都受限。"""

    validate_metrics(clean)
    validate_metrics(perturbed)
    if max_drop < 0:
        raise AcceptanceError("max_drop must be non-negative")
    return robustness_drop(clean, perturbed) <= max_drop and _number(perturbed, "coverage") >= min_coverage


LEDGER_REQUIRED_FIELDS = frozenset({"sample_id", "layer", "neuron", "evidence", "modulator", "old_weights", "new_weights"})


def validate_training_ledger(
    ledger: Sequence[Mapping[str, Any]],
    *,
    output_neuron_count: int = LABEL_COUNT,
    require_teacher_evidence: bool = True,
) -> None:
    """检查每次输出权重更新都有可审计的局部教师三因子证据。"""

    for index, entry in enumerate(ledger):
        missing = LEDGER_REQUIRED_FIELDS - set(entry)
        if missing:
            raise AcceptanceError(f"ledger entry {index} missing: {sorted(missing)}")
        if int(entry["neuron"]) < 0 or int(entry["neuron"]) >= output_neuron_count:
            raise AcceptanceError(f"ledger entry {index} has invalid output neuron")
        evidence = entry.get("evidence")
        if evidence is None and ("teacher_post_tick" in entry or "eligibility" in entry):
            evidence = {
                "teacher_post_tick": entry.get("teacher_post_tick"),
                "eligibility": entry.get("eligibility"),
            }
        if require_teacher_evidence and not evidence:
            raise AcceptanceError(f"ledger entry {index} has no teacher evidence")
        old_weights = tuple(int(value) for value in entry["old_weights"])
        new_weights = tuple(int(value) for value in entry["new_weights"])
        if len(old_weights) != len(new_weights):
            raise AcceptanceError(f"ledger entry {index} weight length changed")
        if "delta" in entry:
            delta = tuple(int(value) for value in entry["delta"])
            if len(delta) != len(old_weights):
                raise AcceptanceError(f"ledger entry {index} delta length changed")
            weight_min = int(entry.get("weight_min", -2**31))
            weight_max = int(entry.get("weight_max", 2**31 - 1))
            expected = tuple(max(weight_min, min(weight_max, old + change)) for old, change in zip(old_weights, delta))
            if expected != new_weights:
                raise AcceptanceError(f"ledger entry {index} violates old + delta = new")
        if old_weights == new_weights:
            raise AcceptanceError(f"ledger entry {index} records no weight change")


def validate_training_summary(summary: Mapping[str, Any]) -> None:
    """检查运行级计数，尤其是训练期禁止直接写权重。"""

    required = ("teacher_posts", "natural_posts_during_train", "weight_updates", "direct_weight_writes")
    missing = [name for name in required if name not in summary]
    if missing:
        raise AcceptanceError(f"training summary missing fields: {', '.join(missing)}")
    if int(summary["teacher_posts"]) <= 0:
        raise AcceptanceError("training produced no explicit teacher posts")
    if int(summary["natural_posts_during_train"]) != 0:
        raise AcceptanceError("natural spikes were counted as training teacher events")
    if int(summary["weight_updates"]) <= 0:
        raise AcceptanceError("training produced no weight updates")
    if int(summary["direct_weight_writes"]) != 0:
        raise AcceptanceError("training used direct weight writes")

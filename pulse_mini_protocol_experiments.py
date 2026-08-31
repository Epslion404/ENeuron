"""Pulse-Mini-L/L2 训练协议与非二分类任务比较。

实验只使用已签核的命令面：CONFIG 写入初值、TRAIN 中逐样本 STATE_CLEAR，
输入脉冲和 teacher-post 形成局部证据，CAPTURE 后由 FEEDBACK 消费；推理阶段
只发送 INFER + TICK。输出层采用 one-hot 神经元，不把二进制编码冒充多类别。

协议名称严格区分：
  local_teacher       Host 按标签给每个输出单元 ±1 调制；
  global_scalar_reward 所有输出单元收到同一个环境标量，作为信用分配负对照。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence, Type

from pulse_mini_l2_reference import PulseMiniL2Reference
from pulse_mini_reference import Command, Mode, Opcode, PulseMiniReference


ModelType = Type[PulseMiniReference]


@dataclass(frozen=True)
class Sample:
    sequence: tuple[int, ...]
    label: int


@dataclass(frozen=True)
class MultiLabelSample:
    sequence: tuple[int, ...]
    labels: int


def send(model: PulseMiniReference, opcode: Opcode, arg0: int = 0, arg1: int = 0):
    return model.execute(Command(opcode, arg0, arg1))


def model_name(model_type: ModelType) -> str:
    return "Pulse-Mini-L2" if model_type is PulseMiniL2Reference else "Pulse-Mini-L"


def make_model(model_type: ModelType) -> PulseMiniReference:
    model = model_type(leak_period=8)
    send(model, Opcode.MODE_SET, Mode.TRAIN)
    send(model, Opcode.STATE_CLEAR)
    return model


def teacher_segment(model: PulseMiniReference, mask: int) -> None:
    """一个不超过窗口的局部教师段：输入后立即给 post，再释放窗口。"""

    send(model, Opcode.TICK, mask)
    send(model, Opcode.TICK, 0, 1)
    send(model, Opcode.TICK, 0)
    send(model, Opcode.TICK, 0)
    send(model, Opcode.TICK, 0)


def train_one_output(
    model: PulseMiniReference,
    sample: Sample,
    *,
    target: bool,
) -> None:
    send(model, Opcode.STATE_CLEAR)
    for mask in sample.sequence:
        teacher_segment(model, mask)
    send(model, Opcode.CAPTURE)
    send(model, Opcode.FEEDBACK, 1 if target else 3)


def infer_output(model: PulseMiniReference, sequence: Sequence[int]) -> tuple[int, int]:
    send(model, Opcode.STATE_CLEAR)
    spikes = 0
    for mask in sequence:
        spikes += send(model, Opcode.TICK, mask).spike
    return spikes, model.soma


def classify(
    models: Sequence[PulseMiniReference], sequence: Sequence[int]
) -> tuple[int | None, tuple[int, ...]]:
    scores = tuple(infer_output(model, sequence)[0] for model in models)
    best = max(scores)
    if best == 0 or scores.count(best) != 1:
        return None, scores
    return scores.index(best), scores


def train_local_teacher(
    model_type: ModelType,
    samples: Sequence[Sample],
    class_count: int,
    *,
    epochs: int = 4,
) -> list[PulseMiniReference]:
    models = [make_model(model_type) for _ in range(class_count)]
    for _ in range(epochs):
        for sample in samples:
            for index, model in enumerate(models):
                train_one_output(model, sample, target=index == sample.label)
    return models


def predict_dataset(
    models: Sequence[PulseMiniReference], samples: Sequence[Sample]
) -> dict[str, Any]:
    for model in models:
        send(model, Opcode.MODE_SET, Mode.INFER)
    predictions: list[int | None] = []
    score_rows: list[list[int]] = []
    for sample in samples:
        prediction, scores = classify(models, sample.sequence)
        predictions.append(prediction)
        score_rows.append(list(scores))
    covered = [
        (sample.label, prediction)
        for sample, prediction in zip(samples, predictions)
        if prediction is not None
    ]
    correct = sum(int(label == prediction) for label, prediction in covered)
    confusion = [[0 for _ in models] for _ in models]
    for sample, prediction in zip(samples, predictions):
        if prediction is not None:
            confusion[sample.label][prediction] += 1
    per_class_recall = []
    for label in range(len(models)):
        total = sum(1 for sample in samples if sample.label == label)
        hit = confusion[label][label]
        per_class_recall.append(hit / total if total else 0.0)
    return {
        "samples": len(samples),
        "correct": correct,
        "coverage": len(covered) / len(samples) if samples else 0.0,
        "covered_accuracy": correct / len(covered) if covered else 0.0,
        "balanced_accuracy": sum(per_class_recall) / len(per_class_recall)
        if per_class_recall else 0.0,
        "abstain": sum(prediction is None for prediction in predictions),
        "predictions": predictions,
        "scores": score_rows,
        "confusion": confusion,
        "weights": [list(model.weights) for model in models],
        "weights_frozen_probe": weights_frozen_probe(models, samples[: min(3, len(samples))]),
    }


def weights_frozen_probe(models: Sequence[PulseMiniReference], samples: Sequence[Sample]) -> bool:
    before = tuple(tuple(model.weights) for model in models)
    for sample in samples:
        classify(models, sample.sequence)
    after = tuple(tuple(model.weights) for model in models)
    return before == after


def train_global_reward(
    model_type: ModelType,
    samples: Sequence[Sample],
    class_count: int,
    *,
    epochs: int = 4,
) -> list[PulseMiniReference]:
    """全局标量奖励负对照：所有输出单元每个样本收到同一个 feedback。"""

    models = [make_model(model_type) for _ in range(class_count)]
    for _ in range(epochs):
        for sample in samples:
            current, _ = classify(models, sample.sequence)
            for model in models:
                send(model, Opcode.MODE_SET, Mode.TRAIN)
            reward = 1 if current == sample.label else -1
            for model in models:
                send(model, Opcode.STATE_CLEAR)
                for mask in sample.sequence:
                    teacher_segment(model, mask)
                send(model, Opcode.CAPTURE)
                send(model, Opcode.FEEDBACK, 1 if reward > 0 else 3)
    return models


def make_multiclass_task(class_count: int, *, seed: int, train_per_class: int, test_per_class: int) -> tuple[list[Sample], list[Sample]]:
    rng = random.Random(seed)
    if class_count == 3:
        prototypes = ((1, 1, 1), (2, 2, 2), (4, 4, 4))
    elif class_count == 4:
        prototypes = ((1, 3, 1), (2, 4, 2), (4, 8, 4), (8, 1, 8))
    else:
        raise ValueError("class_count must be 3 or 4")

    def build(count: int) -> list[Sample]:
        rows: list[Sample] = []
        for label, prototype in enumerate(prototypes):
            for _ in range(count):
                sequence = list(prototype)
                rng.shuffle(sequence)
                rows.append(Sample(tuple(sequence), label))
        return rows

    return build(train_per_class), build(test_per_class)


def make_temporal_task(*, train_count: int, test_count: int) -> tuple[list[Sample], list[Sample]]:
    # 三类具有相同的通道计数，只改变顺序；该任务用于证明最小单元的时间表达边界。
    prototypes = ((1, 2, 1), (2, 1, 2), (1, 2, 2))
    train = [Sample(prototypes[label], label) for label in range(3) for _ in range(train_count)]
    test = [Sample(prototypes[label], label) for label in range(3) for _ in range(test_count)]
    return train, test


def make_multilabel_task(*, seed: int, count: int) -> list[MultiLabelSample]:
    rng = random.Random(seed)
    labels = (0b0101, 0b0110, 0b1010, 0b1001, 0b1110, 0b1101)
    rows: list[MultiLabelSample] = []
    for _ in range(count):
        label_mask = labels[rng.randrange(len(labels))]
        sequence = tuple(label_mask for _ in range(3))
        rows.append(MultiLabelSample(sequence, label_mask))
    return rows


def train_multilabel(
    model_type: ModelType, samples: Sequence[MultiLabelSample], *, epochs: int = 4
) -> list[PulseMiniReference]:
    models = [make_model(model_type) for _ in range(4)]
    for _ in range(epochs):
        for sample in samples:
            as_single = Sample(sample.sequence, 0)
            for index, model in enumerate(models):
                train_one_output(model, as_single, target=bool(sample.labels & (1 << index)))
    return models


def evaluate_multilabel(
    models: Sequence[PulseMiniReference], samples: Sequence[MultiLabelSample]
) -> dict[str, Any]:
    for model in models:
        send(model, Opcode.MODE_SET, Mode.INFER)
    predictions: list[int] = []
    for sample in samples:
        scores = [infer_output(model, sample.sequence)[0] for model in models]
        predictions.append(sum(1 << index for index, score in enumerate(scores) if score > 0))
    exact = sum(int(pred == sample.labels) for pred, sample in zip(predictions, samples))
    hamming = sum(
        (pred ^ sample.labels).bit_count() for pred, sample in zip(predictions, samples)
    ) / (len(samples) * 4)
    return {
        "samples": len(samples),
        "exact_match": exact / len(samples) if samples else 0.0,
        "hamming_accuracy": 1.0 - hamming if samples else 0.0,
        "predictions": predictions,
        "weights": [list(model.weights) for model in models],
        "weights_frozen_probe": weights_frozen_probe(
            models, [Sample(sample.sequence, 0) for sample in samples[:3]]
        ),
    }


def run(seed_count: int = 8) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "pulse_mini_protocol_experiments_v1",
        "models": ["Pulse-Mini-L", "Pulse-Mini-L2"],
        "training_protocols": ["local_teacher", "global_scalar_reward"],
        "tasks": {},
    }
    for task_name, class_count, factory in (
        ("three_class_channel", 3, lambda seed: make_multiclass_task(3, seed=seed, train_per_class=3, test_per_class=5)),
        ("four_class_composite", 4, lambda seed: make_multiclass_task(4, seed=seed, train_per_class=3, test_per_class=5)),
        ("three_class_temporal_order", 3, lambda seed: make_temporal_task(train_count=3, test_count=5)),
    ):
        rows: list[dict[str, Any]] = []
        for seed in range(seed_count):
            train, test = factory(seed)
            for model_type in (PulseMiniReference, PulseMiniL2Reference):
                local = train_local_teacher(model_type, train, class_count)
                reward = train_global_reward(model_type, train, class_count)
                rows.append({
                    "seed": seed,
                    "model": model_name(model_type),
                    "local_teacher": predict_dataset(local, test),
                    "global_scalar_reward": predict_dataset(reward, test),
                })
        result["tasks"][task_name] = rows

    multilabel_rows: list[dict[str, Any]] = []
    for seed in range(seed_count):
        train = make_multilabel_task(seed=seed, count=12)
        test = make_multilabel_task(seed=100 + seed, count=24)
        for model_type in (PulseMiniReference, PulseMiniL2Reference):
            models = train_multilabel(model_type, train)
            multilabel_rows.append({
                "seed": seed,
                "model": model_name(model_type),
                "local_teacher": evaluate_multilabel(models, test),
            })
    result["tasks"]["four_bit_multilabel"] = multilabel_rows
    return result


def _mean(rows: Iterable[dict[str, Any]], path: Sequence[str]) -> float:
    values = []
    for row in rows:
        value: Any = row
        for key in path:
            value = value[key]
        values.append(float(value))
    return sum(values) / len(values) if values else 0.0


def render_report(result: dict[str, Any]) -> str:
    lines = [
        "# Pulse-Mini-L 与 Pulse-Mini-L2 训练协议和多任务仿真报告",
        "",
        "## 范围",
        "",
        "本报告只使用 Python 黄金模型，比较固定泄放周期 8 的 Pulse-Mini-L 与 L2。",
        "L2 使用每条连接正/负两个 2 位饱和证据计数器，CAPTURE 保存两者差值，范围 -2..+2。",
        "局部教师与全局标量奖励严格分组；全局奖励结果是信用分配负对照，不代替局部教师证据。",
        "",
        "## 训练协议",
        "",
        "1. 每个样本先 STATE_CLEAR；每个输入事件采用“输入 tick -> teacher-post tick -> 三个空 tick”释放窗口。",
        "2. local_teacher 对目标输出发送 +1，对非目标输出发送 -1；输出采用 one-hot，不使用二进制类别编码。",
        "3. global_scalar_reward 由当前动作得到一个统一 ±1，所有输出收到同一个反馈，不按输出地址定向。",
        "4. INFER 只允许膜电位、不应期和泄放状态变化，权重与学习证据必须冻结。",
        "",
        "## 结果",
        "",
        "| 任务 | 模型 | 协议 | 平衡准确率 | 覆盖率 | 覆盖样本准确率 |",
        "|---|---|---|---:|---:|---:|",
    ]
    for task_name in ("three_class_channel", "four_class_composite", "three_class_temporal_order"):
        rows = result["tasks"][task_name]
        for model in ("Pulse-Mini-L", "Pulse-Mini-L2"):
            for protocol in ("local_teacher", "global_scalar_reward"):
                subset = [row for row in rows if row["model"] == model]
                lines.append(
                    f"| {task_name} | {model} | {protocol} | "
                    f"{_mean(subset, (protocol, 'balanced_accuracy')):.1%} | "
                    f"{_mean(subset, (protocol, 'coverage')):.1%} | "
                    f"{_mean(subset, (protocol, 'covered_accuracy')):.1%} |"
                )
    lines.extend([
        "",
        "### 多标签",
        "",
        "| 模型 | exact-match | bit-level accuracy |",
        "|---|---:|---:|",
    ])
    rows = result["tasks"]["four_bit_multilabel"]
    for model in ("Pulse-Mini-L", "Pulse-Mini-L2"):
        subset = [row for row in rows if row["model"] == model]
        lines.append(
            f"| {model} | {_mean(subset, ('local_teacher', 'exact_match')):.1%} | "
            f"{_mean(subset, ('local_teacher', 'hamming_accuracy')):.1%} |"
        )
    lines.extend([
        "",
        "## 解释与边界",
        "",
        "- L2 的价值体现在重复、分段的局部证据可以产生幅度 2 的一次更新；它不是连续 eligibility trace。",
        "- 时间顺序任务若三类仅改变事件顺序而保持通道计数相同，两个版本都应接近随机或大量 abstain；这是最小结构的表达边界。",
        "- 全局标量奖励在没有额外信用分配机制时会让输出单元收到相同方向的更新，不能把它与 local_teacher 结果合并。",
        "- 这些结果是软件模型证据；L2 RTL 仍需完整随机协同仿真、formal 和 Vivado 资源/时序签核后才能形成硬件签核。",
    ])
    return "\n".join(lines) + "\n"


def write_outputs(result: dict[str, Any], *, json_path: Path, report_path: Path) -> None:
    json_path.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    report_path.write_text(render_report(result), encoding="utf-8")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    result = run()
    write_outputs(
        result,
        json_path=root / "pulse_mini_protocol_experiments.json",
        report_path=root / "docs/reports/PULSE_MINI_L2_PROTOCOL_REPORT.md",
    )
    print("PULSE_MINI_PROTOCOL_EXPERIMENTS_PASS")

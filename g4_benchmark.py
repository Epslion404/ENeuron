"""G4 benchmark 的确定性数据合同与验收辅助函数。"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger("g4_benchmark")

TASKS = frozenset({"spatial", "temporal", "xor"})
SPLITS = frozenset({"calibration", "train", "validation", "iid_test", "ood_test"})
PURPOSES = frozenset(
    {
        "bootstrap",
        "dataset",
        "evaluation_permutation",
        "exploration",
        "initialization",
        "shuffle",
        "training_order",
    }
)
TEMPORAL_MOTIFS = {0: "AABABABB", 1: "AABBABAB"}
SPLIT_SIZES = {
    "calibration": 128,
    "train": 32,
    "validation": 128,
    "iid_test": 512,
    "ood_test": 512,
}
TEMPORAL_GENERATOR_VERSION = "g4_temporal_dataset_v2"
_IID_SPLITS = frozenset({"calibration", "train", "validation", "iid_test"})
_TEMPORAL_INPUT_FIELDS = frozenset({"episode_ticks", "events"})
_TEMPORAL_SAMPLE_FIELDS = frozenset(
    {
        "split",
        "label",
        "phase",
        "time_skeleton_id",
        "domain",
        "burst_width",
        "master_seed",
        "symbols",
        "starts",
        "intervals",
        "seed",
        "sample_id",
        "input",
    }
)
_IID_PATTERN_OFFSETS = {
    "calibration": 0,
    "train": 64,
    "validation": 80,
    "iid_test": 144,
}


def _require_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _normalize_json(value: object) -> object:
    """校验受限 JSON 类型，并对所有字符串执行 NFC 规范化。"""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be strings")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise ValueError("JSON keys collide after NFC normalization")
            normalized[normalized_key] = _normalize_json(item)
        return normalized
    raise TypeError(f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    """返回无空白、键排序、UTF-8 和 NFC 规范化的 JSON。"""
    normalized = _normalize_json(value)
    text = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return text.encode("utf-8")


def _sha256_hex(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def derive_seed(
    master_seed: int,
    *,
    task: str,
    split: str,
    model_seed: int | None,
    purpose: str,
    index: int = 0,
) -> int:
    """从完整域标签派生稳定的无符号 64-bit seed。"""
    master_seed = _require_non_negative_int("master_seed", master_seed)
    if model_seed is not None:
        model_seed = _require_non_negative_int("model_seed", model_seed)
    index = _require_non_negative_int("index", index)
    if task not in TASKS:
        raise ValueError(f"unknown task: {task}")
    if split not in SPLITS:
        raise ValueError(f"unknown split: {split}")
    if purpose not in PURPOSES:
        raise ValueError(f"unknown purpose: {purpose}")

    payload = {
        "index": index,
        "master_seed": master_seed,
        "model_seed": model_seed,
        "purpose": purpose,
        "split": split,
        "task": task,
    }
    digest = hashlib.sha256(canonical_json_bytes(payload)).digest()
    return int.from_bytes(digest[:8], "big")


def input_hash(sample: Mapping[str, object]) -> str:
    """只哈希语义输入，确保来源元数据不能掩盖 split 泄漏。"""
    if "input" not in sample:
        raise ValueError("sample must contain input")
    input_data = sample["input"]
    if not isinstance(input_data, Mapping):
        raise TypeError("sample input must be a mapping")
    missing = _TEMPORAL_INPUT_FIELDS - set(input_data)
    if missing:
        raise ValueError(f"sample input missing semantic fields: {sorted(missing)}")
    semantic_input = {
        "episode_ticks": input_data["episode_ticks"],
        "events": input_data["events"],
    }
    return _sha256_hex(semantic_input)


def example_hash(sample: Mapping[str, object]) -> str:
    """哈希完整样本，用于 manifest 完整性检查。"""
    return _sha256_hex(dict(sample))


def strict_decode(count0: int, count1: int) -> int:
    """按严格 spike count 解码；任何平局都返回 abstain=-1。"""
    count0 = _require_non_negative_int("count0", count0)
    count1 = _require_non_negative_int("count1", count1)
    if count0 == count1:
        return -1
    return 0 if count0 > count1 else 1


def permutation_seed(
    master_seed: int,
    *,
    task: str,
    split: str,
    model_seed: int,
    permutation_index: int,
) -> int:
    """派生与训练模式无关的 evaluation-label permutation seed。"""
    return derive_seed(
        master_seed,
        task=task,
        split=split,
        model_seed=model_seed,
        purpose="evaluation_permutation",
        index=permutation_index,
    )


def permute_labels(labels: Sequence[int], seed: int) -> list[int]:
    """使用局部 RNG 返回标签的确定性置换，不修改输入。"""
    if len(labels) < 2:
        raise ValueError("at least two labels are required")
    seed = _require_non_negative_int("seed", seed)
    result = list(labels)
    random.Random(seed).shuffle(result)
    return result


def build_temporal_symbols(label: int, phase: int) -> tuple[str, ...]:
    """构造 V3 Temporal 的完整 cycle 加两个闭环 symbol。"""
    label = _require_non_negative_int("label", label)
    phase = _require_non_negative_int("phase", phase)
    if label not in TEMPORAL_MOTIFS:
        raise ValueError("label must be 0 or 1")
    if phase >= 8:
        raise ValueError("phase must be in [0, 7]")
    motif = TEMPORAL_MOTIFS[label]
    rotated = motif[phase:] + motif[:phase]
    return tuple(rotated + rotated[:2])


def _interval_patterns(domain: str) -> list[tuple[int, ...]]:
    """枚举确定性时间骨架；IID 与 OOD 的每个间隔取值域严格不相交。"""
    if domain == "iid":
        return [
            tuple(4 + ((code >> bit) & 1) for bit in range(9))
            for code in range(1 << 9)
        ]
    if domain == "ood":
        patterns = [
            tuple(6 + ((code >> bit) & 1) for bit in range(9))
            for code in range(1 << 9)
        ]
        return [pattern for pattern in patterns if sum(pattern) <= 60]
    raise ValueError(f"unknown temporal domain: {domain}")


def _temporal_events(
    starts: Sequence[int], symbols: Sequence[int], burst_width: int
) -> list[list[int]]:
    return [
        [start + offset, channel]
        for start, channel in zip(starts, symbols)
        for offset in range(burst_width)
    ]


def generate_temporal_split(
    master_seed: int,
    split: str,
    burst_width: int,
) -> list[dict[str, object]]:
    """生成共享的 V3 Temporal split，不把模型初始化 seed 混入数据。"""
    master_seed = _require_non_negative_int("master_seed", master_seed)
    burst_width = _require_non_negative_int("burst_width", burst_width)
    if split not in SPLIT_SIZES:
        raise ValueError(f"unknown split: {split}")
    if burst_width not in range(1, 5):
        raise ValueError("burst_width must be in [1, 4]")

    pair_count = SPLIT_SIZES[split] // 2
    domain = "iid" if split in _IID_SPLITS else "ood"
    patterns = _interval_patterns(domain)
    if domain == "iid":
        offset = _IID_PATTERN_OFFSETS[split]
        selected = patterns[offset : offset + pair_count]
    else:
        selected = patterns[:pair_count]
    if len(selected) != pair_count:
        raise AssertionError(f"insufficient {domain} temporal skeletons")

    dataset_seed = derive_seed(
        master_seed,
        task="temporal",
        split=split,
        model_seed=None,
        purpose="dataset",
    )
    rng = random.Random(dataset_seed)
    selected = list(selected)
    rng.shuffle(selected)

    samples: list[dict[str, object]] = []
    for pair_index, intervals in enumerate(selected):
        phase = pair_index % 8
        maximum_start = 64 - burst_width - sum(intervals)
        if maximum_start < 0:
            raise AssertionError("temporal skeleton exceeds 64 ticks")
        first_start = rng.randint(0, maximum_start)
        starts = [first_start]
        for interval in intervals:
            starts.append(starts[-1] + interval)

        skeleton_seed = derive_seed(
            master_seed,
            task="temporal",
            split=split,
            model_seed=None,
            purpose="dataset",
            index=pair_index + 1,
        )
        skeleton_id = f"{split}:{pair_index}:{skeleton_seed:016x}"
        for label in (0, 1):
            symbol_names = build_temporal_symbols(label, phase)
            symbols = [0 if symbol == "A" else 2 for symbol in symbol_names]
            sample = {
                "split": split,
                "label": label,
                "phase": phase,
                "time_skeleton_id": skeleton_id,
                "domain": domain,
                "burst_width": burst_width,
                "master_seed": master_seed,
                "symbols": symbols,
                "starts": list(starts),
                "intervals": list(intervals),
                "seed": skeleton_seed,
                "sample_id": f"{skeleton_id}:label{label}",
                "input": {
                    "episode_ticks": 64,
                    "events": _temporal_events(starts, symbols, burst_width),
                },
            }
            samples.append(sample)

    LOGGER.info(
        "generated Temporal split=%s samples=%d burst_width=%d",
        split,
        len(samples),
        burst_width,
    )
    return samples


def _require_int_field(sample: Mapping[str, object], key: str) -> int:
    if key not in sample:
        raise ValueError(f"Temporal sample missing field: {key}")
    value = sample[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Temporal sample field {key} must be an integer")
    return value


def validate_temporal_contract(
    splits: Mapping[str, Sequence[Mapping[str, object]]],
    *,
    master_seed: int,
    expected_burst_width: int,
) -> None:
    """检查静态合同，并按冻结参数重放生成器认证全部 provenance。"""
    master_seed = _require_non_negative_int("master_seed", master_seed)
    expected_burst_width = _require_non_negative_int(
        "expected_burst_width", expected_burst_width
    )
    if expected_burst_width not in range(1, 5):
        raise ValueError("expected_burst_width must be in [1, 4]")
    if set(splits) != set(SPLIT_SIZES):
        raise ValueError("Temporal split set does not match the frozen contract")

    seen_hashes: set[str] = set()
    iid_intervals: set[int] = set()
    ood_intervals: set[int] = set()
    for split, expected_count in SPLIT_SIZES.items():
        samples = splits[split]
        if len(samples) != expected_count:
            raise ValueError(
                f"Temporal split {split} count={len(samples)}, expected={expected_count}"
            )
        expected_domain = "iid" if split in _IID_SPLITS else "ood"
        frequency: dict[tuple[int, int], int] = {}
        pairs: dict[object, list[Mapping[str, object]]] = {}
        for sample in samples:
            if set(sample) != _TEMPORAL_SAMPLE_FIELDS:
                raise ValueError("Temporal sample schema does not match the frozen contract")
            if sample.get("split") != split or sample.get("domain") != expected_domain:
                raise ValueError("Temporal sample split/domain mismatch")
            label = _require_int_field(sample, "label")
            phase = _require_int_field(sample, "phase")
            burst_width = _require_int_field(sample, "burst_width")
            if label not in (0, 1) or phase not in range(8):
                raise ValueError("Temporal label or phase is out of range")
            if burst_width != expected_burst_width:
                raise ValueError("Temporal burst width differs from the frozen global value")

            expected_symbols = [
                0 if symbol == "A" else 2
                for symbol in build_temporal_symbols(label, phase)
            ]
            symbols = list(sample.get("symbols", ()))
            starts = list(sample.get("starts", ()))
            intervals = list(sample.get("intervals", ()))
            if symbols != expected_symbols:
                raise ValueError("Temporal motif/tail does not match label and phase")
            if len(starts) != 10 or len(intervals) != 9:
                raise ValueError("Temporal skeleton must contain 10 starts and 9 intervals")
            if any(isinstance(value, bool) or not isinstance(value, int) for value in starts + intervals):
                raise TypeError("Temporal starts and intervals must be integers")
            if intervals != [right - left for left, right in zip(starts, starts[1:])]:
                raise ValueError("Temporal intervals do not match starts")
            allowed_intervals = {4, 5} if expected_domain == "iid" else {6, 7}
            if not set(intervals).issubset(allowed_intervals):
                raise ValueError(
                    f"Temporal {expected_domain} intervals are outside {allowed_intervals}"
                )
            if starts != sorted(starts) or starts[0] < 0 or starts[-1] + burst_width > 64:
                raise ValueError("Temporal events are unordered or outside 64 ticks")
            if any(interval < burst_width for interval in intervals):
                raise ValueError("Temporal bursts overlap")

            input_data = sample.get("input")
            if not isinstance(input_data, Mapping):
                raise TypeError("Temporal input must be a mapping")
            if set(input_data) != _TEMPORAL_INPUT_FIELDS:
                raise ValueError("Temporal input schema must contain exactly episode_ticks/events")
            if input_data.get("episode_ticks") != 64:
                raise ValueError("Temporal episode must be exactly 64 ticks")
            expected_events = _temporal_events(starts, symbols, burst_width)
            actual_events = [list(event) for event in input_data.get("events", ())]
            if actual_events != expected_events:
                raise ValueError("Temporal event stream does not match skeleton and symbols")
            if any(channel not in (0, 2) for _, channel in actual_events):
                raise ValueError("Temporal event channel is outside {0, 2}")

            digest = input_hash(sample)
            if digest in seen_hashes:
                raise ValueError(f"duplicate Temporal input: {digest}")
            seen_hashes.add(digest)
            frequency[(label, phase)] = frequency.get((label, phase), 0) + 1
            pair_key = sample.get("time_skeleton_id")
            pairs.setdefault(pair_key, []).append(sample)
            interval_domain = iid_intervals if expected_domain == "iid" else ood_intervals
            interval_domain.update(intervals)

        expected_frequency = expected_count // 16
        if set(frequency) != {(label, phase) for label in (0, 1) for phase in range(8)}:
            raise ValueError(f"Temporal label/phase coverage failed for {split}")
        if set(frequency.values()) != {expected_frequency}:
            raise ValueError(f"Temporal label/phase balance failed for {split}")
        if len(pairs) != expected_count // 2:
            raise ValueError(f"Temporal skeleton pairing count failed for {split}")
        for pair in pairs.values():
            if len(pair) != 2 or {item["label"] for item in pair} != {0, 1}:
                raise ValueError("Temporal skeleton is not a two-label counterfactual pair")
            paired_fields = (
                "starts",
                "intervals",
                "burst_width",
                "domain",
                "seed",
                "master_seed",
            )
            if any(pair[0].get(field) != pair[1].get(field) for field in paired_fields):
                raise ValueError("Temporal counterfactual pair has label-dependent timing")

    if not iid_intervals.isdisjoint(ood_intervals):
        raise ValueError("Temporal IID and OOD interval domains overlap")

    for split in SPLIT_SIZES:
        expected = generate_temporal_split(master_seed, split, expected_burst_width)
        if canonical_json_bytes(list(splits[split])) != canonical_json_bytes(expected):
            raise ValueError(f"Temporal split {split} provenance/order does not match generator replay")


def write_temporal_manifest(
    path: Path,
    splits: Mapping[str, Sequence[Mapping[str, object]]],
    *,
    master_seed: int,
    burst_width: int,
) -> None:
    """校验正式数据后写出字节级可复现的 canonical manifest。"""
    validate_temporal_contract(
        splits,
        master_seed=master_seed,
        expected_burst_width=burst_width,
    )
    source_path = Path(__file__).resolve()
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()

    manifest_splits: dict[str, dict[str, object]] = {}
    for split in sorted(SPLIT_SIZES):
        input_hashes = sorted(input_hash(sample) for sample in splits[split])
        example_hashes = sorted(example_hash(sample) for sample in splits[split])
        manifest_splits[split] = {
            "count": len(input_hashes),
            "input_hashes": input_hashes,
            "input_sha256": hashlib.sha256(
                canonical_json_bytes(input_hashes)
            ).hexdigest(),
            "example_hashes": example_hashes,
            "example_sha256": hashlib.sha256(
                canonical_json_bytes(example_hashes)
            ).hexdigest(),
        }
    manifest = {
        "generator_version": TEMPORAL_GENERATOR_VERSION,
        "task": "temporal",
        "episode_ticks": 64,
        "burst_width": burst_width,
        "source_sha256": source_sha256,
        "evaluation_policy": {
            "dataset_shared_across_model_seeds": True,
            "statistical_unit": "paired_model_seed",
        },
        "seed_domain": {
            "algorithm": "sha256-canonical-json-first-64-bit",
            "master_seed": master_seed,
            "model_seed": None,
            "purpose": "dataset",
            "split_seeds": {
                split: derive_seed(
                    master_seed,
                    task="temporal",
                    split=split,
                    model_seed=None,
                    purpose="dataset",
                )
                for split in sorted(SPLIT_SIZES)
            },
        },
        "splits": manifest_splits,
    }
    path.write_bytes(canonical_json_bytes(manifest))
    LOGGER.info("wrote Temporal manifest: %s", path)


def validate_split_isolation(splits: Mapping[str, Sequence[Mapping[str, object]]]) -> None:
    """拒绝 split 内或 split 间的语义输入重复。"""
    seen: dict[str, str] = {}
    for split_name, samples in splits.items():
        if split_name not in SPLITS:
            raise ValueError(f"unknown split: {split_name}")
        for sample in samples:
            digest = input_hash(sample)
            previous = seen.get(digest)
            if previous is not None:
                raise ValueError(f"duplicate input across {previous} and {split_name}: {digest}")
            seen[digest] = split_name


def build_manifest(
    splits: Mapping[str, Sequence[Mapping[str, object]]],
    *,
    generator_version: str,
    source_sha256: str,
) -> dict[str, object]:
    """构造稳定、有序且包含输入/完整样本哈希的 manifest。"""
    if not generator_version:
        raise ValueError("generator_version must not be empty")
    if len(source_sha256) != 64 or any(character not in "0123456789abcdef" for character in source_sha256):
        raise ValueError("source_sha256 must be a lowercase SHA-256 hex digest")
    validate_split_isolation(splits)

    manifest_splits: dict[str, list[dict[str, object]]] = {}
    for split_name in sorted(splits):
        entries = []
        for sample in splits[split_name]:
            entry: dict[str, object] = {
                "input_hash": input_hash(sample),
                "example_hash": example_hash(sample),
            }
            for key in ("label", "sample_id", "seed", "time_skeleton_id"):
                if key in sample:
                    entry[key] = sample[key]
            entries.append(entry)
        manifest_splits[split_name] = entries

    manifest = {
        "generator_version": generator_version,
        "source_sha256": source_sha256,
        "splits": manifest_splits,
    }
    LOGGER.info("built G4 manifest for %d splits", len(manifest_splits))
    return manifest


def _freeze_value(value: Any) -> object:
    """把 commit 元数据转换为稳定、可比较的不可变结构。"""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Mapping):
        return tuple(sorted((_freeze_value(key), _freeze_value(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if is_dataclass(value):
        return tuple((field.name, _freeze_value(getattr(value, field.name))) for field in fields(value))
    if hasattr(value, "__dict__"):
        return tuple(sorted((key, _freeze_value(item)) for key, item in vars(value).items()))
    raise TypeError(f"unsupported learning-state value: {type(value).__name__}")


def capture_learning_state(network: object) -> dict[str, object]:
    """捕获推理期间必须冻结的学习状态，不包含膜电位等动态状态。"""
    neurons = getattr(network, "neurons")
    neuron_states = []
    for neuron in neurons:
        neuron_states.append(
            {
                "weights": tuple(getattr(neuron, "weights")),
                "pre_trace": tuple(getattr(neuron, "pre_trace")),
                "post_trace": getattr(neuron, "post_trace"),
                "eligibility": tuple(getattr(neuron, "eligibility")),
                "eligibility_snapshot": tuple(getattr(neuron, "eligibility_snapshot", ())),
                "threshold": getattr(neuron, "threshold"),
            }
        )
    return {
        "neurons": tuple(neuron_states),
        "pending_commits": _freeze_value(getattr(network, "pending_commits", {})),
        "next_commit_to_apply": getattr(network, "next_commit_to_apply", None),
        "max_captured_commit_id": getattr(network, "max_captured_commit_id", None),
        "weight_epoch": getattr(network, "weight_epoch", 0),
    }


def assert_learning_state_frozen(before: object, after: object) -> None:
    """学习状态若发生任何变化则立即失败。"""
    if before != after:
        raise AssertionError("learning state changed during inference")


__all__ = [
    "assert_learning_state_frozen",
    "build_manifest",
    "build_temporal_symbols",
    "canonical_json_bytes",
    "capture_learning_state",
    "derive_seed",
    "example_hash",
    "generate_temporal_split",
    "input_hash",
    "permutation_seed",
    "permute_labels",
    "strict_decode",
    "SPLIT_SIZES",
    "validate_temporal_contract",
    "validate_split_isolation",
    "write_temporal_manifest",
]

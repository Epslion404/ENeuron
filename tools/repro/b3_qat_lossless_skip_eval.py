"""评估 QAT-v3 上可证明无损的动态组跳过基线。"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_fixed_vector_manifest import model_words_from_manifest  # noqa: E402
from npu_eneuron_protocol import decode_model_words  # noqa: E402
from npu_eneuron_reference import saturate_hidden  # noqa: E402


DEFAULT_MANIFEST = ROOT / "tools" / "repro" / "b3_qat_model_manifest.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "results" / "b3_qat_lossless_skip_diagnostic.json"
GROUP_COUNT = 592
HIDDEN_SIZE = 32
INPUT_SIZE = 64
OUTPUT_SIZE = 10
GROUP_SIZE = 4
TRAIN_POOL_COUNT = 1400
TRAIN_COUNT = 1200
HILL_SEED = 1
HILL_STEPS = 4000
INPUT_MAX = 15
DENSE_CYCLES = 2494


def _split_fixture(manifest: dict) -> tuple[list[dict], list[dict]]:
    fixture_path = ROOT / manifest["identity"]["fixture"]
    fixture = json.loads(fixture_path.read_text(encoding="utf-8-sig"))
    rows = fixture["samples"]
    indices = list(range(len(rows)))
    random.Random(int(manifest["identity"]["split_seed"])).shuffle(indices)
    train_pool = [rows[index] for index in indices[:TRAIN_POOL_COUNT]]
    heldout = manifest["samples"]
    if len(heldout) != len(indices) - TRAIN_POOL_COUNT:
        raise ValueError("manifest held-out count does not match canonical split")
    return train_pool[:TRAIN_COUNT], heldout


def _search_input_permutation(train: list[dict]) -> list[int]:
    frequencies = [0] * INPUT_SIZE
    activity_bits = [0] * INPUT_SIZE
    for sample_index, sample in enumerate(train):
        for index, value in enumerate(sample["pixels"]):
            if value:
                frequencies[index] += 1
                activity_bits[index] |= 1 << sample_index
    all_samples = (1 << len(train)) - 1

    def zero_groups(order: list[int]) -> int:
        return sum(
            (all_samples ^ (
                activity_bits[order[group * GROUP_SIZE]]
                | activity_bits[order[group * GROUP_SIZE + 1]]
                | activity_bits[order[group * GROUP_SIZE + 2]]
                | activity_bits[order[group * GROUP_SIZE + 3]]
            )).bit_count()
            for group in range(INPUT_SIZE // GROUP_SIZE)
        )

    order = sorted(range(INPUT_SIZE), key=lambda index: frequencies[index])
    current = order[:]
    best = order[:]
    best_score = zero_groups(order)
    rng = random.Random(HILL_SEED)
    for _ in range(HILL_STEPS):
        left, right = rng.randrange(INPUT_SIZE), rng.randrange(INPUT_SIZE)
        if left == right:
            continue
        current[left], current[right] = current[right], current[left]
        score = zero_groups(current)
        if score > best_score:
            best_score = score
            best = current[:]
        else:
            current[left], current[right] = current[right], current[left]
    return best


def _suffix_bounds(row: tuple[int, ...]) -> tuple[list[int], list[int]]:
    lower = [0] * 17
    upper = [0] * 17
    for group in range(15, -1, -1):
        start = group * GROUP_SIZE
        lower[group] = lower[group + 1] + sum(
            min(0, row[start + lane] * INPUT_MAX) for lane in range(GROUP_SIZE)
        )
        upper[group] = upper[group + 1] + sum(
            max(0, row[start + lane] * INPUT_MAX) for lane in range(GROUP_SIZE)
        )
    return lower, upper


def _evaluate_sample(decoded, sample: dict, order: list[int]) -> tuple[list[int], dict, int]:
    pixels = [int(sample["pixels"][order[index]]) for index in range(INPUT_SIZE)]
    weights0 = tuple(tuple(row[order[index]] for index in range(INPUT_SIZE)) for row in decoded.weights0)
    suffix = [_suffix_bounds(row) for row in weights0]
    nonzero0 = [
        [any(row[group * GROUP_SIZE + lane] for lane in range(GROUP_SIZE)) for group in range(16)]
        for row in weights0
    ]
    nonzero1 = [
        [any(row[group * GROUP_SIZE + lane] for lane in range(GROUP_SIZE)) for group in range(8)]
        for row in decoded.weights1
    ]
    active_inputs = [
        any(pixels[group * GROUP_SIZE + lane] for lane in range(GROUP_SIZE))
        for group in range(16)
    ]
    stats = {"zero_activation": 0, "zero_weight": 0, "relu_early": 0, "executed": 0}
    hidden: list[int] = []
    for unit, row in enumerate(weights0):
        lower, upper = suffix[unit]
        accumulator = decoded.bias0[unit]
        for group in range(16):
            if accumulator + upper[group] <= 0 or accumulator + lower[group] >= 127:
                stats["relu_early"] += 16 - group
                break
            if not active_inputs[group]:
                stats["zero_activation"] += 1
                continue
            if not nonzero0[unit][group]:
                stats["zero_weight"] += 1
                continue
            stats["executed"] += 1
            start = group * GROUP_SIZE
            accumulator += sum(row[start + lane] * pixels[start + lane] for lane in range(GROUP_SIZE))
        hidden.append(saturate_hidden(accumulator))

    logits: list[int] = []
    for output, row in enumerate(decoded.weights1):
        accumulator = decoded.bias1[output]
        for group in range(8):
            start = group * GROUP_SIZE
            if not any(hidden[start + lane] for lane in range(GROUP_SIZE)):
                stats["zero_activation"] += 1
                continue
            if not nonzero1[output][group]:
                stats["zero_weight"] += 1
                continue
            stats["executed"] += 1
            accumulator += sum(row[start + lane] * hidden[start + lane] for lane in range(GROUP_SIZE))
        logits.append(accumulator)

    dense_hidden = [
        saturate_hidden(
            decoded.bias0[unit]
            + sum(decoded.weights0[unit][index] * sample["pixels"][index] for index in range(INPUT_SIZE))
        )
        for unit in range(HIDDEN_SIZE)
    ]
    dense_logits = [
        decoded.bias1[output]
        + sum(decoded.weights1[output][unit] * dense_hidden[unit] for unit in range(HIDDEN_SIZE))
        for output in range(OUTPUT_SIZE)
    ]
    if logits != dense_logits:
        raise AssertionError("lossless skip changed dense logits")
    skipped = GROUP_COUNT - stats["executed"]
    return logits, stats, skipped


def evaluate(manifest_path: Path, output: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    train, heldout = _split_fixture(manifest)
    decoded = decode_model_words(model_words_from_manifest(manifest))
    order = _search_input_permutation(train)

    aggregate = {"zero_activation": 0, "zero_weight": 0, "relu_early": 0, "executed": 0}
    exact = agreement = correct = 0
    max_error = 0
    skipped_per_sample: list[int] = []
    dense_correct = 0
    for sample in heldout:
        logits, stats, skipped = _evaluate_sample(decoded, sample, order)
        for key, value in stats.items():
            aggregate[key] += value
        dense_logits = [int(value) for value in sample["dense_logits"]]
        dense_prediction = int(sample["dense_prediction"])
        prediction = max(range(OUTPUT_SIZE), key=lambda index: logits[index])
        exact += int(logits == dense_logits)
        agreement += int(prediction == dense_prediction)
        correct += int(prediction == int(sample["label"]))
        dense_correct += int(dense_prediction == int(sample["label"]))
        max_error = max(max_error, max(abs(a - b) for a, b in zip(logits, dense_logits)))
        skipped_per_sample.append(skipped)

    total_samples = len(heldout)
    total_groups = GROUP_COUNT * total_samples
    skipped_total = sum(skipped_per_sample)
    mean_cycles = sum(DENSE_CYCLES - 3 * skipped for skipped in skipped_per_sample) / total_samples
    result = {
        "schema": "eneuron_b3_qat_lossless_skip_diagnostic_v2",
        "status": "MEASURED",
        "identity": {
            "manifest": manifest_path.relative_to(ROOT).as_posix(),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "packed_words_sha256": manifest["model"]["packed_words_sha256"],
            "split_seed": manifest["identity"]["split_seed"],
            "training_samples_used_for_permutation": TRAIN_COUNT,
            "permutation_policy": "nonzero_frequency_plus_hillclimb_train_only_v1",
            "permutation": order,
        },
        "samples": total_samples,
        "output": {
            "prediction_agreement": agreement / total_samples,
            "logit_exact_match": exact / total_samples,
            "max_abs_logit_error": max_error,
        },
        "accuracy": {
            "dense_accuracy": dense_correct / total_samples,
            "lossless_skip_accuracy": correct / total_samples,
            "accuracy_drop_pp": (dense_correct - correct) / total_samples * 100.0,
        },
        "sparsity": {
            "group_instances_total": total_groups,
            "skipped_groups_total": skipped_total,
            "skipped_groups_mean": skipped_total / total_samples,
            "skip_rate": skipped_total / total_groups,
            "breakdown": {
                key: {"count": value, "share": value / total_groups}
                for key, value in aggregate.items()
            },
            "estimated_npu_cycles_mean": mean_cycles,
            "estimated_core_speedup": DENSE_CYCLES / mean_cycles,
            "strict_2of4": False,
        },
        "boundary": "Python语义层无损基线；输入置换只使用训练子集，mask由全零激活、全零权重和L0 ReLU早停产生；尚未接入RTL或板级。",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="评估QAT-v3可证明无损的动态跳过基线")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = evaluate(args.manifest, args.output)
    print(
        json.dumps(
            {"status": result["status"], "output": str(args.output), "metrics": result["output"], "sparsity": result["sparsity"]},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

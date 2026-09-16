"""QAT 模型上的 dense/live-PS/calibrated 剪枝仿真评估（不涉及板卡）。

输入：tools/repro/b3_qat_model_manifest.json（canonical 634-word 打包 + 397 held-out；64 可用 --manifest 指向旧 smoke 清单）。
live 决策复用与实板 PS 相同的 `decide_group4way_live` 语义；calibrated 为
512 训练样本多数票固定 mask（零决策成本对照）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from b3_fixed_vector_manifest import model_words_from_manifest
from b3_multi_input_manifest import _pack_input_beats
from eneuron_group4way_live import (
    GROUP_COUNT,
    L0_GROUPS_PER_HIDDEN,
    L1_GROUPS_PER_OUTPUT,
    META_WIDTH,
    decide_group4way_live,
)
from npu_eneuron_protocol import decode_mask_words, load_model_words
from npu_eneuron_reference import NpuReference


ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "tools" / "repro" / "b3_qat_model_manifest.json"
DEFAULT_FIXTURE = ROOT / "archive" / "legacy" / "digit8x8" / "digit8x8_fixture.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "results" / "b3_qat_pruning_diagnostic.json"
CALIBRATION_SAMPLES = 512
SPLIT_SEED = 20260914


def _predict(logits: list[int]) -> int:
    return max(range(len(logits)), key=lambda index: logits[index])


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _calibration_inputs(fixture_path: Path, count: int) -> list[list[int]]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8-sig"))
    rows = fixture["samples"]
    indices = list(range(len(rows)))
    random.Random(SPLIT_SEED).shuffle(indices)
    return [[int(value) for value in rows[index]["pixels"]] for index in indices[:count]]


def calibration_votes(model_words, pixel_sets) -> list[int]:
    votes = [0] * GROUP_COUNT
    for pixels in pixel_sets:
        decision = decide_group4way_live(model_words, pixels)
        for group in range(GROUP_COUNT):
            if (decision.mask_words[group // 32] >> (group % 32)) & 1:
                votes[group] += 1
    return votes


def calibrated_mask_from_votes(votes: list[int]) -> tuple[int, ...]:
    bits = [False] * GROUP_COUNT

    def stable_top2(base: int) -> tuple[int, int]:
        order = sorted(range(META_WIDTH), key=lambda offset: (-votes[base + offset], offset))
        return order[0], order[1]

    for unit in range(32):
        for meta in range(L0_GROUPS_PER_HIDDEN // META_WIDTH):
            base = unit * L0_GROUPS_PER_HIDDEN + meta * META_WIDTH
            for offset in stable_top2(base):
                bits[base + offset] = True
    for output in range(10):
        for meta in range(L1_GROUPS_PER_OUTPUT // META_WIDTH):
            base = 512 + output * L1_GROUPS_PER_OUTPUT + meta * META_WIDTH
            for offset in stable_top2(base):
                bits[base + offset] = True
    words = [0] * 19
    for index, enabled in enumerate(bits):
        if enabled:
            words[index // 32] |= 1 << (index % 32)
    return tuple(words)


def _nonzero_weight_groups(model_words) -> set[int]:
    groups = set()
    for index, word in enumerate(model_words):
        if word == 0:
            continue
        if index < 512:
            groups.add(index)
        elif 544 <= index < 624:
            groups.add(512 + index - 544)
    return groups


def evaluate(manifest_path: Path, fixture_path: Path, calibration_samples: int, output: Path) -> dict:
    manifest = _load_manifest(manifest_path)
    model_words = model_words_from_manifest(manifest)
    samples = manifest["samples"]

    calibration = _calibration_inputs(fixture_path, calibration_samples)
    votes = calibration_votes(model_words, calibration)
    calibrated_mask = calibrated_mask_from_votes(votes)
    decode_mask_words(calibrated_mask)

    reference = NpuReference()
    load_model_words(reference, model_words)
    decoded_calibrated = decode_mask_words(calibrated_mask)

    nz_groups = _nonzero_weight_groups(model_words)
    metas = [(unit * 16 + meta * 4) for unit in range(32) for meta in range(4)] + [
        (512 + output * 8 + meta * 4) for output in range(10) for meta in range(2)
    ]
    meta_hist = Counter(sum(1 for offset in range(4) if (base + offset) in nz_groups) for base in metas)

    ev_hist = Counter()
    metas_total = all_zero = tie23 = 0
    deleted_total = del_nzw = del_nzc = del_zero = 0
    exec_zero = exec_nz = exec_nzc = 0
    live_masks = Counter()
    live_vs_cal = 0
    dense_correct = live_correct = cal_correct = 0
    live_exact = cal_exact = 0
    agreement_live = agreement_cal = 0
    live_max_err = cal_max_err = 0

    for sample in samples:
        pixels = sample["pixels"]
        dense_logits = sample["dense_logits"]
        dense_pred = sample["dense_prediction"]
        label = sample["label"]
        dense_correct += dense_pred == label

        live = decide_group4way_live(model_words, pixels)
        live_logits = list(live.logits)
        live_pred = live.prediction_class
        live_correct += live_pred == label
        agreement_live += live_pred == dense_pred
        if live_logits == dense_logits:
            live_exact += 1
        live_max_err = max(live_max_err, max(abs(a - b) for a, b in zip(live_logits, dense_logits)))

        cal = reference.infer(
            pixels, mode="gated",
            group_mask0=decoded_calibrated.mask0, group_mask1=decoded_calibrated.mask1,
        )
        cal_logits = list(cal.logits)
        cal_pred = cal.prediction
        cal_correct += cal_pred == label
        agreement_cal += cal_pred == dense_pred
        if cal_logits == dense_logits:
            cal_exact += 1
        cal_max_err = max(cal_max_err, max(abs(a - b) for a, b in zip(cal_logits, dense_logits)))

        bits = [False] * GROUP_COUNT
        for group in range(GROUP_COUNT):
            if (live.mask_words[group // 32] >> (group % 32)) & 1:
                bits[group] = True
        live_masks[live.mask_words] += 1
        if live.mask_words != calibrated_mask:
            live_vs_cal += 1

        for commit in live.commits:
            base = commit.group_base
            evidence = commit.evidence_levels
            for level in evidence:
                ev_hist[level] += 1
            metas_total += 1
            if all(level == 0 for level in evidence):
                all_zero += 1
            ordered = sorted(evidence, reverse=True)
            if ordered[1] == ordered[2]:
                tie23 += 1
            for offset in range(4):
                group = base + offset
                contribution = commit.contributions[offset]
                deleted = not bits[group]
                if deleted:
                    deleted_total += 1
                    if group in nz_groups:
                        del_nzw += 1
                    else:
                        del_zero += 1
                    if contribution != 0:
                        del_nzc += 1
                else:
                    if group in nz_groups:
                        exec_nz += 1
                    else:
                        exec_zero += 1
                    if contribution != 0:
                        exec_nzc += 1

    total = len(samples)
    accuracy = {
        "heldout": total,
        "dense_correct": dense_correct,
        "live_correct": live_correct,
        "calibrated_correct": cal_correct,
        "dense_accuracy": dense_correct / total,
        "live_accuracy": live_correct / total,
        "calibrated_accuracy": cal_correct / total,
        "accuracy_drop_live_pp": (dense_correct - live_correct) / total * 100.0,
        "accuracy_drop_calibrated_pp": (dense_correct - cal_correct) / total * 100.0,
    }
    output_section = {
        "prediction_agreement_live": agreement_live / total,
        "prediction_agreement_calibrated": agreement_cal / total,
        "logit_exact_match_live": live_exact / total,
        "logit_exact_match_calibrated": cal_exact / total,
        "max_abs_logit_error_live": live_max_err,
        "max_abs_logit_error_calibrated": cal_max_err,
    }
    checks = {
        "nonzero_group_share": len(nz_groups) / GROUP_COUNT,
        "metas_with_nonzero_group": sum(value for key, value in meta_hist.items() if key > 0),
        "distinct_live_masks": len(live_masks),
        "deleted_nonzero_contribution_instances": del_nzc,
        "dense_accuracy": dense_correct / total,
    }
    if len(nz_groups) < GROUP_COUNT * 0.15 or checks["metas_with_nonzero_group"] < 37:
        verdict = "MODEL_UNDER_DETERMINED"
    elif len(live_masks) < 8 or del_nzc == 0:
        verdict = "GATE_VACUOUS"
    elif dense_correct / total <= 0.5:
        verdict = "MODEL_UNDER_DETERMINED"
    else:
        verdict = "FALSIFIABLE"

    report = {
        "schema": "eneuron_b3_qat_pruning_diagnostic_v1",
        "status": "MEASURED",
        "identity": {
            "manifest": manifest_path.relative_to(ROOT).as_posix(),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "packed_words_sha256": manifest["model"]["packed_words_sha256"],
            "source_model_sha256": manifest["identity"]["source_model_sha256"],
            "fixture_sha256": manifest["identity"]["fixture_sha256"],
            "calibration_samples": calibration_samples,
            "calibration_policy": "majority_vote_top2_stable_index_v1",
            "calibrated_mask_sha256": hashlib.sha256(
                json.dumps(list(calibrated_mask)).encode()
            ).hexdigest(),
        },
        "model": {
            "nonzero_words": sum(1 for word in model_words if word != 0),
            "nonzero_weight_groups": len(nz_groups),
            "nonzero_groups_per_meta_histogram": dict(sorted(meta_hist.items())),
            "metas_with_nonzero_group": checks["metas_with_nonzero_group"],
            "meta_count": len(metas),
        },
        "accuracy": accuracy,
        "output": output_section,
        "deletion": {
            "deleted_group_instances": deleted_total,
            "deleted_nonzero_weight_instances": del_nzw,
            "deleted_nonzero_contribution_instances": del_nzc,
            "deleted_zero_weight_instances": del_zero,
            "executed_nonzero_weight_instances": exec_nz,
            "executed_zero_weight_instances": exec_zero,
            "executed_nonzero_contribution_instances": exec_nzc,
        },
        "evidence": {
            "histogram": dict(sorted(ev_hist.items())),
            "zero_share": ev_hist[0] / sum(ev_hist.values()),
            "metas_all_zero": all_zero,
            "metas_total": metas_total,
            "second_third_tie_rate": tie23 / metas_total,
        },
        "mask": {
            "distinct_live_masks": len(live_masks),
            "samples": total,
            "calibrated_mask_words": [f"0x{word:08X}" for word in calibrated_mask],
            "live_vs_calibrated_difference_rate": live_vs_cal / total,
        },
        "falsifiability": {
            "verdict": verdict,
            "checks": checks,
            "thresholds": {
                "nonzero_group_share_min": 0.15,
                "metas_with_nonzero_group_min": 37,
                "distinct_live_masks_min": 8,
                "deleted_nonzero_contributions_min": 1,
                "dense_accuracy_min": 0.5,
            },
        },
        "boundary": "Python 语义层仿真，不是板级结果；PS C 运行时与 RTL 未参与本轮。",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="QAT 模型 dense/live/calibrated 剪枝仿真评估")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--calibration-samples", type=int, default=CALIBRATION_SAMPLES)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = evaluate(args.manifest, args.fixture, args.calibration_samples, args.output)
    print(json.dumps({
        "accuracy": report["accuracy"],
        "output": report["output"],
        "deletion": report["deletion"],
        "falsifiability": report["falsifiability"],
        "mask": {key: value for key, value in report["mask"].items() if key != "calibrated_mask_words"},
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

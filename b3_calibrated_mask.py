"""B3-22.3：从校准集生成固定 group_4way mask，并生成 held-out 速度/输出对照 manifest。

校准策略：对每个校准样本运行与实板 live 相同的 `decide_group4way_live`，
对每个连接组累计被选中票数；每个 4 组 meta 内按（票数降序、index 升序）
稳定保留 2 组。该校准 mask 与样本无关，可一次性提交到 NPU。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable, Sequence

from b3_fixed_vector_manifest import (
    DEFAULT_MANIFEST_PATH,
    load_b3_manifest,
    model_words_from_manifest,
)
from eneuron_group4way_live import (
    GROUP_COUNT,
    L0_GROUPS_PER_HIDDEN,
    L1_GROUPS_PER_OUTPUT,
    META_WIDTH,
    decide_group4way_live,
)
from npu_eneuron_protocol import decode_mask_words, load_model_words
from npu_eneuron_reference import NpuReference


SCHEMA = "eneuron_b3_calibrated_group4way_v1"
HELDOUT_SCHEMA = "eneuron_b3_multi_input_v1"
CALIBRATION_POLICY = "majority_vote_top2_stable_index_v1"
DEFAULT_CHUNK_DIRECTORY = Path("artifacts/results/b3_accuracy_chunks_20260914_1024")
DEFAULT_MASK_PATH = Path("tools/repro/b3_calibrated_2of4_mask.json")
DEFAULT_HELDOUT_PATH = Path("tools/repro/b3_calibrated_heldout_manifest.json")
HELDOUT_MASK_EPOCH = 1


def load_chunk_samples(paths: Iterable[Path], limit: int | None = None) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        for sample in document["samples"]:
            if limit is not None and len(rows) >= limit:
                return rows
            rows.append(sample)
    return rows


def calibration_votes(samples: Sequence[dict], model_words: Sequence[int]) -> list[int]:
    votes = [0] * GROUP_COUNT
    for sample in samples:
        decision = decide_group4way_live(model_words, sample["pixels"])
        for group in range(GROUP_COUNT):
            if (decision.mask_words[group // 32] >> (group % 32)) & 1:
                votes[group] += 1
    return votes


def _stable_top2(votes: Sequence[int], base: int) -> tuple[int, int]:
    order = sorted(range(META_WIDTH), key=lambda offset: (-votes[base + offset], offset))
    return order[0], order[1]


def calibrated_mask_from_votes(votes: Sequence[int]) -> tuple[int, ...]:
    bits = [False] * GROUP_COUNT
    for unit in range(32):
        for meta in range(L0_GROUPS_PER_HIDDEN // META_WIDTH):
            base = unit * L0_GROUPS_PER_HIDDEN + meta * META_WIDTH
            for offset in _stable_top2(votes, base):
                bits[base + offset] = True
    for output in range(10):
        for meta in range(L1_GROUPS_PER_OUTPUT // META_WIDTH):
            base = 512 + output * L1_GROUPS_PER_OUTPUT + meta * META_WIDTH
            for offset in _stable_top2(votes, base):
                bits[base + offset] = True
    words = [0] * 19
    for index, enabled in enumerate(bits):
        if enabled:
            words[index // 32] |= 1 << (index % 32)
    return tuple(words)


def build_heldout_manifest(
    heldout_samples: Sequence[dict],
    manifest: dict,
    mask_words: Sequence[int],
) -> dict:
    model = NpuReference()
    load_model_words(model, model_words_from_manifest(manifest))
    decoded = decode_mask_words(mask_words)
    rows: list[dict] = []
    for index, sample in enumerate(heldout_samples):
        pixels = sample["pixels"]
        dense = model.infer(pixels, mode="bypass")
        gated = model.infer(
            pixels,
            mode="gated",
            group_mask0=decoded.mask0,
            group_mask1=decoded.mask1,
        )
        rows.append({
            "sample_index": index,
            "sample_id": sample["sample_id"],
            "input_sha256": sample["input_sha256"],
            "pixels": pixels,
            "input_beats": sample["input_beats"],
            "input_crc": sample["input_crc"],
            "label": sample.get("label"),
            "dense_mask_epoch": HELDOUT_MASK_EPOCH,
            "live_mask_epoch": HELDOUT_MASK_EPOCH,
            "mask_epoch": HELDOUT_MASK_EPOCH,
            "dense_logits": list(dense.logits),
            "dense_prediction": dense.prediction,
            "calibrated_static_logits": list(gated.logits),
            "calibrated_static_prediction": gated.prediction,
            "active_groups": gated.group_reads,
            "skipped_groups": GROUP_COUNT - gated.group_reads,
        })
    return {
        "schema": HELDOUT_SCHEMA,
        "target": {"part": "xc7z020clg484-2", "protocol": "ENB2_PACKET_NPU_V1", "model_id": 3},
        "identity": {
            "model": str(manifest["model"]["packed_words_sha256"]),
            "preprocess": "uint4_64_low_nibble_first_v1",
            "generator": "calibrated_static_heldout_v1",
            "calibration_policy": CALIBRATION_POLICY,
        },
        "sample_count": len(rows),
        "unique_input_count": len(rows),
        "samples": rows,
    }


def _chunk_paths(directory: Path, start: int, end: int) -> list[Path]:
    return [directory / f"b3_accuracy_chunk_{index:02d}.json" for index in range(start, end + 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 B3-22.3 校准 group_4way mask 与 held-out manifest")
    parser.add_argument("--chunk-directory", type=Path, default=DEFAULT_CHUNK_DIRECTORY)
    parser.add_argument("--calibration-start", type=int, default=0)
    parser.add_argument("--calibration-end", type=int, default=7)
    parser.add_argument("--heldout-start", type=int, default=8)
    parser.add_argument("--heldout-end", type=int, default=15)
    parser.add_argument("--calibration-limit", type=int, default=512)
    parser.add_argument("--heldout-count", type=int, default=64)
    parser.add_argument("--base-manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--mask-out", type=Path, default=DEFAULT_MASK_PATH)
    parser.add_argument("--heldout-out", type=Path, default=DEFAULT_HELDOUT_PATH)
    args = parser.parse_args()

    manifest = load_b3_manifest(args.base_manifest)
    calibration_paths = _chunk_paths(args.chunk_directory, args.calibration_start, args.calibration_end)
    heldout_paths = _chunk_paths(args.chunk_directory, args.heldout_start, args.heldout_end)
    for path in calibration_paths + heldout_paths:
        if not path.is_file():
            raise SystemExit(f"missing chunk manifest: {path}")
    calibration_samples = load_chunk_samples(calibration_paths, args.calibration_limit)
    heldout_samples = load_chunk_samples(heldout_paths, args.heldout_count)
    if len(calibration_samples) < args.calibration_limit:
        raise SystemExit("calibration chunk set does not contain enough samples")
    if len(heldout_samples) < args.heldout_count:
        raise SystemExit("held-out chunk set does not contain enough samples")

    model_words = model_words_from_manifest(manifest)
    votes = calibration_votes(calibration_samples, model_words)
    mask_words = calibrated_mask_from_votes(votes)
    decode_mask_words(mask_words)

    heldout = build_heldout_manifest(heldout_samples, manifest, mask_words)
    mask_document = {
        "schema": SCHEMA,
        "target": {"part": "xc7z020clg484-2", "protocol": "ENB2_PACKET_NPU_V1", "model_id": 3},
        "identity": {
            "model": str(manifest["model"]["packed_words_sha256"]),
            "policy": CALIBRATION_POLICY,
            "calibration_sample_count": len(calibration_samples),
            "calibration_files": [
                {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                for path in calibration_paths
            ],
            "base_manifest": str(args.base_manifest),
            "base_manifest_sha256": hashlib.sha256(args.base_manifest.read_bytes()).hexdigest(),
        },
        "mask_words": [f"0x{word:08X}" for word in mask_words],
        "active_groups": sum(1 for group in range(GROUP_COUNT) if (mask_words[group // 32] >> (group % 32)) & 1),
    }
    args.mask_out.parent.mkdir(parents=True, exist_ok=True)
    args.mask_out.write_text(json.dumps(mask_document, indent=2) + "\n", encoding="utf-8")
    args.heldout_out.write_text(json.dumps(heldout, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "calibration_samples": len(calibration_samples),
        "heldout_samples": len(heldout_samples),
        "active_groups": mask_document["active_groups"],
        "mask_path": str(args.mask_out),
        "heldout_path": str(args.heldout_out),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

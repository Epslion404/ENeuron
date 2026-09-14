"""生成 B3-22.1 多输入速度/正确性 manifest。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from b3_fixed_vector_manifest import (
    DEFAULT_MANIFEST_PATH,
    load_b3_manifest,
    model_words_from_manifest,
    reference_from_manifest,
)
from eneuron_group4way_live import decide_group4way_live


SCHEMA = "eneuron_b3_multi_input_v1"
MAX_SAMPLES = 64
DENSE_MASK_EPOCH = 1
LIVE_MASK_EPOCH_START = 2


def _xorshift32(state: int) -> int:
    state ^= (state << 13) & 0xFFFFFFFF
    state ^= state >> 17
    state ^= (state << 5) & 0xFFFFFFFF
    return state & 0xFFFFFFFF


def _pixels_for_index(index: int, state: int) -> tuple[tuple[int, ...], int]:
    if index == 0:
        return (0,) * 64, state
    if index == 1:
        return (15,) * 64, state
    if index == 2:
        return tuple(position & 0xF for position in range(64)), state
    if index == 3:
        return tuple(15 - (position & 0xF) for position in range(64)), state
    pixels: list[int] = []
    for _ in range(64):
        state = _xorshift32(state)
        pixels.append(state & 0xF)
    return tuple(pixels), state


def _pack_input_beats(pixels: tuple[int, ...]) -> list[str]:
    beats: list[str] = []
    for beat_index in range(8):
        word = 0
        for lane in range(8):
            word |= pixels[beat_index * 8 + lane] << (4 * lane)
        beats.append(f"0x{word:08X}")
    return beats


def _crc32_word(crc: int, word: int) -> int:
    for byte_index in range(4):
        crc ^= (word >> (byte_index * 8)) & 0xFF
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 & (-(crc & 1) & 0xFFFFFFFF))
    return crc & 0xFFFFFFFF


def _input_crc(beats: list[str]) -> int:
    crc = 0xFFFFFFFF
    for beat in beats:
        crc = _crc32_word(crc, int(beat, 0))
    return (~crc) & 0xFFFFFFFF


def build_multi_input_manifest(
    *,
    sample_count: int = MAX_SAMPLES,
    seed: int = 0xB3221,
    base_manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> dict[str, object]:
    """生成最多 64 个不同输入，并用同一 Python 参考模型计算黄金结果。"""
    if not 1 <= sample_count <= MAX_SAMPLES:
        raise ValueError(f"sample_count must be in [1, {MAX_SAMPLES}]")
    base = load_b3_manifest(base_manifest_path)
    model_words = model_words_from_manifest(base)
    model = reference_from_manifest(base)
    state = seed & 0xFFFFFFFF
    if state == 0:
        state = 1
    samples: list[dict[str, object]] = []
    identities: set[str] = set()
    for index in range(sample_count):
        pixels, state = _pixels_for_index(index, state)
        identity = hashlib.sha256(bytes(pixels)).hexdigest()
        if identity in identities:
            raise RuntimeError(f"deterministic generator produced duplicate sample at index {index}")
        identities.add(identity)
        sample_id = 0x22010000 + index
        input_beats = _pack_input_beats(pixels)
        dense = model.infer(pixels, mode="bypass")
        live_mask_epoch = LIVE_MASK_EPOCH_START + index
        live = decide_group4way_live(
            model_words,
            pixels,
            sample_id=sample_id,
            mask_epoch=live_mask_epoch,
        )
        samples.append({
            "sample_index": index,
            "sample_id": sample_id,
            "input_sha256": identity,
            "pixels": list(pixels),
            "input_beats": input_beats,
            "input_crc": _input_crc(input_beats),
            # dense 的预热和正式样本都复用首个 active mask epoch；live
            # 则在预热后每次重新提交 mask，因此正式样本从 epoch 2 开始。
            "dense_mask_epoch": DENSE_MASK_EPOCH,
            "live_mask_epoch": live_mask_epoch,
            "mask_epoch": live_mask_epoch,
            "dense_logits": list(dense.logits),
            "dense_prediction": dense.prediction,
            "live_logits": list(live.logits),
            "live_prediction": live.prediction_class,
            "live_mask_words": [f"0x{word:08X}" for word in live.mask_words],
            "active_groups": live.active_groups,
            "skipped_groups": live.skipped_groups,
        })
    model_identity = str(base["model"]["packed_words_sha256"])
    return {
        "schema": SCHEMA,
        "target": {
            "part": "xc7z020clg484-2",
            "protocol": "ENB2_PACKET_NPU_V1",
            "model_id": 3,
        },
        "identity": {
            "model": model_identity,
            "preprocess": "uint4_64_low_nibble_first_v1",
            "generator": "xorshift32_with_four_edge_patterns_v1",
            "seed": seed,
        },
        "sample_count": sample_count,
        "unique_input_count": len(identities),
        "samples": samples,
    }


def write_multi_input_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 B3-22.1 多输入 manifest")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=MAX_SAMPLES)
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=0xB3221)
    args = parser.parse_args()
    write_multi_input_manifest(
        args.output,
        build_multi_input_manifest(sample_count=args.samples, seed=args.seed),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

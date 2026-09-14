"""从仓库内 8x8 数字样本生成 B3 逐块精度 manifest。"""

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
DEFAULT_FIXTURE = Path("archive/legacy/digit8x8/digit8x8_fixture.json")
CHUNK_SIZE = 64


def _pack_input_beats(pixels: list[int]) -> list[str]:
    return [
        f"0x{sum(pixels[beat * 8 + lane] << (4 * lane) for lane in range(8)):08X}"
        for beat in range(8)
    ]


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


def build_accuracy_samples(
    *, fixture_path: Path = DEFAULT_FIXTURE, sample_count: int = 1000,
    start: int = 0, base_manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> list[dict[str, object]]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    source = fixture.get("samples")
    if not isinstance(source, list):
        raise ValueError("fixture samples must be a list")
    selected = source[start : start + sample_count]
    if len(selected) != sample_count:
        raise ValueError("fixture does not contain the requested sample range")
    base = load_b3_manifest(base_manifest_path)
    model_words = model_words_from_manifest(base)
    model = reference_from_manifest(base)
    rows: list[dict[str, object]] = []
    for local_index, raw in enumerate(selected):
        pixels = raw.get("pixels")
        label = raw.get("label")
        if not isinstance(pixels, list) or len(pixels) != 64:
            raise ValueError(f"fixture sample {start + local_index} has invalid pixels")
        if not isinstance(label, int) or not 0 <= label < 10:
            raise ValueError(f"fixture sample {start + local_index} has invalid label")
        if any(not isinstance(pixel, int) or not 0 <= pixel <= 15 for pixel in pixels):
            raise ValueError(f"fixture sample {start + local_index} has invalid uint4 pixel")
        beats = _pack_input_beats(pixels)
        sample_id = 0x23000000 + start + local_index
        dense = model.infer(pixels, mode="bypass")
        live_epoch = local_index + 2
        live = decide_group4way_live(
            model_words, pixels, sample_id=sample_id, mask_epoch=live_epoch
        )
        rows.append({
            "sample_index": local_index,
            "source_index": start + local_index,
            "sample_id": sample_id,
            "input_sha256": hashlib.sha256(bytes(pixels)).hexdigest(),
            "pixels": pixels,
            "input_beats": beats,
            "input_crc": _input_crc(beats),
            "label": label,
            "dense_mask_epoch": 1,
            "live_mask_epoch": live_epoch,
            "mask_epoch": live_epoch,
            "dense_logits": list(dense.logits),
            "dense_prediction": dense.prediction,
            "live_logits": list(live.logits),
            "live_prediction": live.prediction_class,
            "live_mask_words": [f"0x{word:08X}" for word in live.mask_words],
            "active_groups": live.active_groups,
            "skipped_groups": live.skipped_groups,
        })
    return rows


def write_accuracy_chunks(output_dir: Path, *, sample_count: int = 1000,
                          fixture_path: Path = DEFAULT_FIXTURE) -> list[Path]:
    all_rows = build_accuracy_samples(
        fixture_path=fixture_path, sample_count=sample_count
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for offset in range(0, len(all_rows), CHUNK_SIZE):
        rows = all_rows[offset : offset + CHUNK_SIZE]
        # 每个分块对应一次独立板端进程，live epoch 必须从 2 重新开始。
        for local_index, row in enumerate(rows):
            row["live_mask_epoch"] = local_index + 2
            row["mask_epoch"] = local_index + 2
        chunk_index = offset // CHUNK_SIZE
        payload = {
            "schema": SCHEMA,
            "target": {"part": "xc7z020clg484-2", "protocol": "ENB2_PACKET_NPU_V1", "model_id": 3},
            "identity": {
                "dataset": "archive/legacy/digit8x8/digit8x8_fixture.json",
                "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
                "source_start": offset,
                "source_count": len(rows),
            },
            "sample_count": len(rows),
            "unique_input_count": len({row["input_sha256"] for row in rows}),
            "samples": rows,
        }
        path = output_dir / f"b3_accuracy_chunk_{chunk_index:02d}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 B3 64 样本精度 manifest 分块")
    parser.add_argument("-o", "--output-dir", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()
    if args.samples < 1:
        raise SystemExit("--samples must be positive")
    paths = write_accuracy_chunks(args.output_dir, sample_count=args.samples, fixture_path=args.fixture)
    print(json.dumps({"sample_count": args.samples, "chunk_size": CHUNK_SIZE,
                      "chunk_count": len(paths), "paths": [str(path) for path in paths]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

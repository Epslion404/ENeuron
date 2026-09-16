"""把 QAT int8 模型打包为 canonical 634-word NPU 镜像并生成 held-out 清单。

复用现有 canonical packing：words[0:512] L0 权重（16*hidden+group）、
words[512:544] L0 bias、words[544:624] L1 权重（544+8*output+group）、
words[624:634] L1 bias；每个权重 word 为四个 little-endian signed int8 lane。
不修改 tools/repro/b3_fixed_vector_manifest.json。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from b3_multi_input_manifest import _input_crc, _pack_input_beats  # noqa: E402
from npu_eneuron_protocol import decode_model_words  # noqa: E402

SCHEMA = "eneuron_b3_qat_model_v1"
DEFAULT_MODEL = ROOT / "int8_model_qat.json"
DEFAULT_FIXTURE = ROOT / "archive" / "legacy" / "digit8x8" / "digit8x8_fixture.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "b3_qat_model_manifest.json"
MODEL_VERSION = "qat-v3-val200-temp400-150ep-seed20260914"
HELDOUT_COUNT = 397
TRAIN_POOL_COUNT = 1400
TRAIN_COUNT = 1200
VALIDATION_COUNT = TRAIN_POOL_COUNT - TRAIN_COUNT
SPLIT_SEED = 20260914
SAMPLE_ID_BASE = 0x51415400
WORD_COUNT = 634
LAYOUT = {
    "l0_weights": {"word_start": 0, "word_count": 512, "index": "16*hidden + group"},
    "l0_bias": {"word_start": 512, "word_count": 32, "index": "hidden"},
    "l1_weights": {"word_start": 544, "word_count": 80, "index": "8*output + group"},
    "l1_bias": {"word_start": 624, "word_count": 10, "index": "output"},
    "byte_order": "little_endian_lane0_first",
}
INPUT_PREPROCESS = "uint4_64_low_nibble_first_v1"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_qat_model(path: Path) -> dict:
    model = json.loads(path.read_text(encoding="utf-8-sig"))
    for key in ("W0", "b0", "W1", "b1"):
        if key not in model:
            raise ValueError(f"QAT model missing {key}")
    if len(model["W0"]) != 32 or any(len(row) != 64 for row in model["W0"]):
        raise ValueError("QAT W0 must be 32x64")
    if len(model["b0"]) != 32:
        raise ValueError("QAT b0 must contain 32 values")
    if len(model["W1"]) != 10 or any(len(row) != 32 for row in model["W1"]):
        raise ValueError("QAT W1 must be 10x32")
    if len(model["b1"]) != 10:
        raise ValueError("QAT b1 must contain 10 values")
    for name in ("W0", "W1"):
        for row in model[name]:
            for value in row:
                if type(value) is not int or not -128 <= value <= 127:
                    raise ValueError(f"QAT {name} must be signed int8 integers")
    for name in ("b0", "b1"):
        for value in model[name]:
            if type(value) is not int or not -(1 << 31) <= value < (1 << 31):
                raise ValueError(f"QAT {name} must be signed int32 integers")
    return model


def pack_model_words(model: dict) -> tuple[int, ...]:
    words = [0] * WORD_COUNT

    def pack_weights(row: list[int]) -> int:
        word = 0
        for lane, value in enumerate(row):
            word |= (value & 0xFF) << (8 * lane)
        return word

    for hidden in range(32):
        for group in range(16):
            lane_values = model["W0"][hidden][group * 4:group * 4 + 4]
            words[16 * hidden + group] = pack_weights(lane_values)
        words[512 + hidden] = model["b0"][hidden] & 0xFFFFFFFF
    for output in range(10):
        for group in range(8):
            lane_values = model["W1"][output][group * 4:group * 4 + 4]
            words[544 + 8 * output + group] = pack_weights(lane_values)
        words[624 + output] = model["b1"][output] & 0xFFFFFFFF
    return tuple(words)


def packed_words_sha256(words: tuple[int, ...]) -> str:
    return _sha256_bytes(b"".join(word.to_bytes(4, "little") for word in words))


def verify_round_trip(model: dict, words: tuple[int, ...]) -> None:
    decoded = decode_model_words(words)
    if [list(row) for row in decoded.weights0] != model["W0"]:
        raise ValueError("round-trip W0 mismatch")
    if list(decoded.bias0) != model["b0"]:
        raise ValueError("round-trip b0 mismatch")
    if [list(row) for row in decoded.weights1] != model["W1"]:
        raise ValueError("round-trip W1 mismatch")
    if list(decoded.bias1) != model["b1"]:
        raise ValueError("round-trip b1 mismatch")


def integer_npu_forward(model: dict, pixels: list[int]) -> list[int]:
    hidden = [
        max(0, min(127, model["b0"][j] + sum(model["W0"][j][i] * pixels[i] for i in range(64))))
        for j in range(32)
    ]
    return [model["b1"][k] + sum(model["W1"][k][j] * hidden[j] for j in range(32)) for k in range(10)]


def heldout_samples(fixture_path: Path, count: int) -> list[dict]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8-sig"))
    rows = fixture["samples"]
    indices = list(range(len(rows)))
    random.Random(SPLIT_SEED).shuffle(indices)
    train_indices = set(indices[:TRAIN_POOL_COUNT])
    heldout_indices = indices[TRAIN_POOL_COUNT:TRAIN_POOL_COUNT + count]
    if not heldout_indices:
        raise ValueError("fixture does not contain enough held-out samples")
    samples = []
    for sample_index, source_index in enumerate(heldout_indices):
        source = rows[source_index]
        pixels = [int(value) for value in source["pixels"]]
        if len(pixels) != 64 or any(not 0 <= value <= 15 for value in pixels):
            raise ValueError(f"held-out sample {source_index} is not 64 uint4 pixels")
        beats = _pack_input_beats(tuple(pixels))
        identity = _sha256_bytes(bytes(pixels))
        samples.append({
            "sample_index": sample_index,
            "source_index": source_index,
            "sample_id": f"0x{SAMPLE_ID_BASE + sample_index:08X}",
            "pixels": pixels,
            "input_beats": beats,
            "input_crc": _input_crc(beats),
            "input_sha256": identity,
            "label": int(source["label"]),
        })
    if len({sample["input_sha256"] for sample in samples}) != len(samples):
        raise ValueError("held-out inputs are not unique")
    if any(sample["source_index"] in train_indices for sample in samples):
        raise ValueError("held-out sample overlaps the training split")
    return samples


def build_manifest(model_path: Path, fixture_path: Path, heldout_count: int = HELDOUT_COUNT) -> dict:
    model = load_qat_model(model_path)
    words = pack_model_words(model)
    if len(words) != WORD_COUNT:
        raise ValueError("packed image must contain 634 words")
    verify_round_trip(model, words)
    samples = heldout_samples(fixture_path, heldout_count)
    nonzero = {str(index): f"0x{word:08X}" for index, word in enumerate(words) if word != 0}
    for sample in samples:
        sample["dense_logits"] = integer_npu_forward(model, sample["pixels"])
        sample["dense_prediction"] = max(range(10), key=lambda index: sample["dense_logits"][index])
    return {
        "schema": SCHEMA,
        "identity": {
            "source_model": model_path.relative_to(ROOT).as_posix() if model_path.is_relative_to(ROOT) else model_path.as_posix(),
            "source_model_sha256": _sha256_bytes(model_path.read_bytes()),
            "model_version": model.get("model_version", MODEL_VERSION),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "tools/repro/b3_qat_model_manifest.py",
            "fixture": fixture_path.relative_to(ROOT).as_posix() if fixture_path.is_relative_to(ROOT) else fixture_path.as_posix(),
            "fixture_sha256": _sha256_bytes(fixture_path.read_bytes()),
            "split_seed": SPLIT_SEED,
            "train_pool_count": TRAIN_POOL_COUNT,
            "train_count": TRAIN_COUNT,
            "validation_count": VALIDATION_COUNT,
            "heldout_count": len(samples),
            "selection_protocol": model.get("selection_protocol", "unknown"),
            "input_preprocess": INPUT_PREPROCESS,
        },
        "model": {
            "word_count": WORD_COUNT,
            "word_bits": 32,
            "word_order": "index_0_first",
            "weight_encoding": "four_little_endian_signed_int8_lanes",
            "hidden_accumulator": "signed_saturating",
            "default_word": "0x00000000",
            "packed_words_sha256": packed_words_sha256(words),
            "layout": LAYOUT,
            "nonzero_words": nonzero,
            "model_version": model.get("model_version", MODEL_VERSION),
            "validation_acc": model.get("validation_acc"),
            "test_acc": model.get("test_acc"),
            "train_acc": model.get("train_acc"),
        },
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 QAT canonical NPU 模型清单")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--heldout", type=int, default=HELDOUT_COUNT)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build_manifest(args.model, args.fixture, args.heldout)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "packed_words_sha256": manifest["model"]["packed_words_sha256"],
        "nonzero_words": len(manifest["model"]["nonzero_words"]),
        "heldout_samples": manifest["identity"]["heldout_count"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""B3 固定向量黄金 manifest 的 Python 读取器。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from npu_eneuron_protocol import MASK_WORD_COUNT, decode_mask_words, load_model_words
from npu_eneuron_reference import NpuReference


DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parent / "tools" / "repro" / "b3_fixed_vector_manifest.json"


def load_b3_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict:
    """读取并做最小结构校验，返回可供 Host/参考模型共用的字典。"""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "eneuron_b3_fixed_vector_v1":
        raise ValueError("unsupported B3 fixed-vector manifest schema")
    if manifest.get("model", {}).get("word_count") != 634:
        raise ValueError("B3 manifest must contain a 634-word model")
    samples = manifest.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("B3 manifest must contain at least one sample")
    return manifest


def model_words_from_manifest(manifest: Mapping[str, object]) -> tuple[int, ...]:
    """展开稀疏模型摘要，并核对 little-endian packed SHA-256。"""
    model = manifest["model"]
    if not isinstance(model, Mapping):
        raise ValueError("B3 manifest model must be an object")
    word_count = int(model["word_count"])
    words = [0] * word_count
    nonzero_words = model["nonzero_words"]
    if not isinstance(nonzero_words, Mapping):
        raise ValueError("B3 manifest nonzero_words must be an object")
    for index_text, value in nonzero_words.items():
        index = int(index_text)
        if not 0 <= index < word_count:
            raise ValueError("B3 model word index out of range")
        parsed = int(str(value), 0)
        if not 0 <= parsed <= 0xFFFFFFFF:
            raise ValueError("B3 model word must be uint32")
        words[index] = parsed
    packed = b"".join(word.to_bytes(4, "little") for word in words)
    digest = hashlib.sha256(packed).hexdigest()
    if digest != str(model["packed_words_sha256"]):
        raise ValueError("B3 packed model SHA-256 mismatch")
    return tuple(words)


def sample_inputs_from_manifest(sample: Mapping[str, object]) -> tuple[int, ...]:
    """按板端低 nibble 优先规则展开八个输入 beat。"""
    beats = sample["input_beats"]
    if not isinstance(beats, Sequence) or isinstance(beats, (str, bytes)) or len(beats) != 8:
        raise ValueError("B3 sample must contain eight input beats")
    pixels: list[int] = []
    for beat_text in beats:
        beat = int(str(beat_text), 0)
        if not 0 <= beat <= 0xFFFFFFFF:
            raise ValueError("B3 input beat must be uint32")
        pixels.extend((beat >> (4 * lane)) & 0xF for lane in range(8))
    return tuple(pixels)


def mode_mask_words(mode: Mapping[str, object]) -> tuple[int, ...]:
    """读取 gated 模式的完整 19-word mask，并验证保留位。"""
    raw_words = mode.get("mask_words_data")
    if not isinstance(raw_words, Sequence) or isinstance(raw_words, (str, bytes)):
        raise ValueError("B3 gated mode is missing mask_words_data")
    words = tuple(int(str(value), 0) for value in raw_words)
    if len(words) != MASK_WORD_COUNT:
        raise ValueError("B3 mask must contain exactly 19 words")
    decode_mask_words(words)
    return words


def reference_from_manifest(manifest: Mapping[str, object]) -> NpuReference:
    """用同一份 manifest 构造已提交模型的 Python 参考实例。"""
    model = NpuReference()
    load_model_words(model, model_words_from_manifest(manifest))
    return model

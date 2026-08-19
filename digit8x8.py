"""固定 8x8 数字输入与硬件友好的秩序延迟编码。

运行时只依赖标准库。数据 fixture 由一次性生成工具创建，编码器不读取标签、
不使用随机数，并把每个像素位置固定映射到一个 2x2 patch 的四位输入掩码。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


IMAGE_SIDE = 8
PIXEL_COUNT = IMAGE_SIDE * IMAGE_SIDE
PATCH_SIDE = 2
PATCH_GRID_SIDE = IMAGE_SIDE // PATCH_SIDE
PATCH_COUNT = PATCH_GRID_SIDE * PATCH_GRID_SIDE
RANK_K = 16
TIME_STEPS = 16
PIXEL_MAX = 16


@dataclass(frozen=True)
class DigitSample:
    sample_id: int
    label: int
    pixels: tuple[int, ...]


def _validate_pixels(pixels: Sequence[int]) -> tuple[int, ...]:
    if len(pixels) != PIXEL_COUNT:
        raise ValueError(f"expected {PIXEL_COUNT} pixels, got {len(pixels)}")
    values = tuple(int(value) for value in pixels)
    if any(value < 0 or value >= PIXEL_MAX for value in values):
        raise ValueError("pixels must be quantized to 0..15")
    return values


def load_fixture(path: str | Path) -> tuple[DigitSample, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("format") != "eneuron_digit8x8_fixture_v1":
        raise ValueError("unsupported digit fixture format")
    samples: list[DigitSample] = []
    for row in payload.get("samples", []):
        sample_id = int(row["sample_id"])
        label = int(row["label"])
        if not 0 <= label <= 9:
            raise ValueError("digit labels must be in 0..9")
        samples.append(DigitSample(sample_id, label, _validate_pixels(row["pixels"])))
    if [sample.sample_id for sample in samples] != list(range(len(samples))):
        raise ValueError("fixture sample_id must be contiguous and ordered")
    return tuple(samples)


def load_manifest(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("format") != "eneuron_digit8x8_manifest_v1":
        raise ValueError("unsupported digit manifest format")
    return payload


def encode_rank_order(
    pixels: Sequence[int],
    *,
    k: int = RANK_K,
    time_steps: int = TIME_STEPS,
) -> tuple[tuple[int, ...], ...]:
    """将图像编码为固定数量的单脉冲像素事件。

    亮度越高，事件越早。相同亮度按像素编号升序排列，保证结果与随机状态无关。
    当 ``k`` 小于等于像素数且 ``time_steps`` 与 ``k`` 相等时，每个 tick 恰有一个
    选中像素；一般参数下仍保证每个像素最多一个事件和总事件数恰为 k。
    """
    values = _validate_pixels(pixels)
    if not 0 < k <= PIXEL_COUNT:
        raise ValueError("k must be within 1..64")
    if time_steps <= 0 or time_steps < k:
        raise ValueError("time_steps must be positive and at least k")
    ranked = sorted(range(PIXEL_COUNT), key=lambda index: (-values[index], index))[:k]
    events: list[list[int]] = [[] for _ in range(time_steps)]
    for rank, pixel_index in enumerate(ranked):
        tick = (rank * time_steps) // k
        events[tick].append(pixel_index)
    return tuple(tuple(tick_events) for tick_events in events)


def _patch_index(pixel_index: int) -> tuple[int, int]:
    row, column = divmod(pixel_index, IMAGE_SIDE)
    patch_row, patch_column = row // PATCH_SIDE, column // PATCH_SIDE
    local_row, local_column = row % PATCH_SIDE, column % PATCH_SIDE
    patch = patch_row * PATCH_GRID_SIDE + patch_column
    local_bit = local_row * PATCH_SIDE + local_column
    return patch, local_bit


def encode_patch_masks(
    pixels: Sequence[int],
    *,
    k: int = RANK_K,
    time_steps: int = TIME_STEPS,
) -> tuple[tuple[int, ...], ...]:
    """返回 ``time_steps x 16`` 的四位局部 patch 输入掩码。"""
    events = encode_rank_order(pixels, k=k, time_steps=time_steps)
    masks = [[0 for _ in range(PATCH_COUNT)] for _ in range(time_steps)]
    for tick, tick_events in enumerate(events):
        for pixel_index in tick_events:
            patch, local_bit = _patch_index(pixel_index)
            masks[tick][patch] |= 1 << local_bit
    return tuple(tuple(tick_masks) for tick_masks in masks)


def reconstruct_pixel_events(patch_masks: Iterable[Sequence[int]]) -> tuple[tuple[int, ...], ...]:
    """将 patch 掩码还原为扁平像素事件，用于编码器合同测试。"""
    result: list[tuple[int, ...]] = []
    for tick_masks in patch_masks:
        masks = tuple(int(mask) for mask in tick_masks)
        if len(masks) != PATCH_COUNT:
            raise ValueError(f"expected {PATCH_COUNT} patch masks")
        events: list[int] = []
        for patch, mask in enumerate(masks):
            if mask < 0 or mask > 0xF:
                raise ValueError("patch masks must be four bits")
            patch_row, patch_column = divmod(patch, PATCH_GRID_SIDE)
            for local_bit in range(4):
                if mask & (1 << local_bit):
                    local_row, local_column = divmod(local_bit, PATCH_SIDE)
                    row = patch_row * PATCH_SIDE + local_row
                    column = patch_column * PATCH_SIDE + local_column
                    events.append(row * IMAGE_SIDE + column)
        result.append(tuple(sorted(events)))
    return tuple(result)


def fixture_statistics(samples: Sequence[DigitSample]) -> dict[str, object]:
    counts = {str(label): 0 for label in range(10)}
    for sample in samples:
        counts[str(sample.label)] += 1
    return {
        "sample_count": len(samples),
        "label_counts": counts,
        "image_side": IMAGE_SIDE,
        "pixel_quantization": [0, PIXEL_MAX - 1],
        "rank_k": RANK_K,
        "time_steps": TIME_STEPS,
    }

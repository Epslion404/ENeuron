"""传统 64->32->10 NPU 的严格连接级 2:4 lane-mask 编码合同。

当前板端 V1 使用 592-bit 四权重组掩码；本模块只定义下一阶段 Host
候选格式，不改变现有 packet 协议。每个组用一个 4-bit lane mask 表示，
并要求恰好两位为 1。592 组共占 74 个 32-bit word，采用 LSB-first 打包。
"""

from __future__ import annotations

from collections.abc import Sequence

GROUP_COUNT = 512 + 80
LANE_COUNT = 4
LANE_MASK_BITS = 4
LANE_MASK_WORDS = (GROUP_COUNT * LANE_MASK_BITS) // 32
LEGAL_MASKS = (0b0011, 0b0101, 0b0110, 0b1001, 0b1010, 0b1100)


def validate_lane_mask(mask: int) -> int:
    """校验并返回一个严格 2:4 的四位 lane mask。"""
    if type(mask) is not int or not 0 <= mask < (1 << LANE_MASK_BITS):
        raise ValueError("lane mask must be a 4-bit integer")
    if mask.bit_count() != 2:
        raise ValueError("lane mask must enable exactly two lanes")
    return mask


def encode_lane_masks(masks: Sequence[int]) -> tuple[int, ...]:
    """将 592 个 lane mask 按每组 4 bit、LSB-first 打包成 74 words。"""
    if len(masks) != GROUP_COUNT:
        raise ValueError(f"expected {GROUP_COUNT} lane masks")
    words = [0] * LANE_MASK_WORDS
    for group, raw_mask in enumerate(masks):
        mask = validate_lane_mask(raw_mask)
        bit_offset = group * LANE_MASK_BITS
        words[bit_offset // 32] |= mask << (bit_offset % 32)
    return tuple(words)


def decode_lane_masks(words: Sequence[int]) -> tuple[int, ...]:
    """解码 74 个 32-bit word，并对每组执行严格 2:4 校验。"""
    if len(words) != LANE_MASK_WORDS:
        raise ValueError(f"expected {LANE_MASK_WORDS} lane-mask words")
    checked_words: list[int] = []
    for index, word in enumerate(words):
        if type(word) is not int or not 0 <= word <= 0xFFFFFFFF:
            raise ValueError(f"word {index} must be an unsigned 32-bit integer")
        checked_words.append(word)
    masks = []
    for group in range(GROUP_COUNT):
        bit_offset = group * LANE_MASK_BITS
        mask = (checked_words[bit_offset // 32] >> (bit_offset % 32)) & 0xF
        masks.append(validate_lane_mask(mask))
    return tuple(masks)


def active_lane_count(masks: Sequence[int]) -> int:
    """返回结构掩码实际保留的 lane 数，不能把输入活动误计入。"""
    if len(masks) != GROUP_COUNT:
        raise ValueError(f"expected {GROUP_COUNT} lane masks")
    return sum(validate_lane_mask(mask).bit_count() for mask in masks)


__all__ = [
    "GROUP_COUNT",
    "LANE_COUNT",
    "LANE_MASK_BITS",
    "LANE_MASK_WORDS",
    "LEGAL_MASKS",
    "active_lane_count",
    "decode_lane_masks",
    "encode_lane_masks",
    "validate_lane_mask",
]

"""严格 2:4 Host lane-mask 编码合同。"""

from __future__ import annotations

import unittest

from strict_2of4_mask import (
    GROUP_COUNT,
    LANE_MASK_WORDS,
    LEGAL_MASKS,
    active_lane_count,
    decode_lane_masks,
    encode_lane_masks,
    validate_lane_mask,
)


class Strict2of4MaskTests(unittest.TestCase):
    def test_all_six_legal_masks_round_trip(self) -> None:
        masks = tuple(LEGAL_MASKS[index % len(LEGAL_MASKS)] for index in range(GROUP_COUNT))
        words = encode_lane_masks(masks)
        self.assertEqual(len(words), LANE_MASK_WORDS)
        self.assertEqual(decode_lane_masks(words), masks)
        self.assertEqual(active_lane_count(masks), GROUP_COUNT * 2)

    def test_rejects_non_2of4_masks_and_wrong_lengths(self) -> None:
        for mask in (0, 1, 2, 4, 7, 8, 15, -1, 16, True):
            with self.assertRaises(ValueError):
                validate_lane_mask(mask)
        with self.assertRaises(ValueError):
            encode_lane_masks((3,) * (GROUP_COUNT - 1))
        with self.assertRaises(ValueError):
            decode_lane_masks((0,) * (LANE_MASK_WORDS - 1))

    def test_rejects_invalid_packed_group_without_affecting_other_groups(self) -> None:
        masks = (3,) * GROUP_COUNT
        words = list(encode_lane_masks(masks))
        # group 7 occupies bits 28..31 of word 0; replace it with 1:4.
        words[0] = (words[0] & ~(0xF << 28)) | (0x1 << 28)
        with self.assertRaises(ValueError):
            decode_lane_masks(words)


if __name__ == "__main__":
    unittest.main()

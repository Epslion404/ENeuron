"""生成 V3 Temporal development cohort 的可复现 manifest。"""

from __future__ import annotations

import logging
from pathlib import Path

from g4_benchmark import SPLIT_SIZES, generate_temporal_split, write_temporal_manifest


LOGGER = logging.getLogger("generate_g4_temporal_manifest")
ROOT = Path(__file__).resolve().parent
MASTER_SEED = 0x473454454D504F52
BURST_WIDTH = 2
OUTPUT = ROOT / "g4_temporal_development_manifest.json"


def main() -> int:
    """构造全部五个 split 并写出 development-only manifest。"""
    splits = {
        split: generate_temporal_split(
            MASTER_SEED,
            split,
            BURST_WIDTH,
        )
        for split in SPLIT_SIZES
    }
    write_temporal_manifest(
        OUTPUT,
        splits,
        master_seed=MASTER_SEED,
        burst_width=BURST_WIDTH,
    )
    LOGGER.info(
        "Temporal development manifest complete: samples=%d output=%s",
        sum(len(samples) for samples in splits.values()),
        OUTPUT,
    )
    LOGGER.warning(
        "development cohort only: burst_width=2 is not the three-task global P0b result"
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())

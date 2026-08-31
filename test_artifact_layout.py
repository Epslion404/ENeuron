"""验证普通实验结果采用唯一、可浏览的归档布局。"""

from __future__ import annotations

import logging
import unittest
from pathlib import Path


LOGGER = logging.getLogger("test_artifact_layout")
ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "artifacts" / "results"
EXPECTED_RESULTS = {
    "comparison_simulation_results.json",
    "digit8x8_d1_results.json",
    "digit8x8_d2_results.json",
    "local_prune_b0_results.json",
    "local_prune_b1_results.json",
    "local_prune_b2_results.json",
    "local_prune_b21_results.json",
    "local_prune_np2_results.json",
    "local_prune_np3_results.json",
    "network_results.json",
    "network_sweep_results.json",
    "pulse_mini_protocol_experiments.json",
    "rtl_smoke_results.json",
    "simulation_results.json",
    "sweep_results.json",
}


class ArtifactLayoutTests(unittest.TestCase):
    """结果文件必须只有一个权威路径，避免根目录和归档目录漂移。"""

    def test_results_are_archived_once_and_indexed(self) -> None:
        self.assertTrue(RESULTS_DIR.is_dir(), "缺少 artifacts/results 目录")
        actual = {path.name for path in RESULTS_DIR.glob("*.json")}
        self.assertEqual(EXPECTED_RESULTS, actual)

        stale_root_files = sorted(name for name in EXPECTED_RESULTS if (ROOT / name).exists())
        self.assertEqual([], stale_root_files, "根目录仍有旧结果副本")

        index_text = (ROOT / "artifacts" / "README.md").read_text(encoding="utf-8")
        missing_index_entries = sorted(name for name in EXPECTED_RESULTS if name not in index_text)
        self.assertEqual([], missing_index_entries, "artifacts 索引不完整")
        LOGGER.info("verified %d archived result files", len(actual))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    unittest.main()

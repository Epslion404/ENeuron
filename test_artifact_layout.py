"""验证普通实验结果采用唯一、可浏览的归档布局。"""

from __future__ import annotations

import logging
import unittest
from pathlib import Path


LOGGER = logging.getLogger("test_artifact_layout")
ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "artifacts" / "results"
EXPECTED_RESULTS = {
    "hellozynq_b0_smoke_summary.json",
    "hellozynq_b1a_hw_summary.json",
    "hellozynq_b1b_uart_ddr_summary.json",
    "local_prune_b0_results.json",
    "np7_cosim_ledgers.json",
    "np7_formal_and_mutations.json",
    "np7_software_cost_manifest.json",
    "npu_single_clock_ooc_manifest.json",
    "b2_packet_memory_ooc_manifest.json",
    "rtl_smoke_results.json",
    "b3_accuracy_reference_only.json",
    "b3_accuracy_reference_only_report.json",
    "b3_accuracy_256_board_pairs.json",
    "b3_accuracy_256_board_report.json",
    "b3_accuracy_chunk00_board_pairs.json",
    "b3_accuracy_chunk00_board_report.json",
    "b3_accuracy_chunk00_01_board_report.json",
    "b3_accuracy_1024_board_pairs.json",
    "b3_accuracy_1024_board_report.json",
    "b3_accuracy_1024_board_pairs_v2.json",
    "b3_accuracy_1024_board_report_v2.json",
    "b3_calibrated_static_ab.json",
    "b3_fixed_overhead_ab.json",
    "b3_live_optimized_ab.json",
    "b3_pruning_diagnostic.json",
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

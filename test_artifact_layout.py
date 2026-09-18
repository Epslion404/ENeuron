"""验证普通实验结果采用唯一、可浏览的归档布局。"""

from __future__ import annotations

import hashlib
import json
import logging
import unittest
from pathlib import Path


LOGGER = logging.getLogger("test_artifact_layout")
ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "artifacts" / "results"
CP8_EVIDENCE_DIR = ROOT / "artifacts" / "logs" / "b3_cp8_physical_pass_20260917_14e8e06"
CP8_MANIFEST = CP8_EVIDENCE_DIR / "artifact_sha256.json"
CP8_SOURCE_HEAD = "14e8e0686ada1f691e039239d0b942f8024253ca"
CP8_ARCHIVE_FILES = (
    "build_manifest.json",
    "signoff_summary.txt",
    "timing_impl.rpt",
    "utilization_impl.rpt",
    "route_status_impl.rpt",
    "drc_impl.rpt",
)
CP8_MODES = ("dense", "lossless")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
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
    "b3_qat_pruning_diagnostic.json",
    "b3_qat_pl_auto_mask_sim.json",
    "b3_qat_cp1_dense_64_board.json",
    "b3_qat_lossless_skip_diagnostic.json",
    "b3_qat_lossless_zero_group_rtl_sim.json",
    "b3_qat_lossless_zero_group_ooc.json",
    "b3_qat_cp4_lossless_zero_group_board_397.json",
    "b3_qat_cp5a_pl_replay_board_pair.json",
    "b3_qat_cp5b_pl_distribution_board_pair.json",
    "network_results.json",
    "network_sweep_results.json",
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


class Cp8PhysicalEvidenceTests(unittest.TestCase):
    """CP8 物理构建证据必须绑定 clean HEAD、两模式签核数字并逐文件复算哈希。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(CP8_MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_identity_and_layout(self) -> None:
        self.assertTrue(CP8_EVIDENCE_DIR.is_dir(), "缺少 CP8 物理证据目录")
        self.assertTrue(CP8_MANIFEST.is_file(), "缺少 artifact_sha256.json")
        self.assertEqual(CP8_SOURCE_HEAD, self.manifest["source_head"])
        self.assertEqual("xc7z020clg484-2", self.manifest["part"])
        self.assertEqual(200000000, self.manifest["clock_hz"])
        self.assertEqual(set(CP8_MODES), set(self.manifest["modes"]))

    def test_both_modes_signoff_dsp_and_clock(self) -> None:
        for mode in CP8_MODES:
            entry = self.manifest["modes"][mode]
            signoff = entry["signoff"]
            self.assertEqual(1, signoff["timing_pass"], mode)
            self.assertEqual(1, signoff["route_pass"], mode)
            self.assertEqual(1, signoff["drc_pass"], mode)
            self.assertEqual(1, signoff["signoff_pass"], mode)
            self.assertEqual(4, signoff["dsp48e1_count"], mode)
            self.assertEqual(200000000, signoff["clock_hz"], mode)
            self.assertEqual(CP8_SOURCE_HEAD, signoff["build_head"], mode)
            self.assertEqual(0, signoff["route_errors"], mode)
            self.assertEqual(0, signoff["drc_hard_errors"], mode)

    def test_archived_files_and_recorded_hashes(self) -> None:
        for mode in CP8_MODES:
            entry = self.manifest["modes"][mode]
            recorded = entry["archived_files"]
            expected_paths = {
                f"artifacts/logs/b3_cp8_physical_pass_20260917_14e8e06/{mode}_{name}"
                for name in CP8_ARCHIVE_FILES
            }
            self.assertEqual(expected_paths, set(recorded), mode)
            for relative, expected in recorded.items():
                archived = ROOT / relative
                self.assertTrue(archived.is_file(), relative)
                self.assertEqual(expected, sha256_file(archived), relative)

    def test_archived_manifests_match_recorded_hashes(self) -> None:
        for mode in CP8_MODES:
            entry = self.manifest["modes"][mode]
            archived_manifest = json.loads(
                (CP8_EVIDENCE_DIR / f"{mode}_build_manifest.json").read_text(encoding="utf-8")
            )
            signoff = archived_manifest["signoff"]
            self.assertEqual(CP8_SOURCE_HEAD, archived_manifest["git_head"], mode)
            self.assertEqual(self.manifest["part"], archived_manifest["part"], mode)
            self.assertEqual(entry["mode"], archived_manifest["npu_mode"], mode)
            self.assertEqual(entry["bitstream_sha256"], archived_manifest["bitstream_sha256"], mode)
            self.assertEqual(entry["xsa_sha256"], archived_manifest["xsa_sha256"], mode)
            self.assertEqual(entry["signoff"]["build_head"], signoff["B2_BUILD_HEAD"], mode)
            self.assertEqual(entry["signoff"]["part"], signoff["B2_PART"], mode)
            self.assertEqual(str(entry["signoff"]["clock_hz"]), signoff["B2_NPU_CLOCK_HZ"], mode)
            self.assertEqual(
                str(entry["signoff"]["dsp48e1_count"]), signoff["B2_NPU_DSP48E1_COUNT"], mode
            )
            self.assertEqual(str(entry["signoff"]["timing_pass"]), signoff["B2_TIMING_PASS"], mode)
            self.assertEqual(str(entry["signoff"]["route_pass"]), signoff["B2_ROUTE_PASS"], mode)
            self.assertEqual(str(entry["signoff"]["drc_pass"]), signoff["B2_DRC_PASS"], mode)
            self.assertEqual(str(entry["signoff"]["signoff_pass"]), signoff["B2_SIGNOFF_PASS"], mode)
        LOGGER.info("verified CP8 physical evidence manifests")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    unittest.main()

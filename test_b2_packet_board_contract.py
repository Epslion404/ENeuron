import unittest
from pathlib import Path

from tools.ci.classify_changes import classify_paths


ROOT = Path(__file__).resolve().parent


class B2PacketBoardContractTests(unittest.TestCase):
    def test_packet_board_sources_exist(self):
        self.assertTrue((ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").is_file())
        self.assertTrue((ROOT / "boards/hellozynq/b2_sw/run_b2_packet_board.ps1").is_file())

    def test_packet_board_contract_markers_are_present(self):
        source = (ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").read_text(encoding="utf-8")
        for token in (
            "B2_PACKET_BEGIN",
            "B2_PACKET_FENCE_PASS",
            "B2_PACKET_RESULT_PASS",
            "B2_PACKET_PASS",
            "ENB2",
            "OP_MODEL_BEGIN",
            "OP_MASK_BEGIN",
        ):
            self.assertIn(token, source)

    def test_packet_board_runner_checks_packet_marker(self):
        source = (ROOT / "boards/hellozynq/b2_sw/run_b2_packet_board.ps1").read_text(encoding="utf-8")
        self.assertIn("B2_PACKET_PASS", source)
        self.assertIn("VID_1A86", source)
        self.assertIn("hello_zynq_b2.bit", source)

    def test_packet_board_runner_rejects_missing_jtag_target(self):
        source = (ROOT / "boards/hellozynq/b2_sw/run_b2_packet_board.ps1").read_text(encoding="utf-8")
        self.assertIn("available targets: none", source)
        self.assertIn("JTAG_TARGET_UNAVAILABLE", source)
        self.assertIn("xsct_stderr.log", source)

    def test_b3_dense_mode_checks_full_result_vector(self):
        source = (ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").read_text(encoding="utf-8")
        for token in (
            "B3_DENSE",
            "B3_BYPASS",
            "B3_FULL_OPEN",
            "B3_NUMERIC_CHECK",
            "B3_DENSE_PASS",
            "B3_BYPASS_PASS",
            "B3_FULL_OPEN_PASS",
            "B3_DENSE_LOGITS",
            "result_logits",
            "crc32_word",
            "rx[18]",
        ):
            self.assertIn(token, source)
        self.assertIn("165", source)
        self.assertIn("-18", source)
        self.assertIn("153", source)

    def test_packet_software_build_exposes_b3_mode_and_manifest(self):
        source = (ROOT / "boards/hellozynq/b2_sw/run_b2_packet_sw_build.ps1").read_text(encoding="utf-8")
        for token in (
            "[switch]$B3Dense",
            "[switch]$B3FullOpen",
            "[switch]$B3Bypass",
            "[switch]$B3StaticMixed",
            "[switch]$B3LiveEneuron",
            "[switch]$B3EpochOverlap",
            "-DB3_DENSE",
            "-DB3_FULL_OPEN",
            "-DB3_BYPASS",
            "-DB3_STATIC_MIXED",
            "-DB3_LIVE_ENEURON",
            "-DB3_EPOCH_OVERLAP",
            "b3_dense",
            "b3_full_open",
            "b3_bypass",
            "b3_static_mixed",
            "b3_live_eneuron",
            "expected_logits",
            "input_pattern",
            "mask_pattern",
        ):
            self.assertIn(token, source)

    def test_packet_software_build_reads_single_b3_golden_manifest(self):
        source = (ROOT / "boards/hellozynq/b2_sw/run_b2_packet_sw_build.ps1").read_text(encoding="utf-8")
        self.assertIn("b3_fixed_vector_manifest.json", source)
        self.assertIn("ConvertFrom-Json", source)
        self.assertIn("goldenSample.modes", source)
        self.assertIn("golden_manifest = $goldenManifestPath", source)

    def test_packet_host_generates_c_header_from_manifest(self):
        build = (ROOT / "boards/hellozynq/b2_sw/run_b2_packet_sw_build.ps1").read_text(encoding="utf-8")
        source = (ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").read_text(encoding="utf-8")
        for token in ("b3_fixed_vector_generated.h", "B3_SAMPLE_INPUT_BEATS", "mask_words_data", "Set-Content"):
            self.assertIn(token, build)
        self.assertIn('#include "b3_fixed_vector_generated.h"', source)
        self.assertNotIn("static const s32 EXPECTED_DENSE_LOGITS", source)
        self.assertNotIn("case 633U: return 0xFFFFFFFEU", source)

    def test_static_mixed_mode_declares_group_mask_not_strict_lane_2of4(self):
        source = (ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").read_text(encoding="utf-8")
        for token in (
            "B3_STATIC_MIXED",
            "B3_STATIC_MIXED_PASS",
            "STATIC_MIXED_MASK_WORD",
            "GROUP_MASK_GRANULARITY",
            "strict_2of4_candidate",
        ):
            self.assertIn(token, source)
        self.assertIn("group_4way", source)
        self.assertIn("false", source)

    def test_live_eneuron_mode_computes_mask_on_host(self):
        source = (ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").read_text(encoding="utf-8")
        for token in (
            "B3_LIVE_ENEURON",
            "B3_LIVE_ENEURON_PASS",
            "compute_live_group4way_mask",
            "live_eneuron_s2",
            "B3_LIVE_MASK_VALID",
        ):
            self.assertIn(token, source)
        self.assertNotIn("B3_LIVE_ENEURON_MASK_WORDS", source)

    def test_packet_board_runner_selects_terminal_marker_from_manifest(self):
        source = (ROOT / "boards/hellozynq/b2_sw/run_b2_packet_board.ps1").read_text(encoding="utf-8")
        for token in ("application_mode", "B3_DENSE_PASS", "B3_FULL_OPEN_PASS", "B3_BYPASS_PASS", "B3_STATIC_MIXED_PASS", "B3_LIVE_ENEURON_PASS", "B3_EPOCH_OVERLAP_PASS", "B3_11_PENDING_HOLD", "terminal_marker"):
            self.assertIn(token, source)

    def test_packet_board_runner_probes_status_block_and_epoch_hold(self):
        source = (ROOT / "boards/hellozynq/b2_sw/run_b2_packet_board.ps1").read_text(encoding="utf-8")
        for token in (
            "Invoke-B2StateProbe",
            "Get-ProbeU32",
            "post_pass_probe.log",
            "pending_hold_probe.log",
            "B2_NPU_ACTIVE_MASK_EPOCH",
            "B2_NPU_PENDING_MASK_EPOCH",
            "EPOCH_HOLD_MISMATCH",
            "AddSeconds(30)",
        ):
            self.assertIn(token, source)

    def test_changes_use_b2_board_scope(self):
        scopes = classify_paths([
            "boards/hellozynq/b2_sw/src/packet_main.c",
            "boards/hellozynq/b2_sw/run_b2_packet_board.ps1",
            "test_b2_packet_board_contract.py",
        ])
        self.assertTrue(scopes["full_repository"])


if __name__ == "__main__":
    unittest.main()

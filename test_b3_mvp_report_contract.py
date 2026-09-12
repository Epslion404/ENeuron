"""B3-14 报告器合同：字段齐全，static 与 live 分行。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from b3_mvp_report import (
    REQUIRED_FIELDS,
    REQUIRED_MODES,
    build_comparison,
    parse_probe_u32,
    record_from_artifacts,
    write_comparison,
)


def _probe(execute: int, skip: int, cycles: int, active: int, pending: int) -> str:
    return "\n".join([
        "B2_NPU_RUNTIME_STATUS=1",
        f"B2_NPU_ACTIVE_MASK_EPOCH={active}",
        f"B2_NPU_PENDING_MASK_EPOCH={pending}",
        f"B2_NPU_LAST_COMPUTE_CYCLES={cycles}",
        "B2_NPU_PROTOCOL_ERROR_COUNT=0",
        f"B2_NPU_EXECUTE_GROUP_COUNT={execute}",
        f"B2_NPU_SKIP_GROUP_COUNT={skip}",
    ])


class B3MvpReportContractTests(unittest.TestCase):
    def test_parse_probe_reads_shipped_keys_not_a_reimplemented_map(self) -> None:
        text = _probe(592, 0, 2494, 1, 0)
        self.assertEqual(parse_probe_u32(text, "B2_NPU_EXECUTE_GROUP_COUNT"), 592)
        self.assertEqual(parse_probe_u32(text, "B2_NPU_SKIP_GROUP_COUNT"), 0)
        self.assertEqual(parse_probe_u32(text, "B2_NPU_LAST_COMPUTE_CYCLES"), 2494)
        with self.assertRaises(ValueError):
            parse_probe_u32(text, "B2_NPU_NOT_A_REGISTER")

    def test_comparison_keeps_static_and_live_on_separate_rows(self) -> None:
        records = {
            "b3_dense": record_from_artifacts(
                mode="b3_dense",
                run_manifest={"status": "PASS", "elf_sha256": "a", "bitstream_sha256": "b"},
                probe_text=_probe(592, 0, 2000, 1, 0),
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                decision_source="none_full_open_or_dense",
            ),
            "b3_full_open": record_from_artifacts(
                mode="b3_full_open",
                run_manifest={"status": "PASS", "elf_sha256": "a", "bitstream_sha256": "b"},
                probe_text=_probe(592, 0, 2000, 1, 0),
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                decision_source="host_full_open_mask",
            ),
            "b3_static_mixed": record_from_artifacts(
                mode="b3_static_mixed",
                run_manifest={"status": "PASS", "elf_sha256": "a", "bitstream_sha256": "b"},
                probe_text=_probe(296, 296, 1200, 1, 0),
                logits=(74, -18, 14, 0, 0, 0, 0, 0, 0, 114),
                decision_source="host_replay_static_mixed",
            ),
            "b3_live_eneuron": record_from_artifacts(
                mode="b3_live_eneuron",
                run_manifest={"status": "PASS", "elf_sha256": "a", "bitstream_sha256": "b"},
                probe_text=_probe(296, 296, 1200, 1, 0),
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                decision_source="live_eneuron_s2",
            ),
        }
        comparison = build_comparison(records)
        self.assertEqual(comparison["modes"], REQUIRED_MODES)
        self.assertEqual(len(comparison["rows"]), 4)
        self.assertEqual([row["mode"] for row in comparison["rows"]], list(REQUIRED_MODES))
        for row in comparison["rows"]:
            for field in REQUIRED_FIELDS:
                self.assertIn(field, row)
        collapsed = dict(records)
        collapsed["b3_live_eneuron"] = dict(records["b3_live_eneuron"])
        collapsed["b3_live_eneuron"]["decision_source"] = "host_replay_static_mixed"
        with self.assertRaises(ValueError):
            build_comparison(collapsed)

    def test_failed_run_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            record_from_artifacts(
                mode="b3_dense",
                run_manifest={"status": "FAIL"},
                probe_text=_probe(1, 0, 1, 0, 0),
                logits=(0,) * 10,
                decision_source="none_full_open_or_dense",
            )

    def test_write_comparison_round_trip(self) -> None:
        records = {
            "b3_dense": record_from_artifacts(
                mode="b3_dense",
                run_manifest={"status": "PASS"},
                probe_text=_probe(592, 0, 10, 0, 0),
                logits=(1,) * 10,
                decision_source="none_full_open_or_dense",
            ),
            "b3_full_open": record_from_artifacts(
                mode="b3_full_open",
                run_manifest={"status": "PASS"},
                probe_text=_probe(592, 0, 10, 0, 0),
                logits=(1,) * 10,
                decision_source="host_full_open_mask",
            ),
            "b3_static_mixed": record_from_artifacts(
                mode="b3_static_mixed",
                run_manifest={"status": "PASS"},
                probe_text=_probe(296, 296, 8, 1, 0),
                logits=(2,) * 10,
                decision_source="host_replay_static_mixed",
            ),
            "b3_live_eneuron": record_from_artifacts(
                mode="b3_live_eneuron",
                run_manifest={"status": "PASS"},
                probe_text=_probe(296, 296, 8, 1, 0),
                logits=(1,) * 10,
                decision_source="live_eneuron_s2",
            ),
        }
        comparison = build_comparison(records)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "b3_14_comparison.json"
            write_comparison(path, comparison)
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["schema"], "eneuron_b3_14_comparison_v1")
        self.assertEqual(len(loaded["rows"]), 4)


if __name__ == "__main__":
    unittest.main()

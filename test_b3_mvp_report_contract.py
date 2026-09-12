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
    comparison_from_run_dirs,
    parse_probe_u32,
    record_from_artifacts,
    record_from_run_dir,
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
    def test_committed_board_artifact_keeps_static_and_live_apart(self) -> None:
        path = Path(__file__).resolve().parent / "artifacts/logs/b3_mvp_20260912_be84596/b3_14_comparison.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "eneuron_b3_14_comparison_v1")
        self.assertEqual(data["modes"], list(REQUIRED_MODES))
        rows = {row["mode"]: row for row in data["rows"]}
        self.assertEqual(set(rows), set(REQUIRED_MODES))
        for field in REQUIRED_FIELDS:
            for row in rows.values():
                self.assertIn(field, row)
        live = rows["b3_live_eneuron"]
        static = rows["b3_static_mixed"]
        dense = rows["b3_dense"]
        self.assertEqual(live["decision_source"], "live_eneuron_s2")
        self.assertEqual(static["decision_source"], "host_replay_static_mixed")
        self.assertNotEqual(live["decision_source"], static["decision_source"])
        self.assertGreater(static["skip_group_count"], 0)
        self.assertGreater(live["skip_group_count"], 0)
        self.assertLessEqual(static["last_compute_cycles"], dense["last_compute_cycles"])
        self.assertLessEqual(live["last_compute_cycles"], dense["last_compute_cycles"])
        self.assertEqual(live["bitstream_sha256"].lower(), dense["bitstream_sha256"].lower())

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

    def test_record_from_run_dir_reads_shipped_uart_and_probe(self) -> None:
        uart = (
            "B2_PACKET_BEGIN\r\n"
            "B3_LIVE_ENEURON_PASS sequence=1 sample_id=0x1 response_words=1 mask_words=19 "
            "logits=165,-18,14,0,0,0,0,0,0,153 decision_source=live_eneuron_s2\r\n"
        )
        static_uart = (
            "B2_PACKET_BEGIN\r\n"
            "B3_STATIC_MIXED_PASS sequence=1 sample_id=0x1 response_words=1 mask_words=19 "
            "logits=74,-18,14,0,0,0,0,0,0,114\r\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            live_dir = Path(temp) / "live"
            live_dir.mkdir()
            (live_dir / "run_manifest.json").write_text(
                "\ufeff" + json.dumps({"status": "PASS", "elf_sha256": "e", "bitstream_sha256": "b"}),
                encoding="utf-8",
            )
            (live_dir / "post_pass_probe.log").write_text(_probe(296, 296, 1200, 1, 0), encoding="utf-8")
            (live_dir / "uart.log").write_text(uart, encoding="utf-8")
            live = record_from_run_dir(live_dir, "b3_live_eneuron")
            self.assertEqual(live["decision_source"], "live_eneuron_s2")
            self.assertEqual(live["logits"], [165, -18, 14, 0, 0, 0, 0, 0, 0, 153])
            self.assertEqual(live["last_compute_cycles"], 1200)
            static_dir = Path(temp) / "static"
            static_dir.mkdir()
            (static_dir / "run_manifest.json").write_text(
                json.dumps({"status": "PASS"}),
                encoding="utf-8",
            )
            (static_dir / "post_pass_probe.log").write_text(_probe(296, 296, 1100, 1, 0), encoding="utf-8")
            (static_dir / "uart.log").write_text(static_uart, encoding="utf-8")
            static = record_from_run_dir(static_dir, "b3_static_mixed")
            self.assertEqual(static["decision_source"], "host_replay_static_mixed")
            with self.assertRaises(ValueError):
                record_from_run_dir(live_dir, "b3_static_mixed")
            dense_dir = Path(temp) / "dense"
            dense_dir.mkdir()
            (dense_dir / "run_manifest.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
            (dense_dir / "post_pass_probe.log").write_text(_probe(592, 0, 2000, 1, 0), encoding="utf-8")
            (dense_dir / "uart.log").write_text(
                "B3_DENSE_PASS logits=165,-18,14,0,0,0,0,0,0,153\n",
                encoding="utf-8",
            )
            open_dir = Path(temp) / "open"
            open_dir.mkdir()
            (open_dir / "run_manifest.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
            (open_dir / "post_pass_probe.log").write_text(_probe(592, 0, 2000, 1, 0), encoding="utf-8")
            (open_dir / "uart.log").write_text(
                "B3_FULL_OPEN_PASS logits=165,-18,14,0,0,0,0,0,0,153\n",
                encoding="utf-8",
            )
            comparison = comparison_from_run_dirs({
                "b3_dense": dense_dir,
                "b3_full_open": open_dir,
                "b3_static_mixed": static_dir,
                "b3_live_eneuron": live_dir,
            })
            self.assertEqual(len(comparison["rows"]), 4)

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

"""B3-SPEED 合同：四模式分行，每行四段墙钟，禁止 888 当端到端加速。"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from b3_mvp_report import (
    REQUIRED_MODES,
    SPEED_SEGMENT_FIELDS,
    build_comparison,
    build_speed_comparison,
    parse_speed_split_from_uart,
    record_from_artifacts,
    record_from_run_dir,
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


def _speed_record(mode: str, *, cycles: int, execute: int, skip: int, logits: tuple[int, ...],
                  source: str, ps_us: int, dma_us: int, uart_us: int) -> dict[str, object]:
    return record_from_artifacts(
        mode=mode,
        run_manifest={
            "status": "PASS",
            "elf_sha256": "e",
            "bitstream_sha256": "b",
            "host_uart_us": uart_us,
        },
        probe_text=_probe(execute, skip, cycles, 1, 0),
        logits=logits,
        decision_source=source,
        speed={
            "ps_schedule_us": ps_us,
            "dma_roundtrip_us": dma_us,
            "host_uart_us": uart_us,
        },
    )


class B3SpeedReportContractTests(unittest.TestCase):
    @staticmethod
    def _last_packet_transaction(uart: str) -> str:
        if "B2_PACKET_BEGIN" not in uart:
            raise AssertionError("UART missing B2_PACKET_BEGIN")
        packet = uart.rsplit("B2_PACKET_BEGIN", 1)[-1]
        if not packet.strip():
            raise AssertionError("last packet transaction is empty")
        return packet

    def test_uart_without_begin_marker_is_rejected(self) -> None:
        with self.assertRaises(AssertionError):
            B3SpeedReportContractTests._last_packet_transaction(
                "B3_SPEED_SPLIT ps_us=1 dma_us=2\nB3_LIVE_ENEURON_PASS logits=1\n"
            )

    def test_live_l0_cache_board_artifact_is_self_consistent(self) -> None:
        root = Path(__file__).resolve().parent
        artifact = root / "artifacts/logs/b3_live_l0_cache_20260913_82b079e"
        data = json.loads((artifact / "b3_live_l0_cache_comparison.json").read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "BOARD_DIAGNOSTIC_PASS_SPEED_GATE_OPEN")
        self.assertEqual(data["candidate_ps_us"], [827, 829, 828])
        self.assertEqual(data["candidate_ps_us_median"], 828)
        self.assertEqual(data["npu_cycles"], [1606, 1606, 1606])
        self.assertEqual(data["execute_groups"], [296, 296, 296])
        self.assertEqual(data["skip_groups"], [296, 296, 296])
        self.assertEqual(data["protocol_errors"], [0, 0, 0])
        observed_ps: list[int] = []
        observed_dma: list[int] = []
        observed_cycles: list[int] = []
        observed_execute: list[int] = []
        observed_skip: list[int] = []
        observed_errors: list[int] = []
        for run in data["run_files"]:
            run_dir = artifact / f"run-{run['run']}"
            for name, field in (
                ("run_manifest.json", "manifest_canonical_lf_sha256"),
                ("uart.log", "uart_canonical_lf_sha256"),
                ("post_pass_probe.log", "probe_canonical_lf_sha256"),
            ):
                canonical = (run_dir / name).read_text(encoding="utf-8").replace("\r\n", "\n")
                digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                self.assertEqual(digest, run[field])

            manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "PASS")
            self.assertEqual(manifest["git_head"], data["git_head"])
            self.assertEqual(manifest["elf_sha256"].lower(), data["elf_sha256"])
            self.assertEqual(manifest["bitstream_sha256"].lower(), data["bitstream_sha256"])
            self.assertEqual(manifest["xsa_sha256"].lower(), data["xsa_sha256"])
            uart = (run_dir / "uart.log").read_text(encoding="utf-8")
            packet = self._last_packet_transaction(uart)
            speed = re.search(r"(?m)^B3_SPEED_SPLIT ps_us=(\d+) dma_us=(\d+)\r?$", packet)
            result = re.search(
                r"(?m)^B3_LIVE_ENEURON_PASS sequence=\d+ .*?logits=([-\d,]+) "
                r"group_reads=(\d+) group_skips=(\d+) .*?$",
                packet,
            )
            self.assertIsNotNone(speed)
            self.assertIsNotNone(result)
            assert speed is not None and result is not None
            observed_ps.append(int(speed.group(1)))
            observed_dma.append(int(speed.group(2)))
            self.assertEqual([int(value) for value in result.group(1).split(",")], data["logits"])
            observed_execute.append(int(result.group(2)))
            observed_skip.append(int(result.group(3)))

            probe = (run_dir / "post_pass_probe.log").read_text(encoding="utf-8")
            probe_values = {
                key: int(value, 0)
                for key, value in re.findall(r"(?m)^B2_NPU_([A-Z_]+)=(0x[0-9A-Fa-f]+|\d+)\r?$", probe)
            }
            observed_cycles.append(probe_values["LAST_COMPUTE_CYCLES"])
            observed_errors.append(probe_values["PROTOCOL_ERROR_COUNT"])
            self.assertEqual(probe_values["EXECUTE_GROUP_COUNT"], observed_execute[-1])
            self.assertEqual(probe_values["SKIP_GROUP_COUNT"], observed_skip[-1])

        self.assertEqual(len(data["run_files"]), 3)
        self.assertEqual(len(list(artifact.glob("run-*"))), 3)
        packet_source = (
            root / "boards/hellozynq/b2_sw/src/packet_main.c"
        ).read_bytes()
        self.assertEqual(
            hashlib.sha256(packet_source).hexdigest(),
            data["packet_source_sha256"],
        )
        self.assertEqual(observed_ps, data["candidate_ps_us"])
        self.assertEqual(observed_dma, data["dma_us"])
        self.assertEqual(observed_cycles, data["npu_cycles"])
        self.assertEqual(observed_execute, data["execute_groups"])
        self.assertEqual(observed_skip, data["skip_groups"])
        self.assertEqual(observed_errors, data["protocol_errors"])

    def test_current_management_entries_follow_post_cache_state(self) -> None:
        root = Path(__file__).resolve().parent
        b2 = json.loads((root / ".nexus-map/concepts/b2_packet_npu.json").read_text(encoding="utf-8"))
        p16 = json.loads(
            (root / ".nexus-map/concepts/p16_board_validation.json").read_text(encoding="utf-8")
        )
        concept = json.loads(
            (root / ".nexus-map/concepts/concept_model.json").read_text(encoding="utf-8")
        )
        state = concept["current_repository_state"]
        p16_node = next(node for node in concept["nodes"] if node["id"] == "p16-board-validation")
        board_b2 = next(node for node in concept["nodes"] if node["id"] == "board-phase2-b2")

        self.assertEqual(b2["source_identity_rule"], "QUERY_CURRENT_CHECKOUT_AT_RUNTIME")
        self.assertIn("B3_09_BOARD_PASS", b2["current_status"])
        self.assertIn("B3_GOAL_GATE_OPEN", b2["current_status"])
        self.assertTrue(b2["next_gate"].startswith("B3-SPEED-GATE"))
        self.assertIn("B3-GOAL-GATE", p16["current_gates"])
        self.assertEqual(state["b3_goal_gate"], "OPEN")
        self.assertIn("82b079e", p16_node["evidence_gap"])
        self.assertNotIn("setup_fail", board_b2["implementation_status"])
        self.assertTrue(str(concept["generated_at"]).startswith("2026-09-13"))

        workflow = (root / "WORKFLOW_STATE.md").read_text(encoding="utf-8")
        next_action = workflow.split("## 下一动作", 1)[1].split("## ", 1)[0]
        self.assertIn("82b079e", next_action)
        git_forensics = (root / ".nexus-map/hotspots/git_forensics.md").read_text(encoding="utf-8")
        self.assertIn("artifacts/logs/b3_live_l0_cache_20260913_82b079e", git_forensics)
        self.assertIn("PR #93", git_forensics)
        self.assertIn("be84596", git_forensics)
        current = (root / "docs/CURRENT_STATUS.md").read_text(encoding="utf-8")
        self.assertNotIn("B3_SPEED_PASS", current)
        self.assertIn("B3_GOAL_GATE_OPEN", current)

    def test_current_docs_separate_measurement_from_speed_gate(self) -> None:
        root = Path(__file__).resolve().parent
        todo = (root / "docs/planning/TODO.md").read_text(encoding="utf-8")
        current = (root / "docs/CURRENT_STATUS.md").read_text(encoding="utf-8")
        workflow = (root / "WORKFLOW_STATE.md").read_text(encoding="utf-8")
        self.assertIn("- [x] B3-SPEED-MEASURED", todo)
        self.assertIn("- [ ] B3-SPEED-GATE", todo)
        self.assertIn("B3_SPEED_GATE_OPEN", current)
        self.assertIn("B3-SPEED-GATE", workflow)
        self.assertNotIn("B3_SPEED_PASS", current)

    def test_nexus_keeps_speed_measurement_separate_from_goal_gate(self) -> None:
        root = Path(__file__).resolve().parent
        domains = (root / ".nexus-map/concepts/domains.md").read_text(encoding="utf-8")
        coverage = (root / ".nexus-map/arch/test_coverage.md").read_text(encoding="utf-8")
        hierarchy = json.loads(
            (root / ".nexus-map/concepts/p16_board_validation.json").read_text(encoding="utf-8")
        )["b3_gate_hierarchy"]
        self.assertIn("B3_SPEED_MEASURED / B3_SPEED_GATE_OPEN", domains)
        self.assertNotIn("`B3_SPEED_PASS`", domains)
        self.assertIn("B3-SPEED-GATE=OPEN", coverage)
        self.assertEqual(
            hierarchy["parallel_goal_gates"], ["B3-SPEED-GATE", "B3-POWER-GATE"]
        )
        self.assertIn("B3-POWER-MEASURED", hierarchy["current_gates"])

    def test_nexus_live_board_state_has_no_pending_contradiction(self) -> None:
        root = Path(__file__).resolve().parent
        p16 = json.loads(
            (root / ".nexus-map/concepts/p16_board_validation.json").read_text(encoding="utf-8")
        )
        live = p16["b3_live_eneuron_host_subgate"]
        board_arch = (root / ".nexus-map/arch/p16_board_validation.md").read_text(
            encoding="utf-8"
        )
        concept = json.loads(
            (root / ".nexus-map/concepts/concept_model.json").read_text(encoding="utf-8")
        )
        authoritative = concept["current_repository_state"]

        self.assertEqual(live["status"], "BOARD_CACHE_DIAGNOSTIC_PASS_SPEED_GATE_OPEN")
        self.assertEqual(live["board_elf_jtag"], "CURRENT_CACHE_ELF_THREE_RUNS_PASS")
        self.assertNotIn("B3-09 board ELF/JTAG", live["does_not_close"])
        self.assertIn("B3-09 实板已关闭", board_arch)
        self.assertNotIn("实板 ELF/JTAG 未关闭", board_arch)
        self.assertEqual(authoritative["source_identity_rule"], "QUERY_CURRENT_CHECKOUT_AT_RUNTIME")
        self.assertEqual(authoritative["b3_mvp_gate"], "PASS")
        self.assertEqual(authoritative["b3_speed_gate"], "OPEN")
        self.assertEqual(authoritative["b3_power_gate"], "OPEN")
        release = next(stage for stage in p16["stages"] if stage["id"] == "B4-RELEASE")
        self.assertNotIn("B3-STRICT-GATE", release["requires"])
        self.assertNotIn("完整 B2-GATE 与 B3-STRICT-GATE", board_arch)

    def test_committed_board_artifact_keeps_four_segments_and_forbids_e2e_claim(self) -> None:
        path = Path(__file__).resolve().parent / "artifacts/logs/b3_speed_20260912_be84596/b3_speed_comparison.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        from b3_mvp_report import forbid_end_to_end_from_npu_cycles
        forbid_end_to_end_from_npu_cycles(data)
        self.assertEqual(data["schema"], "eneuron_b3_speed_comparison_v1")
        self.assertEqual(data["claim"], "local_npu_cycle_delta_only")
        self.assertEqual(data["measurement_status"], "SINGLE_SAMPLE_DIAGNOSTIC")
        self.assertEqual(data["speed_gate"], "OPEN")
        self.assertEqual(data["end_to_end_acceleration_status"], "NOT_PROVEN")
        self.assertEqual(data["timing_relationship"], "nested_not_additive")
        rows = {row["mode"]: row for row in data["rows"]}
        self.assertEqual(set(rows), set(REQUIRED_MODES))
        for row in rows.values():
            for field in SPEED_SEGMENT_FIELDS:
                self.assertIn(field, row)
                self.assertIsInstance(row[field], int)
                self.assertGreaterEqual(row[field], 0)
            self.assertEqual(row["mask_granularity"], "group_4way")
        dense = rows["b3_dense"]
        static = rows["b3_static_mixed"]
        live = rows["b3_live_eneuron"]
        self.assertEqual(live["decision_source"], "live_eneuron_s2")
        self.assertEqual(static["decision_source"], "host_replay_static_mixed")
        self.assertNotEqual(live["decision_source"], static["decision_source"])
        self.assertEqual(data["npu_cycle_delta"], dense["last_compute_cycles"] - static["last_compute_cycles"])
        npu_us = dense["last_compute_cycles"] / 200.0
        self.assertGreater(dense["host_uart_us"], npu_us)
        self.assertGreater(static["host_uart_us"], npu_us)

    def test_speed_rows_keep_four_wall_clock_segments(self) -> None:
        records = {
            "b3_dense": _speed_record(
                "b3_dense", cycles=2494, execute=592, skip=0,
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                source="none_full_open_or_dense", ps_us=120, dma_us=800, uart_us=45000,
            ),
            "b3_full_open": _speed_record(
                "b3_full_open", cycles=2494, execute=592, skip=0,
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                source="host_full_open_mask", ps_us=110, dma_us=790, uart_us=44000,
            ),
            "b3_static_mixed": _speed_record(
                "b3_static_mixed", cycles=1606, execute=296, skip=296,
                logits=(74, -18, 14, 0, 0, 0, 0, 0, 0, 114),
                source="host_replay_static_mixed", ps_us=130, dma_us=810, uart_us=46000,
            ),
            "b3_live_eneuron": _speed_record(
                "b3_live_eneuron", cycles=1606, execute=296, skip=296,
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                source="live_eneuron_s2", ps_us=900, dma_us=820, uart_us=47000,
            ),
        }
        comparison = build_speed_comparison(records)
        self.assertEqual(comparison["schema"], "eneuron_b3_speed_comparison_v1")
        self.assertEqual(comparison["modes"], REQUIRED_MODES)
        self.assertEqual(len(comparison["rows"]), 4)
        self.assertEqual([row["mode"] for row in comparison["rows"]], list(REQUIRED_MODES))
        for row in comparison["rows"]:
            for field in SPEED_SEGMENT_FIELDS:
                self.assertIn(field, row)
                self.assertIsInstance(row[field], int)
                self.assertGreaterEqual(row[field], 0)
        self.assertEqual(comparison["claim"], "local_npu_cycle_delta_only")
        self.assertEqual(comparison["measurement_status"], "SINGLE_SAMPLE_DIAGNOSTIC")
        self.assertEqual(comparison["speed_gate"], "OPEN")
        self.assertEqual(comparison["end_to_end_acceleration_status"], "NOT_PROVEN")
        self.assertEqual(comparison["timing_relationship"], "nested_not_additive")

    def test_live_must_not_collapse_into_static(self) -> None:
        records = {
            "b3_dense": _speed_record(
                "b3_dense", cycles=2494, execute=592, skip=0,
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                source="none_full_open_or_dense", ps_us=1, dma_us=2, uart_us=3,
            ),
            "b3_full_open": _speed_record(
                "b3_full_open", cycles=2494, execute=592, skip=0,
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                source="host_full_open_mask", ps_us=1, dma_us=2, uart_us=3,
            ),
            "b3_static_mixed": _speed_record(
                "b3_static_mixed", cycles=1606, execute=296, skip=296,
                logits=(74, -18, 14, 0, 0, 0, 0, 0, 0, 114),
                source="host_replay_static_mixed", ps_us=1, dma_us=2, uart_us=3,
            ),
            "b3_live_eneuron": _speed_record(
                "b3_live_eneuron", cycles=1606, execute=296, skip=296,
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                source="host_replay_static_mixed", ps_us=1, dma_us=2, uart_us=3,
            ),
        }
        with self.assertRaises(ValueError):
            build_speed_comparison(records)
        with self.assertRaises(ValueError):
            build_comparison(records)

    def test_missing_wall_clock_segment_is_rejected(self) -> None:
        records = {
            "b3_dense": _speed_record(
                "b3_dense", cycles=2494, execute=592, skip=0,
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                source="none_full_open_or_dense", ps_us=1, dma_us=2, uart_us=3,
            ),
            "b3_full_open": _speed_record(
                "b3_full_open", cycles=2494, execute=592, skip=0,
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                source="host_full_open_mask", ps_us=1, dma_us=2, uart_us=3,
            ),
            "b3_static_mixed": _speed_record(
                "b3_static_mixed", cycles=1606, execute=296, skip=296,
                logits=(74, -18, 14, 0, 0, 0, 0, 0, 0, 114),
                source="host_replay_static_mixed", ps_us=1, dma_us=2, uart_us=3,
            ),
            "b3_live_eneuron": record_from_artifacts(
                mode="b3_live_eneuron",
                run_manifest={"status": "PASS"},
                probe_text=_probe(296, 296, 1606, 1, 0),
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                decision_source="live_eneuron_s2",
            ),
        }
        with self.assertRaises(ValueError) as ctx:
            build_speed_comparison(records)
        self.assertIn("ps_schedule_us", str(ctx.exception))

    def test_npu_cycle_delta_cannot_be_claimed_as_end_to_end(self) -> None:
        records = {
            "b3_dense": _speed_record(
                "b3_dense", cycles=2494, execute=592, skip=0,
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                source="none_full_open_or_dense", ps_us=10, dma_us=20, uart_us=30000,
            ),
            "b3_full_open": _speed_record(
                "b3_full_open", cycles=2494, execute=592, skip=0,
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                source="host_full_open_mask", ps_us=10, dma_us=20, uart_us=30000,
            ),
            "b3_static_mixed": _speed_record(
                "b3_static_mixed", cycles=1606, execute=296, skip=296,
                logits=(74, -18, 14, 0, 0, 0, 0, 0, 0, 114),
                source="host_replay_static_mixed", ps_us=10, dma_us=20, uart_us=30000,
            ),
            "b3_live_eneuron": _speed_record(
                "b3_live_eneuron", cycles=1606, execute=296, skip=296,
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                source="live_eneuron_s2", ps_us=10, dma_us=20, uart_us=30000,
            ),
        }
        comparison = build_speed_comparison(records)
        self.assertEqual(comparison["npu_cycle_delta"], 888)
        self.assertEqual(comparison["speed_gate"], "OPEN")
        self.assertEqual(comparison["end_to_end_acceleration_status"], "NOT_PROVEN")
        poisoned = dict(comparison)
        poisoned["end_to_end_accelerated"] = True
        poisoned["claim"] = "end_to_end_acceleration"
        from b3_mvp_report import forbid_end_to_end_from_npu_cycles
        with self.assertRaises(ValueError) as claim_ctx:
            forbid_end_to_end_from_npu_cycles(poisoned)
        self.assertIn("end-to-end", str(claim_ctx.exception).lower())

    def test_primary_npu_cycle_delta_uses_live_not_static_mode(self) -> None:
        records = {
            "b3_dense": _speed_record(
                "b3_dense", cycles=2494, execute=592, skip=0,
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                source="none_full_open_or_dense", ps_us=10, dma_us=20, uart_us=30000,
            ),
            "b3_full_open": _speed_record(
                "b3_full_open", cycles=2494, execute=592, skip=0,
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                source="host_full_open_mask", ps_us=10, dma_us=20, uart_us=30000,
            ),
            "b3_static_mixed": _speed_record(
                "b3_static_mixed", cycles=1400, execute=250, skip=342,
                logits=(74, -18, 14, 0, 0, 0, 0, 0, 0, 114),
                source="host_replay_static_mixed", ps_us=10, dma_us=20, uart_us=30000,
            ),
            "b3_live_eneuron": _speed_record(
                "b3_live_eneuron", cycles=1700, execute=350, skip=242,
                logits=(165, -18, 14, 0, 0, 0, 0, 0, 0, 153),
                source="live_eneuron_s2", ps_us=10, dma_us=20, uart_us=30000,
            ),
        }
        comparison = build_speed_comparison(records)
        self.assertEqual(comparison["npu_cycle_delta"], 794)
        self.assertEqual(comparison["static_npu_cycle_delta"], 1094)

    def test_parse_speed_split_from_shipped_uart_line(self) -> None:
        text = "B3_SPEED_SPLIT ps_us=120 dma_us=800\nB3_DENSE_PASS logits=1,2,3,4,5,6,7,8,9,10\n"
        split = parse_speed_split_from_uart(text)
        self.assertEqual(split["ps_schedule_us"], 120)
        self.assertEqual(split["dma_roundtrip_us"], 800)
        with self.assertRaises(ValueError):
            parse_speed_split_from_uart("B3_DENSE_PASS logits=1,2,3,4,5,6,7,8,9,10\n")

    def test_record_from_run_dir_reads_speed_split_and_host_uart(self) -> None:
        uart = (
            "B2_PACKET_BEGIN\r\n"
            "B3_SPEED_SPLIT ps_us=55 dma_us=900\r\n"
            "B3_DENSE_PASS logits=165,-18,14,0,0,0,0,0,0,153\r\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp) / "dense"
            run_dir.mkdir()
            (run_dir / "run_manifest.json").write_text(
                json.dumps({"status": "PASS", "host_uart_us": 12345, "elf_sha256": "e", "bitstream_sha256": "b"}),
                encoding="utf-8",
            )
            (run_dir / "post_pass_probe.log").write_text(_probe(592, 0, 2494, 1, 0), encoding="utf-8")
            (run_dir / "uart.log").write_text(uart, encoding="utf-8")
            row = record_from_run_dir(run_dir, "b3_dense", require_speed=True)
            self.assertEqual(row["ps_schedule_us"], 55)
            self.assertEqual(row["dma_roundtrip_us"], 900)
            self.assertEqual(row["host_uart_us"], 12345)
            self.assertEqual(row["last_compute_cycles"], 2494)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SUMMARY = ROOT / "artifacts/results/b3_cp8_four_state_board.json"
EVIDENCE = ROOT / "artifacts/logs/b3_cp8_four_state_board_20260918_1714fc8"
HEAD = "1714fc85ffe498c91c3ef5a9033cb36a4042ce18"
FALLBACK = ["git-blob:boards/hellozynq/b2_hw/run_b2_build.ps1"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_cp8_four_state_board_evidence() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["schema"] == "eneuron_b3_cp8_four_state_board_v1"
    assert summary["status"] == "CP8_BOARD_FOUR_STATE_CONTROL_PASS"
    assert summary["git_head"] == HEAD
    assert summary["power_measurement_status"] == "NOT_MEASURED"
    assert summary["continuous_measured_cycles_semantics"] == "not_finalized_while_running"
    assert summary["packet_manifest_rebuilt_per_invocation"] is True
    assert summary["paired_identity_scope"] == ["bitstream_sha256", "xsa_sha256", "elf_sha256"]

    expected = {
        "dense_idle": ("dense", "idle"),
        "dense_full": ("dense", "full"),
        "lossless_idle": ("lossless_zero_group_skip", "idle"),
        "lossless_full": ("lossless_zero_group_skip", "full"),
    }
    assert set(summary["states"]) == set(expected)

    raw_states: dict[str, dict[str, object]] = {}
    for name, (mode, state_name) in expected.items():
        entry = summary["states"][name]
        raw_path = ROOT / entry["raw_state_json"]
        program_path = ROOT / entry["program_log"]
        probe_path = ROOT / entry["probe_log"]
        assert raw_path.is_file() and program_path.is_file() and probe_path.is_file()
        assert _sha256(raw_path) == entry["raw_state_json_sha256"]
        assert _sha256(program_path) == entry["program_log_sha256"]
        assert _sha256(probe_path) == entry["probe_log_sha256"]
        assert "B2_FPGA_PROGRAM_PASS" in program_path.read_text(encoding="utf-8")
        assert "B2_ELF_DOWNLOAD_PASS" in program_path.read_text(encoding="utf-8")
        assert "B2_CPU_RUN_PASS" in program_path.read_text(encoding="utf-8")
        assert "B3_CP8_POWER_PROBE_PASS=1" in probe_path.read_text(encoding="utf-8")

        raw = json.loads(raw_path.read_text(encoding="utf-8-sig"))
        raw_states[name] = raw
        assert raw["git_head"] == HEAD
        assert raw["status"] == "CP8_POWER_STATE_PASS"
        assert raw["mode"] == mode and raw["state"] == state_name
        assert raw["formal_evidence"] is True
        assert raw["protocol_error_count"] == 0
        assert raw["hardware_source_canonical_fallbacks"] == FALLBACK
        if state_name == "idle":
            assert raw["control"] == 0x43503849
            assert raw["replay_status"] == 1
            assert raw["capture_count"] == 0
            assert raw["completed_count"] == 0
        else:
            assert raw["control"] == 0x43503852
            assert raw["replay_status"] == 3
            assert raw["capture_count"] == 397
            assert raw["completed_count"] > 0
            assert raw["completed_second"] > raw["completed_first"]

    for mode in ("dense", "lossless"):
        idle = raw_states[f"{mode}_idle"]
        full = raw_states[f"{mode}_full"]
        for field in ("bitstream_sha256", "xsa_sha256", "elf_sha256"):
            assert idle[field] == full[field], f"{mode} {field} changed across idle/full"
        packet = EVIDENCE / f"{mode}_packet_build_manifest.json"
        assert packet.is_file()
        assert _sha256(packet) == full["packet_manifest_sha256"]

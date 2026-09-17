from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RESULT = ROOT / "artifacts/results/b3_qat_cp5b_pl_distribution_board_pair.json"


def test_cp5b_formal_distribution_closes_the_pure_pl_speed_gate() -> None:
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    dense = data["dense"]
    lossless = data["lossless_zero_group_skip"]
    paired = data["paired_checks"]

    assert data["schema"] == "eneuron_b3_qat_cp5b_pl_distribution_board_pair_v1"
    assert data["status"] == "CP5B_FORMAL_PASS"
    assert data["phase"] == "B3-PAPER-CP5B"
    assert data["input_samples"] == 397
    assert data["warmup_samples"] == 1000
    assert data["measured_samples"] == 10000
    assert len(dense["rounds"]) == len(lossless["rounds"]) == 5

    for mode in (dense, lossless):
        assert mode["timing"]["wns_ns"] >= 0
        assert mode["timing"]["whs_ns"] >= 0
        assert mode["timing"]["route_errors"] == 0
        assert mode["timing"]["drc_hard_errors"] == 0
        assert mode["timing"]["dsp48e1"] == 4
        for round_data in mode["rounds"]:
            assert round_data["formal_evidence"] is True
            assert round_data["input_samples"] == 397
            assert round_data["measured_samples"] == 10000
            assert round_data["observed_group_instances"] == 6_747_024
            assert round_data["final_sample_index"] == 74
            assert round_data["result_frame_pass"] is True
            assert round_data["protocol_error_count"] == 0

    assert all(value > 1.08 for value in paired["throughput_speedup_by_round"])
    assert paired["minimum_throughput_speedup"] > 1.08
    assert paired["same_result_crc"] is True
    assert paired["all_result_frames_pass"] is True
    assert paired["protocol_error_count"] == 0
    assert paired["speed_gate"] == "PASS"
    assert "PL-internal steady-state" in data["boundary"]
    assert "not a packet end-to-end" in data["boundary"]


def test_cp5b_pair_binds_all_archived_raw_evidence() -> None:
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    for mode_name in ("dense", "lossless_zero_group_skip"):
        mode = data[mode_name]
        for path_key, sha_key in (
            ("hardware_manifest", "hardware_manifest_sha256"),
            ("signoff_summary", "signoff_summary_sha256"),
            ("packet_manifest", "packet_manifest_sha256"),
        ):
            path = ROOT / mode[path_key]
            assert path.is_file(), path
            assert hashlib.sha256(path.read_bytes()).hexdigest() == mode[sha_key]

        for round_data in mode["rounds"]:
            for path_key, sha_key in (
                ("run", "run_sha256"),
                ("program_log", "program_log_sha256"),
                ("probe_log", "probe_log_sha256"),
            ):
                path = ROOT / round_data[path_key]
                assert path.is_file(), path
                assert hashlib.sha256(path.read_bytes()).hexdigest() == round_data[sha_key]

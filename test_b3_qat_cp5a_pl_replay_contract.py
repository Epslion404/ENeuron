from __future__ import annotations

import json
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RESULT = ROOT / "artifacts/results/b3_qat_cp5a_pl_replay_board_pair.json"


def test_cp5a_formal_pair_is_self_consistent_and_scope_limited() -> None:
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    dense = data["dense"]
    lossless = data["lossless_zero_group_skip"]
    paired = data["paired_checks"]

    assert data["schema"] == "eneuron_b3_qat_cp5a_pl_replay_board_pair_v1"
    assert data["status"] == "CP5A_FORMAL_PASS"
    assert data["qat_sample_index"] == 201
    assert data["warmup_samples"] == 1000
    assert data["measured_samples"] == 10000
    assert dense["timing"]["wns_ns"] >= 0
    assert lossless["timing"]["wns_ns"] >= 0
    assert dense["timing"]["dsp48e1"] == 4
    assert lossless["timing"]["dsp48e1"] == 4
    assert dense["replay_overhead_cycles"] == lossless["replay_overhead_cycles"] == 18
    assert dense["result_frame_pass"] and lossless["result_frame_pass"]
    assert dense["result_crc"] == lossless["result_crc"]
    assert dense["protocol_error_count"] == lossless["protocol_error_count"] == 0
    assert lossless["skip_groups_total"] > 0
    assert paired["throughput_speedup"] > 1.08
    assert paired["throughput_speedup"] < 1.10
    assert "single-representative-sample" in data["boundary"]
    assert "does not close CP5b or B3-SPEED-GATE" in data["boundary"]


def test_cp5a_pair_binds_existing_raw_runs_and_manifests() -> None:
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    for mode in ("dense", "lossless_zero_group_skip"):
        entry = data[mode]
        for path_key, sha_key in (
            ("hardware_manifest", "hardware_manifest_sha256"),
            ("signoff_summary", "signoff_summary_sha256"),
            ("packet_manifest", "packet_manifest_sha256"),
            ("program_log", "program_log_sha256"),
            ("probe_log", "probe_log_sha256"),
            ("run", "run_sha256"),
        ):
            path = ROOT / entry[path_key]
            assert path.is_file(), path
            assert hashlib.sha256(path.read_bytes()).hexdigest() == entry[sha_key]

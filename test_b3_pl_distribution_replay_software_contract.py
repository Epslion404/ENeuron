from pathlib import Path


ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "boards/hellozynq/b2_sw/run_b2_packet_sw_build.ps1"
PACKET = ROOT / "boards/hellozynq/b2_sw/src/packet_main.c"
RUNNER = ROOT / "boards/hellozynq/b2_sw/run_b3_pl_distribution_replay_benchmark.ps1"
PROBE = ROOT / "boards/hellozynq/b2_sw/probe_b3_pl_distribution_replay_benchmark.tcl"


def test_distribution_replay_software_mode_is_explicit() -> None:
    build = BUILD.read_text(encoding="utf-8")
    packet = PACKET.read_text(encoding="utf-8")
    assert "B3DistributionReplay" in build
    assert "B3_PL_DISTRIBUTION_REPLAY" in build
    assert "b3_distribution_replay" in build
    assert "B3_PL_DISTRIBUTION_REPLAY" in packet
    assert "send_sample_frame_only" in packet
    assert "receive_result_frame_only" in packet
    assert "0x64U" in packet
    assert "0x70U" in packet


def test_distribution_replay_runner_and_probe_are_uart_independent() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    probe = PROBE.read_text(encoding="utf-8")
    for token in (
        "B3_PL_DISTRIBUTION_REPLAY_STATUS",
        "B3_PL_DISTRIBUTION_REPLAY_CAPTURE",
        "B3_PL_DISTRIBUTION_REPLAY_COMPLETED",
        "B3_PL_DISTRIBUTION_REPLAY_CYCLES",
        "result_frame_pass",
        "397",
        "10000",
        "formal_evidence",
    ):
        assert token in runner
    assert "uart" not in runner.lower()
    assert "B3_PL_DISTRIBUTION_REPLAY_RX_WORD_%02d" in probe


def test_distribution_replay_mode_is_in_t1_scope() -> None:
    from tools.ci.classify_changes import classify_paths

    scopes = classify_paths(
        [
            "boards/hellozynq/b2_sw/src/packet_main.c",
            "boards/hellozynq/b2_sw/run_b3_pl_distribution_replay_benchmark.ps1",
        ]
    )
    assert scopes["t1_repro"]

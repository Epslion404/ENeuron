import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from tools.ci.classify_changes import classify_paths


ROOT = Path(__file__).resolve().parent


def test_pl_replay_is_compile_time_opt_in_and_exports_measurement_counters() -> None:
    wrapper = (ROOT / "npu_zynq7020_t1_wrapper.sv").read_text(encoding="utf-8")
    adapter = (ROOT / "b2_npu_packet_adapter.sv").read_text(encoding="utf-8")
    axis_top = (
        ROOT / "boards/hellozynq/b2_hw/b2_npu_axis_top.v"
    ).read_text(encoding="utf-8")
    status = (
        ROOT / "boards/hellozynq/b2_hw/b2_npu_status_probe.v"
    ).read_text(encoding="utf-8")

    assert "`ifdef B3_PL_REPLAY_BENCHMARK" in wrapper
    assert "B3_PL_REPLAY_WARMUP_SAMPLES" in wrapper
    assert "B3_PL_REPLAY_MEASURE_SAMPLES" in wrapper
    for signal in (
        "pl_replay_status",
        "pl_replay_completed_count",
        "pl_replay_measured_cycles",
    ):
        assert signal in wrapper
        assert signal in adapter
        assert signal in axis_top
        assert signal in status


def test_pl_replay_status_registers_are_read_only_and_outside_frozen_map() -> None:
    status = (
        ROOT / "boards/hellozynq/b2_hw/b2_npu_status_probe.v"
    ).read_text(encoding="utf-8")

    assert "PL_REPLAY_STATUS_ADDR = 12'h064" in status
    assert "PL_REPLAY_COMPLETED_ADDR = 12'h068" in status
    assert "PL_REPLAY_CYCLES_ADDR = 12'h06C" in status
    assert "状态块没有可写寄存器" in status


def test_normal_hardware_modes_do_not_enable_pl_replay() -> None:
    build = (
        ROOT / "boards/hellozynq/b2_hw/build_b2.tcl"
    ).read_text(encoding="utf-8")

    assert "dense_pl_replay" in build
    assert "lossless_zero_group_skip_pl_replay" in build
    assert "if {[string match {*_pl_replay} $npu_mode]}" in build


def test_pl_replay_shim_behavior() -> None:
    fixed = Path("C:/msys64/ucrt64/bin")
    iverilog = fixed / "iverilog.exe"
    vvp = fixed / "vvp.exe"
    if not iverilog.is_file() or not vvp.is_file():
        fallback_iverilog = shutil.which("iverilog")
        fallback_vvp = shutil.which("vvp")
        if not fallback_iverilog or not fallback_vvp:
            pytest.skip("Icarus Verilog unavailable")
        iverilog = Path(fallback_iverilog)
        vvp = Path(fallback_vvp)

    with tempfile.TemporaryDirectory(prefix="b3-pl-replay-") as temp:
        binary = Path(temp) / "tb.vvp"
        compiled = subprocess.run(
            [
                str(iverilog),
                "-g2012",
                "-s",
                "tb_b3_pl_replay_shim",
                "-o",
                str(binary),
                "b3_pl_replay_shim.sv",
                "tb_b3_pl_replay_shim.sv",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert compiled.returncode == 0, compiled.stdout + compiled.stderr
        ran = subprocess.run(
            [str(vvp), str(binary)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "B3_PL_REPLAY_SHIM_PASS samples=6 measured=3" in ran.stdout


def test_pl_replay_changes_use_t1_repro_scope() -> None:
    scopes = classify_paths(
        [
            "b3_pl_replay_shim.sv",
            "tb_b3_pl_replay_shim.sv",
            "boards/hellozynq/b2_sw/run_b3_pl_replay_benchmark.ps1",
        ]
    )
    assert scopes["t1_repro"]
    assert not scopes["full_repository"]


def test_pl_replay_runner_freezes_bringup_boundary() -> None:
    runner = (
        ROOT / "boards/hellozynq/b2_sw/run_b3_pl_replay_benchmark.ps1"
    ).read_text(encoding="utf-8")
    probe = (
        ROOT / "boards/hellozynq/b2_sw/probe_b3_pl_replay_benchmark.tcl"
    ).read_text(encoding="utf-8")
    for token in (
        "QatSampleIndex = 201",
        "B3_PL_REPLAY_COMPLETED",
        "expectedGroupInstances",
        "observedGroupInstances",
        "resultFramePass",
        "CP5A_BRINGUP_PASS",
        "不关闭正式 CP5/B3-SPEED-GATE",
        "Hardware source closure mismatch",
    ):
        assert token in runner
    assert "B3_PL_REPLAY_RX_WORD_%02d" in probe
    assert "for {set index 0} {$index < 19}" in probe


def test_replay_formal_identity_uses_hardware_source_closure() -> None:
    runner = (
        ROOT / "boards/hellozynq/b2_sw/run_b3_pl_replay_benchmark.ps1"
    ).read_text(encoding="utf-8")
    assert "$hardwareSourceClosurePass" in runner
    assert "source_sha256" in runner
    assert "Hardware source closure mismatch" in runner
    assert "formal_evidence = $formalEvidence" in runner
    assert "$hardwareSameHead" not in runner

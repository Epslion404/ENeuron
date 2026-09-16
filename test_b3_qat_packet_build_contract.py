"""B3-PAPER-CP1：QAT manifest 到 packet ELF 的构建接线合同。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_qat_manifest_and_runner_are_explicitly_supported() -> None:
    build = (ROOT / "boards/hellozynq/b2_sw/run_b2_packet_sw_build.ps1").read_text(
        encoding="utf-8"
    )
    runner = (ROOT / "boards/hellozynq/b2_sw/run_b3_speed_benchmark.ps1").read_text(
        encoding="utf-8"
    )
    packet = (ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").read_text(
        encoding="utf-8"
    )

    assert "B3QatManifest" in build
    assert "B3BenchmarkSampleCount" in build
    assert "$goldenIsQat" in build
    assert "$goldenDenseMaskWords" in build
    assert "B3QatManifest = $BenchmarkManifest" in runner
    assert "Select-Object -First $Samples" in runner
    assert "if ($isQatManifest) { return [uint32]1 }" in runner
    assert "[BitConverter]::ToInt32([BitConverter]::GetBytes($rawLogit), 0)" in runner
    assert "B3 QAT logit mismatch" in runner
    assert "                           result_logits[index]);" not in packet
    assert "logits=165,-18" not in packet


def test_qat_manifest_has_cp1_dense_inputs_and_logits() -> None:
    manifest = json.loads(
        (ROOT / "tools/repro/b3_qat_model_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema"] == "eneuron_b3_qat_model_v1"
    assert manifest["model"]["word_count"] == 634
    assert len(manifest["samples"]) == 397
    assert all(len(sample["input_beats"]) == 8 for sample in manifest["samples"])
    assert all(len(sample["dense_logits"]) == 10 for sample in manifest["samples"])
    assert len({sample["input_sha256"] for sample in manifest["samples"]}) == 397
    assert any(value > 0 for value in manifest["samples"][0]["dense_logits"])
    assert any(value < 0 for value in manifest["samples"][0]["dense_logits"])


def test_full_wrapper_build_exposes_explicit_npu_mode() -> None:
    build = (ROOT / "boards/hellozynq/b2_hw/build_b2.tcl").read_text(encoding="utf-8")
    runner = (ROOT / "boards/hellozynq/b2_hw/run_b2_build.ps1").read_text(encoding="utf-8")
    assert "lossless_zero_group_skip" in build
    assert "set_property verilog_define $verilog_defines [current_fileset]" in build
    assert "B2_NPU_MODE=$npu_mode" in build
    assert "B2_VERILOG_DEFINE=[join $verilog_defines ,]" in build
    assert "[string]$NpuMode = 'dense'" in runner
    assert "-tclargs $gitHead $outDir $NpuMode" in runner
    assert "B2 NPU mode mismatch" in runner
    assert "npu_mode = $NpuMode" in runner


def test_packet_build_can_bind_an_explicit_hardware_build() -> None:
    sw_build = (ROOT / "boards/hellozynq/b2_sw/run_b2_sw_build.ps1").read_text(encoding="utf-8")
    packet_build = (ROOT / "boards/hellozynq/b2_sw/run_b2_packet_sw_build.ps1").read_text(encoding="utf-8")
    runner = (ROOT / "boards/hellozynq/b2_sw/run_b3_speed_benchmark.ps1").read_text(encoding="utf-8")
    for source in (sw_build, packet_build, runner):
        assert "HardwareBuildDir" in source
        assert "BuildTag" in source
    assert "hardware_npu_mode" in packet_build
    assert "HardwareBuildDir = $HardwareBuildDir" in runner


def test_speed_probe_allows_397_samples_with_accuracy_capture() -> None:
    probe = (ROOT / "boards/hellozynq/b2_sw/probe_b3_speed_benchmark.tcl").read_text(
        encoding="utf-8"
    )
    assert "sample count must be in 1..397" in probe
    assert "capture_logits sample count must be in 1..64" not in probe
    runner = (ROOT / "boards/hellozynq/b2_sw/run_b3_speed_benchmark.ps1").read_text(
        encoding="utf-8"
    )
    assert "if ($CaptureLogits -and $Samples -gt 64) { 600000 }" in runner

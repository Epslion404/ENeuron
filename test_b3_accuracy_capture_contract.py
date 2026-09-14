"""B3-22.1e1 合同：可选的板端逐样本 logits 采集。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_accuracy_capture_sources_and_layout_contract() -> None:
    packet = (ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").read_text(encoding="utf-8")
    build = (ROOT / "boards/hellozynq/b2_sw/run_b2_packet_sw_build.ps1").read_text(encoding="utf-8")
    runner = (ROOT / "boards/hellozynq/b2_sw/run_b3_speed_benchmark.ps1").read_text(encoding="utf-8")
    probe = (ROOT / "boards/hellozynq/b2_sw/probe_b3_speed_benchmark.tcl").read_text(encoding="utf-8")

    assert "B3_ACCURACY_BENCHMARK" in packet
    assert "ACCURACY_BENCH_BASE 0x0100A000U" in packet
    assert "struct accuracy_bench_sample" in packet
    assert "last_result_logits" in packet
    assert "#define ACCURACY_BENCH_FAIL 3U" in packet
    assert "++accuracy_bench->result_failures" in packet
    assert "accuracy_bench->status = ACCURACY_BENCH_FAIL" in packet
    assert packet.count("accuracy_bench_record_failure(") >= 6
    assert "B3AccuracyBenchmark" in build
    assert "B3_ACCURACY_BENCHMARK" in build
    assert "CaptureLogits" in runner
    assert "accuracy_capture" in runner
    assert "Get-ExpectedMaskEpoch" in runner
    assert "dense_mask_epoch" in runner
    assert "live_mask_epoch" in runner
    assert "B3_ACCURACY_MAGIC" in probe
    assert "B3_ACCURACY_SAMPLE_%02d_LOGIT_%02d" in probe

    layout = json.loads(
        (ROOT / "tools/repro/b2_dma_address_layout.json").read_text(encoding="utf-8")
    )
    region = next(item for item in layout["regions"] if item["name"] == "accuracy_benchmark_scratch")
    assert region == {
        "name": "accuracy_benchmark_scratch",
        "base": 0x0100A000,
        "capacity_bytes": 4096,
        "payload_bytes": 3612,
        "purpose": "B3-22.1e1 optional 64-sample logits capture",
        "dma_role": "cpu_only",
    }


def test_accuracy_capture_is_optional_and_preserves_speed_contract() -> None:
    runner = (ROOT / "boards/hellozynq/b2_sw/run_b3_speed_benchmark.ps1").read_text(encoding="utf-8")
    assert "[switch]$CaptureLogits" in runner
    assert "B3AccuracyBenchmark = $CaptureLogits" in runner
    assert "capture_logits" in runner
    assert "B3_ACCURACY_STATUS" in runner
    assert "accuracy_capture" in runner

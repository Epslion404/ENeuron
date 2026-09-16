"""B3-22.1 合同：无 UART 文本的 64 个不同输入请求到结果记录。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_speed_benchmark_sources_and_address_contract() -> None:
    packet = (ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").read_text(encoding="utf-8")
    build = (ROOT / "boards/hellozynq/b2_sw/run_b2_packet_sw_build.ps1").read_text(encoding="utf-8")
    runner = (ROOT / "boards/hellozynq/b2_sw/run_b3_speed_benchmark.ps1").read_text(encoding="utf-8")
    probe = (ROOT / "boards/hellozynq/b2_sw/probe_b3_speed_benchmark.tcl").read_text(encoding="utf-8")

    assert "B3_SPEED_BENCHMARK" in packet
    assert "SPEED_BENCH_BASE 0x01009000U" in packet
    assert "SPEED_BENCH_SAMPLES B3_BENCHMARK_SAMPLE_COUNT" in packet
    assert "B3_PRINT(...) ((void)0)" in packet
    assert "B3SpeedBenchmark" in build
    assert "B3_SPEED_BENCHMARK" in build
    assert "[int]$Samples = 64" in runner
    assert "B3BenchmarkManifest" in build
    assert "b3_multi_input_manifest.json" in runner
    assert "$buildParams = @{" in runner
    assert "& $buildScript @buildParams" in runner
    assert "$buildParams.B3Dense = $true" in runner
    assert "$buildParams.B3StaticMixed = $true" in runner
    assert "$buildParams.B3LiveEneuron = $true" in runner
    assert "packet_source_sha256" in runner
    assert "Packet source SHA-256 does not match" in runner
    assert "application_mode" in runner
    assert "B2_FPGA_PROGRAM_PASS" in runner
    assert "B2_ELF_DOWNLOAD_PASS" in runner
    assert "B2_CPU_RUN_PASS" in runner
    assert "XSCT programming failed with exit code" in runner
    assert "$modeSwitch" not in runner
    assert "run_b3_speed_benchmark.ps1" not in runner
    assert "probe_b3_speed_benchmark.tcl" in runner
    assert "Open-SerialPort" not in runner
    assert "SPEED_BENCH_MAGIC" not in probe
    assert "B3_SPEED_SAMPLE_" in probe
    assert "set sample_count [lindex $argv 0]" in probe
    assert "{$index < $sample_count}" in probe
    assert "mask_split_us" in packet
    assert "B3_SPEED_MASK_COMPUTE_US" in probe
    assert "B3_SPEED_MASK_SUBMIT_US" in probe
    assert "mask_compute_us = Get-U32" in runner
    assert "mask_submit_us = Get-U32" in runner

    layout = json.loads(
        (ROOT / "tools/repro/b2_dma_address_layout.json").read_text(encoding="utf-8")
    )
    region = next(item for item in layout["regions"] if item["name"] == "speed_benchmark_scratch")
    assert region == {
        "name": "speed_benchmark_scratch",
        "base": 0x01009000,
        "capacity_bytes": 24576,
        "payload_bytes": 23928,
        "purpose": "B3-22.1/22.2 no-UART timing, mask compute/submit split and identity record (up to 397 unique inputs)",
        "dma_role": "cpu_only",
    }


def test_live_benchmark_recomputes_mask_and_records_setup_costs() -> None:
    packet = (ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").read_text(encoding="utf-8")
    benchmark = packet[packet.index("static int run_speed_benchmark(void)"):packet.index("#endif\n\nint main(void)", packet.index("static int run_speed_benchmark(void)"))]

    assert "send_mask_for_epoch" in benchmark
    assert "compute_live_group4way_mask(sample_index);" in benchmark
    assert "speed_bench->setup_us" in benchmark
    assert "speed_bench->mask_us" in benchmark
    assert "speed_bench->mask_compute_us" in benchmark
    assert "speed_bench->mask_submit_us" in benchmark
    assert "XTime_GetTime(&mask_compute_stop);" in benchmark
    assert "speed_bench->fence_us" in benchmark
    assert "build_sample_frame(tx, sample_id, MODEL_ID, epoch, sample_index)" in packet
    assert "XTime_GetTime(&fence_start);" in benchmark
    assert "send_fence_and_check(active_epoch) != XST_SUCCESS" in benchmark
    assert "send_fence_and_check(0U) != XST_SUCCESS" in packet
    assert "active_epoch = SAMPLE_MASK_EPOCH" in benchmark
    assert "expected_epoch_word1" in packet
    assert "expected_epoch_word2" in packet
    assert "sample->total_us = xtime_delta_us(sample_start, sample_stop);" in benchmark


def test_live_benchmark_batch_update_contract() -> None:
    packet = (ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").read_text(encoding="utf-8")
    build = (ROOT / "boards/hellozynq/b2_sw/run_b2_packet_sw_build.ps1").read_text(encoding="utf-8")
    runner = (ROOT / "boards/hellozynq/b2_sw/run_b3_speed_benchmark.ps1").read_text(encoding="utf-8")

    assert "B3_LIVE_MASK_BATCH_K" in packet
    assert "B3_BENCHMARK_UNIQUE_INPUT_COUNT > 1U" in packet
    assert "B3LiveMaskBatchK" in build
    assert "LiveMaskBatchK" in runner
    assert "live_mask_batch_k" in runner
    assert "live_mask_update_count" in runner
    assert "multi-input live benchmark requires B3_LIVE_MASK_BATCH_K=1" in build
    assert "// fence 是每个样本的协议边界，不能与 mask 更新一起摊销。" in packet


def test_speed_benchmark_records_fail_stage_for_pre_sample_diagnostics() -> None:
    packet = (ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").read_text(encoding="utf-8")
    runner = (ROOT / "boards/hellozynq/b2_sw/run_b3_speed_benchmark.ps1").read_text(encoding="utf-8")
    probe = (ROOT / "boards/hellozynq/b2_sw/probe_b3_speed_benchmark.tcl").read_text(encoding="utf-8")
    layout = json.loads(
        (ROOT / "tools/repro/b2_dma_address_layout.json").read_text(encoding="utf-8")
    )

    assert "failure_stage" in packet
    assert "failure_sample_index" in packet
    assert "failure_check_mask" in packet
    assert "failure_response_words" in packet
    assert "B3_SPEED_FAILURE_CHECK_MASK" in probe
    assert "B3_SPEED_FAILURE_RESPONSE_WORDS" in probe
    assert "B3_SPEED_FAILURE_RESPONSE_SEQUENCE" in probe
    assert "failure_check_mask = Get-U32" in runner
    assert "failure_response_words = Get-U32" in runner
    assert "failure_response_sequence = Get-U32" in runner
    assert "B3_SPEED_FAILURE_STAGE" in probe
    assert "B3_SPEED_FAILURE_SAMPLE_INDEX" in probe
    assert "failure_stage = Get-U32" in runner
    assert "failure_sample_index = Get-U32" in runner
    region = next(item for item in layout["regions"] if item["name"] == "speed_benchmark_scratch")
    assert region["payload_bytes"] == 23928


def test_multi_input_identity_is_recorded_per_sample() -> None:
    packet = (ROOT / "boards/hellozynq/b2_sw/src/packet_main.c").read_text(encoding="utf-8")
    runner = (ROOT / "boards/hellozynq/b2_sw/run_b3_speed_benchmark.ps1").read_text(encoding="utf-8")
    probe = (ROOT / "boards/hellozynq/b2_sw/probe_b3_speed_benchmark.tcl").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "tools/repro/b3_multi_input_manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema"] == "eneuron_b3_multi_input_v1"
    assert manifest["sample_count"] == 64
    assert manifest["unique_input_count"] == 64
    assert "u32 mask_epoch;" in packet
    assert "u32 input_crc;" in packet
    assert "B3_SPEED_SAMPLE_%02d_MASK_EPOCH" in probe
    assert "B3_SPEED_SAMPLE_%02d_INPUT_CRC" in probe
    assert "mask_epoch = Get-U32" in runner
    assert "input_crc = Get-U32" in runner
    assert "input_manifest_sha256" in runner
    assert "unique_input_count" in runner

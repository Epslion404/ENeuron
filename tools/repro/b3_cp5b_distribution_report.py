#!/usr/bin/env python3
"""归档并汇总 CP5b 纯 PL 分布 replay 的正式成对证据。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
from pathlib import Path
from typing import Any


EXPECTED_INPUT_SAMPLES = 397
EXPECTED_WARMUP_SAMPLES = 1000
EXPECTED_MEASURED_SAMPLES = 10000
EXPECTED_GROUP_INSTANCES = 6_747_024
EXPECTED_FINAL_SAMPLE_INDEX = 74


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def repo_path(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def archive_file(repo_root: Path, source: Path, destination: Path) -> tuple[str, str]:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return repo_path(repo_root, destination), sha256(destination)


def validate_run(data: dict[str, Any], expected_mode: str) -> None:
    expected = {
        "schema": "eneuron_b3_cp5b_pl_distribution_replay_v1",
        "status": "CP5B_DISTRIBUTION_PASS",
        "mode": expected_mode,
        "formal_evidence": True,
        "input_samples": EXPECTED_INPUT_SAMPLES,
        "warmup_samples": EXPECTED_WARMUP_SAMPLES,
        "measured_samples": EXPECTED_MEASURED_SAMPLES,
        "observed_group_instances": EXPECTED_GROUP_INSTANCES,
        "final_sample_index": EXPECTED_FINAL_SAMPLE_INDEX,
        "protocol_error_count": 0,
        "result_frame_pass": True,
    }
    for key, value in expected.items():
        if data.get(key) != value:
            raise ValueError(f"{expected_mode} run field mismatch: {key}={data.get(key)!r}, expected={value!r}")
    if data.get("expected_group_instances") != EXPECTED_GROUP_INSTANCES:
        raise ValueError(f"{expected_mode} expected group ledger mismatch")


def timing_from_manifest(manifest: dict[str, Any]) -> dict[str, float | int]:
    signoff = manifest["signoff"]
    if signoff["B2_SIGNOFF_PASS"] != "1":
        raise ValueError("hardware signoff did not pass")
    if int(signoff["B2_NPU_DSP48E1_COUNT"]) != 4:
        raise ValueError("hardware DSP48E1 contract did not pass")
    return {
        "wns_ns": float(signoff["B2_WNS_NS"]),
        "tns_ns": float(signoff["B2_TNS_NS"]),
        "whs_ns": float(signoff["B2_WHS_NS"]),
        "ths_ns": float(signoff["B2_THS_NS"]),
        "route_errors": int(signoff["B2_ROUTE_ERRORS"]),
        "drc_hard_errors": int(signoff["B2_DRC_HARD_ERRORS"]),
        "dsp48e1": int(signoff["B2_NPU_DSP48E1_COUNT"]),
    }


def build_mode_summary(
    *,
    repo_root: Path,
    archive_root: Path,
    archive_name: str,
    expected_mode: str,
    hardware_dir: Path,
    packet_dir: Path,
    run_paths: list[Path],
) -> dict[str, Any]:
    if len(run_paths) != 5:
        raise ValueError(f"{expected_mode} requires exactly five rounds")

    mode_archive = archive_root / archive_name
    hardware_manifest_source = hardware_dir / "build_manifest.json"
    signoff_source = hardware_dir / "signoff_summary.txt"
    packet_manifest_source = packet_dir / "packet_build_manifest.json"
    hardware_manifest = load_json(hardware_manifest_source)
    packet_manifest = load_json(packet_manifest_source)

    hardware_manifest_path, hardware_manifest_sha = archive_file(
        repo_root, hardware_manifest_source, mode_archive / "hardware_build_manifest.json"
    )
    signoff_path, signoff_sha = archive_file(
        repo_root, signoff_source, mode_archive / "signoff_summary.txt"
    )
    packet_manifest_path, packet_manifest_sha = archive_file(
        repo_root, packet_manifest_source, mode_archive / "packet_build_manifest.json"
    )

    rounds: list[dict[str, Any]] = []
    for index, run_source in enumerate(run_paths, start=1):
        data = load_json(run_source)
        validate_run(data, expected_mode)
        if data["hardware_manifest_sha256"] != sha256(hardware_manifest_source):
            raise ValueError(f"{expected_mode} round {index} hardware manifest hash mismatch")
        # runner 会在每轮构建 packet ELF，manifest 含生成时间，因此每轮 hash
        # 可能不同；当前构建目录只保留最后一份 manifest。逐轮 hash 仍保留在
        # raw run 中，不能把最后一份文件错误宣称为所有轮次的原件。

        round_archive = mode_archive / f"round_{index}"
        run_path, run_sha = archive_file(
            repo_root, run_source, round_archive / "b3_pl_distribution_replay_benchmark.json"
        )
        program_source = run_source.parent / "program.log"
        probe_source = run_source.parent / "probe_001.log"
        program_path, program_sha = archive_file(repo_root, program_source, round_archive / "program.log")
        probe_path, probe_sha = archive_file(repo_root, probe_source, round_archive / "probe.log")
        if data["program_log_sha256"] != program_sha:
            raise ValueError(f"{expected_mode} round {index} program log hash mismatch")

        rounds.append(
            {
                "round": index,
                "run": run_path,
                "run_sha256": run_sha,
                "program_log": program_path,
                "program_log_sha256": program_sha,
                "probe_log": probe_path,
                "probe_log_sha256": probe_sha,
                "packet_manifest_sha256_recorded": data["packet_manifest_sha256"],
                "formal_evidence": data["formal_evidence"],
                "input_samples": data["input_samples"],
                "warmup_samples": data["warmup_samples"],
                "measured_samples": data["measured_samples"],
                "measured_cycles": data["measured_cycles"],
                "cycles_per_sample": data["cycles_per_sample"],
                "samples_per_second": data["samples_per_second"],
                "observed_group_instances": data["observed_group_instances"],
                "execute_groups_total": data["execute_groups_total"],
                "skip_groups_total": data["skip_groups_total"],
                "skip_rate": data["skip_rate"],
                "final_sample_index": data["final_sample_index"],
                "result_crc": data["result_crc"],
                "result_frame_pass": data["result_frame_pass"],
                "protocol_error_count": data["protocol_error_count"],
            }
        )

    cycles = [float(item["cycles_per_sample"]) for item in rounds]
    throughput = [float(item["samples_per_second"]) for item in rounds]
    return {
        "hardware_manifest": hardware_manifest_path,
        "hardware_manifest_sha256": hardware_manifest_sha,
        "signoff_summary": signoff_path,
        "signoff_summary_sha256": signoff_sha,
        "packet_manifest": packet_manifest_path,
        "packet_manifest_sha256": packet_manifest_sha,
        "hardware_git_head": hardware_manifest["git_head"],
        "packet_git_head": packet_manifest["git_head"],
        "bitstream_sha256": hardware_manifest["bitstream_sha256"],
        "xsa_sha256": hardware_manifest["xsa_sha256"],
        "timing": timing_from_manifest(hardware_manifest),
        "rounds": rounds,
        "cycles_per_sample": {
            "minimum": min(cycles),
            "median": statistics.median(cycles),
            "maximum": max(cycles),
        },
        "samples_per_second": {
            "minimum": min(throughput),
            "median": statistics.median(throughput),
            "maximum": max(throughput),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--date", required=True)
    parser.add_argument("--dense-hardware-dir", type=Path, required=True)
    parser.add_argument("--lossless-hardware-dir", type=Path, required=True)
    parser.add_argument("--dense-packet-dir", type=Path, required=True)
    parser.add_argument("--lossless-packet-dir", type=Path, required=True)
    parser.add_argument("--dense-run", type=Path, action="append", required=True)
    parser.add_argument("--lossless-run", type=Path, action="append", required=True)
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=Path("artifacts/logs/b3_qat_cp5b_pl_distribution_20260916"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/results/b3_qat_cp5b_pl_distribution_board_pair.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    archive_root = (repo_root / args.archive_root).resolve()
    output = (repo_root / args.output).resolve()

    dense = build_mode_summary(
        repo_root=repo_root,
        archive_root=archive_root,
        archive_name="dense",
        expected_mode="dense",
        hardware_dir=(repo_root / args.dense_hardware_dir).resolve(),
        packet_dir=(repo_root / args.dense_packet_dir).resolve(),
        run_paths=[(repo_root / path).resolve() for path in args.dense_run],
    )
    lossless = build_mode_summary(
        repo_root=repo_root,
        archive_root=archive_root,
        archive_name="lossless",
        expected_mode="lossless_zero_group_skip",
        hardware_dir=(repo_root / args.lossless_hardware_dir).resolve(),
        packet_dir=(repo_root / args.lossless_packet_dir).resolve(),
        run_paths=[(repo_root / path).resolve() for path in args.lossless_run],
    )

    dense_rounds = dense["rounds"]
    lossless_rounds = lossless["rounds"]
    throughput_speedups = [
        float(lossless_round["samples_per_second"]) / float(dense_round["samples_per_second"])
        for dense_round, lossless_round in zip(dense_rounds, lossless_rounds, strict=True)
    ]
    cycle_speedups = [
        float(dense_round["cycles_per_sample"]) / float(lossless_round["cycles_per_sample"])
        for dense_round, lossless_round in zip(dense_rounds, lossless_rounds, strict=True)
    ]
    result_crcs = {round_data["result_crc"] for round_data in dense_rounds + lossless_rounds}
    all_frames_pass = all(round_data["result_frame_pass"] for round_data in dense_rounds + lossless_rounds)
    protocol_errors = sum(round_data["protocol_error_count"] for round_data in dense_rounds + lossless_rounds)
    speed_gate_pass = min(throughput_speedups) > 1.0 and len(result_crcs) == 1 and all_frames_pass and protocol_errors == 0
    if not speed_gate_pass:
        raise ValueError("CP5b speed gate did not pass")

    first_run = load_json(args.dense_run[0])
    result = {
        "schema": "eneuron_b3_qat_cp5b_pl_distribution_board_pair_v1",
        "status": "CP5B_FORMAL_PASS",
        "phase": "B3-PAPER-CP5B",
        "date": args.date,
        "software_git_head": first_run["git_head"],
        "target_part": first_run["target_part"],
        "clock_hz": first_run["clock_hz"],
        "qat_manifest": "tools/repro/b3_qat_model_manifest.json",
        "qat_manifest_sha256": first_run["qat_manifest_sha256"],
        "input_samples": EXPECTED_INPUT_SAMPLES,
        "warmup_samples": EXPECTED_WARMUP_SAMPLES,
        "measured_samples": EXPECTED_MEASURED_SAMPLES,
        "round_count": 5,
        "dense": dense,
        "lossless_zero_group_skip": lossless,
        "paired_checks": {
            "throughput_speedup_by_round": throughput_speedups,
            "cycle_speedup_by_round": cycle_speedups,
            "minimum_throughput_speedup": min(throughput_speedups),
            "median_throughput_speedup": statistics.median(throughput_speedups),
            "maximum_throughput_speedup": max(throughput_speedups),
            "latency_reduction_percent": (
                1.0
                - float(lossless["cycles_per_sample"]["median"])
                / float(dense["cycles_per_sample"]["median"])
            )
            * 100.0,
            "same_result_crc": len(result_crcs) == 1,
            "result_crc": result_crcs.pop(),
            "all_result_frames_pass": all_frames_pass,
            "protocol_error_count": protocol_errors,
            "speed_gate": "PASS",
        },
        "boundary": (
            "CP5b formal 397-sample PL-internal steady-state distribution replay. "
            "It includes 1000 warmup and 10000 measured samples in each of five alternating dense/lossless rounds, "
            "and closes the pure-PL B3-SPEED-GATE for LOSSLESS_ZERO_GROUP_SKIP. "
            "It is not a packet end-to-end PS/DMA throughput result and does not close the power or overall goal gates."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"B3_CP5B_REPORT={output}")
    print(f"B3_CP5B_SPEEDUP={result['paired_checks']['median_throughput_speedup']:.9f}")
    print("B3_SPEED_GATE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

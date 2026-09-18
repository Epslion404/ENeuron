"""CP8 功耗 replay RED 合同测试。

本文件只描述 CP8 四态功耗测量所需的未来生产接口，不实现生产代码。
当前分支 `codex/b3-cp8-power-prep` 下预期 RED：生产文件尚未包含这些 token。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent

SHIM = ROOT / "b3_pl_distribution_replay_shim.sv"
STATUS_PROBE = ROOT / "boards/hellozynq/b2_hw/b2_npu_status_probe.v"
HW_BUILD = ROOT / "boards/hellozynq/b2_hw/build_b2.tcl"
HW_RUNNER = ROOT / "boards/hellozynq/b2_hw/run_b2_build.ps1"
WRAPPER = ROOT / "npu_zynq7020_t1_wrapper.sv"
SW_BUILD = ROOT / "boards/hellozynq/b2_sw/run_b2_packet_sw_build.ps1"
PACKET = ROOT / "boards/hellozynq/b2_sw/src/packet_main.c"
CP5B_RUNNER = ROOT / "boards/hellozynq/b2_sw/run_b3_pl_distribution_replay_benchmark.ps1"
CP8_RUNNER = ROOT / "boards/hellozynq/b2_sw/run_b3_cp8_power_state.ps1"
CP8_PROBE = ROOT / "boards/hellozynq/b2_sw/probe_b3_cp8_power_state.tcl"
CP8_TB = ROOT / "tb_b3_cp8_power_replay_shim.sv"

IVERILOG_CANDIDATES = (
    "/mnt/c/msys64/ucrt64/bin/iverilog.exe",
    "C:/msys64/ucrt64/bin/iverilog.exe",
    "/usr/bin/iverilog",
    "/usr/local/bin/iverilog",
)
VVP_CANDIDATES = (
    "/mnt/c/msys64/ucrt64/bin/vvp.exe",
    "C:/msys64/ucrt64/bin/vvp.exe",
    "/usr/bin/vvp",
    "/usr/local/bin/vvp",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tool(candidates: tuple[str, ...], fallback: str) -> Path | None:
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return path
    found = shutil.which(fallback)
    return Path(found) if found else None


def _output_arg(tool: Path, name: str) -> str:
    if tool.suffix.lower() == ".exe":
        return f"C:/Windows/Temp/{name}"
    return str(Path(tempfile.gettempdir()) / name)


def _cleanup(tool: Path, name: str) -> None:
    if tool.suffix.lower() == ".exe":
        for base in ("/mnt/c/Windows/Temp", "C:/Windows/Temp"):
            try:
                (Path(base) / name).unlink()
            except OSError:
                pass
    else:
        try:
            (Path(tempfile.gettempdir()) / name).unlink()
        except OSError:
            pass


def test_shim_declares_continuous_replay_parameter() -> None:
    shim = _read(SHIM)
    assert "CONTINUOUS_REPLAY" in shim, "shim 缺少 CONTINUOUS_REPLAY 参数"
    assert re.search(r"CONTINUOUS_REPLAY\s*=\s*0", shim), "CONTINUOUS_REPLAY 默认值必须为 0"
    assert shim.count("CONTINUOUS_REPLAY") >= 2, "CONTINUOUS_REPLAY 必须被实际使用"
    assert "STATUS_MEASURE" in shim
    assert "STATUS_PASS" in shim
    assert "STATE_DONE" in shim


def test_cp5b_finite_semantics_are_retained() -> None:
    shim = _read(SHIM)
    assert "MEASURE_SAMPLES = 10000" in shim, "CP5b 默认有限 10000 语义被破坏"
    runner = _read(CP5B_RUNNER)
    assert "B3_PL_DISTRIBUTION_REPLAY_COMPLETED=10000" in runner, "CP5b runner 不再要求 10000"
    assert "CONTINUOUS" not in runner.upper(), "CP5b 正式 run 不得被改成 continuous"


def test_status_probe_declares_cp8_control_register() -> None:
    probe = _read(STATUS_PROBE)
    assert "CP8_CONTROL_ADDR" in probe, "状态块缺少 CP8_CONTROL_ADDR"
    assert "12'h074" in probe, "CP8 控制寄存器地址必须为 12'h074"
    assert probe.count("CP8_CONTROL") >= 3, "CP8 控制寄存器必须在读/写路径被引用"


def test_build_modes_define_cp8_power_replay() -> None:
    build = _read(HW_BUILD)
    runner = _read(HW_RUNNER)
    wrapper = _read(WRAPPER)
    assert "dense_pl_power_replay" in build, "缺少 dense CP8 power replay 模式"
    assert "lossless_zero_group_skip_pl_power_replay" in build, "缺少 lossless CP8 power replay 模式"
    assert "B3_CP8_POWER_MEASUREMENT" in build, "缺少 B3_CP8_POWER_MEASUREMENT define"
    assert "B3_PL_REPLAY_CONTINUOUS=1" in build, "缺少 B3_PL_REPLAY_CONTINUOUS=1"
    assert "B3_PL_REPLAY_INPUT_SAMPLES=397" in build
    assert "B3_PL_REPLAY_WARMUP_SAMPLES=1000" in build
    assert "B3_PL_REPLAY_MEASURE_SAMPLES=10000" in build, "CP5b 有限模式 define 被移除"
    for token in (
        "dense_pl_power_replay",
        "lossless_zero_group_skip_pl_power_replay",
        "B3_PL_REPLAY_CONTINUOUS=1",
    ):
        assert token in runner, f"hardware runner 缺少 {token}"
    assert "B3_PL_REPLAY_CONTINUOUS" in wrapper
    assert ".CONTINUOUS_REPLAY(`B3_PL_REPLAY_CONTINUOUS)" in wrapper


def test_packet_build_adds_exclusive_cp8_power_measurement_mode() -> None:
    sw = _read(SW_BUILD)
    packet = _read(PACKET)
    assert "B3Cp8PowerMeasurement" in sw, "packet 构建缺少 B3Cp8PowerMeasurement 开关"
    assert sw.count("B3Cp8PowerMeasurement") >= 2, "B3Cp8PowerMeasurement 必须参与互斥判定"
    assert "B3_CP8_POWER_MEASUREMENT" in sw
    assert "B3_CP8_POWER_MEASUREMENT" in packet, "固件缺少 B3_CP8_POWER_MEASUREMENT 模式"
    assert "0x74" in packet, "固件未通过 0x74 控制 CP8 READY/START/RUNNING"
    for token in (
        "CP8_CONTROL_READY",
        "CP8_CONTROL_START",
        "CP8_CONTROL_RUNNING",
        "run_cp8_power_control_loop",
        "start_distribution_replay_capture",
        "wait_cp8_capture_complete",
        "cp8_capture_timeout",
    ):
        assert token in packet, f"固件缺少 CP8 控制合同: {token}"
    for token in (
        "requires the canonical QAT manifest",
        "cannot be combined with speed or accuracy benchmark modes",
        "requires exactly 397 QAT samples",
        "cp8_power_samples",
    ):
        assert token in sw, f"packet 构建缺少 CP8 守卫: {token}"


def test_cp8_runner_and_probe_are_separate_and_watch_registers() -> None:
    assert CP8_RUNNER.is_file(), f"缺少 CP8 runner: {CP8_RUNNER}"
    assert CP8_PROBE.is_file(), f"缺少 CP8 probe: {CP8_PROBE}"
    runner = _read(CP8_RUNNER)
    probe = _read(CP8_PROBE)
    for token in ("idle", "full", "0x74", "0x64", "0x70", "0x60"):
        assert token in runner, f"CP8 runner 缺少 {token}"
    for token in ("0x74", "0x64", "0x70", "0x60"):
        assert token in probe, f"CP8 probe 缺少 {token}"
    assert "b3_qat_cp5b_pl_distribution_board_pair" not in runner, "CP8 不得复用 CP5b 正式结果路径"
    assert '"cp8_${Mode}_power"' in runner, "idle/full 必须复用同一 BuildTag 与 ELF 身份"
    assert '"cp8_${State}_${Mode}_power"' not in runner
    assert "catch {disconnect}" in probe, "probe 失败时也必须释放 JTAG 连接"


def test_cp8_runner_limits_source_hash_fallback_to_non_synth_build_runner() -> None:
    runner = _read(CP8_RUNNER)
    assert "boards/hellozynq/b2_hw/run_b2_build.ps1" in runner
    assert "git-blob:" in runner, "回退必须显式记录为 Git blob 证明"
    assert "rev-parse" in runner, "必须读取 manifest git_head 对应 blob"
    assert "hash-object" in runner, "必须对当前工作树文件应用 Git clean filter"
    assert "hardware_source_canonical_fallbacks" in runner, "状态 JSON 必须记录回退"
    assert runner.count("hardwareSourceCanonicalFallbacks") >= 3


def test_cp8_continuous_replay_shim_behavior() -> None:
    iverilog = _tool(IVERILOG_CANDIDATES, "iverilog")
    vvp = _tool(VVP_CANDIDATES, "vvp")
    if iverilog is None or vvp is None:
        pytest.skip("Icarus Verilog unavailable")

    output = _output_arg(iverilog, "tb_b3_cp8_power_replay_shim.vvp")
    try:
        compiled = subprocess.run(
            [
                str(iverilog), "-g2012", "-s", "tb_b3_cp8_power_replay_shim",
                "-o", output, SHIM.name, CP8_TB.name,
            ],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        assert compiled.returncode == 0, compiled.stdout + compiled.stderr
        ran = subprocess.run(
            [str(vvp), output], cwd=ROOT, text=True, capture_output=True, check=False,
        )
    finally:
        _cleanup(iverilog, "tb_b3_cp8_power_replay_shim.vvp")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "B3_CP8_POWER_REPLAY_SHIM_PASS" in ran.stdout, ran.stdout

"""一键复核 ENeuron 的数字学习基石、4->2->2 Tile 与 Host Bridge 工程证据。"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import subprocess
import sys
import unittest
from pathlib import Path

from m3_acceptance import M3AcceptanceSummary, run_m3_acceptance
from rtl_tile_cosim import run as run_tile_cosim


LOGGER = logging.getLogger("verify_goal")
ROOT = Path(__file__).resolve().parent
TILE_REPORTS = ROOT / "vivado_tile_reports"
XPM_REPORTS = ROOT / "vivado_xpm_wrapper_sim"
SYSTEM_REPORTS = ROOT / "vivado_host_bridge_reports"
MINIMUM_TEST_COUNT = 169
TILE_LUT_BUDGET = 3200
TILE_FF_BUDGET = 2000


def require_match(pattern: str, text: str, description: str) -> re.Match[str]:
    """读取一个必须存在的报告字段，缺失时立即使审计失败。"""
    match = re.search(pattern, text, flags=re.MULTILINE)
    if match is None:
        raise AssertionError(f"报告缺少字段: {description}")
    return match


def run_command(command: list[str], description: str) -> None:
    """执行外部验证命令，并将退出码作为硬门槛。"""
    LOGGER.info("开始: %s", description)
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        raise AssertionError(f"{description} 失败，退出码 {result.returncode}")
    LOGGER.info("通过: %s", description)


def powershell_script(script_name: str) -> list[str]:
    """构造不依赖本机执行策略的 PowerShell 脚本命令。"""
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ROOT / script_name),
    ]


def read_key_values(path: Path) -> dict[str, str]:
    """严格解析每行一个 KEY=VALUE 的 Vivado 签核摘要。"""
    values: dict[str, str] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        if "=" not in line:
            raise AssertionError(f"签核摘要第 {line_number} 行格式错误: {line!r}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise AssertionError(f"签核摘要第 {line_number} 行含空字段")
        if key in values:
            raise AssertionError(f"签核摘要含重复字段: {key}")
        values[key] = value
    return values


def read_xpm_summary(path: Path) -> dict[str, str]:
    """解析固定 PASS marker 加严格 KEY=VALUE 的 XPM 签核摘要。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    marker = "VIVADO_XPM_WRAPPER_PASS"
    if not lines or lines[0] != marker:
        actual = lines[0] if lines else "<empty>"
        raise AssertionError(f"XPM 摘要首行 marker 错误: {actual!r}, expected={marker}")

    values: dict[str, str] = {}
    for line_number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        if "=" not in line:
            raise AssertionError(f"XPM 摘要第 {line_number} 行格式错误: {line!r}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise AssertionError(f"XPM 摘要第 {line_number} 行含空字段")
        if key in values:
            raise AssertionError(f"XPM 摘要含重复字段: {key}")
        values[key] = value
    return values


def read_system_cdc_summary(path: Path) -> dict[str, str]:
    """解析固定 marker 加严格 KEY=VALUE 的系统 CDC 分类摘要。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    marker = "CDC_CLASSIFICATION"
    if not lines or lines[0] != marker:
        actual = lines[0] if lines else "<empty>"
        raise AssertionError(
            f"系统 CDC 摘要首行 marker 错误: {actual!r}, expected={marker}"
        )

    values: dict[str, str] = {}
    for line_number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        if "=" not in line:
            raise AssertionError(
                f"系统 CDC 摘要第 {line_number} 行格式错误: {line!r}"
            )
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise AssertionError(f"系统 CDC 摘要第 {line_number} 行含空字段")
        if key in values:
            raise AssertionError(f"系统 CDC 摘要含重复字段: {key}")
        values[key] = value
    return values


def require_key(values: dict[str, str], key: str) -> str:
    """读取签核摘要中的必需字段。"""
    if key not in values:
        raise AssertionError(f"签核摘要缺少字段: {key}")
    return values[key]


def require_fresh_reports(
    report_root: Path,
    report_names: tuple[str, ...],
    source_names: tuple[str, ...],
) -> None:
    """拒绝缺失或早于相关 RTL/测试脚本的历史报告。"""
    missing = [name for name in report_names if not (report_root / name).is_file()]
    if missing:
        raise AssertionError(f"缺少报告: {', '.join(missing)}")

    source_paths = tuple(ROOT / name for name in source_names)
    missing_sources = [str(path) for path in source_paths if not path.is_file()]
    if missing_sources:
        raise AssertionError(f"缺少报告依赖源文件: {', '.join(missing_sources)}")

    latest_source_time = max(path.stat().st_mtime for path in source_paths)
    stale = [
        name
        for name in report_names
        if (report_root / name).stat().st_mtime <= latest_source_time
    ]
    if stale:
        raise AssertionError(
            "报告早于相关源文件，请使用 --rerun-vivado 重建: " + ", ".join(stale)
        )


def report_rule_rows(text: str, description: str) -> list[tuple[str, str, int]]:
    """解析 Vivado DRC/methodology 汇总表中的规则、严重度和数量。"""
    rows = [
        (rule.strip(), severity, int(count))
        for rule, severity, count in re.findall(
            r"^\|\s*([^|]+?)\s*\|\s*(Error|Critical Warning|Warning)\s*\|"
            r".*\|\s*(\d+)\s*\|$",
            text,
            re.MULTILINE,
        )
    ]
    if not rows:
        raise AssertionError(f"无法解析 {description} 规则汇总")
    return rows


def require_summary_matches(
    summary: dict[str, str], key: str, actual: int | float | str
) -> None:
    """要求机器摘要字段与原始报告解析值精确一致。"""
    raw = require_key(summary, key)
    if isinstance(actual, float):
        try:
            matches = abs(float(raw) - actual) <= 1e-9
        except ValueError as error:
            raise AssertionError(f"Tile 摘要 {key} 不是数值: {raw}") from error
    elif isinstance(actual, int):
        try:
            matches = int(raw) == actual
        except ValueError as error:
            raise AssertionError(f"Tile 摘要 {key} 不是整数: {raw}") from error
    else:
        matches = raw == actual
    if not matches:
        raise AssertionError(f"Tile 摘要与原始报告不一致: {key}={raw}, actual={actual}")


def sha256_file(path: Path) -> str:
    """返回文件内容的大写 SHA-256，用于跨阶段证据绑定。"""
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_t0_signoff_summary() -> None:
    """生成供后续 G4 阶段消费的 T0 Tile 工程基线摘要。"""
    tile_summary_path = TILE_REPORTS / "signoff_summary.txt"
    tile_summary = read_key_values(tile_summary_path)
    if require_key(tile_summary, "RESULT") != "PASS":
        raise AssertionError("Tile 摘要未通过，不能生成 T0 交接摘要")

    lut = require_key(tile_summary, "LUT")
    ff = require_key(tile_summary, "FF")
    wns = require_key(tile_summary, "WNS_NS")
    whs = require_key(tile_summary, "WHS_NS")
    document_checks = {
        "README.md": (lut, ff, wns, whs),
        "docs/verification/goal_audit.md": (lut, ff, wns),
        "docs/design/recommended_design.md": (lut, ff, wns),
    }
    for name, required_values in document_checks.items():
        path = ROOT / name
        if not path.is_file():
            raise AssertionError(f"缺少 T0 文档: {name}")
        text = path.read_text(encoding="utf-8")
        missing = [value for value in required_values if value not in text]
        if missing:
            raise AssertionError(f"T0 文档数值不一致: {name}, missing={missing}")

    bound_files = {
        "ENGINE_RTL_SHA256": ROOT / "digital_lif_engine.sv",
        "TILE_RTL_SHA256": ROOT / "digital_snn_tile_4x2x2.sv",
        "TILE_TCL_SHA256": ROOT / "vivado_tile_synth.tcl",
        "TILE_RUNNER_SHA256": ROOT / "run_vivado_tile_synth.ps1",
        "VERIFY_GOAL_SHA256": ROOT / "verify_goal.py",
    }
    missing_sources = [str(path) for path in bound_files.values() if not path.is_file()]
    if missing_sources:
        raise AssertionError(f"缺少 T0 哈希依赖: {', '.join(missing_sources)}")

    lines = [
        "RESULT=PASS",
        "SCHEMA=T0_TILE_SIGNOFF_V1",
        "TILE_RESULT=PASS",
        f"TILE_SUMMARY_SHA256={sha256_file(tile_summary_path)}",
    ]
    lines.extend(f"{key}={sha256_file(path)}" for key, path in bound_files.items())
    lines.append("DOCUMENT_VALUES_MATCH=1")
    (ROOT / "t0_signoff_summary.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    LOGGER.info("已生成 T0 交接摘要: %s", ROOT / "t0_signoff_summary.txt")


def verify_software() -> None:
    """运行回归、两层有限 BMC 和显式 Tile 随机事务压力。"""
    suite = unittest.defaultTestLoader.discover(str(ROOT), pattern="test_*.py")
    test_count = suite.countTestCases()
    if test_count < MINIMUM_TEST_COUNT:
        raise AssertionError(
            f"回归数量下降: discovered={test_count}, minimum={MINIMUM_TEST_COUNT}"
        )
    LOGGER.info("发现 %d 项 unittest", test_count)

    run_command(
        [sys.executable, "-m", "compileall", "-q", "."],
        "Python compileall",
    )
    run_command(
        [sys.executable, "-m", "unittest", "discover", "-v"],
        "完整 Python/Icarus 回归",
    )
    run_command(
        powershell_script("run_formal_tile.ps1"),
        "Yosys 24 拍真实四核 Tile 协议 BMC",
    )
    run_command(
        powershell_script("run_formal_host_bridge_controller.ps1"),
        "Yosys 20 拍 Host Bridge controller BMC 与 6 类 witness",
    )

    LOGGER.info("开始: Tile 20 seeds x 500 事务压力测试")
    for seed in range(20):
        run_tile_cosim(seed=seed, transaction_count=500)
    LOGGER.info("通过: Tile 共 10000 个混合事务")


def verify_m3() -> M3AcceptanceSummary:
    """运行真实双时钟 M3 闭环，并写出机器可读签核摘要。"""

    summary = run_m3_acceptance()
    final_weights = ";".join(
        ",".join(str(value) for value in neuron)
        for neuron in summary.final_weights
    )
    lines = (
        "RESULT=PASS",
        "SCHEMA=M3_RTL_CLOSURE_V1",
        f"COMMAND_COUNT={summary.command_count}",
        f"TRAINING_START={summary.training_start}",
        f"COMMAND_SHA256={summary.command_sha256}",
        f"LEDGER_SHA256={summary.ledger_sha256}",
        f"LEDGER_CHAIN_TAIL={summary.ledger_chain_tail}",
        f"MOD_COMMIT_COUNT={summary.mod_commit_count}",
        f"TRAINING_WEIGHT_WRITE_COUNT={summary.weight_write_count}",
        f"NOISY_ACCURACY={summary.noisy_correct}/{summary.noisy_total}",
        f"FINAL_WEIGHTS={final_weights}",
    )
    path = ROOT / "m3_signoff_summary.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    LOGGER.info("M3 签核摘要已写入: %s", path)
    return summary


def verify_tile_reports() -> None:
    """审计独立四核 Tile 的 routed 时序、路由、规则、资源和功耗。"""
    report_names = (
        "signoff_summary.txt",
        "timing_impl.rpt",
        "utilization_impl.rpt",
        "route_status_impl.rpt",
        "drc_impl.rpt",
        "methodology_impl.rpt",
        "power_impl.rpt",
        "digital_snn_tile_4x2x2_impl.dcp",
        "vivado_run.log",
    )
    require_fresh_reports(
        TILE_REPORTS,
        report_names,
        (
            "digital_lif_engine.sv",
            "digital_snn_tile_4x2x2.sv",
            "vivado_tile_synth.tcl",
            "run_vivado_tile_synth.ps1",
        ),
    )

    summary = read_key_values(TILE_REPORTS / "signoff_summary.txt")
    expected = {
        "RESULT": "PASS",
        "VIVADO_VERSION": "2024.1",
        "PART": "xc7a35tcpg236-1",
        "TOP": "digital_snn_tile_4x2x2",
        "MODE": "OUT_OF_CONTEXT",
        "CLOCK_MHZ": "100.000",
    }
    for key, expected_value in expected.items():
        actual = require_key(summary, key)
        if actual != expected_value:
            raise AssertionError(
                f"Tile 摘要 {key}={actual}, expected={expected_value}"
            )

    timing = (TILE_REPORTS / "timing_impl.rpt").read_text(encoding="utf-8")
    timing_row = require_match(
        r"^\s*([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+(\d+)\s+(\d+)\s+"
        r"([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+(\d+)\s+(\d+)(?:\s|$)",
        timing,
        "Tile Design Timing Summary",
    )
    wns, tns, setup_failures, _setup_endpoints, whs, ths, hold_failures, _ = (
        float(timing_row.group(1)),
        float(timing_row.group(2)),
        int(timing_row.group(3)),
        int(timing_row.group(4)),
        float(timing_row.group(5)),
        float(timing_row.group(6)),
        int(timing_row.group(7)),
        int(timing_row.group(8)),
    )
    explicit_setup = re.search(r"Setup\s*:\s*(\d+)\s+Failing Endpoints", timing)
    explicit_hold = re.search(r"Hold\s*:\s*(\d+)\s+Failing Endpoints", timing)
    if explicit_setup is not None and int(explicit_setup.group(1)) != 0:
        raise AssertionError("Tile 时序 Setup failing endpoints 非零")
    if explicit_hold is not None and int(explicit_hold.group(1)) != 0:
        raise AssertionError("Tile 时序 Hold failing endpoints 非零")
    if wns < 0.0 or whs < 0.0:
        raise AssertionError(f"Tile 时序未收敛: WNS={wns}, WHS={whs}")
    if tns != 0.0 or ths != 0.0 or setup_failures != 0 or hold_failures != 0:
        raise AssertionError(
            "Tile 时序总违例非零: "
            f"TNS={tns}, THS={ths}, setup={setup_failures}, hold={hold_failures}"
        )
    if "All user specified timing constraints are met." not in timing:
        raise AssertionError("Vivado 未确认 Tile 的全部已指定时序约束满足")

    route = (TILE_REPORTS / "route_status_impl.rpt").read_text(encoding="utf-8")
    fully_routed = int(
        require_match(
            r"# of fully routed nets\.*\s*:\s*(\d+)",
            route,
            "Tile fully routed nets",
        ).group(1)
    )
    route_errors = int(
        require_match(
            r"# of nets with routing errors\.*\s*:\s*(\d+)",
            route,
            "Tile route errors",
        ).group(1)
    )
    if fully_routed == 0 or route_errors != 0:
        raise AssertionError(
            f"Tile 路由状态不完整: routed={fully_routed}, errors={route_errors}"
        )

    drc_rows = report_rule_rows(
        (TILE_REPORTS / "drc_impl.rpt").read_text(encoding="utf-8"),
        "Tile DRC",
    )
    methodology_rows = report_rule_rows(
        (TILE_REPORTS / "methodology_impl.rpt").read_text(encoding="utf-8"),
        "Tile methodology",
    )
    if drc_rows != [("CFGBVS-1", "Warning", 1)]:
        raise AssertionError(f"Tile DRC 白名单发生变化: {drc_rows}")
    if methodology_rows != [("TIMING-18", "Warning", 180)]:
        raise AssertionError(f"Tile methodology 白名单发生变化: {methodology_rows}")

    utilization = (TILE_REPORTS / "utilization_impl.rpt").read_text(
        encoding="utf-8"
    )
    resource_patterns = {
        "LUT": r"\| Slice LUTs\s*\|\s*(\d+)",
        "FF": r"\| Slice Registers\s*\|\s*(\d+)",
        "BRAM36": r"\|\s*RAMB36/FIFO\*\s*\|\s*(\d+)",
        "BRAM18": r"\|\s*RAMB18\s*\|\s*(\d+)",
        "DSP": r"\| DSPs\s*\|\s*(\d+)",
    }
    resources = {
        key: int(require_match(pattern, utilization, f"Tile {key}").group(1))
        for key, pattern in resource_patterns.items()
    }
    if resources["LUT"] > TILE_LUT_BUDGET or resources["FF"] > TILE_FF_BUDGET:
        raise AssertionError(
            "Tile 资源超预算: "
            f"LUT={resources['LUT']}/{TILE_LUT_BUDGET}, "
            f"FF={resources['FF']}/{TILE_FF_BUDGET}"
        )
    if any(resources[key] != 0 for key in ("BRAM36", "BRAM18", "DSP")):
        raise AssertionError(f"Tile 资源结构发生变化: {resources}")

    power = (TILE_REPORTS / "power_impl.rpt").read_text(encoding="utf-8")
    watts = float(
        require_match(
            r"\| Total On-Chip Power \(W\)\s*\|\s*(\d+\.\d+)",
            power,
            "Tile total power",
        ).group(1)
    )
    confidence = require_match(
        r"\| Confidence Level\s*\|\s*([^|]+?)\s*\|",
        power,
        "Tile power confidence",
    ).group(1).strip()
    if watts <= 0.0:
        raise AssertionError(f"Tile 功耗必须为正数: {watts}")
    if confidence not in {"Medium", "High"}:
        raise AssertionError(f"Tile 功耗 confidence 过低: {confidence}")
    if not re.search(
        r"\| Simulation Activity File\s*\|\s*---\s*\|", power
    ):
        raise AssertionError("Tile 功耗报告不再是冻结的 vector-less activity 条件")

    raw_values: dict[str, int | float | str] = {
        "WNS_NS": wns,
        "TNS_NS": tns,
        "SETUP_VIOLATIONS": setup_failures,
        "WHS_NS": whs,
        "THS_NS": ths,
        "HOLD_VIOLATIONS": hold_failures,
        "ROUTE_ERRORS": route_errors,
        "FULLY_ROUTED_NETS": fully_routed,
        "DRC_ERRORS": 0,
        "DRC_CRITICAL_WARNINGS": 0,
        "DRC_CFGBVS1_WARNINGS": 1,
        "METHODOLOGY_ERRORS": 0,
        "METHODOLOGY_CRITICAL_WARNINGS": 0,
        "METHODOLOGY_TIMING18_WARNINGS": 180,
        **resources,
        "POWER_W": watts,
        "POWER_CONFIDENCE": confidence,
        "POWER_ACTIVITY_FILE": "NONE",
    }
    for key, actual in raw_values.items():
        require_summary_matches(summary, key, actual)

    LOGGER.info(
        "独立 Tile Vivado PASS: WNS/WHS=%+.3f/%+.3f ns, LUT=%d FF=%d",
        wns,
        whs,
        resources["LUT"],
        resources["FF"],
    )
    LOGGER.warning(
        "独立 Tile 功耗仅为 vector-less OOC 估算: %.3f W, confidence=%s",
        watts,
        confidence,
    )


def verify_xpm_reports() -> None:
    """审计真实 Vivado XPM 仿真、容量、复位和综合网表隔离证据。"""
    simulate_log = (
        XPM_REPORTS
        / "project"
        / "ene_xpm_wrapper.sim"
        / "sim_1"
        / "behav"
        / "xsim"
        / "simulate.log"
    )
    report_names = (
        "vivado_xpm_wrapper_summary.txt",
        "cdc_post_synth.rpt",
    )
    require_fresh_reports(
        XPM_REPORTS,
        report_names,
        (
            "digital_snn_host_bridge.sv",
            "xpm_fifo_async_sim.sv",
            "test_host_bridge_xpm_wrapper.py",
            "tb_vivado_xpm_wrapper.sv",
            "vivado_xpm_wrapper_sim.tcl",
        ),
    )
    if not simulate_log.is_file():
        raise AssertionError(f"缺少真实 XPM 仿真日志: {simulate_log}")

    latest_source_time = max(
        (ROOT / name).stat().st_mtime
        for name in (
            "digital_snn_host_bridge.sv",
            "tb_vivado_xpm_wrapper.sv",
            "vivado_xpm_wrapper_sim.tcl",
        )
    )
    if simulate_log.stat().st_mtime <= latest_source_time:
        raise AssertionError("真实 XPM 仿真日志早于当前 wrapper/testbench")

    log_text = simulate_log.read_text(encoding="utf-8")
    capacity = require_match(
        r"VIVADO_XPM_WRAPPER_PASS command_capacity=(\d+) response_capacity=(\d+)",
        log_text,
        "真实 XPM 容量与通过标记",
    )
    command_capacity = int(capacity.group(1))
    response_capacity = int(capacity.group(2))
    if (command_capacity, response_capacity) != (17, 17):
        raise AssertionError(
            "真实 XPM FWFT 容量不符合冻结配置: "
            f"command={command_capacity}, response={response_capacity}"
        )
    for forbidden in (
        "Fatal:",
        "FATAL_ERROR",
        "RESET_REENTRY_ERROR",
        "XPM_FIFO 20-",
        "overflow",
        "underflow",
    ):
        if forbidden in log_text:
            raise AssertionError(f"真实 XPM 仿真日志含禁止文本: {forbidden}")

    summary = read_xpm_summary(XPM_REPORTS / "vivado_xpm_wrapper_summary.txt")
    expected = {
        "vivado_version": "2024.1",
        "part": "xc7a35tcpg236-1",
        "xpm_libraries": "XPM_FIFO",
        "simulation_top": "tb_vivado_xpm_wrapper",
        "synthesis_top": "digital_snn_host_bridge",
        "synthesis_status": "synth_design complete",
        "reset_reentry_assertion_in_netlist": "0",
    }
    for key, expected_value in expected.items():
        actual = require_key(summary, key)
        if actual != expected_value:
            raise AssertionError(f"XPM 摘要 {key}={actual}, expected={expected_value}")

    cdc = (XPM_REPORTS / "cdc_post_synth.rpt").read_text(encoding="utf-8")
    cdc_rows = re.findall(r"^CDC-(\d+)\s+(\w+)\s+(\d+)\s+", cdc, re.MULTILINE)
    if cdc_rows != [("3", "Info", "4")]:
        raise AssertionError(f"XPM wrapper CDC 项目发生变化: {cdc_rows}")
    LOGGER.info("真实 XPM PASS: command/response FWFT 容量均为 17")


def verify_system_reports() -> None:
    """审计双时钟 Host Bridge 全系统 routed timing、CDC、DRC 和资源。"""
    report_names = (
        "signoff_summary.txt",
        "timing_summary_impl.rpt",
        "clock_interaction_impl.rpt",
        "cdc_impl.rpt",
        "cdc_classification.txt",
        "route_status_impl.rpt",
        "drc_impl.rpt",
        "methodology_impl.rpt",
        "utilization_hierarchical_impl.rpt",
        "power_impl.rpt",
    )
    require_fresh_reports(
        SYSTEM_REPORTS,
        report_names,
        (
            "digital_lif_engine.sv",
            "digital_snn_tile_4x2x2.sv",
            "digital_snn_host_bridge_controller.sv",
            "digital_snn_host_bridge.sv",
            "digital_snn_host_bridge_system.sv",
            "vivado_host_bridge_system_ooc.tcl",
        ),
    )

    summary = read_key_values(SYSTEM_REPORTS / "signoff_summary.txt")
    expected = {
        "RESULT": "PASS",
        "PART": "xc7a35tcpg236-1",
        "TOP": "digital_snn_host_bridge_system",
        "HOST_CLOCK_MHZ": "50.000",
        "TILE_CLOCK_MHZ": "100.000",
        "CLOCK_GROUPS": "ASYNCHRONOUS",
    }
    for key, expected_value in expected.items():
        actual = require_key(summary, key)
        if actual != expected_value:
            raise AssertionError(f"系统摘要 {key}={actual}, expected={expected_value}")

    for key in ("HOST_WNS_NS", "HOST_WHS_NS", "TILE_WNS_NS", "TILE_WHS_NS"):
        value = float(require_key(summary, key))
        if value < 0.0:
            raise AssertionError(f"系统时序未收敛: {key}={value}")
    for key in (
        "HOST_TNS_NS",
        "HOST_THS_NS",
        "HOST_SETUP_VIOLATIONS",
        "HOST_HOLD_VIOLATIONS",
        "TILE_TNS_NS",
        "TILE_THS_NS",
        "TILE_SETUP_VIOLATIONS",
        "TILE_HOLD_VIOLATIONS",
        "ROUTE_ERRORS",
        "DRC_ERRORS",
        "DRC_CRITICAL_WARNINGS",
        "EXTERNAL_CDC_CRITICAL_LINES",
        "EXTERNAL_CDC_UNSAFE_LINES",
        "EXTERNAL_CDC_WARNING_LINES",
        "XPM_CDC_CRITICAL_LINES",
        "XPM_CDC_UNKNOWN_LINES",
    ):
        if float(require_key(summary, key)) != 0.0:
            raise AssertionError(f"系统硬门槛非零: {key}={summary[key]}")

    timing = (SYSTEM_REPORTS / "timing_summary_impl.rpt").read_text(encoding="utf-8")
    if "All user specified timing constraints are met." not in timing:
        raise AssertionError("Vivado 未确认全部已指定系统时序约束满足")

    clock_interaction = (
        SYSTEM_REPORTS / "clock_interaction_impl.rpt"
    ).read_text(encoding="utf-8")
    if clock_interaction.count("Asynchronous Groups") < 2:
        raise AssertionError("Host/Tile 双向时钟关系未被完整声明为异步组")

    route = (SYSTEM_REPORTS / "route_status_impl.rpt").read_text(encoding="utf-8")
    route_errors = int(
        require_match(
            r"# of nets with routing errors\.*\s*:\s*(\d+)",
            route,
            "system route errors",
        ).group(1)
    )
    fully_routed = int(
        require_match(
            r"# of fully routed nets\.*\s*:\s*(\d+)",
            route,
            "system fully routed nets",
        ).group(1)
    )
    if route_errors != 0 or fully_routed == 0:
        raise AssertionError(
            f"系统路由状态不完整: errors={route_errors}, fully_routed={fully_routed}"
        )

    cdc = read_system_cdc_summary(SYSTEM_REPORTS / "cdc_classification.txt")
    cdc_expected_zero = (
        "XPM_CRITICAL_LINES",
        "XPM_UNKNOWN_LINES",
        "EXTERNAL_CRITICAL_LINES",
        "EXTERNAL_UNSAFE_LINES",
        "EXTERNAL_WARNING_LINES",
    )
    for key in cdc_expected_zero:
        if int(require_key(cdc, key)) != 0:
            raise AssertionError(f"系统 CDC 未解释项: {key}={cdc[key]}")
    if require_key(cdc, "EXTERNAL_FINDINGS") != "NONE":
        raise AssertionError("系统 CDC 分类报告存在 XPM 外部发现")
    allowed_classes = {"XPM_FIFO_GRAY_POINTER", "XPM_FIFO_RESET_SYNC"}
    actual_classes = {
        value for key, value in cdc.items() if re.fullmatch(r"ITEM_\d+_CLASS", key)
    }
    if not actual_classes or not actual_classes.issubset(allowed_classes):
        raise AssertionError(f"系统 XPM CDC 分类发生变化: {sorted(actual_classes)}")

    utilization = (
        SYSTEM_REPORTS / "utilization_hierarchical_impl.rpt"
    ).read_text(encoding="utf-8")
    top = require_match(
        r"^\|\s*digital_snn_host_bridge_system\s*\|\s*\(top\)\s*\|"
        r"\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|"
        r"\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|",
        utilization,
        "system top utilization",
    )
    lut, _logic_lut, _lutram, _srl, ff, ramb36, ramb18, dsp = (
        int(value) for value in top.groups()
    )
    if lut == 0 or ff == 0 or (ramb36, ramb18, dsp) != (4, 0, 0):
        raise AssertionError(
            "系统资源不符合冻结结构: "
            f"LUT={lut}, FF={ff}, RAMB36={ramb36}, RAMB18={ramb18}, DSP={dsp}"
        )

    power = (SYSTEM_REPORTS / "power_impl.rpt").read_text(encoding="utf-8")
    watts = float(
        require_match(
            r"\| Total On-Chip Power \(W\)\s*\|\s*(\d+\.\d+)",
            power,
            "system total power",
        ).group(1)
    )
    confidence = require_match(
        r"\| Confidence Level\s*\|\s*([^|]+?)\s*\|",
        power,
        "system power confidence",
    ).group(1).strip()
    if "| Simulation Activity File | ---" not in power:
        raise AssertionError("系统功耗报告活动文件状态与 vector-less 假设不一致")

    LOGGER.info(
        "系统 Vivado PASS: Host WNS/WHS=%+.3f/%+.3f ns, "
        "Tile WNS/WHS=%+.3f/%+.3f ns, LUT=%d FF=%d RAMB36=%d DSP=%d",
        float(summary["HOST_WNS_NS"]),
        float(summary["HOST_WHS_NS"]),
        float(summary["TILE_WNS_NS"]),
        float(summary["TILE_WHS_NS"]),
        lut,
        ff,
        ramb36,
        dsp,
    )
    LOGGER.warning(
        "功耗仅为 vector-less OOC 估算: %.3f W, confidence=%s",
        watts,
        confidence,
    )


def verify_reports() -> None:
    """组合检查独立 Tile、真实 XPM 与完整双时钟系统 Vivado 证据。"""
    verify_tile_reports()
    verify_xpm_reports()
    verify_system_reports()


def rerun_vivado() -> None:
    """按依赖顺序重建全部 Vivado 证据，任一失败立即停止。"""
    run_command(
        powershell_script("run_vivado_tile_synth.ps1"),
        "Vivado 2024.1 独立 Tile OOC 实现",
    )
    run_command(
        powershell_script("run_vivado_xpm_wrapper_sim.ps1"),
        "Vivado 2024.1 真实 XPM xsim/综合",
    )
    run_command(
        powershell_script("run_vivado_host_bridge_system_ooc.ps1"),
        "Vivado 2024.1 双时钟 Host Bridge 系统 OOC 实现",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rerun-vivado",
        action="store_true",
        help="依次重建独立 Tile、真实 XPM 和完整双时钟系统 Vivado 证据",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        verify_software()
        verify_m3()
        if args.rerun_vivado:
            rerun_vivado()
        verify_reports()
        write_t0_signoff_summary()
    except (AssertionError, OSError, UnicodeError, ValueError) as error:
        LOGGER.error("GOAL_AUDIT_FAIL: %s", error)
        return 1

    LOGGER.info("GOAL_AUDIT_PASS: 原始 Goal M1-M4 最小硬件基石门槛通过")
    LOGGER.warning(
        "NOT_PROVEN: 无限时域/全状态等价、共享 RAM 大规模扩展、"
        "板级 bitstream 闭环、真实活动功耗与通用 AI 自训练"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

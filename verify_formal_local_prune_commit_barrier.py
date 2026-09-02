"""验证真实 barrier proof/reach，并绑定 gate 合同与三个真实网络顶层。

工具发现遵循 `docs/WINDOWS_MSYS2_XPM_TOOLCHAIN.md`：优先使用 PATH 上的 `iverilog`，
其次兼容 Windows + MSYS2 UCRT64 专用固定路径 `C:/msys64/ucrt64/bin/iverilog.exe`
（仓库 admin 在 PR #6 issue comment 5506790489 裁定允许保留该路径，但它不是跨平台默认路径）。
两者都找不到时打印 `SKIPPED/NOT APPLICABLE` 并跳过编译绑定，不把“环境没装工具”
误报成 RTL 功能失败；`iverilog.exe` 带 `-Wall` 静默崩溃（非 0 退出且完全无输出）时
去掉 `-Wall` 重试一次，任何有输出的错误仍按失败处理。
"""

from pathlib import Path
import shutil
import subprocess
import tempfile

import verify_formal_local_prune_gate

ROOT = Path(__file__).resolve().parent
MSYS2_UCRT64_BIN = Path("C:/msys64/ucrt64/bin")  # Windows + MSYS2 UCRT64 专用，非跨平台默认路径
SILENT_CRASH_CODES = (0xC0000005, 0xC0000409)


def find_tool(name: str) -> Path | None:
    """优先使用 PATH，再兼容本机 MSYS2 UCRT64 安装。"""
    discovered = shutil.which(name)
    if discovered:
        return Path(discovered)
    for candidate in (MSYS2_UCRT64_BIN / f"{name}.exe", Path("C:/msys64/mingw64/bin") / f"{name}.exe"):
        if candidate.exists():
            return candidate
    return None


def compile_top(iverilog: Path, top: str, sources: list[str], tmp: str) -> subprocess.CompletedProcess[str]:
    command = [str(iverilog), "-g2012", "-Wall", "-s", top, "-o", str(Path(tmp) / "a.vvp"), *[str(ROOT / s) for s in sources]]
    run = subprocess.run(command, capture_output=True, text=True)
    if (run.returncode and (run.returncode & 0xFFFFFFFF) in SILENT_CRASH_CODES
            and not (run.stdout or "").strip() and not (run.stderr or "").strip()):
        print(f"TOOLCHAIN_DEFECT=iverilog_compile_silent_crash return_code=0x{(run.returncode & 0xFFFFFFFF):08X} retry_without=-Wall")
        command.remove("-Wall")
        run = subprocess.run(command, capture_output=True, text=True)
    return run

def require(text: str, needle: str, name: str) -> None:
    if needle not in text: raise AssertionError(f"{name} 缺少 {needle}")

def read_log(name: str) -> str:
    raw = (ROOT / name).read_bytes()
    return raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw[:32] else "utf-8", errors="replace")

def verify() -> dict[str, int]:
    harness = (ROOT / "formal_local_prune_commit_barrier.sv").read_text(encoding="utf-8")
    proof = (ROOT / "formal_local_prune_commit_barrier.ys").read_text(encoding="utf-8")
    reach = (ROOT / "formal_local_prune_commit_barrier_reach.ys").read_text(encoding="utf-8")
    for needle in ("local_prune_commit_barrier #(.N_GATES(N))", "N = 10", "reached_success", "saw_gate_stagger", "saw_rsp_backpressure", "saw_unblock", "runtime_blocked == !commit_ready", "epoch_changed_for_commit"):
        require(harness, needle, "barrier harness")
    require(proof, "-seq 32", "proof"); require(proof, "-prove-asserts -verify", "proof")
    require(reach, "-seq 32", "reach"); require(reach, "-prove reached_success 0 -falsify", "reach")
    # exact-two 不在 barrier 内伪证，必须实际验证真实 gate 的 proof、reach 与 witness。
    gate_result = verify_formal_local_prune_gate.verify()
    if gate_result["formal_depth"] != 32 or gate_result["reach_depth"] != 8:
        raise AssertionError("公共 gate 形式证据深度不匹配")
    proof_log = read_log("formal_local_prune_commit_barrier.log")
    reach_log = read_log("formal_local_prune_commit_barrier_reach.log")
    require(proof_log, "SAT proof finished - no model found: SUCCESS!", "proof log")
    require(reach_log, "SAT proof finished - model found: FAIL!", "reach log")
    witness = ROOT / "formal_local_prune_commit_barrier_success.vcd"
    if not witness.is_file() or witness.stat().st_size == 0: raise AssertionError("成功 witness 缺失")
    witness_text = witness.read_text(encoding="utf-8", errors="replace")
    for signal in ("saw_gate_stagger", "saw_rsp_backpressure", "saw_unblock"):
        require(witness_text, signal, witness.name)

    sources = ["digital_lif_engine.sv","local_prune_gate_2of4.sv","eneuron_local_prune_wrapper.sv","local_prune_evidence_gain.sv","pulse_mini_prune_bridge.sv","pulse_mini_core.sv","pulse_mini_l2_core.sv","pulse_mini_l_prune_wrapper.sv","pulse_mini_l2_prune_wrapper.sv","pruned_network_tick_scheduler.sv","local_prune_commit_barrier.sv","eneuron_pruned_network_4x8x2.sv","pulse_mini_pruned_network_4x8x2.sv","pulse_mini_l_pruned_network_4x8x2.sv","pulse_mini_l2_pruned_network_4x8x2.sv"]
    tops = ["eneuron_pruned_network_4x8x2","pulse_mini_l_pruned_network_4x8x2","pulse_mini_l2_pruned_network_4x8x2"]
    pulse_base = (ROOT / "pulse_mini_pruned_network_4x8x2.sv").read_text(encoding="utf-8")
    require(pulse_base, "local_prune_commit_barrier #(.N_GATES(N_NEURONS))", "pulse shared top")
    require(pulse_base, "!barrier_runtime_blocked", "pulse shared top")
    # 定向仿真入口必须在 commit 请求及整个 blocked 区间检查 runtime ready 全低。
    for name in ("eneuron_pruned_network_4x8x2_cosim.py", "pulse_mini_pruned_network_4x8x2_cosim.py"):
        contract = (ROOT / name).read_text(encoding="utf-8")
        require(contract, "if (tick_ready || route_flush_ready", name)
        require(contract, "host_cmd_ready", name)
    iverilog = find_tool("iverilog")
    if iverilog is None:
        print("SKIPPED/NOT APPLICABLE: 三顶层编译绑定需要 iverilog，PATH 与 Windows + MSYS2 UCRT64"
              f" 固定路径 {MSYS2_UCRT64_BIN} 都未提供，跳过编译而不是报成 RTL 功能失败")
    else:
        print(f"COMMIT_BARRIER_COMPILE_TOOL={iverilog}")
    compiled_tops = 0
    for top in tops:
        text = (ROOT / f"{top}.sv").read_text(encoding="utf-8")
        if top.startswith("eneuron"):
            require(text, "local_prune_commit_barrier #(.N_GATES(N_NEURONS))", top)
            require(text, "!barrier_runtime_blocked", top)
        else:
            require(text, "pulse_mini_pruned_network_4x8x2", top)
        if iverilog is None:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            run = compile_top(iverilog, top, sources, tmp)
            if run.returncode: raise AssertionError(run.stdout + run.stderr)
            compiled_tops += 1
    return {"formal_depth": 32, "participants": 10, "real_tops": compiled_tops}

if __name__ == "__main__":
    print("LOCAL_PRUNE_COMMIT_BARRIER_VERIFY_PASS", verify())

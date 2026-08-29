"""验证真实 barrier proof/reach，并绑定 gate 合同与三个真实网络顶层。"""

from pathlib import Path
import subprocess
import tempfile

import verify_formal_local_prune_gate

ROOT = Path(__file__).resolve().parent

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
    for top in tops:
        text = (ROOT / f"{top}.sv").read_text(encoding="utf-8")
        if top.startswith("eneuron"):
            require(text, "local_prune_commit_barrier #(.N_GATES(N_NEURONS))", top)
            require(text, "!barrier_runtime_blocked", top)
        else:
            require(text, "pulse_mini_pruned_network_4x8x2", top)
        with tempfile.TemporaryDirectory() as tmp:
            run = subprocess.run([r"C:\msys64\ucrt64\bin\iverilog.exe","-g2012","-Wall","-s",top,"-o",str(Path(tmp)/"a.vvp"),*[str(ROOT/s) for s in sources]],capture_output=True,text=True)
            if run.returncode: raise AssertionError(run.stdout + run.stderr)
    return {"formal_depth": 32, "participants": 10, "real_tops": 3}

if __name__ == "__main__":
    print("LOCAL_PRUNE_COMMIT_BARRIER_VERIFY_PASS", verify())

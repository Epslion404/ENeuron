"""Fail-closed 审计 ENeuron 剪枝 wrapper 的形式证明与非空轨迹。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def require(text: str, needle: str, source: str) -> None:
    """关键合同、工具结果或签核标记缺失时立即失败。"""
    if needle not in text:
        raise AssertionError(f"{source} 缺少合同: {needle}")


def require_file(name: str) -> Path:
    """返回必须存在且非空的证据文件。"""
    path = ROOT / name
    if not path.is_file() or path.stat().st_size == 0:
        raise AssertionError(f"缺少非空证据文件: {name}")
    return path


def main() -> None:
    wrapper_path = require_file("eneuron_local_prune_wrapper.sv")
    harness_path = require_file("formal_eneuron_prune_wrapper.sv")
    proof_path = require_file("formal_eneuron_prune_wrapper.ys")
    reach_path = require_file("formal_eneuron_prune_wrapper_reach.ys")
    runner_path = require_file("run_formal_eneuron_prune_wrapper.ps1")
    log_path = require_file("formal_eneuron_prune_wrapper.log")
    witness_path = require_file("formal_eneuron_prune_wrapper_mod_reach.vcd")

    wrapper = wrapper_path.read_text(encoding="utf-8")
    harness = harness_path.read_text(encoding="utf-8")
    proof = proof_path.read_text(encoding="utf-8")
    reach = reach_path.read_text(encoding="utf-8")
    runner = runner_path.read_text(encoding="utf-8")
    log = log_path.read_text(encoding="utf-8", errors="replace")

    for needle in (
        "`ifdef FORMAL",
        "formal_core_mod_accept",
        "formal_gate_observe_accept",
        "assert(formal_core_mod_accept == formal_gate_observe_accept)",
    ):
        require(wrapper, needle, wrapper_path.name)

    for needle in (
        "expected_utility_after_mod",
        "reached_public_nonzero_mod_success",
        "reached_wrong_mode_reject",
        "reached_wrong_id_reject",
        "reached_repeat_id_reject",
        "$past(prune_rsp_valid && !prune_rsp_ready)",
        "eligibility_snapshot_flat_state != 0",
    ):
        require(harness, needle, harness_path.name)

    require(proof, "-seq 32", proof_path.name)
    require(proof, "-prove-asserts -verify", proof_path.name)
    require(reach, "-seq 32", reach_path.name)
    require(
        reach,
        "-prove reached_public_nonzero_mod_success 0 -falsify",
        reach_path.name,
    )
    require(runner, "FORMAL_LOG_SCHEMA=np4b5_eneuron_wrapper_v1", runner_path.name)

    require(log, "FORMAL_LOG_SCHEMA=np4b5_eneuron_wrapper_v1", log_path.name)
    if log.count("SAT proof finished - no model found: SUCCESS!") != 1:
        raise AssertionError(f"{log_path.name} 必须恰有一次不变量证明成功")
    if log.count("SAT proof finished - model found: FAIL!") != 1:
        raise AssertionError(f"{log_path.name} 必须恰有一个公开成功路径 witness")
    if "ERROR:" in log:
        raise AssertionError(f"{log_path.name} 含 Yosys 错误")
    require(
        log,
        "ENEURON_PRUNE_WRAPPER_FORMAL_PASS depth=32 "
        "invariant=mod_observe_atomic_public_state "
        "reach=public_nonzero_snapshot_mod_done",
        log_path.name,
    )

    print(
        "ENEURON_PRUNE_WRAPPER_FORMAL_CONTRACT_PASS "
        "depth=32 invariant=mod_observe_atomic_public_state "
        f"reach_vcd_bytes={witness_path.stat().st_size}"
    )


if __name__ == "__main__":
    main()

"""审计 Pulse 剪枝 wrapper 形式证明及其非空 witness。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def require(text: str, needle: str, source: str) -> None:
    """关键合同或证据缺失时立即失败。"""
    if needle not in text:
        raise AssertionError(f"{source} 缺少合同: {needle}")


def main() -> None:
    harness_path = ROOT / "formal_pulse_mini_prune_wrapper.sv"
    proof_path = ROOT / "formal_pulse_mini_prune_wrapper.ys"
    reach_path = ROOT / "formal_pulse_mini_prune_wrapper_reach.ys"
    log_path = ROOT / "formal_pulse_mini_prune_wrapper.log"
    witness_path = ROOT / "formal_pulse_mini_prune_wrapper_feedback_reach.vcd"

    harness = harness_path.read_text(encoding="utf-8")
    proof = proof_path.read_text(encoding="utf-8")
    reach = reach_path.read_text(encoding="utf-8")
    log = log_path.read_text(encoding="utf-8", errors="replace")

    for needle in (
        "accepted_nonzero_feedback",
        "feedback_observe_before",
        "feedback_utility_after_observe",
        "prune_observe_count_state == feedback_observe_before + 1'b1",
        "assert(observe_completed)",
        "prune_utility_state == feedback_utility_after_observe",
        "assert(!feedback_observed)",
        "reached_successful_nonzero_feedback",
        "$past(rsp_valid && !rsp_ready)",
        "$past(prune_rsp_valid && !prune_rsp_ready)",
    ):
        require(harness, needle, harness_path.name)
    require(proof, "-seq 32", proof_path.name)
    require(proof, "-prove-asserts -verify", proof_path.name)
    require(reach, "-seq 32", reach_path.name)
    require(
        reach,
        "-prove reached_successful_nonzero_feedback 0 -falsify",
        reach_path.name,
    )

    require(log, "FORMAL_LOG_SCHEMA=np4b5_wrapper_v1", log_path.name)
    if log.count("SAT proof finished - no model found: SUCCESS!") != 1:
        raise AssertionError(f"{log_path.name} 必须恰有一次不变量证明成功")
    if log.count("SAT proof finished - model found: FAIL!") != 1:
        raise AssertionError(f"{log_path.name} 必须恰有一个成功路径 witness")
    if "ERROR:" in log:
        raise AssertionError(f"{log_path.name} 含 Yosys 错误")
    require(
        log,
        "PULSE_PRUNE_WRAPPER_FORMAL_PASS depth=32 "
        "invariant=feedback_observe_utility_order "
        "reach=successful_nonzero_feedback",
        log_path.name,
    )
    if not witness_path.is_file() or witness_path.stat().st_size == 0:
        raise AssertionError(f"缺少非空 witness: {witness_path.name}")

    print(
        "PULSE_PRUNE_WRAPPER_FORMAL_CONTRACT_PASS "
        "depth=32 invariant=feedback_observe_utility_order "
        "reach=successful_nonzero_feedback"
    )


if __name__ == "__main__":
    main()

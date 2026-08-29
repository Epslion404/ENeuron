"""审计 Pulse-Mini-L2 wrapper 形式证明和非空 witness。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def require(text: str, needle: str, source: str) -> None:
    if needle not in text:
        raise AssertionError(f"{source} 缺少合同: {needle}")


def main() -> None:
    harness_path = ROOT / "formal_pulse_mini_l2_prune_wrapper.sv"
    proof_path = ROOT / "formal_pulse_mini_l2_prune_wrapper.ys"
    reach_path = ROOT / "formal_pulse_mini_l2_prune_wrapper_reach.ys"
    log_path = ROOT / "formal_pulse_mini_l2_prune_wrapper.log"
    witness_path = ROOT / "formal_pulse_mini_l2_prune_wrapper_feedback_reach.vcd"

    harness = harness_path.read_text(encoding="utf-8")
    proof = proof_path.read_text(encoding="utf-8")
    reach = reach_path.read_text(encoding="utf-8")
    log = log_path.read_text(encoding="utf-8", errors="replace")

    for needle in (
        "accepted_nonzero_feedback",
        "feedback_observe_before",
        "feedback_utility_after_observe",
        "assert(observe_completed)",
        "prune_utility_state == feedback_utility_after_observe",
        "assert(!feedback_observed)",
        "$past(rsp_valid && !rsp_ready)",
        "reached_successful_nonzero_feedback",
    ):
        require(harness, needle, harness_path.name)
    require(proof, "-seq 32", proof_path.name)
    require(proof, "-prove-asserts -verify", proof_path.name)
    require(reach, "-seq 32", reach_path.name)
    require(reach, "-prove reached_successful_nonzero_feedback 0 -falsify", reach_path.name)

    require(log, "FORMAL_LOG_SCHEMA=np4b5_l2_wrapper_v1", log_path.name)
    if log.count("SAT proof finished - no model found: SUCCESS!") != 1:
        raise AssertionError("必须恰有一次不变量证明成功")
    if log.count("SAT proof finished - model found: FAIL!") != 1:
        raise AssertionError("必须恰有一个非空成功 witness")
    if "ERROR:" in log:
        raise AssertionError("Yosys 日志含错误")
    require(log, "PULSE_L2_PRUNE_WRAPPER_FORMAL_PASS", log_path.name)
    if not witness_path.is_file() or witness_path.stat().st_size == 0:
        raise AssertionError("缺少 L2 非空 witness")
    print("PULSE_L2_PRUNE_WRAPPER_FORMAL_CONTRACT_PASS depth=32")


if __name__ == "__main__":
    main()

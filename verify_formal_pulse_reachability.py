"""审计 Pulse-Mini 形式 harness 是否包含非空复位与命令可达性合同。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def require(text: str, needle: str, source: str) -> None:
    """缺少关键合同即停止，避免把空轨迹的证明误报为通过。"""
    if needle not in text:
        raise AssertionError(f"{source} 缺少合同: {needle}")


def audit_variant(stem: str) -> None:
    harness_path = ROOT / f"{stem}.sv"
    proof_path = ROOT / f"{stem}.ys"
    reach_path = ROOT / f"{stem}_reach.ys"
    harness = harness_path.read_text(encoding="utf-8")
    proof = proof_path.read_text(encoding="utf-8")

    forbidden = "if (!past_valid) assume(rst);"
    if forbidden in harness:
        raise AssertionError(
            f"{harness_path.name} 仍在 rst=0 分支中 assume(rst)，非复位轨迹不可达"
        )

    require(harness, "if (!past_valid)", harness_path.name)
    require(harness, "assume(rst);", harness_path.name)
    require(harness, "else", harness_path.name)
    require(harness, "assume(!rst);", harness_path.name)
    require(harness, "reached_tick_ok", harness_path.name)
    require(harness, "reached_capture_ok", harness_path.name)
    require(harness, "reached_feedback_ok", harness_path.name)
    require(harness, "reached_capture_then_feedback_ok", harness_path.name)
    require(proof, "-seq 20", proof_path.name)

    if not reach_path.is_file():
        raise AssertionError(f"缺少可达性脚本: {reach_path.name}")
    reach = reach_path.read_text(encoding="utf-8")
    for signal in (
        "reached_tick_ok",
        "reached_capture_ok",
        "reached_feedback_ok",
        "reached_capture_then_feedback_ok",
    ):
        require(reach, f"-prove {signal} 0 -falsify", reach_path.name)
    require(reach, "-seq 20", reach_path.name)

    log_path = ROOT / f"{stem}.log"
    if not log_path.is_file():
        raise AssertionError(f"缺少形式验证日志: {log_path.name}")
    log = log_path.read_text(encoding="utf-8", errors="replace")
    require(log, "FORMAL_LOG_SCHEMA=np4b5_v2", log_path.name)
    if log.count("SAT proof finished - no model found: SUCCESS!") != 1:
        raise AssertionError(f"{log_path.name} 必须恰有一次不变量证明成功")
    if log.count("SAT proof finished - model found: FAIL!") != 4:
        raise AssertionError(f"{log_path.name} 必须恰有四个可达 witness")
    if "ERROR:" in log:
        raise AssertionError(f"{log_path.name} 含 Yosys 错误")
    require(
        log,
        "FORMAL_PASS depth=20 reach=tick,capture,feedback,capture_then_feedback",
        log_path.name,
    )

    for suffix in (
        "tick_reach.vcd",
        "capture_reach.vcd",
        "feedback_reach.vcd",
        "capture_feedback_reach.vcd",
    ):
        witness = ROOT / f"{stem}_{suffix}"
        if not witness.is_file() or witness.stat().st_size == 0:
            raise AssertionError(f"缺少非空 witness: {witness.name}")


def main() -> None:
    audit_variant("formal_pulse_mini")
    audit_variant("formal_pulse_mini_l2")
    print("PULSE_FORMAL_REACHABILITY_CONTRACT_PASS variants=2 depth=20")


if __name__ == "__main__":
    main()

"""Fail-closed 验证公共 2:4 gate 的 proof、reach 和 exact-two witness。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _require(text: str, needle: str, source: str) -> None:
    """关键合同或工具标记缺失时立即失败。"""
    if needle not in text:
        raise AssertionError(f"{source} 缺少 {needle}")


def _read_log(name: str) -> str:
    """兼容 PowerShell Tee-Object 生成的 UTF-8/UTF-16 日志。"""
    raw = (ROOT / name).read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw[:32] else "utf-8"
    return raw.decode(encoding, errors="replace")


def verify() -> dict[str, int]:
    """验证 depth、proof、非空 exact-two 轨迹和证据文件。"""
    proof_script = (ROOT / "formal_local_prune_gate.ys").read_text(encoding="utf-8")
    reach_script = (ROOT / "formal_local_prune_gate_reach.ys").read_text(encoding="utf-8")
    proof_log = _read_log("formal_local_prune_gate.log")
    reach_log = _read_log("formal_local_prune_gate_reach.log")

    _require(proof_script, "-seq 32", "gate proof script")
    _require(proof_script, "-prove-asserts -verify", "gate proof script")
    for needle in (
        "-seq 8",
        "-set-at 8 mask_valid_state 1",
        "-set-at 8 mask_commits_state 1",
        "-set-at 8 structural_mask_state 3",
        "-dump_vcd formal_local_prune_gate_success.vcd",
    ):
        _require(reach_script, needle, "gate reach script")

    if proof_log.count("SAT proof finished - no model found: SUCCESS!") != 1:
        raise AssertionError("gate proof 日志必须恰有一次 SUCCESS")
    if reach_log.count("SAT solving finished - model found:") != 1:
        raise AssertionError("gate reach 日志必须恰有一个成功模型")
    if "ERROR:" in proof_log or "ERROR:" in reach_log:
        raise AssertionError("gate 形式日志包含 Yosys 错误")

    witness = ROOT / "formal_local_prune_gate_success.vcd"
    if not witness.is_file() or witness.stat().st_size == 0:
        raise AssertionError("gate exact-two 成功 witness 缺失")
    witness_text = witness.read_text(encoding="utf-8", errors="replace")
    for signal in ("mask_valid_state", "structural_mask_state", "mask_commits_state"):
        _require(witness_text, signal, witness.name)

    return {"formal_depth": 32, "reach_depth": 8, "witness_bytes": witness.stat().st_size}


if __name__ == "__main__":
    result = verify()
    print(
        "LOCAL_PRUNE_GATE_FORMAL_VERIFY_PASS "
        f"depth={result['formal_depth']} reach_depth={result['reach_depth']} "
        f"witness_bytes={result['witness_bytes']}"
    )

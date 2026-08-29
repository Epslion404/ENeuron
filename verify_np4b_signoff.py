"""独立验证 NP4B 总摘要、三模型结果和全部形式证据。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import verify_eneuron_pruned_network_summary
import verify_formal_eneuron_prune_wrapper
import verify_formal_local_prune_commit_barrier
import verify_formal_local_prune_gate
import verify_formal_pulse_mini_l2_prune_wrapper
import verify_formal_pulse_mini_prune_wrapper
import verify_pulse_pruned_network_summaries
from generate_np4b_signoff import (
    FILE_GROUPS,
    FREEZE_COMMIT,
    ROOT,
    SUMMARY_PATH,
    WITNESS_FILES,
    sha256,
)


def require_equal(actual: object, expected: object, name: str) -> None:
    """字段不一致时给出稳定、可定位的失败。"""
    if actual != expected:
        raise AssertionError(f"{name}: actual={actual!r} expected={expected!r}")


def load_json(name: str) -> dict[str, object]:
    """读取必须存在的 JSON 对象。"""
    path = ROOT / name
    if not path.is_file() or path.stat().st_size == 0:
        raise AssertionError(f"缺少非空 JSON: {name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{name} 顶层必须为对象")
    return cast(dict[str, object], data)


def verify_summary(data: dict[str, object], *, check_files: bool = True) -> None:
    """验证固定状态、统计、工具边界和精确哈希集合。"""
    require_equal(data.get("schema"), "eneuron.np4b.signoff.v1", "schema")
    require_equal(data.get("date"), "2026-08-29", "date")
    require_equal(data.get("status"), "NP4B_INTEGRATION_PASS", "status")
    require_equal(data.get("next_gate"), "NP6_REVIEW_REQUIRED", "next_gate")
    require_equal(data.get("freeze_commit"), FREEZE_COMMIT, "freeze_commit")
    require_equal(data.get("scope"), "logical_functional_integration_only", "scope")
    require_equal(
        data.get("not_proven"),
        [
            "physical_bram_skip",
            "wall_clock_speedup",
            "power_reduction",
            "xc7z020_timing",
        ],
        "not_proven",
    )

    models = cast(dict[str, dict[str, object]], data.get("models"))
    expected_models = {
        "eneuron": (list(range(101, 121)), "ENEURON_NP4B4_PASS"),
        "pulse_l": (list(range(201, 221)), "PULSE_L_NP4B4_PASS"),
        "pulse_l2": (list(range(301, 321)), "PULSE_L2_NP4B4_PASS"),
    }
    require_equal(set(models), set(expected_models), "models.keys")
    for name, (seeds, status) in expected_models.items():
        require_equal(models[name].get("seeds"), seeds, f"models.{name}.seeds")
        require_equal(models[name].get("transactions"), 20_000, f"models.{name}.transactions")
        require_equal(models[name].get("status"), status, f"models.{name}.status")

    regression = cast(dict[str, object], data.get("regression"))
    for key, expected in {
        "command": "python -m unittest discover -v",
        "exit_code": 0,
        "tests": 359,
        "failures": 0,
        "errors": 0,
        "elapsed_seconds": 378.291,
    }.items():
        require_equal(regression.get(key), expected, f"regression.{key}")

    compile_result = cast(dict[str, object], data.get("compile"))
    require_equal(compile_result.get("compileall_exit_code"), 0, "compile.compileall_exit_code")
    require_equal(compile_result.get("iverilog_targets"), 8, "compile.iverilog_targets")
    require_equal(compile_result.get("iverilog_exit_code"), 0, "compile.iverilog_exit_code")

    formal = cast(dict[str, object], data.get("formal"))
    require_equal(formal.get("depth"), 32, "formal.depth")
    require_equal(formal.get("runner_count"), 5, "formal.runner_count")
    require_equal(formal.get("verifier_count"), 5, "formal.verifier_count")
    witness_bytes = cast(dict[str, int], formal.get("witness_bytes"))
    require_equal(set(witness_bytes), set(WITNESS_FILES), "formal.witness_bytes.keys")
    for key, name in WITNESS_FILES.items():
        size = (ROOT / name).stat().st_size
        if size <= 0:
            raise AssertionError(f"成功 witness 为空: {name}")
        require_equal(witness_bytes[key], size, f"formal.witness_bytes.{key}")

    expected_groups = {key: list(value) for key, value in FILE_GROUPS.items()}
    require_equal(data.get("file_groups"), expected_groups, "file_groups")
    expected_names = {name for names in FILE_GROUPS.values() for name in names}
    hashes = cast(dict[str, str], data.get("file_sha256"))
    require_equal(set(hashes), expected_names, "file_sha256.keys")
    if any("cex" in name or name.endswith(".tmp.log") for name in hashes):
        raise AssertionError("正式哈希集合包含 cex/tmp 证据")
    if check_files:
        for name in sorted(expected_names):
            require_equal(hashes[name], sha256(ROOT / name), f"file_sha256.{name}")


def verify_external_evidence() -> None:
    """复用现有独立 verifier，并额外检查结果恒等式与 Git 冻结点。"""
    verify_eneuron_pruned_network_summary.main()
    verify_pulse_pruned_network_summaries.main()
    verify_formal_eneuron_prune_wrapper.main()
    verify_formal_pulse_mini_prune_wrapper.main()
    verify_formal_pulse_mini_l2_prune_wrapper.main()
    verify_formal_local_prune_gate.verify()
    verify_formal_local_prune_commit_barrier.verify()

    for name in ("pulse_mini_l_np4b4_summary.json", "pulse_mini_l2_np4b4_summary.json"):
        result = load_json(name)
        require_equal(
            result["hidden_dense_reads"],
            result["hidden_reads_issued"] + result["hidden_reads_saved"],
            f"{name}.hidden_read_identity",
        )
        require_equal(
            result["output_dense_reads"],
            result["output_reads_issued"] + result["output_reads_saved"],
            f"{name}.output_read_identity",
        )

    ancestor = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "merge-base",
            "--is-ancestor",
            FREEZE_COMMIT,
            "HEAD",
        ],
        cwd=ROOT,
        check=False,
    )
    if ancestor.returncode != 0:
        raise AssertionError(f"冻结提交不是当前 HEAD 祖先: {FREEZE_COMMIT}")


def main() -> None:
    """执行总验证并输出最终唯一通过标记。"""
    if not SUMMARY_PATH.is_file() or SUMMARY_PATH.stat().st_size == 0:
        raise AssertionError(f"缺少非空总摘要: {SUMMARY_PATH.name}")
    verify_summary(load_json(SUMMARY_PATH.name))
    verify_external_evidence()
    print(
        "NP4B_SIGNOFF_VERIFY_PASS models=3 transactions=60000 "
        "tests=359 formal=5 next=NP6_REVIEW_REQUIRED"
    )


if __name__ == "__main__":
    main()

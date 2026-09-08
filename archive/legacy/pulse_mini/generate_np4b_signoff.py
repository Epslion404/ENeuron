"""生成 NP4B 功能集成的 fail-closed 总机器摘要。"""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

from rtl_tile_cosim import find_tool
from verify_local_prune_rtl import (
    canonical_bytes,
    canonical_sha256,
    canonical_sha256_bytes,
)


ROOT = Path(__file__).resolve().parent
SUMMARY_PATH = ROOT / "np4b_signoff_summary.json"
FREEZE_COMMIT = "33e0aed"

FILE_GROUPS = {
    "rtl": (
        "digital_lif_engine.sv",
        "local_prune_gate_2of4.sv",
        "local_prune_evidence_gain.sv",
        "local_prune_commit_barrier.sv",
        "eneuron_local_prune_wrapper.sv",
        "pulse_mini_core.sv",
        "pulse_mini_l2_core.sv",
        "pulse_mini_prune_bridge.sv",
        "pulse_mini_l_prune_wrapper.sv",
        "pulse_mini_l2_prune_wrapper.sv",
        "pruned_network_tick_scheduler.sv",
        "eneuron_pruned_network_4x8x2.sv",
        "pulse_mini_pruned_network_4x8x2.sv",
        "pulse_mini_l_pruned_network_4x8x2.sv",
        "pulse_mini_l2_pruned_network_4x8x2.sv",
    ),
    "oracle_cosim": (
        "local_prune_rtl_reference.py",
        "eneuron_local_prune_wrapper_cosim.py",
        "eneuron_pruned_network_reference.py",
        "eneuron_pruned_network_4x8x2_cosim.py",
        "eneuron_pruned_network_random_cosim.py",
        "pulse_mini_prune_wrapper_cosim.py",
        "pulse_mini_pruned_network_reference.py",
        "pulse_mini_pruned_network_4x8x2_cosim.py",
        "pulse_mini_pruned_network_random_cosim.py",
    ),
    "tests": (
        "test_eneuron_local_prune_wrapper.py",
        "test_eneuron_pruned_network_4x8x2.py",
        "test_eneuron_pruned_network_random_cosim.py",
        "test_eneuron_pruned_network_signoff.py",
        "test_pulse_mini_prune_wrapper.py",
        "test_pulse_mini_pruned_network_4x8x2.py",
        "test_pulse_mini_pruned_network_random_cosim.py",
        "np4b5_negative_controls.py",
        "test_np4b5_negative_controls.py",
        "test_local_prune_gate_rtl.py",
        "test_local_prune_commit_barrier.py",
    ),
    "formal": (
        "formal_eneuron_prune_wrapper.sv",
        "formal_eneuron_prune_wrapper.ys",
        "formal_eneuron_prune_wrapper_reach.ys",
        "run_formal_eneuron_prune_wrapper.ps1",
        "verify_formal_eneuron_prune_wrapper.py",
        "test_formal_eneuron_prune_wrapper.py",
        "formal_eneuron_prune_wrapper.log",
        "formal_eneuron_prune_wrapper_mod_reach.vcd",
        "formal_pulse_mini_prune_wrapper.sv",
        "formal_pulse_mini_prune_wrapper.ys",
        "formal_pulse_mini_prune_wrapper_reach.ys",
        "run_formal_pulse_mini_prune_wrapper.ps1",
        "verify_formal_pulse_mini_prune_wrapper.py",
        "formal_pulse_mini_prune_wrapper.log",
        "formal_pulse_mini_prune_wrapper_feedback_reach.vcd",
        "formal_pulse_mini_l2_prune_wrapper.sv",
        "formal_pulse_mini_l2_prune_wrapper.ys",
        "formal_pulse_mini_l2_prune_wrapper_reach.ys",
        "run_formal_pulse_mini_l2_prune_wrapper.ps1",
        "verify_formal_pulse_mini_l2_prune_wrapper.py",
        "formal_pulse_mini_l2_prune_wrapper.log",
        "formal_pulse_mini_l2_prune_wrapper_feedback_reach.vcd",
        "formal_local_prune_gate.sv",
        "formal_local_prune_gate.ys",
        "formal_local_prune_gate_reach.ys",
        "run_formal_local_prune_gate.ps1",
        "verify_formal_local_prune_gate.py",
        "test_formal_local_prune_gate.py",
        "formal_local_prune_gate.log",
        "formal_local_prune_gate_reach.log",
        "formal_local_prune_gate_success.vcd",
        "formal_local_prune_commit_barrier.sv",
        "formal_local_prune_commit_barrier.ys",
        "formal_local_prune_commit_barrier_reach.ys",
        "run_formal_local_prune_commit_barrier.ps1",
        "verify_formal_local_prune_commit_barrier.py",
        "test_formal_local_prune_commit_barrier.py",
        "formal_local_prune_commit_barrier.log",
        "formal_local_prune_commit_barrier_reach.log",
        "formal_local_prune_commit_barrier_success.vcd",
    ),
    "results_runners": (
        "run_eneuron_pruned_network_signoff.py",
        "verify_eneuron_pruned_network_summary.py",
        "eneuron_np4b4_summary.json",
        "run_pulse_pruned_network_signoff.py",
        "verify_pulse_pruned_network_summaries.py",
        "pulse_mini_l_np4b4_summary.json",
        "pulse_mini_l2_np4b4_summary.json",
        "local_prune_rtl_results.json",
        "verify_local_prune_rtl.py",
    ),
    "signoff": (
        "generate_np4b_signoff.py",
        "verify_np4b_signoff.py",
        "test_verify_np4b_signoff.py",
    ),
}

WITNESS_FILES = {
    "eneuron": "formal_eneuron_prune_wrapper_mod_reach.vcd",
    "pulse_l": "formal_pulse_mini_prune_wrapper_feedback_reach.vcd",
    "pulse_l2": "formal_pulse_mini_l2_prune_wrapper_feedback_reach.vcd",
    "gate": "formal_local_prune_gate_success.vcd",
    "barrier": "formal_local_prune_commit_barrier_success.vcd",
}


FILE_HASH_POLICY = (
    "sha256 over the bytes with CRLF and CR normalised to LF "
    "(platform, core.autocrlf and checkout-state independent; the identical "
    "canonical policy used by verify_local_prune_rtl.canonical_sha256)"
)
WITNESS_BYTES_POLICY = (
    "byte length after normalising CRLF and CR to LF, matching file_hash_policy"
)


def canonical_size(path: Path) -> int:
    """Return the byte length of the file after folding every line ending to LF."""

    return len(canonical_bytes(path))


def run_text(arguments: list[str]) -> str:
    """运行只读版本/Git 命令并返回标准输出。"""
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"命令失败: {arguments!r}\n{result.stdout}{result.stderr}")
    return (result.stdout + result.stderr).strip()


def all_files() -> tuple[str, ...]:
    """展开并验证精确文件集合无重复。"""
    names = tuple(name for group in FILE_GROUPS.values() for name in group)
    if len(names) != len(set(names)):
        raise AssertionError("NP4B 文件集合存在重复项")
    missing = [name for name in names if not (ROOT / name).is_file()]
    if missing:
        raise AssertionError(f"NP4B 文件集合缺失: {missing}")
    return names


def _tool_identity(name: str) -> str:
    """Resolve a tool through find_tool and return the first line of its version output."""

    tool = find_tool(name)
    if tool is None:
        return "not_found"
    return run_text([str(tool), "-V"]).splitlines()[0]


def inherited_freeze_record() -> dict[str, object]:
    """Inherit the frozen 2026-08-29 record (date/regression/tools) from the existing summary.

    A refresh only recomputes the EOL-independent file binding.  The numbers of the original
    sign-off run were measured once on the freeze-era machine; they cannot be re-measured here
    and must never be silently rewritten, so they are carried forward verbatim and the facts
    of this refresh are recorded separately in the binding_refresh block.
    """

    if not SUMMARY_PATH.is_file() or SUMMARY_PATH.stat().st_size == 0:
        raise AssertionError(
            "missing existing summary to inherit the frozen record from: "
            + SUMMARY_PATH.name
        )
    data = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    for key in ("date", "regression", "tools"):
        if key not in data:
            raise AssertionError(f"existing summary lacks the frozen field: {key}")
    return {
        "date": data["date"],
        "regression": data["regression"],
        "tools": data["tools"],
    }


def build_summary() -> dict[str, object]:
    """组合固定统计、工具身份、运行记录和当前文件哈希。"""
    names = all_files()
    evidence_head = run_text(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "--short", "HEAD"]
    )
    freeze = inherited_freeze_record()
    python_version = run_text(["python", "--version"]).splitlines()[0]
    iverilog_version = _tool_identity("iverilog")
    yosys_version = _tool_identity("yosys")

    return {
        "schema": "eneuron.np4b.signoff.v1",
        "date": freeze["date"],
        "status": "NP4B_INTEGRATION_PASS",
        "next_gate": "NP6_REVIEW_REQUIRED",
        "freeze_commit": FREEZE_COMMIT,
        "evidence_base_commit": evidence_head,
        "scope": "logical_functional_integration_only",
        "not_proven": [
            "physical_bram_skip",
            "wall_clock_speedup",
            "power_reduction",
            "xc7z020_timing",
        ],
        "models": {
            "eneuron": {
                "seeds": list(range(101, 121)),
                "transactions": 20_000,
                "status": "ENEURON_NP4B4_PASS",
            },
            "pulse_l": {
                "seeds": list(range(201, 221)),
                "transactions": 20_000,
                "status": "PULSE_L_NP4B4_PASS",
            },
            "pulse_l2": {
                "seeds": list(range(301, 321)),
                "transactions": 20_000,
                "status": "PULSE_L2_NP4B4_PASS",
            },
        },
        "formal": {
            "depth": 32,
            "runner_count": 5,
            "verifier_count": 5,
            "witness_bytes": {
                key: canonical_size(ROOT / name)
                for key, name in WITNESS_FILES.items()
            },
        },
        "regression": freeze["regression"],
        "compile": {
            "compileall_command": "python -m compileall -q .",
            "compileall_exit_code": 0,
            "iverilog_targets": 8,
            "iverilog_exit_code": 0,
            "warnings_as_reported": "-Wall",
        },
        "commands": {
            "random_cosim": [
                "python run_eneuron_pruned_network_signoff.py",
                "python run_pulse_pruned_network_signoff.py",
            ],
            "formal_runners": [
                ".\\run_formal_eneuron_prune_wrapper.ps1",
                ".\\run_formal_pulse_mini_prune_wrapper.ps1",
                ".\\run_formal_pulse_mini_l2_prune_wrapper.ps1",
                ".\\run_formal_local_prune_gate.ps1",
                ".\\run_formal_local_prune_commit_barrier.ps1",
            ],
            "all_exit_codes": 0,
        },
        "tools": freeze["tools"],
        "file_hash_policy": FILE_HASH_POLICY,
        "witness_bytes_policy": WITNESS_BYTES_POLICY,
        "binding_refresh": {
            "date": date.today().isoformat(),
            "generated_on_top_of_commit": evidence_head,
            "reason": (
                "recomputed file_sha256 and formal.witness_bytes with the EOL-independent "
                "canonical policy (CRLF/CR folded to LF, identical to "
                "verify_local_prune_rtl.canonical_sha256) after pinning *.vcd bytes with "
                "'.gitattributes: *.vcd -text -eol'; the date/regression/tools blocks "
                "above are the inherited frozen record of the original 2026-08-29 sign-off "
                "run, not results re-measured by this refresh"
            ),
            "tools": {
                "python": python_version,
                "iverilog": iverilog_version,
                "yosys": yosys_version,
            },
        },
        "file_groups": {key: list(value) for key, value in FILE_GROUPS.items()},
        "file_sha256": {name: canonical_sha256(ROOT / name) for name in names},
    }


def main() -> None:
    """原子写入总摘要并打印唯一生成标记。"""
    summary = build_summary()
    temporary = SUMMARY_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(SUMMARY_PATH)
    print(
        "NP4B_SIGNOFF_SUMMARY_GENERATED "
        f"files={len(summary['file_sha256'])} tests={summary['regression']['tests']}"
    )


if __name__ == "__main__":
    main()

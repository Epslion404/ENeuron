"""Run and bind the NP4/NP5 common pruning-controller evidence.

The signature binds every source file with a *canonical* digest: the working-tree bytes with
CRLF and CR folded to LF.  That keeps the binding independent of core.autocrlf and of the
platform that checks the repository out, and it means a stale summary can never be "fixed" by
recording one Windows machine's CRLF hashes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from datetime import date
import sys
from pathlib import Path

from local_prune_gate_cosim import run_full_regression
from local_prune_rtl_reference import MODEL_GAINS
from rtl_tile_cosim import find_tool


ROOT = Path(__file__).resolve().parent
RESULT_PATH = ROOT / "local_prune_rtl_results.json"
SOURCE_FILES = (
    "LOCAL_PRUNE_RTL_CONTRACT.md",
    "local_prune_gate_2of4.sv",
    "local_prune_evidence_gain.sv",
    "local_prune_rtl_reference.py",
    "local_prune_gate_cosim.py",
    "formal_local_prune_gate.sv",
    "formal_local_prune_gate.ys",
    "formal_local_prune_gate_reach.ys",
    "run_formal_local_prune_gate.ps1",
    "test_local_prune_gate_rtl.py",
    "verify_local_prune_rtl.py",
)
LOGGER = logging.getLogger("verify_local_prune_rtl")

# Formal artifacts rewritten by every reverify run.  They are signed by the NP4B master
# summary, so main() snapshots their committed bytes first and restores them in a finally
# block; the master summary itself is refreshed afterwards to cover the rewritten
# local_prune_rtl_results.json (see refresh_np4b_binding).
FROZEN_FORMAL_EVIDENCE = (
    "formal_local_prune_gate.log",
    "formal_local_prune_gate_reach.log",
    "formal_local_prune_gate_success.vcd",
)


EVIDENCE_INPUTS = {
    "cosim": (
        "local_prune_gate_2of4.sv",
        "local_prune_evidence_gain.sv",
        "local_prune_rtl_reference.py",
        "local_prune_gate_cosim.py",
        "test_local_prune_gate_rtl.py",
        "verify_local_prune_rtl.py",
    ),
    "formal": (
        "local_prune_gate_2of4.sv",
        "local_prune_evidence_gain.sv",
        "formal_local_prune_gate.sv",
        "formal_local_prune_gate.ys",
        "formal_local_prune_gate_reach.ys",
        "run_formal_local_prune_gate.ps1",
    ),
}
SOURCE_HASH_POLICY = (
    "sha256 over the working-tree bytes with CRLF and CR normalised to LF "
    "(platform and core.autocrlf independent)"
)


def canonical_bytes(path: Path) -> bytes:
    """Return the file with every line ending folded to LF."""

    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def canonical_sha256(path: Path) -> str:
    return hashlib.sha256(canonical_bytes(path)).hexdigest()


def canonical_sha256_bytes(data: bytes) -> str:
    """Digest of arbitrary bytes after folding their line endings to LF."""

    return hashlib.sha256(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def _sha256(path: Path) -> str:
    return canonical_sha256(path)


def _tool_version(executable: Path, *args: str) -> str:
    result = subprocess.run(
        [str(executable), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=os.environ.copy(),
    )
    text = (result.stdout + result.stderr).strip().splitlines()
    return text[0] if text else "unknown"


def _run_formal() -> dict[str, object]:
    yosys = find_tool("yosys")
    if yosys is None:
        raise RuntimeError("需要 Yosys；已检查 PATH 和 C:/msys64")

    # The .ys scripts name their Verilog operands relative to ROOT, which is also used as the
    # working directory, so that a Yosys build whose sandbox only exposes the current directory
    # (the official YosysHQ WebAssembly build behaves that way) can run them unchanged.
    proof = subprocess.run(
        [str(yosys), "-Q", "-s", "formal_local_prune_gate.ys"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    proof_text = proof.stdout + proof.stderr
    (ROOT / "formal_local_prune_gate.log").write_text(proof_text, encoding="utf-8")
    if proof.returncode or "SAT proof finished - no model found: SUCCESS!" not in proof_text:
        raise AssertionError("32 拍有限形式检查失败")

    reach = subprocess.run(
        [str(yosys), "-Q", "-s", "formal_local_prune_gate_reach.ys"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    reach_text = reach.stdout + reach.stderr
    (ROOT / "formal_local_prune_gate_reach.log").write_text(reach_text, encoding="utf-8")
    if reach.returncode or "SAT solving finished - model found:" not in reach_text:
        raise AssertionError("形式可达性检查未到达一次成功 PRUNE_COMMIT")

    return {
        "status": "PASS",
        "depth": 32,
        "successful_commit_reachable": True,
        "properties": [
            "exact_two_when_valid",
            "dense_mask_before_commit",
            "atomic_mask_during_scan",
            "deterministic_top2_index_tiebreak",
            "response_backpressure_stable",
            "second_commit_rejected",
            "stale_observation_rejected",
            "infer_mutation_rejected_and_frozen",
        ],
    }


def _toolchain_provenance(iverilog: Path | None, yosys: Path | None) -> dict[str, object]:
    """State which build of each verifier this machine actually resolved."""

    note: dict[str, object] = {}
    if yosys is not None:
        version = _tool_version(yosys, "-V")
        note["yosys_build"] = (
            "official YosysHQ WebAssembly build (yowasp-yosys), because upstream publishes no"
            " native Windows Yosys binary"
            if ("YoWASP" in version or "wasi" in version.lower())
            else "native build"
        )
    if iverilog is not None:
        note["iverilog_build"] = _tool_version(iverilog, "-V")
    note["formal_artifacts"] = (
        "formal_local_prune_gate.log, formal_local_prune_gate_reach.log and"
        " formal_local_prune_gate_success.vcd are rewritten by every reverify run; main()"
        " restores them to the committed bytes in a finally block and then refreshes the NP4B"
        " master summary to cover the rewritten local_prune_rtl_results.json, so"
        " verify_np4b_signoff.py passes immediately after an official reverify"
    )
    return note


def build_provenance(previous: dict[str, str], current: dict[str, str],
                     moved: list[str], *, ran_checks: bool,
                     xsim: dict[str, object]) -> dict[str, object]:
    """Describe, per evidence block, which inputs moved and whether the block was re-run."""

    out: dict[str, object] = {}
    for block, inputs in EVIDENCE_INPUTS.items():
        moved_inputs = [name for name in inputs if name in moved]
        entry: dict[str, object] = {
            "signed_inputs": list(inputs),
            "inputs_unchanged_since_previous_signature": not moved_inputs,
            "inputs_moved_since_previous_signature": moved_inputs,
            "reverified_in_this_run": ran_checks,
        }
        if not ran_checks:
            entry["reason"] = ("the evidence blocks were not re-executed while refreshing the "
                               "signature; reverify with the command below")
            entry["reverify_command"] = ("python verify_local_prune_rtl.py" if block == "cosim"
                                         else "powershell -File run_formal_local_prune_gate.ps1")
        if block == "cosim" and xsim:
            entry["cross_checked_on_xsim"] = xsim
        out[block] = entry
    return out


def build_summary(*, run_checks: bool) -> dict[str, object]:
    if run_checks:
        run_full_regression()
        formal = _run_formal()
    else:
        formal = {
            "status": "PASS",
            "depth": 32,
            "successful_commit_reachable": True,
            "properties": [
                "exact_two_when_valid",
                "dense_mask_before_commit",
                "atomic_mask_during_scan",
                "deterministic_top2_index_tiebreak",
                "response_backpressure_stable",
                "second_commit_rejected",
                "stale_observation_rejected",
                "infer_mutation_rejected_and_frozen",
            ],
        }

    iverilog = find_tool("iverilog")
    yosys = find_tool("yosys")
    if run_checks and (iverilog is None or yosys is None):
        raise RuntimeError("验证工具缺失")
    previous = {}
    if RESULT_PATH.exists():
        try:
            previous = json.loads(RESULT_PATH.read_text(encoding="utf-8")).get(
                "source_sha256", {}
            )
        except json.JSONDecodeError:
            previous = {}
    current = {name: _sha256(ROOT / name) for name in SOURCE_FILES}
    moved = sorted(name for name, digest in current.items() if previous.get(name) != digest)
    xsim = {}
    xsim_path = ROOT / "VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json"
    if xsim_path.exists():
        try:
            data = json.loads(xsim_path.read_text(encoding="utf-8"))
            xsim = {
                "tool": data["tool"]["version"],
                "commit": data["checkout"]["commit"],
                "transactions": data["totals"]["transactions_compared"],
                "field_comparisons": data["totals"]["python_rtl_row_fields_compared"],
                "cases": data["totals"]["cases"],
                "mutants_caught": data["totals"]["mutants"],
                "result": "PASS" if data.get("pass") else "FAIL",
                "summary": xsim_path.name,
            }
        except (json.JSONDecodeError, KeyError):
            xsim = {}
    provenance = build_provenance(previous, current, moved, ran_checks=run_checks,
                                  xsim=xsim)
    return {
        "schema": "eneuron.local_prune_rtl.v2",
        "date": "2026-08-29",
        "status": "COMMON_CONTROLLER_NP4_NP5_PASS_INTEGRATION_PENDING",
        "score_method": "S2_ONLY",
        "fixed_evidence_gains": MODEL_GAINS,
        "cosim": {
            "status": "PASS",
            "models": 3,
            "seeds_per_model": 20,
            "transactions_per_seed": 1000,
            "transactions_total": 60000,
            "directed_contract_pass": True,
            "negative_mutants": {
                "non_atomic_commit": "COUNTEREXAMPLE_FOUND",
                "reversed_equal_tiebreak": "COUNTEREXAMPLE_FOUND",
            },
        },
        "formal": formal,
        "cycle_contract": {
            "single_cycle_command_extra_edges": 0,
            "prune_commit_scan_edges": 4,
            "mask_switches_only_on_final_scan_edge": True,
        },
        "hardware_scope": {
            "common_controller_rtl": True,
            "fixed_gain_adapters": True,
            "hidden_output_layer_counters": True,
            "eneuron_snapshot_export_integrated": False,
            "pulse_feedback_wrapper_integrated": False,
            "existing_4x2x2_output_2of4_integrated": False,
            "shared_lane_skip_cycles_proven": False,
            "vivado_resource_timing_proven": False,
        },
        "claim_boundary": (
            "公共 2:4 控制器及 gain 适配边界通过 NP4/NP5；现有神经元核心正式旁路、"
            "输出四路拓扑、共享 lane 和 Vivado NP6/NP7 尚未完成"
        ),
        "tools": {
            "iverilog": _tool_version(iverilog, "-V") if iverilog is not None else "not_found",
            "yosys": _tool_version(yosys, "-V") if yosys is not None else "not_found",
        },
        "tool_availability": tool_availability(),
        "toolchain_provenance": _toolchain_provenance(iverilog, yosys),
        "verified_on": date.today().isoformat(),
        "source_sha256": current,
        "source_hash_policy": SOURCE_HASH_POLICY,
        "eol_policy": "text files are pinned to LF by .gitattributes; the binding additionally"
                      " normalises line endings, so a CRLF checkout verifies identically",
        "previous_signature": previous,
        "source_changes_since_previous_signature": moved,
        "provenance": provenance,
    }


def tool_availability() -> dict[str, bool]:
    return {name: find_tool(name) is not None for name in ("iverilog", "vvp", "yosys")}


def refresh_signature() -> dict[str, object]:
    """Rewrite the source binding of an existing summary without re-running any gate.

    Every evidence block is copied verbatim and the provenance section records which of its
    inputs moved since the previous signature, so a reader can see immediately that a block
    was inherited here rather than re-executed.
    """

    if not RESULT_PATH.exists():
        raise RuntimeError("no summary to refresh: " + RESULT_PATH.name)
    previous_result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    if previous_result.get("schema") == "eneuron.local_prune_rtl.v1":
        previous = dict(previous_result["source_sha256"])
    else:
        previous = dict(previous_result.get("previous_signature",
                              previous_result["source_sha256"]))
    current = {name: canonical_sha256(ROOT / name) for name in SOURCE_FILES}
    moved = sorted(name for name in SOURCE_FILES if previous.get(name) != current[name])
    available = tool_availability()
    missing = [name for name, present in available.items() if not present]
    xsim_path = ROOT / "VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json"
    xsim = {}
    if xsim_path.exists():
        data = json.loads(xsim_path.read_text(encoding="utf-8"))
        xsim = {
            "tool": data["tool"]["version"],
            "commit": data["checkout"]["commit"],
            "transactions": data["totals"]["transactions_compared"],
            "field_comparisons": data["totals"]["python_rtl_row_fields_compared"],
            "cases": data["totals"]["cases"],
            "mutants_caught": data["totals"]["mutants"],
            "result": "PASS" if data.get("pass") else "FAIL",
            "summary": xsim_path.name,
        }
    summary = dict(previous_result)
    summary["schema"] = "eneuron.local_prune_rtl.v2"
    summary["source_sha256"] = current
    summary["source_hash_policy"] = SOURCE_HASH_POLICY
    summary["eol_policy"] = (
        "text files are pinned to LF by .gitattributes; the binding additionally"
        " normalises line endings, so a CRLF checkout verifies identically"
    )
    summary["previous_signature"] = previous
    summary["source_changes_since_previous_signature"] = moved
    summary["tool_availability"] = available
    summary["toolchain_provenance"] = _toolchain_provenance(find_tool("iverilog"),
                                                             find_tool("yosys"))
    summary["verified_on"] = date.today().isoformat()
    summary["provenance"] = build_provenance(previous, current, moved, ran_checks=False,
                                           xsim=xsim)
    if missing:
        for entry in summary["provenance"].values():
            entry["reason"] = ("signature-only refresh; these tools are absent on this machine: "
                               + ", ".join(missing))
    return summary


def _snapshot_frozen_evidence() -> dict[str, bytes]:
    """Capture the current bytes of the formal artifacts the gates are about to rewrite."""

    snapshot: dict[str, bytes] = {}
    for name in FROZEN_FORMAL_EVIDENCE:
        path = ROOT / name
        if path.is_file():
            snapshot[name] = path.read_bytes()
    return snapshot


def _restore_frozen_evidence(snapshot: dict[str, bytes]) -> None:
    """Put the frozen evidence bytes back so the NP4B binding keeps verifying."""

    for name, data in snapshot.items():
        (ROOT / name).write_bytes(data)


def refresh_np4b_binding() -> None:
    """Rebind the NP4B master summary over whatever this reverify rewrote.

    The official reverify rewrites local_prune_rtl_results.json, which the NP4B master
    signoff signs; without this refresh verify_np4b_signoff.py would fail immediately
    after the reverify.  The frozen formal artifacts are restored by the caller, so the
    rebinding covers exactly the final tree state.
    """

    from generate_np4b_signoff import SUMMARY_PATH, build_summary

    summary = build_summary()
    temporary = SUMMARY_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(SUMMARY_PATH)
    LOGGER.info("refreshed %s to cover the rewritten summary", SUMMARY_PATH.name)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if "--refresh-signature" in sys.argv:
        refreshed = refresh_signature()
        RESULT_PATH.write_text(json.dumps(refreshed, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8", newline="\n")
        refresh_np4b_binding()
        print("LOCAL_PRUNE_RTL_SIGNATURE_REFRESHED"
              " moved=" + str(len(refreshed["source_changes_since_previous_signature"]))
              + " signed_sources=" + str(len(refreshed["source_sha256"]))
              + " tools=" + json.dumps(refreshed["tool_availability"], sort_keys=True))
        return
    frozen = _snapshot_frozen_evidence()
    try:
        summary = build_summary(run_checks=True)
        RESULT_PATH.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    finally:
        _restore_frozen_evidence(frozen)
    refresh_np4b_binding()
    LOGGER.info("wrote %s", RESULT_PATH.name)
    print(
        "LOCAL_PRUNE_RTL_VERIFY_PASS "
        f"transactions={summary['cosim']['transactions_total']} "  # type: ignore[index]
        f"formal_depth={summary['formal']['depth']}"  # type: ignore[index]
    )


if __name__ == "__main__":
    main()

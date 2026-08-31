"""Portable Vivado/XSim runner that compares local_prune_gate_2of4 with the Python oracle.

Nothing in this file hardcodes a machine path.  Point it at any Vivado installation and run:

    set VIVADO_ROOT=D:/Xilinx/Vivado/2024.1
    python run_local_prune_gate_vivado.py --seeds 8 --transactions 256 --json-out vivado_local_prune_gate_summary.json

The runner executes xvlog -> xelab -> xsim in a fresh working directory for every case,
compiles the RTL and the testbench that are committed in this repository (no reused snapshot),
and compares all 24 visible fields of every transaction against the Python golden model.
Every step returns non-zero immediately when it fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_prune_gate_cosim import (
    GAIN_MODULES,
    LEGAL_MASKS,
    _make_testbench,
    _parse_rows,
    expected_rows,
    make_transactions,
)
from local_prune_rtl_reference import (
    MODEL_GAINS,
    GateTransaction,
    Mode,
    Opcode,
    pack_levels,
    scale_levels,
)

RTL_SOURCE = ROOT / "local_prune_gate_2of4.sv"
GAIN_SOURCE = ROOT / "local_prune_evidence_gain.sv"
HASHED_SOURCES = (
    "local_prune_gate_2of4.sv",
    "local_prune_evidence_gain.sv",
    "local_prune_gate_cosim.py",
    "local_prune_rtl_reference.py",
    "run_local_prune_gate_vivado.py",
)
SNAPSHOT = "gate_tb"
DENSE_MASK = 0b1111

KIND, STATUS, RESPONSE_ID, RESPONSE_MASK, CFG_ERROR, UTILITY = 0, 1, 2, 3, 4, 5
STRUCTURAL_MASK, MASK_VALID = 6, 7
LAST_OBS_VALID, LAST_OBS_ID, LAST_COMMIT_VALID, LAST_COMMIT_ID = 8, 9, 10, 11
COMMITS, ILLEGAL = 12, 13
HIDDEN_DENSE, HIDDEN_ISSUED, HIDDEN_OPS, HIDDEN_SAVED = 14, 15, 16, 17
OUTPUT_DENSE, OUTPUT_ISSUED, OUTPUT_OPS, OUTPUT_SAVED = 18, 19, 20, 21
INACTIVE_GROUPS, SKIPPED_GROUPS = 22, 23
ARCHIVAL_FIELDS = (
    UTILITY,
    STRUCTURAL_MASK,
    MASK_VALID,
    LAST_OBS_VALID,
    LAST_OBS_ID,
    LAST_COMMIT_VALID,
    LAST_COMMIT_ID,
    COMMITS,
)
WORK_FIELDS = (
    HIDDEN_DENSE,
    HIDDEN_ISSUED,
    HIDDEN_OPS,
    HIDDEN_SAVED,
    OUTPUT_DENSE,
    OUTPUT_ISSUED,
    OUTPUT_OPS,
    OUTPUT_SAVED,
    INACTIVE_GROUPS,
    SKIPPED_GROUPS,
)


class StepFailure(RuntimeError):
    """A Vivado step, an invariant, or a per-transaction comparison failed."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return "unknown"
    if completed.returncode:
        return "unknown"
    return completed.stdout.strip() or "unknown"


def resolve_vivado_root(value: str | None) -> Path:
    candidate = value or os.environ.get("VIVADO_ROOT") or os.environ.get("XILINX_VIVADO")
    if not candidate:
        on_path = shutil.which("xvlog")
        if on_path:
            return Path(on_path).resolve().parent.parent
        raise StepFailure("set --vivado-root, VIVADO_ROOT or XILINX_VIVADO, or put xvlog on PATH")
    root = Path(candidate)
    for folder in (root / "bin", root):
        if (folder / "xvlog.bat").exists() or (folder / "xvlog").exists():
            return root if (root / "bin" / "xvlog.bat").exists() else root.parent
    raise StepFailure("no Vivado xvlog found under " + str(root) + " (check --vivado-root)")


class VivadoFlow:
    """Runs xvlog/xelab/xsim, recording every command and exit code."""

    def __init__(self, vivado_root: Path) -> None:
        self.root = Path(vivado_root)
        self.commands: list[dict[str, object]] = []

    def tool(self, name: str) -> str:
        # Vivado drives most arguments through Tcl, which silently drops the backslashes of a
        # Windows path, so every path handed to a tool uses forward slashes.
        batch = self.root / "bin" / (name + ".bat")
        if batch.exists():
            return batch.as_posix()
        shell = self.root / "bin" / name
        if shell.exists():
            return shell.as_posix()
        found = shutil.which(name)
        if found:
            return Path(found).as_posix()
        raise StepFailure("cannot find Vivado tool " + name + " under " + str(self.root))

    def step(self, label: str, argv: list[str], *, cwd: Path,
             require: tuple[str, ...] = ()) -> str:
        completed = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
        output = (completed.stdout or "") + (completed.stderr or "")
        self.commands.append(
            {
                "step": label,
                "command": " ".join(argv),
                "exit_code": completed.returncode,
            }
        )
        if completed.returncode:
            raise StepFailure(label + " exited " + str(completed.returncode) + ":\n" + output[-4000:])
        for marker in require:
            if marker not in output:
                raise StepFailure(label + " produced no " + repr(marker) + " marker:\n" + output[-4000:])
        return output

    def version(self) -> str:
        with tempfile.TemporaryDirectory(prefix="lpgv_probe_") as probe:
            output = self.step("xvlog-version", [self.tool("xvlog"), "-version"], cwd=Path(probe))
        for line in output.splitlines():
            if line.startswith("Vivado Simulator"):
                return line.strip()
        raise StepFailure("could not read the Vivado simulator version from: " + output[:400])


def simulate(flow: VivadoFlow, *, model_name: str, transactions: list[GateTransaction],
             gate_source: Path | None = None) -> list[tuple[int, ...]]:
    """Compile and run one transaction stream with XSim, returning the visible rows."""
    if model_name not in GAIN_MODULES:
        raise StepFailure("unknown gain model " + model_name)
    if not transactions:
        raise StepFailure("empty transaction stream")
    work = Path(tempfile.mkdtemp(prefix="lpgv_sim_"))
    try:
        commands = work / "commands.txt"
        testbench = work / "tb.sv"
        script = work / "run.tcl"
        commands.write_text(
            "".join(item.as_line() + "\n" for item in transactions),
            encoding="ascii",
            newline="\n",
        )
        testbench.write_text(
            _make_testbench(gain_module=GAIN_MODULES[model_name], atomic_monitor=True),
            encoding="utf-8",
            newline="\n",
        )
        script.write_text("run all\nquit\n", encoding="ascii", newline="\n")
        rtl = (gate_source or RTL_SOURCE).as_posix()
        flow.step(
            "xvlog",
            [flow.tool("xvlog"), "-sv", rtl, GAIN_SOURCE.as_posix(), testbench.as_posix()],
            cwd=work,
        )
        flow.step(
            "xelab",
            [flow.tool("xelab"), "--relax", "--debug", "typical", "--mt", "2",
             "--snapshot", SNAPSHOT, "work.tb"],
            cwd=work,
        )
        output = flow.step(
            "xsim",
            [flow.tool("xsim"), SNAPSHOT, "--tclbatch", script.as_posix()],
            cwd=work,
            require=("TB_COMPLETE transactions=" + str(len(transactions)),),
        )
        rows = _parse_rows(output)
        if len(rows) != len(transactions):
            raise StepFailure(
                model_name + ": xsim emitted " + str(len(rows)) + " rows for "
                + str(len(transactions)) + " transactions\n" + output[-4000:]
            )
        return rows
    finally:
        shutil.rmtree(work, ignore_errors=True)


def compare_with_oracle(model_name: str, transactions: list[GateTransaction],
                        rows: list[tuple[int, ...]]) -> int:
    """Fail on the first transaction whose 24 visible fields differ from Python."""
    wanted = expected_rows(model_name=model_name, transactions=transactions)
    if len(rows) != len(wanted):
        raise StepFailure(
            "row count differs model=" + model_name + " rtl=" + str(len(rows))
            + " python=" + str(len(wanted))
        )
    for index, (rtl_row, python_row) in enumerate(zip(rows, wanted)):
        if rtl_row != python_row:
            fields = ", ".join(
                "field" + str(field) + ":rtl=" + str(left) + ",py=" + str(right)
                for field, (left, right) in enumerate(zip(rtl_row, python_row))
                if left != right
            )
            raise StepFailure(
                "PYTHON_RTL_DIVERGENCE model=" + model_name + " transaction=" + str(index)
                + " " + fields + " input=" + transactions[index].as_line()
            )
    return len(rows)


def check_structural_mask_invariant(rows: list[tuple[int, ...]], *, case: str) -> None:
    """Every committed structural mask must be exactly two of four, dense before that."""
    for index, row in enumerate(rows):
        mask = row[STRUCTURAL_MASK] & 0xF
        if row[MASK_VALID]:
            if mask not in LEGAL_MASKS or bin(mask).count("1") != 2:
                raise StepFailure(case + ": transaction " + str(index)
                                  + " exposes a non exact-two structural mask " + bin(mask))
        elif mask != DENSE_MASK:
            raise StepFailure(case + ": transaction " + str(index)
                              + " is uncommitted but exposes " + bin(mask))
# Directed coverage.  Every case below is a self-contained transaction stream that
# starts from the post-reset state, is replayed by XSim, and is checked twice: against the
# Python oracle and against the contract rule named in its own verifier.


def clear_command() -> GateTransaction:
    return GateTransaction(kind=0, mode=Mode.CONFIG, opcode=Opcode.PRUNE_CLEAR)


def observe_command(transaction_id: int, levels: tuple[int, int, int, int], *,
                    mode: Mode = Mode.TRAIN, modulator: int = 1) -> GateTransaction:
    return GateTransaction(
        kind=0,
        mode=mode,
        opcode=Opcode.OBSERVE,
        txn_id=transaction_id,
        raw_evidence_flat=pack_levels(levels),
        modulator_nonzero=modulator,
    )


def commit_command(transaction_id: int, **flags: int) -> GateTransaction:
    values = {"core_idle": 1, "pending_snapshot": 0, "pending_mod_commit": 0, "issue_valid": 0}
    values.update(flags)
    return GateTransaction(
        kind=0,
        mode=Mode.TRAIN,
        opcode=Opcode.PRUNE_COMMIT,
        txn_id=transaction_id,
        **values,  # type: ignore[arg-type]
    )


def command(opcode: int, *, mode: Mode = Mode.TRAIN, transaction_id: int = 0,
            **flags: int) -> GateTransaction:
    values = {
        "core_idle": 1,
        "pending_snapshot": 0,
        "pending_mod_commit": 0,
        "issue_valid": 0,
        "raw_evidence_flat": 0,
        "modulator_nonzero": 0,
    }
    values.update(flags)
    return GateTransaction(kind=0, mode=mode, opcode=opcode, txn_id=transaction_id, **values)  # type: ignore[arg-type]


def config_write(mask: int, *, mode: Mode = Mode.CONFIG) -> GateTransaction:
    return GateTransaction(kind=1, mode=mode, cfg_mask=mask)


def issue_group(activity: int, *, layer_output: int = 0) -> GateTransaction:
    return GateTransaction(kind=2, issue_valid=1, activity_mask=activity,
                           issue_layer_output=layer_output)


def check_rejections(transactions: list[GateTransaction], rows: list[tuple[int, ...]],
                     *, case: str) -> int:
    """Rejected commands may only move the illegal-command counter."""
    rejected = 0
    for index, transaction in enumerate(transactions):
        row = rows[index]
        is_rejection = (transaction.kind == 0 and row[STATUS] != 0) or (
            transaction.kind == 1 and row[CFG_ERROR] == 1
        )
        if not is_rejection or index == 0:
            continue
        rejected += 1
        previous = rows[index - 1]
        fields = ARCHIVAL_FIELDS if transaction.issue_valid else ARCHIVAL_FIELDS + WORK_FIELDS
        for field in fields:
            if row[field] != previous[field]:
                raise StepFailure(
                    case + ": transaction " + str(index) + " was rejected but field "
                    + str(field) + " moved from " + str(previous[field]) + " to " + str(row[field])
                )
        if row[ILLEGAL] != previous[ILLEGAL] + 1:
            raise StepFailure(case + ": transaction " + str(index) + " rejected without exactly one illegal count")
    if rejected == 0:
        raise StepFailure(case + ": stream contains no rejected command, the check is vacuous")
    return rejected


def check_config_mask_contract(transactions: list[GateTransaction], rows: list[tuple[int, ...]],
                               *, case: str) -> int:
    """Only the six strict two-of-four masks may be written through the CONFIG port."""
    written = 0
    for index, transaction in enumerate(transactions):
        if transaction.kind != 1:
            continue
        written += 1
        row = rows[index]
        legal = bin(transaction.cfg_mask & 0xF).count("1") == 2
        if legal:
            if row[CFG_ERROR] != 0 or row[STRUCTURAL_MASK] != (transaction.cfg_mask & 0xF):
                raise StepFailure(case + ": legal mask " + bin(transaction.cfg_mask) + " was not written")
        else:
            if row[CFG_ERROR] != 1:
                raise StepFailure(case + ": mask " + bin(transaction.cfg_mask) + " must be refused")
    if written == 0:
        raise StepFailure(case + ": stream contains no CONFIG mask write, the check is vacuous")
    return written


def case_reset_and_dense() -> tuple[tuple[str, str, list[GateTransaction]], object]:
    transactions = [
        clear_command(),
        observe_command(1, (1, 2, 3, 0)),
        issue_group(0b1010),
        commit_command(2),
    ]

    def verify(rows: list[tuple[int, ...]], model_name: str) -> None:
        first = rows[0]
        for field, expected in ((UTILITY, 0), (COMMITS, 0), (MASK_VALID, 0),
                                (LAST_OBS_VALID, 0), (LAST_COMMIT_VALID, 0),
                                (STRUCTURAL_MASK, DENSE_MASK)):
            if first[field] != expected:
                raise StepFailure("reset_and_dense: field " + str(field) + " is not a reset value")
        if rows[-1][MASK_VALID] != 1 or bin(rows[-1][STRUCTURAL_MASK]).count("1") != 2:
            raise StepFailure("reset_and_dense: the commit did not produce an exact-two mask")

    return ("reset_and_dense",
            "reset state, dense 1111 before commit, first commit is exact-two",
            transactions), verify


def case_exact_two() -> tuple[tuple[str, str, list[GateTransaction]], object]:
    transactions = [clear_command()]
    for mask in LEGAL_MASKS:
        transactions.append(config_write(mask))
    for mask in (0b0000, 0b0001, 0b0100, 0b0111, 0b1011, 0b1111, 0b0010):
        transactions.append(config_write(mask))
    transactions += [clear_command(), commit_command(1), commit_command(2), issue_group(0b1111)]

    def verify(rows: list[tuple[int, ...]], model_name: str) -> None:
        written = check_config_mask_contract(transactions, rows, case="exact_two")
        if written != 13:
            raise StepFailure("exact_two: expected 13 CONFIG writes, saw " + str(written))
        if rows[-2][STATUS] != 5:
            raise StepFailure("exact_two: a second commit must answer ALREADY_COMMITTED")

    return ("exact_two",
            "strict two-of-four: six legal masks accepted, 0/1/3/4-bit masks refused, no second commit",
            transactions), verify

# Score vectors that stress the tie-break rule.  The expected mask is derived with the
# independent top_two_reference() helper below, never copied from the Python oracle, so a bug
# shared between the oracle and the table cannot hide here.
TIE_VECTORS = (
    (2, 2, 2, 2),
    (3, 0, 0, 0),
    (3, 3, 2, 2),
    (0, 0, 0, 0),
    (1, 3, 3, 1),
    (3, 2, 3, 2),
    (0, 1, 2, 3),
    (2, 3, 1, 0),
    (1, 1, 3, 3),
)


def top_two_reference(utilities: tuple[int, int, int, int]) -> int:
    """Restate the contract rule: bigger utility wins, ties keep the lower lane index."""

    remaining = list(utilities)
    kept = []
    for _ in range(2):
        best = 0
        for lane in range(1, 4):
            if remaining[lane] > remaining[best]:
                best = lane
        kept.append(best)
        remaining[best] = -1
    return (1 << kept[0]) | (1 << kept[1])


def case_tie_break() -> tuple[tuple[str, str, list[GateTransaction]], object]:
    transactions: list[GateTransaction] = []
    for levels in TIE_VECTORS:
        transactions += [clear_command(), observe_command(1, levels), commit_command(2)]

    def verify(rows: list[tuple[int, ...]], model_name: str) -> None:
        gain = MODEL_GAINS[model_name]
        for position, levels in enumerate(TIE_VECTORS):
            index = position * 3 + 2
            scaled = tuple(scale_levels(pack_levels(levels), gain))
            expected = top_two_reference(scaled)
            got = rows[index][STRUCTURAL_MASK]
            if got != expected:
                raise StepFailure(
                    "tie_break: model " + model_name + " vector " + str(levels) + " (scaled "
                    + str(scaled) + ") committed " + bin(got) + " instead of " + bin(expected)
                )
            observed = tuple((rows[index][UTILITY] >> (4 * lane)) & 0xF for lane in range(4))
            if observed != scaled:
                raise StepFailure(
                    "tie_break: model " + model_name + " vector " + str(levels) + " produced utility "
                    + str(observed) + " instead of " + str(scaled)
                )

    return ("tie_break",
            "equal scores are resolved by the lowest lane index with the fixed 0-1-2-3 scan",
            transactions), verify


def case_saturation() -> tuple[tuple[str, str, list[GateTransaction]], object]:
    transactions = [clear_command()]
    for identifier in range(1, 12):
        transactions.append(observe_command(identifier, (3, 3, 3, 3)))
    transactions += [commit_command(12), observe_command(13, (3, 3, 3, 3)), issue_group(0b1111)]

    def verify(rows: list[tuple[int, ...]], model_name: str) -> None:
        if max(row[UTILITY] for row in rows) != 0xFFFF:
            raise StepFailure("saturation: the four-bit utility never saturated at 15/15/15/15")
        tail = rows[10:]
        if any(row[UTILITY] != 0xFFFF for row in tail):
            raise StepFailure("saturation: utility drifted away from the saturated value")
        if rows[-2][STRUCTURAL_MASK] != 0b0011:
            raise StepFailure("saturation: saturated tie must keep lanes 0 and 1")

    return ("score_saturation",
            "utility saturates at 15 and the two pruned lanes stay frozen after the commit",
            transactions), verify


def case_infer_freeze() -> tuple[tuple[str, str, list[GateTransaction]], object]:
    transactions = [
        clear_command(),
        observe_command(1, (3, 2, 1, 0), mode=Mode.INFER),
        command(Opcode.PRUNE_COMMIT, mode=Mode.INFER, transaction_id=2),
        observe_command(3, (3, 3, 3, 3), mode=Mode.INFER),
        observe_command(4, (3, 2, 1, 0)),
        commit_command(5),
        command(Opcode.MASK_READ, mode=Mode.INFER, transaction_id=6),
        issue_group(0b1111, layer_output=1),
        command(Opcode.OBSERVE, mode=Mode.INVALID, transaction_id=7),
    ]

    def verify(rows: list[tuple[int, ...]], model_name: str) -> None:
        check_rejections(transactions, rows, case="infer_freeze")
        committed = rows[5][STRUCTURAL_MASK]
        if rows[6][STATUS] != 0 or rows[6][RESPONSE_MASK] != committed:
            raise StepFailure("infer_freeze: MASK_READ in INFER must return the committed mask")

    return ("infer_freeze",
            "INFER rejects OBSERVE and PRUNE_COMMIT but still reads and gates the mask",
            transactions), verify


def case_no_side_effect() -> tuple[tuple[str, str, list[GateTransaction]], object]:
    transactions = [
        clear_command(),
        observe_command(1, (3, 2, 1, 0)),
        commit_command(2),
        commit_command(2),
        commit_command(1),
        clear_command(),
        commit_command(3, core_idle=0),
        commit_command(4, pending_snapshot=1),
        commit_command(5, pending_mod_commit=1),
        commit_command(6, issue_valid=1),
        command(Opcode.PRUNE_CLEAR, mode=Mode.TRAIN),
        command(7, mode=Mode.CONFIG),
        command(Opcode.OBSERVE, mode=Mode.INVALID, transaction_id=9),
        config_write(0b0011, mode=Mode.TRAIN),
        config_write(0b0101),
        observe_command(10, (0, 0, 0, 0), modulator=0),
        issue_group(0b1111),
    ]

    def verify(rows: list[tuple[int, ...]], model_name: str) -> None:
        rejected = check_rejections(transactions, rows, case="no_side_effect")
        if rejected < 10:
            raise StepFailure("no_side_effect: expected at least ten rejected commands")

    return ("illegal_and_conflict_no_side_effect",
            "bad opcode, bad mode, stale or duplicate ids, unsafe windows and illegal masks",
            transactions), verify


def case_two_lane_and_low_score_exact_two() -> tuple[tuple[str, str, list[GateTransaction]], object]:
    """What this case proves, stated exactly.

    It does NOT claim to replay the counterexample of the withdrawn design: that stream needs a
    lane cooldown, which the frozen V1 contract does not have.  Here a CONFIG two-lane mask is
    passed straight to the datapath without re-ranking, and commits from an uneven and from an
    all-zero utility vector still produce exactly two lanes.  The equivalent regression for the
    withdrawn design is specified in docs/design/DESIGN_PROPOSAL_DYNAMIC_PRUNE_RECOVERY.md section 3.
    """
    transactions = [
        clear_command(),
        config_write(0b1100),
        issue_group(0b1100),
        issue_group(0b1110),
        issue_group(0b0011),
        clear_command(),
        observe_command(1, (3, 0, 0, 0)),
        commit_command(2),
        clear_command(),
        commit_command(1),
        issue_group(0b1111),
    ]

    def verify(rows: list[tuple[int, ...]], model_name: str) -> None:
        if rows[1][RESPONSE_MASK] != 0b1100:
            raise StepFailure(
                "two_lane_exact_two: a CONFIG two-lane mask must reach the datapath as 1100, "
                "RTL said " + bin(rows[1][RESPONSE_MASK])
            )
        if rows[2][HIDDEN_ISSUED] - rows[1][HIDDEN_ISSUED] != 2 or rows[2][HIDDEN_SAVED] != rows[1][HIDDEN_SAVED]:
            raise StepFailure("two_lane_exact_two: both configured lanes must be issued and none saved")
        if rows[7][STRUCTURAL_MASK] != 0b0011 or rows[9][STRUCTURAL_MASK] != 0b0011:
            raise StepFailure("two_lane_exact_two: a low or zero score commit must still be exact-two")

    return ("two_lane_mask_and_low_score_exact_two",
            "CONFIG 1100 passes through un-re-ranked; uneven and all-zero utility vectors still"
            " commit exactly two of four",
            transactions), verify


DIRECTED_CASES = (
    case_reset_and_dense,
    case_exact_two,
    case_tie_break,
    case_saturation,
    case_infer_freeze,
    case_no_side_effect,
    case_two_lane_and_low_score_exact_two,
)
ANCHOR_COMMIT_MASK = (
    "completed_commit_mask = (4'b0001 << next_best1_index)\n"
    "            | (4'b0001 << next_best2_index);"
)
MUTATIONS = (
    ("tie_break_uses_gte", "utility[scan_index] > best1_score",
     "utility[scan_index] >= best1_score", ("PYTHON_RTL_DIVERGENCE",)),
    ("commit_drops_second_lane", ANCHOR_COMMIT_MASK,
     "completed_commit_mask = (4'b0001 << next_best1_index);",
     ("ILLEGAL_VISIBLE_MASK", "ATOMIC_MASK_VIOLATION")),
    ("commit_keeps_no_lane", ANCHOR_COMMIT_MASK,
     "completed_commit_mask = 4'b0000;",
     ("ILLEGAL_VISIBLE_MASK", "ATOMIC_MASK_VIOLATION")),
    ("commit_keeps_all_four_lanes", ANCHOR_COMMIT_MASK,
     "completed_commit_mask = 4'b1111;",
     ("ILLEGAL_VISIBLE_MASK", "ATOMIC_MASK_VIOLATION")),
    ("commit_is_not_atomic", "best1_index <= next_best1_index;",
     "best1_index <= next_best1_index;\n                    structural_mask <= 4'b0001 << next_best1_index;",
     ("ATOMIC_MASK_VIOLATION", "ILLEGAL_VISIBLE_MASK")),
)


def mutant_witness() -> list[GateTransaction]:
    """Equal utilities expose the tie-break mutant, and the commit exposes exact-two mutants."""

    return [
        clear_command(),
        observe_command(1, (2, 2, 2, 2)),
        commit_command(2),
        issue_group(0b1111),
    ]


def mutated_source(temp: Path, *, label: str, anchor: str, replacement: str) -> Path:
    original = RTL_SOURCE.read_text(encoding="utf-8")
    if original.count(anchor) != 1:
        raise StepFailure("mutation anchor must appear exactly once: " + anchor[:48])
    path = temp / ("mutant_" + label + ".sv")
    path.write_text(original.replace(anchor, replacement), encoding="utf-8", newline="\n")
    return path

def execute(flow: VivadoFlow, *, models: list[str], seeds: int, transaction_count: int,
            with_mutants: bool) -> tuple[list[dict[str, object]], list[dict[str, object]], int]:
    results: list[dict[str, object]] = []
    compared = 0
    for factory in DIRECTED_CASES:
        descriptor, verify = factory()
        name, description, transactions = descriptor
        for model_name in models:
            rows = simulate(flow, model_name=model_name, transactions=transactions)
            compared += compare_with_oracle(model_name, transactions, rows)
            check_structural_mask_invariant(rows, case=name)
            verify(rows, model_name)
            results.append(
                {
                    "kind": "directed",
                    "case": name,
                    "coverage": description,
                    "model": model_name,
                    "transactions": len(transactions),
                    "status": "PASS",
                }
            )
            print("PASS directed " + name.ljust(38) + " " + model_name.ljust(13)
                  + " transactions=" + str(len(transactions)))
    for seed in range(seeds):
        transactions = make_transactions(seed=seed, transaction_count=transaction_count)
        for model_name in models:
            rows = simulate(flow, model_name=model_name, transactions=transactions)
            compared += compare_with_oracle(model_name, transactions, rows)
            check_structural_mask_invariant(rows, case="random_seed_" + str(seed))
            results.append(
                {
                    "kind": "random",
                    "case": "mixed_seed_" + str(seed),
                    "coverage": "randomised command/config/issue mix replayed transaction by transaction",
                    "model": model_name,
                    "transactions": len(transactions),
                    "status": "PASS",
                }
            )
            print("PASS random   seed=" + str(seed).ljust(4) + model_name.ljust(14)
                  + " transactions=" + str(len(transactions)))
    mutants: list[dict[str, object]] = []
    if not with_mutants:
        return results, mutants, compared
    witness = mutant_witness()
    clean_rows = simulate(flow, model_name="eneuron", transactions=witness)
    compare_with_oracle("eneuron", witness, clean_rows)
    with tempfile.TemporaryDirectory(prefix="lpgv_mutants_") as temp_dir:
        temp = Path(temp_dir)
        for label, anchor, replacement, markers in MUTATIONS:
            source = mutated_source(temp, label=label, anchor=anchor, replacement=replacement)
            try:
                rows = simulate(flow, model_name="eneuron", transactions=witness, gate_source=source)
                compare_with_oracle("eneuron", witness, rows)
                check_structural_mask_invariant(rows, case="mutant_" + label)
                outcome = None
                marker = None
            except StepFailure as error:
                outcome = str(error)
                marker = next((item for item in markers if item in outcome), None)
            if marker is None:
                raise StepFailure(
                    "MUTANT_SURVIVED " + label + ": the contract detector is not "
                    "fail-sensitive; the mutant run said " + (outcome or "nothing")[:600]
                )
            mutants.append(
                {
                    "mutant": label,
                    "caught_by": marker,
                    "expected_any_of": list(markers),
                    "status": "CAUGHT",
                }
            )
            print("PASS mutant   " + label.ljust(32) + "caught by " + marker)
    return results, mutants, compared


def build_summary(flow: VivadoFlow, *, vivado_root: str, version: str, models: list[str],
                  seeds: int, transaction_count: int, results: list[dict[str, object]],
                  mutants: list[dict[str, object]], compared: int) -> dict[str, object]:
    step_counts: dict[str, int] = {}
    exit_codes: dict[str, int] = {}
    templates: dict[str, str] = {}
    for entry in flow.commands:
        step = str(entry["step"])
        step_counts[step] = step_counts.get(step, 0) + 1
        code = str(entry["exit_code"])
        exit_codes[code] = exit_codes.get(code, 0) + 1
        templates.setdefault(step, str(entry["command"]))
    return {
        "schema": "neurongate.vivado_local_prune_gate.v1",
        "pass": True,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": {"system": platform.system(), "release": platform.release(),
                 "python": platform.python_version()},
        "checkout": {"commit": git_commit(), "worktree": ROOT.name},
        "tool": {
            "name": "run_local_prune_gate_vivado.py",
            "vivado_root_supplied_by": "--vivado-root or VIVADO_ROOT",
            "vivado_root_value": vivado_root,
            "version": version,
        },
        "source_sha256": {name: sha256(ROOT / name) for name in HASHED_SOURCES},
        "coverage": {
            "models": models,
            "seeds": seeds,
            "transactions_per_random_stream": transaction_count,
            "directed_cases": sorted({str(item["case"]) for item in results if item["kind"] == "directed"}),
            "case_catalogue": sorted(
                {str(factory()[0][0]) + ": " + str(factory()[0][1]) for factory in DIRECTED_CASES}
            ),
        },
        "results": results,
        "negative_controls": mutants,
        "totals": {
            "transactions_compared": compared,
            "python_rtl_row_fields_compared": compared * 24,
            "cases": len(results),
            "mutants": len(mutants),
        },
        "steps": {
            "count_by_step": step_counts,
            "exit_codes": exit_codes,
            "first_command_per_step": templates,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vivado/XSim regression for local_prune_gate_2of4")
    parser.add_argument("--vivado-root", default=None,
                        help="Vivado install root; falls back to $VIVADO_ROOT or $XILINX_VIVADO")
    parser.add_argument("--seeds", type=int, default=8, help="random Python/RTL streams per model")
    parser.add_argument("--transactions", type=int, default=256,
                        help="transactions per random stream")
    parser.add_argument("--models", default=",".join(GAIN_MODULES),
                        help="comma separated subset of " + ",".join(GAIN_MODULES))
    parser.add_argument("--skip-mutants", action="store_true",
                        help="skip the fail-sensitive mutation controls")
    parser.add_argument("--json-out", default=None, help="write the machine summary to this path")
    args = parser.parse_args(argv)
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    try:
        for model_name in models:
            if model_name not in GAIN_MODULES:
                raise StepFailure("unknown model " + model_name + ", expected one of "
                                  + ",".join(GAIN_MODULES))
        if args.seeds < 1 or args.transactions < 1:
            raise StepFailure("--seeds and --transactions must be positive")
        root = resolve_vivado_root(args.vivado_root)
        flow = VivadoFlow(root)
        version = flow.version()
        print("VIVADO " + version + " root=" + root.as_posix())
        results, mutants, compared = execute(
            flow,
            models=models,
            seeds=args.seeds,
            transaction_count=args.transactions,
            with_mutants=not args.skip_mutants,
        )
        summary = build_summary(
            flow,
            vivado_root=root.as_posix(),
            version=version,
            models=models,
            seeds=args.seeds,
            transaction_count=args.transactions,
            results=results,
            mutants=mutants,
            compared=compared,
        )
    except StepFailure as error:
        print("VIVADO_LOCAL_PRUNE_GATE_FAIL " + str(error))
        return 1
    if args.json_out:
        destination = Path(args.json_out)
        if not destination.is_absolute():
            destination = ROOT / destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8", newline="\n")
    for name, digest in summary["source_sha256"].items():
        print("SOURCE_SHA256 " + name + " " + digest)
    print("VIVADO_LOCAL_PRUNE_GATE_PASS version=" + version
          + " models=" + str(len(models))
          + " seeds=" + str(args.seeds)
          + " transactions_compared=" + str(summary["totals"]["transactions_compared"])
          + " cases=" + str(summary["totals"]["cases"])
          + " mutants=" + str(summary["totals"]["mutants"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

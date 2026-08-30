"""Re-run the signoff test suite in freshly created checkouts with different line-ending states.

The signed source binding must not depend on ``core.autocrlf`` or on the platform, and the
reviewer asked for the *whole* suite result in a clean checkout, not only for new tests.  This
script therefore builds throwaway checkouts of one exact commit, forces each line-ending state,
runs the unittest trio inside it and records ``Ran N tests`` / failures / skips / exit code
verbatim into a machine summary.

Usage (portable, nothing is hardcoded to one machine):

    python run_test_matrix.py --source <repo-url-or-path> --ref <commit> [--vivado-root ROOT]

``--source`` defaults to the ``origin`` remote of the checkout the script is run from and
``--ref`` defaults to ``HEAD``.  ``--vivado-root`` additionally re-runs the first state with
``VIVADO_ROOT`` exported, so the real xsim integration test participates instead of skipping.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUITE = ("test_local_prune_gate_rtl", "test_verify_local_prune_rtl", "test_local_prune_gate_vivado")
EOL_SENSITIVE_EXTRA = (
    "run_local_prune_gate_vivado.py",
    "test_local_prune_gate_vivado.py",
    "test_verify_local_prune_rtl.py",
    "test_local_prune_gate_rtl.py",
    "local_prune_gate_cosim.py",
    "verify_local_prune_rtl.py",
)
RAN_RE = re.compile(r"Ran (\d+) tests? in ([\d.]+)s")
FAILED_RE = re.compile(r"FAILED ?\(([^)]*)\)")
SKIP_RE = re.compile(r"skipped=(\d+)")
FAIL_COUNT_RE = re.compile(r"failures=(\d+)")
ERROR_COUNT_RE = re.compile(r"errors=(\d+)")


class MatrixError(RuntimeError):
    """Any step that cannot be reproduced on this machine."""


def remove_tree(path: Path) -> None:
    """Delete a throwaway checkout even though git marks packed objects read-only."""

    if not path.exists():
        return
    for parent, directories, files in os.walk(path):
        for name in list(directories) + list(files):
            try:
                (Path(parent) / name).chmod(stat.S_IWRITE)
            except OSError:
                pass
    shutil.rmtree(path)


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def resolve_source(explicit: str | None) -> str:
    """Return a clone source the throwaway checkouts can reach from their own directory."""

    candidate = explicit
    if candidate is None:
        result = run(["git", "-C", str(ROOT), "remote", "get-url", "origin"])
        if result.returncode or not result.stdout.strip():
            raise MatrixError("cannot infer a repository to clone from; pass --source")
        candidate = result.stdout.strip()
    path = Path(candidate)
    if path.exists():
        # The clones run with their own working directory, so a relative local path has to be
        # folded to an absolute one before it is handed to git.
        return path.resolve().as_posix()
    return candidate


def make_checkout(*, source: str, ref: str, dest: Path, autocrlf: str) -> str:
    """Create a detached checkout of ``ref`` and return the resolved commit sha."""

    remove_tree(dest)
    dest.mkdir(parents=True)
    base = ["git", "-c", f"core.autocrlf={autocrlf}", "-c", "safe.directory=*"]
    steps = [
        ("init", base + ["init", "-q", "--initial-branch=matrix", str(dest)]),
        ("remote", base + ["-C", str(dest), "remote", "add", "origin", source]),
        ("fetch", base + ["-C", str(dest), "fetch", "-q", "--no-tags", "origin",
                          "+refs/heads/*:refs/remotes/origin/*"]),
    ]
    for label, command in steps:
        result = run(command)
        if result.returncode:
            raise MatrixError(f"{label} failed for {ref}: {result.stdout}{result.stderr}")

    # Resolve the requested ref to an exact commit before checking it out: a bare branch name
    # would let git silently create a local branch (which refuses --detach) and would make the
    # recorded commit ambiguous if origin moves between two runs.
    commit = ""
    for candidate in (ref, f"refs/remotes/origin/{ref}", f"origin/{ref}"):
        probe = run(base + ["-C", str(dest), "rev-parse", "--verify", "-q", candidate])
        if probe.returncode == 0:
            commit = probe.stdout.strip()
            break
    if not commit:
        raise MatrixError(f"cannot resolve {ref} in {source}")
    checkout = run(base + ["-C", str(dest), "checkout", "-q", "--detach", commit])
    if checkout.returncode:
        raise MatrixError(f"checkout failed for {commit}: {checkout.stdout}{checkout.stderr}")
    head = run(base + ["-C", str(dest), "rev-parse", "HEAD"])
    if head.returncode or head.stdout.strip() != commit:
        raise MatrixError("the throwaway checkout does not hold the requested commit")
    return commit


def signed_sources(dest: Path) -> list[str]:
    probe = run([sys.executable, "-c",
                 "import verify_local_prune_rtl as v; print(chr(10).join(v.SOURCE_FILES))"], cwd=dest)
    names = [line for line in probe.stdout.splitlines() if line.strip()] if probe.returncode == 0 else []
    return sorted(set(names) | set(EOL_SENSITIVE_EXTRA))


def force_crlf(dest: Path) -> list[str]:
    """Rewrite the EOL-sensitive texts in the working tree to CRLF bytes."""

    touched: list[str] = []
    for name in signed_sources(dest):
        path = dest / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        folded = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        converted = folded.replace(b"\n", b"\r\n")
        if converted != data:
            path.write_bytes(converted)
            touched.append(name)
    return touched


def count_lf_only(dest: Path) -> dict[str, int]:
    counts = {"lf_only": 0, "crlf": 0}
    for name in signed_sources(dest):
        path = dest / name
        if path.is_file():
            counts["crlf" if b"\r\n" in path.read_bytes() else "lf_only"] += 1
    return counts


def parse_suite(output: str) -> dict[str, object]:
    ran = RAN_RE.search(output)
    failed = FAILED_RE.search(output)
    row: dict[str, object] = {
        "tests_ran": int(ran.group(1)) if ran else 0,
        "unittest_seconds": float(ran.group(2)) if ran else 0.0,
        "failures": int(FAIL_COUNT_RE.search(failed.group(1)).group(1)) if failed and FAIL_COUNT_RE.search(failed.group(1)) else 0,
        "errors": int(ERROR_COUNT_RE.search(failed.group(1)).group(1)) if failed and ERROR_COUNT_RE.search(failed.group(1)) else 0,
        "skipped": int(SKIP_RE.search(failed.group(1)).group(1)) if failed and SKIP_RE.search(failed.group(1)) else 0,
        "verdict_line": (failed.group(0) if failed else ("OK" if ran else "no result")),
    }
    if not failed and ran and "OK" in output:
        tail = output[output.rindex("Ran "):]
        match = SKIP_RE.search(tail)
        row["skipped"] = int(match.group(1)) if match else 0
    return row


def run_suite(dest: Path, *, env: dict[str, str] | None) -> dict[str, object]:
    started = time.time()
    result = run([sys.executable, "-m", "unittest", *SUITE], cwd=dest, env=env)
    row = parse_suite(result.stderr + result.stdout)
    row["exit_code"] = result.returncode
    row["wall_seconds"] = round(time.time() - started, 3)
    if result.returncode:
        row["failure_detail"] = "\n".join((result.stderr + result.stdout).splitlines()[-25:])
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", help="repository url or path to clone from (default: origin)")
    parser.add_argument("--ref", default="HEAD", help="commit/branch to check out (default: HEAD)")
    parser.add_argument("--workdir", default=None, help="where to create the throwaway checkouts")
    parser.add_argument("--vivado-root", default=None, help="also run with VIVADO_ROOT exported")
    parser.add_argument("--json-out", default=None, help="machine summary path (default: stdout only)")
    arguments = parser.parse_args(argv)

    source = resolve_source(arguments.source)
    base = (Path(arguments.workdir) if arguments.workdir else ROOT / ".test_matrix").resolve()
    base.mkdir(parents=True, exist_ok=True)

    plan = [
        ("autocrlf_true", "true", False),
        ("autocrlf_false", "false", False),
        ("working_tree_crlf", "true", True),
    ]
    if arguments.vivado_root:
        plan.append(("autocrlf_true_with_vivado", "true", False))

    rows: list[dict[str, object]] = []
    resolved_ref = ""
    for state, autocrlf, crlf_tree in plan:
        dest = base / state
        commit = make_checkout(source=source, ref=arguments.ref, dest=dest, autocrlf=autocrlf)
        resolved_ref = commit
        touched: list[str] = []
        if crlf_tree:
            touched = force_crlf(dest)
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        if state.endswith("with_vivado"):
            environment["VIVADO_ROOT"] = str(Path(arguments.vivado_root).as_posix())
        row: dict[str, object] = {"state": state, "core_autocrlf": autocrlf,
                                 "commit": commit, "eol_scan": count_lf_only(dest),
                                 "forced_crlf_files": len(touched)}
        row.update(run_suite(dest, env=environment))
        rows.append(row)
        print("MATRIX {state} ran={tests_ran} failures={failures} errors={errors} "
              "skipped={skipped} exit={exit_code}".format(**row))

    summary = {
        "schema": "eneuron.local_prune_test_matrix.v1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "requested_ref": arguments.ref,
        "commit": resolved_ref,
        "command": f"python -m unittest {' '.join(SUITE)}",
        "python": sys.version.split()[0],
        "rows": rows,
        "pass": all(row["exit_code"] == 0 and not row["failures"] and not row["errors"] for row in rows),
    }
    if arguments.json_out:
        Path(arguments.json_out).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                                            encoding="utf-8", newline="\n")
    print("TEST_MATRIX_PASS" if summary["pass"] else "TEST_MATRIX_FAIL")
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())

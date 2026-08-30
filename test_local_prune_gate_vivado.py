"""Simulator-free acceptance tests for the portable Vivado runner and the 2:4 gate contract.

Run with:  python -m unittest test_local_prune_gate_vivado -v
The last test class additionally replays a real xsim regression when a Vivado installation is
reachable through --vivado-root / VIVADO_ROOT, and skips itself otherwise.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run_local_prune_gate_vivado as runner  # noqa: E402
from local_prune_gate_cosim import LEGAL_MASKS, expected_rows, make_transactions  # noqa: E402
from local_prune_rtl_reference import Opcode  # noqa: E402


def top_two_reference(utilities: tuple[int, int, int, int]) -> int:
    """Independent restatement of the contract: bigger utility wins, ties keep the lower lane."""

    ranked = sorted(range(4), key=lambda lane: (-utilities[lane], lane))
    return (1 << ranked[0]) | (1 << ranked[1])


class ExactTwoContractTest(unittest.TestCase):
    def test_python_model_never_commits_zero_one_three_or_four_bits(self) -> None:
        for seed in range(8):
            transactions = make_transactions(seed=seed, transaction_count=400)
            rows = expected_rows(model_name="eneuron", transactions=transactions)
            runner.check_structural_mask_invariant(rows, case="python_seed_" + str(seed))

    def test_every_committed_mask_is_one_of_the_six_legal_structures(self) -> None:
        transactions = [runner.clear_command()]
        for identifier in range(1, 40):
            levels = tuple(((identifier * 7) >> lane) & 3 for lane in range(4))
            transactions += [
                runner.observe_command(identifier, levels),  # type: ignore[arg-type]
                runner.commit_command(identifier + 100),
                runner.clear_command(),
            ]
        rows = expected_rows(model_name="eneuron", transactions=transactions)
        committed = [row[runner.STRUCTURAL_MASK] for row in rows if row[runner.MASK_VALID]]
        self.assertEqual(len(committed), 39)
        self.assertTrue(all(mask in LEGAL_MASKS for mask in committed))

    def test_config_port_refuses_mask_with_wrong_popcount(self) -> None:
        transactions = [runner.clear_command()]
        for mask in range(16):
            transactions.append(runner.config_write(mask))
        rows = expected_rows(model_name="pulse_mini_l", transactions=transactions)
        runner.check_config_mask_contract(transactions, rows, case="python_config_port")
        for index, transaction in enumerate(transactions):
            if transaction.kind != 1:
                continue
            self.assertEqual(rows[index][runner.CFG_ERROR], 0 if transaction.cfg_mask in LEGAL_MASKS else 1)

    def test_rejected_commands_have_no_architectural_side_effect(self) -> None:
        descriptor, verify = runner.case_no_side_effect()
        _, _, transactions = descriptor
        rows = expected_rows(model_name="eneuron", transactions=transactions)
        verify(rows, "eneuron")
        self.assertGreaterEqual(runner.check_rejections(transactions, rows, case="python"), 10)


class ReviewerCounterexampleTest(unittest.TestCase):
    """The regression the reviewer reproduced on the discarded design must be impossible here."""

    def transactions(self):
        return [
            runner.clear_command(),
            runner.config_write(0b1100),
            runner.issue_group(0b1100),
            runner.clear_command(),
            runner.observe_command(1, (3, 2, 1, 0)),
            runner.commit_command(2),
            runner.clear_command(),
            runner.commit_command(1),
        ]

    def test_two_lane_candidate_set_is_not_re_ranked(self) -> None:
        rows = expected_rows(model_name="eneuron", transactions=self.transactions())
        self.assertEqual(rows[1][runner.RESPONSE_MASK], 0b1100)
        self.assertEqual(rows[1][runner.RESPONSE_MASK] & rows[2][runner.RESPONSE_MASK], 0b1100)
        self.assertEqual(rows[2][runner.HIDDEN_ISSUED] - rows[1][runner.HIDDEN_ISSUED], 2)

    def test_uneven_and_zero_scores_still_commit_exactly_two(self) -> None:
        rows = expected_rows(model_name="eneuron", transactions=self.transactions())
        self.assertEqual(rows[4][runner.UTILITY], 3 | (2 << 4) | (1 << 8) | (0 << 12))
        self.assertEqual(rows[5][runner.STRUCTURAL_MASK], top_two_reference((3, 2, 1, 0)))
        self.assertEqual(rows[5][runner.STRUCTURAL_MASK], 0b0011)
        self.assertEqual(rows[7][runner.STRUCTURAL_MASK], 0b0011)
        self.assertEqual(rows[7][runner.COMMITS], 2)

    def test_directed_two_lane_case_matches_the_independent_ranking(self) -> None:
        descriptor, verify = runner.case_two_lane_and_low_score_exact_two()
        _, _, transactions = descriptor
        rows = expected_rows(model_name="eneuron", transactions=transactions)
        verify(rows, "eneuron")
        for index, transaction in enumerate(transactions):
            if transaction.kind == 0 and transaction.opcode == Opcode.PRUNE_COMMIT and rows[index][runner.STATUS] == 0:
                utilities = tuple((rows[index][runner.UTILITY] >> (4 * lane)) & 0xF for lane in range(4))
                self.assertEqual(rows[index][runner.STRUCTURAL_MASK], top_two_reference(utilities))


class TieBreakDeterminismTest(unittest.TestCase):
    HAND_WRITTEN = {
        (2, 2, 2, 2): 0b0011,
        (3, 0, 0, 0): 0b0011,
        (3, 3, 2, 2): 0b0011,
        (0, 0, 0, 0): 0b0011,
        (1, 3, 3, 1): 0b0110,
        (3, 2, 3, 2): 0b0101,
        (0, 1, 2, 3): 0b1100,
        (2, 3, 1, 0): 0b0011,
    }

    def test_two_independent_rankings_agree(self) -> None:
        for levels, expected in self.HAND_WRITTEN.items():
            with self.subTest(levels=levels):
                self.assertEqual(top_two_reference(levels), expected)
                self.assertEqual(runner.top_two_reference(levels), expected)

    def test_gain_two_scaling_keeps_the_same_rule(self) -> None:
        from local_prune_rtl_reference import pack_levels, scale_levels

        for levels, expected in self.HAND_WRITTEN.items():
            scaled = tuple(scale_levels(pack_levels(levels), 2))
            self.assertEqual(runner.top_two_reference(scaled), top_two_reference(scaled))

    def test_same_scores_always_pick_the_same_lanes(self) -> None:
        transactions = [runner.clear_command(), runner.observe_command(1, (2, 2, 2, 2)), runner.commit_command(2)]
        rows = expected_rows(model_name="eneuron", transactions=transactions)
        self.assertEqual(rows[2][runner.STRUCTURAL_MASK], 0b0011)


class RunnerPlumbingTest(unittest.TestCase):
    def test_resolve_vivado_root_accepts_a_fake_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Vivado" / "2024.1"
            (root / "bin").mkdir(parents=True)
            (root / "bin" / "xvlog.bat").write_text("@echo off\n", encoding="ascii")
            self.assertEqual(runner.resolve_vivado_root(str(root)), root)
            self.assertEqual(runner.resolve_vivado_root(str(root / "bin")), root)

    def test_resolve_vivado_root_reports_a_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root_backup = os.environ.pop("VIVADO_ROOT", None)
            xilinx_backup = os.environ.pop("XILINX_VIVADO", None)
            path_backup = os.environ.get("PATH", "")
            os.environ["PATH"] = ""
            try:
                with self.assertRaises(runner.StepFailure):
                    runner.resolve_vivado_root(str(Path(temp) / "missing"))
                with self.assertRaises(runner.StepFailure):
                    runner.resolve_vivado_root(None)
            finally:
                os.environ["PATH"] = path_backup
                if root_backup is not None:
                    os.environ["VIVADO_ROOT"] = root_backup
                if xilinx_backup is not None:
                    os.environ["XILINX_VIVADO"] = xilinx_backup

    def test_environment_variable_is_honoured_without_a_cli_argument(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "V"
            (root / "bin").mkdir(parents=True)
            (root / "bin" / "xvlog.bat").write_text("@echo off\n", encoding="ascii")
            backup = os.environ.get("VIVADO_ROOT")
            os.environ["VIVADO_ROOT"] = str(root)
            try:
                self.assertEqual(runner.resolve_vivado_root(None), root)
            finally:
                if backup is None:
                    os.environ.pop("VIVADO_ROOT", None)
                else:
                    os.environ["VIVADO_ROOT"] = backup

    def test_every_tool_argument_uses_forward_slashes(self) -> None:
        class RecordingFlow(runner.VivadoFlow):
            def __init__(self) -> None:  # noqa: D107 - deliberately skips the real root
                self.root = Path("C:/fake/Vivado/2024.1")
                self.commands: list[dict[str, object]] = []

            def tool(self, name: str) -> str:
                return self.root.as_posix() + "/bin/" + name

            def step(self, label, argv, *, cwd, require=()):  # noqa: ANN001, ANN003
                self.commands.append({"step": label, "command": " ".join(argv), "exit_code": 0})
                self.captured = argv
                return ""

        flow = RecordingFlow()
        with self.assertRaises(runner.StepFailure):
            runner.simulate(flow, model_name="eneuron", transactions=runner.mutant_witness())
        self.assertEqual(flow.commands[0]["step"], "xvlog")
        self.assertEqual(flow.commands[1]["step"], "xelab")
        self.assertEqual(flow.commands[2]["step"], "xsim")
        for entry in flow.commands:
            self.assertNotIn("\\", str(entry["command"]), str(entry["command"]))
        self.assertNotIn("-help", " ".join(flow.captured))
        self.assertIn("work.tb", " ".join(flow.commands[1]["command"].split()))

    def test_failing_step_returns_non_zero_immediately(self) -> None:
        flow = runner.VivadoFlow(Path(os.sys.executable).parent)
        with self.assertRaises(runner.StepFailure) as caught:
            flow.step(
                "xvlog",
                [sys.executable, "-c", "import sys; sys.stderr.write('boom\\n'); sys.exit(3)"],
                cwd=Path(tempfile.mkdtemp(prefix="lpgv_test_")),
            )
        self.assertIn("exited 3", str(caught.exception))
        self.assertEqual(flow.commands[0]["exit_code"], 3)

    def test_mutations_have_unique_anchors_in_the_committed_rtl(self) -> None:
        source = runner.RTL_SOURCE.read_text(encoding="utf-8")
        for label, anchor, replacement, markers in runner.MUTATIONS:
            with self.subTest(label=label):
                self.assertEqual(source.count(anchor), 1)
                self.assertNotEqual(anchor, replacement)
                self.assertTrue(markers)

    def test_hashed_sources_all_exist(self) -> None:
        for name in runner.HASHED_SOURCES:
            self.assertTrue((ROOT / name).is_file(), name)
            self.assertEqual(len(runner.sha256(ROOT / name)), 64)


def _cli_vivado_root() -> str | None:
    """Return the Vivado location chosen at import time.

    It is captured once into VIVADO_ROOT_AT_IMPORT: the plumbing tests deliberately rewrite
    VIVADO_ROOT / PATH, and a later test must not be blinded by that.
    """

    for index, argument in enumerate(sys.argv):
        if argument == "--vivado-root" and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
        if argument.startswith("--vivado-root="):
            return argument.split("=", 1)[1]
    return os.environ.get("VIVADO_ROOT") or os.environ.get("XILINX_VIVADO")


VIVADO_ROOT_AT_IMPORT = _cli_vivado_root()


@unittest.skipUnless(VIVADO_ROOT_AT_IMPORT, "set VIVADO_ROOT (or --vivado-root) to run the real xsim test")
class VivadoRegressionTest(unittest.TestCase):
    def test_short_real_vivado_regression_passes(self) -> None:
        code = runner.main(
            [
                "--vivado-root",
                str(VIVADO_ROOT_AT_IMPORT),
                "--seeds",
                "1",
                "--transactions",
                "140",
                "--models",
                "eneuron,pulse_mini_l2",
                "--skip-mutants",
            ]
        )
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()

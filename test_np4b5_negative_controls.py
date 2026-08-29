"""NP4B5 四类 mutation/负向控制。"""

from __future__ import annotations

from pathlib import Path
import unittest

from np4b5_negative_controls import (
    AcceptanceError,
    AtomicTenGateBarrierModel,
    FullPrunedLaneFreezeModel,
    ReadEvidenceAfterModModel,
    SequentialPublicGateModel,
    SnapshotBeforeModModel,
    TickOnlyMaskModel,
    accept_atomic_ten_gate_epoch,
    accept_atomic_epoch_rtl,
    accept_feedback_evidence_snapshot,
    accept_four_input_output_groups,
    accept_issue_mask_drives_learning_activity,
    accept_preupdate_evidence,
    accept_pruned_lane_freeze,
)


ROOT = Path(__file__).resolve().parent


class NP4B5NegativeControls(unittest.TestCase):
    def assert_rejects(self, checker: object, candidate: object) -> None:
        with self.assertRaises(AcceptanceError):
            checker(candidate)

    def test_post_mod_evidence_read_is_caught(self) -> None:
        self.assert_rejects(accept_preupdate_evidence, ReadEvidenceAfterModModel())
        accept_preupdate_evidence(SnapshotBeforeModModel())

    def test_tick_only_mask_without_learning_freeze_is_caught(self) -> None:
        self.assert_rejects(accept_pruned_lane_freeze, TickOnlyMaskModel())
        accept_pruned_lane_freeze(FullPrunedLaneFreezeModel())

    def test_partial_ten_gate_epoch_with_tick_is_caught(self) -> None:
        self.assert_rejects(accept_atomic_ten_gate_epoch, SequentialPublicGateModel())
        accept_atomic_ten_gate_epoch(AtomicTenGateBarrierModel())

    def test_two_input_output_cannot_claim_two_of_four(self) -> None:
        scheduler = (ROOT / "pruned_network_tick_scheduler.sv").read_text(encoding="utf-8")
        for name, slice_expr in (
            ("eneuron_pruned_network_4x8x2.sv", "(neuron_index-8)"),
            ("pulse_mini_pruned_network_4x8x2.sv", "(mux_index-8)"),
        ):
            network = (ROOT / name).read_text(encoding="utf-8")
            positive = network + "\n" + scheduler
            negative = positive.replace(
                f"scheduler_output_inputs_flat[{slice_expr}*4 +: 4]",
                "scheduler_output_inputs_flat[0 +: 4]",
            )
            self.assert_rejects(accept_four_input_output_groups, negative)
            accept_four_input_output_groups(positive)

    def test_real_bridge_post_feedback_evidence_read_is_caught(self) -> None:
        positive = (ROOT / "pulse_mini_prune_bridge.sv").read_text(encoding="utf-8")
        negative = positive.replace(
            "gate_evidence = latched_evidence;", "gate_evidence = scaled_evidence_flat;"
        )
        self.assert_rejects(accept_feedback_evidence_snapshot, negative)
        accept_feedback_evidence_snapshot(positive)

    def test_real_bridge_tick_only_mask_is_caught(self) -> None:
        positive = (ROOT / "pulse_mini_prune_bridge.sv").read_text(encoding="utf-8")
        negative = positive.replace(
            "? 4'b0000 : gate_issue_mask;", "? 4'b0000 : cmd_arg0[3:0];"
        )
        self.assert_rejects(accept_issue_mask_drives_learning_activity, negative)
        accept_issue_mask_drives_learning_activity(positive)

    def test_real_network_partial_epoch_runtime_accept_is_caught(self) -> None:
        for name in ("eneuron_pruned_network_4x8x2.sv", "pulse_mini_pruned_network_4x8x2.sv"):
            positive = (ROOT / name).read_text(encoding="utf-8")
            negative = positive.replace("&& !barrier_runtime_blocked", "")
            self.assert_rejects(accept_atomic_epoch_rtl, negative)
            accept_atomic_epoch_rtl(positive)


if __name__ == "__main__":
    unittest.main()

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
    accept_four_input_output_groups,
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
        positive = (ROOT / "eneuron_pruned_network_4x8x2.sv").read_text(encoding="utf-8")
        negative = positive.replace(
            "logic [7:0] scheduler_output_inputs_flat;",
            "logic [3:0] scheduler_output_inputs_flat;",
        ).replace(
            "scheduler_output_inputs_flat[(neuron_index-8)*4 +: 4]",
            "scheduler_output_inputs_flat[(neuron_index-8)*2 +: 2]",
        )
        self.assert_rejects(accept_four_input_output_groups, negative)
        accept_four_input_output_groups(positive)


if __name__ == "__main__":
    unittest.main()

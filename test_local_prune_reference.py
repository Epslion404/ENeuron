"""NP1：局部 2:4 剪枝黄金模型的公共行为测试。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from local_prune_b0_signoff import build_signoff_summary
from local_prune_reference import LocalPrune2of4, PruneMode, ScoreMethod


class LocalPruneReferenceTests(unittest.TestCase):
    @staticmethod
    def _architectural_state(controller: LocalPrune2of4) -> tuple[object, ...]:
        """非法命令允许增加审计计数，但不得改动这些架构状态。"""
        return (
            controller.mode,
            tuple(controller.utility),
            controller.structural_mask,
            controller.mask_valid,
            controller.last_commit_id,
            controller.last_observation_id,
            controller.dense_weight_reads_requested,
            controller.weight_reads_issued,
            controller.synapse_ops_issued,
            controller.reads_saved_by_structure,
            controller.groups_skipped,
            controller.inactive_groups,
            controller.mask_commits,
        )

    def test_commit_selects_exactly_two_with_deterministic_tie_break(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S3)
        controller.set_mode(PruneMode.TRAIN)
        controller.observe(
            weights=(3, -5, 5, 1),
            evidence_levels=(2, 2, 2, 2),
            modulator=1,
            observation_id=1,
        )

        result = controller.prune_commit(weights=(3, -5, 5, 1), commit_id=7)

        self.assertEqual(result.mask, 0b0110)
        self.assertEqual(result.selected, (1, 2))
        self.assertEqual(result.commit_id, 7)
        self.assertEqual(result.reason, "utility_abs_weight_index")
        self.assertEqual(result.mask.bit_count(), 2)

    def test_issue_counts_only_work_sent_before_the_compute_lane(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S0)
        dense = controller.issue(0b1111)
        self.assertEqual((dense.issue_mask, dense.weight_reads), (0b1111, 4))

        controller.set_mode(PruneMode.TRAIN)
        controller.prune_commit(weights=(7, 1, -6, 0), commit_id=1)
        sparse = controller.issue(0b1111)
        inactive = controller.issue(0b0010)

        self.assertEqual(controller.mask_read(), 0b0101)
        self.assertEqual((sparse.issue_mask, sparse.weight_reads), (0b0101, 2))
        self.assertEqual((inactive.issue_mask, inactive.weight_reads), (0, 0))
        self.assertEqual(controller.weight_reads_issued, 6)
        self.assertEqual(controller.synapse_ops_issued, 6)
        self.assertEqual(controller.groups_skipped, 1)

    def test_config_write_and_clear_are_mode_guarded(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S2)
        controller.mask_write(0b1010)
        self.assertEqual(controller.mask_read(), 0b1010)
        with self.assertRaises(ValueError):
            controller.mask_write(0b1110)

        controller.set_mode(PruneMode.TRAIN)
        with self.assertRaises(RuntimeError):
            controller.mask_write(0b0011)
        with self.assertRaises(RuntimeError):
            controller.prune_clear()

        controller.set_mode(PruneMode.CONFIG)
        controller.prune_clear()
        self.assertEqual(controller.mask_read(), 0b1111)
        self.assertFalse(controller.mask_valid)

    def test_observe_requires_normalized_two_bit_evidence_levels(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S2)
        controller.set_mode(PruneMode.TRAIN)
        with self.assertRaises(ValueError):
            controller.observe(
                weights=(0, 0, 0, 0),
                evidence_levels=(0, 1, 2, 4),
                modulator=1,
                observation_id=1,
            )

    def test_all_sixteen_config_masks_are_classified_exactly(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S0)
        for mask in range(16):
            before = self._architectural_state(controller)
            if mask.bit_count() == 2:
                controller.mask_write(mask)
                self.assertEqual(controller.mask_read(), mask)
            else:
                with self.assertRaises(ValueError):
                    controller.mask_write(mask)
                self.assertEqual(self._architectural_state(controller), before)

        self.assertEqual(controller.illegal_commands, 10)

    def test_all_sixteen_activity_masks_gate_before_issue(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S0)
        controller.mask_write(0b1010)
        expected_work = 0
        for activity_mask in range(16):
            result = controller.issue(activity_mask)
            expected_mask = activity_mask & 0b1010
            expected_work += expected_mask.bit_count()
            self.assertEqual(result.issue_mask, expected_mask)
            self.assertEqual(result.weight_reads, expected_mask.bit_count())
            self.assertEqual(result.synapse_ops, expected_mask.bit_count())

        self.assertEqual(controller.weight_reads_issued, expected_work)
        self.assertEqual(controller.synapse_ops_issued, expected_work)
        self.assertEqual(controller.groups_skipped, 3)
        self.assertEqual(controller.inactive_groups, 1)
        self.assertEqual(controller.dense_weight_reads_requested, 32)
        self.assertEqual(controller.reads_saved_by_structure, 16)

    def test_dense_issue_enumeration_has_no_fake_structural_savings(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S0)
        for activity_mask in range(16):
            result = controller.issue(activity_mask)
            self.assertEqual(result.issue_mask, activity_mask)
            self.assertEqual(result.reads_saved_by_structure, 0)

        self.assertEqual(controller.dense_weight_reads_requested, 32)
        self.assertEqual(controller.weight_reads_issued, 32)
        self.assertEqual(controller.reads_saved_by_structure, 0)
        self.assertEqual(controller.groups_skipped, 0)
        self.assertEqual(controller.inactive_groups, 1)

    def test_s0_s1_s2_s3_are_distinct_and_deterministic(self) -> None:
        weights = (1, 2, 9, 8)

        s0 = LocalPrune2of4(score_method=ScoreMethod.S0)
        s0.set_mode(PruneMode.TRAIN)
        self.assertEqual(s0.prune_commit(weights=weights, commit_id=1).mask, 0b1100)

        s1 = LocalPrune2of4(score_method=ScoreMethod.S1)
        s1.set_mode(PruneMode.TRAIN)
        s1.observe(
            weights=weights,
            evidence_levels=(3, 2, 1, 0),
            modulator=1,
            observation_id=1,
        )
        self.assertEqual(s1.prune_commit(weights=weights, commit_id=1).mask, 0b0011)

        s2 = LocalPrune2of4(score_method=ScoreMethod.S2)
        s2.set_mode(PruneMode.TRAIN)
        s2.observe(
            weights=weights,
            evidence_levels=(1, 1, 1, 1),
            modulator=1,
            observation_id=1,
        )
        self.assertEqual(s2.prune_commit(weights=weights, commit_id=1).mask, 0b0011)

        s3 = LocalPrune2of4(score_method=ScoreMethod.S3)
        s3.set_mode(PruneMode.TRAIN)
        s3.observe(
            weights=weights,
            evidence_levels=(1, 1, 1, 1),
            modulator=1,
            observation_id=1,
        )
        self.assertEqual(s3.prune_commit(weights=weights, commit_id=1).mask, 0b1100)

    def test_s2_saturates_decays_and_zero_modulator_is_a_noop(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S2)
        controller.set_mode(PruneMode.TRAIN)
        for observation_id in range(20):
            controller.observe(
                weights=(0, 0, 0, 0),
                evidence_levels=(3, 2, 1, 0),
                modulator=-1,
                observation_id=observation_id,
            )
        self.assertEqual(controller.utility, [15, 15, 1, 0])

        before = tuple(controller.utility)
        controller.observe(
            weights=(0, 0, 0, 0),
            evidence_levels=(3, 3, 3, 3),
            modulator=0,
            observation_id=20,
        )
        self.assertEqual(tuple(controller.utility), before)

        controller.observe(
            weights=(0, 0, 0, 0),
            evidence_levels=(0, 0, 0, 0),
            modulator=1,
            observation_id=21,
        )
        self.assertEqual(controller.utility, [14, 14, 0, 0])

    def test_s1_overwrites_only_on_nonzero_modulation(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S1)
        controller.set_mode(PruneMode.TRAIN)
        controller.observe(
            weights=(0, 0, 0, 0),
            evidence_levels=(3, 2, 1, 0),
            modulator=1,
            observation_id=1,
        )
        controller.observe(
            weights=(0, 0, 0, 0),
            evidence_levels=(0, 0, 3, 3),
            modulator=0,
            observation_id=2,
        )
        self.assertEqual(controller.utility, [3, 2, 1, 0])

        controller.observe(
            weights=(0, 0, 0, 0),
            evidence_levels=(0, 1, 2, 3),
            modulator=-1,
            observation_id=3,
        )
        self.assertEqual(controller.utility, [0, 1, 2, 3])

    def test_observation_id_is_exactly_once_and_atomic(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S2)
        controller.set_mode(PruneMode.TRAIN)
        controller.observe(
            weights=(1, 2, 3, 4),
            evidence_levels=(1, 2, 3, 0),
            modulator=1,
            observation_id=9,
        )
        for observation_id in (9, 8, -1, 65536, True, 1.5):
            before = self._architectural_state(controller)
            with self.assertRaises((TypeError, ValueError)):
                controller.observe(
                    weights=(9, 9, 9, 9),
                    evidence_levels=(3, 3, 3, 3),
                    modulator=1,
                    observation_id=observation_id,  # type: ignore[arg-type]
                )
            self.assertEqual(self._architectural_state(controller), before)

        self.assertEqual(controller.illegal_commands, 6)

    def test_invalid_types_are_rejected_before_architectural_state_changes(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S2)
        before = self._architectural_state(controller)
        with self.assertRaises(TypeError):
            controller.set_mode("infer")  # type: ignore[arg-type]
        self.assertEqual(self._architectural_state(controller), before)

        controller.set_mode(PruneMode.TRAIN)
        bad_observations = (
            {"weights": (0, 0, 0, 0), "evidence_levels": (0, 1, 2, 3), "modulator": "bad"},
            {"weights": (0, 0, 0, 0), "evidence_levels": (0, 1, 2, 1.5), "modulator": 1},
            {"weights": (0, 0, 0), "evidence_levels": (0, 1, 2, 3), "modulator": 1},
        )
        for observation_id, kwargs in enumerate(bad_observations, start=1):
            before = self._architectural_state(controller)
            with self.assertRaises((TypeError, ValueError)):
                controller.observe(
                    **kwargs,  # type: ignore[arg-type]
                    observation_id=observation_id,
                )
            self.assertEqual(self._architectural_state(controller), before)

    def test_commit_id_domain_and_unsafe_flags_are_strict(self) -> None:
        invalid_ids = (-1, 65536, True, 1.5)
        for commit_id in invalid_ids:
            controller = LocalPrune2of4(score_method=ScoreMethod.S0)
            controller.set_mode(PruneMode.TRAIN)
            before = self._architectural_state(controller)
            with self.assertRaises((TypeError, ValueError)):
                controller.prune_commit(
                    weights=(4, 3, 2, 1),
                    commit_id=commit_id,  # type: ignore[arg-type]
                )
            self.assertEqual(self._architectural_state(controller), before)

        controller = LocalPrune2of4(score_method=ScoreMethod.S0)
        controller.set_mode(PruneMode.TRAIN)
        before = self._architectural_state(controller)
        with self.assertRaises(TypeError):
            controller.prune_commit(
                weights=(4, 3, 2, 1),
                commit_id=1,
                core_idle=1,  # type: ignore[arg-type]
            )
        self.assertEqual(self._architectural_state(controller), before)

    def test_all_six_possible_output_masks_have_fixed_vectors(self) -> None:
        vectors = {
            0b0011: (9, 8, 2, 1),
            0b0101: (9, 2, 8, 1),
            0b1001: (9, 2, 1, 8),
            0b0110: (2, 9, 8, 1),
            0b1010: (2, 9, 1, 8),
            0b1100: (2, 1, 9, 8),
        }
        for expected_mask, weights in vectors.items():
            controller = LocalPrune2of4(score_method=ScoreMethod.S0)
            controller.set_mode(PruneMode.TRAIN)
            result = controller.prune_commit(weights=weights, commit_id=1)
            self.assertEqual(result.mask, expected_mask)
            self.assertEqual(result.mask.bit_count(), 2)

    def test_clear_and_hard_reset_have_distinct_audit_semantics(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S2)
        controller.set_mode(PruneMode.TRAIN)
        controller.observe(
            weights=(1, 2, 3, 4),
            evidence_levels=(1, 2, 3, 0),
            modulator=1,
            observation_id=1,
        )
        controller.prune_commit(weights=(1, 2, 3, 4), commit_id=2)
        controller.issue(0b1111)
        issued_before_clear = controller.weight_reads_issued

        controller.set_mode(PruneMode.CONFIG)
        controller.prune_clear()
        self.assertEqual(controller.utility, [0, 0, 0, 0])
        self.assertEqual(controller.mask_read(), 0b1111)
        self.assertIsNone(controller.last_commit_id)
        self.assertIsNone(controller.last_observation_id)
        self.assertEqual(controller.weight_reads_issued, issued_before_clear)

        controller.hard_reset()
        self.assertEqual(controller.mode, PruneMode.CONFIG)
        self.assertEqual(controller.weight_reads_issued, 0)
        self.assertEqual(controller.illegal_commands, 0)
        self.assertEqual(controller.event_log, [{"event": "hard_reset", "accepted": True}])

    def test_machine_signoff_summary_matches_committed_result(self) -> None:
        result_path = Path(__file__).with_name("local_prune_b0_results.json")
        expected = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(build_signoff_summary(), expected)

    def test_rejected_commit_is_atomic_and_counted(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S0)
        controller.set_mode(PruneMode.TRAIN)
        controller.prune_commit(weights=(9, 8, 1, 0), commit_id=5)

        for kwargs in (
            {"commit_id": 5},
            {"commit_id": 4},
            {"commit_id": 6},
        ):
            before = self._architectural_state(controller)
            with self.assertRaises((RuntimeError, ValueError)):
                controller.prune_commit(weights=(0, 1, 8, 9), **kwargs)
            self.assertEqual(self._architectural_state(controller), before)

        self.assertEqual(controller.illegal_commands, 3)
        self.assertEqual(controller.mask_commits, 1)

        for unsafe in (
            {"core_idle": False},
            {"pending_snapshot": True},
            {"pending_mod_commit": True},
        ):
            fresh = LocalPrune2of4(score_method=ScoreMethod.S0)
            fresh.set_mode(PruneMode.TRAIN)
            before = self._architectural_state(fresh)
            with self.assertRaises(RuntimeError):
                fresh.prune_commit(weights=(9, 8, 1, 0), commit_id=1, **unsafe)
            self.assertEqual(self._architectural_state(fresh), before)
            self.assertEqual(fresh.illegal_commands, 1)

    def test_infer_freezes_utility_and_mask(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S2)
        controller.set_mode(PruneMode.TRAIN)
        controller.observe(
            weights=(0, 0, 0, 0),
            evidence_levels=(1, 2, 3, 0),
            modulator=1,
            observation_id=1,
        )
        controller.prune_commit(weights=(0, 0, 0, 0), commit_id=1)
        controller.set_mode(PruneMode.INFER)
        frozen = self._architectural_state(controller)

        with self.assertRaises(RuntimeError):
            controller.observe(
                weights=(9, 9, 9, 9),
                evidence_levels=(3, 3, 3, 3),
                modulator=1,
                observation_id=2,
            )
        with self.assertRaises(RuntimeError):
            controller.prune_commit(weights=(9, 9, 9, 9), commit_id=2)
        with self.assertRaises(RuntimeError):
            controller.mask_write(0b1010)
        with self.assertRaises(RuntimeError):
            controller.prune_clear()

        self.assertEqual(self._architectural_state(controller), frozen)
        self.assertEqual(controller.illegal_commands, 4)

    def test_pruned_connections_stop_updating_utility(self) -> None:
        controller = LocalPrune2of4(score_method=ScoreMethod.S2)
        controller.set_mode(PruneMode.TRAIN)
        controller.observe(
            weights=(0, 0, 0, 0),
            evidence_levels=(3, 2, 1, 0),
            modulator=1,
            observation_id=1,
        )
        controller.prune_commit(weights=(0, 0, 0, 0), commit_id=1)
        self.assertEqual(controller.mask_read(), 0b0011)

        controller.observe(
            weights=(0, 0, 0, 0),
            evidence_levels=(0, 0, 3, 3),
            modulator=1,
            observation_id=2,
        )

        self.assertEqual(controller.utility, [2, 1, 1, 0])


if __name__ == "__main__":
    unittest.main()

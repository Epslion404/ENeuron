"""Pulse-Mini-L/L2 的 B1 局部剪枝适配器测试。"""

from __future__ import annotations

import unittest

from compare_simulation import make_shared_network_evaluation_data
from local_prune_reference import ScoreMethod
from pulse_mini_l2_reference import PulseMiniL2Reference
from pulse_mini_reference import Command, Opcode, PulseMiniReference, Status
from pulse_prune_adapter import PulsePruneAdapter


class PulsePruneAdapterTests(unittest.TestCase):
    def test_warmup_records_hidden_evidence_without_direct_writes(self) -> None:
        adapter = PulsePruneAdapter(core_type=PulseMiniReference)
        adapter.train_p8(repetitions=2, phase="warmup")

        self.assertEqual(len(adapter.evidence_ledger), 4)
        self.assertTrue(all(entry.layer == "hidden" for entry in adapter.evidence_ledger))
        self.assertTrue(all(entry.modulator == 1 for entry in adapter.evidence_ledger))
        self.assertEqual(adapter.direct_weight_write_count, 0)

    def test_s0_prune_is_local_exact_two_and_gates_before_tick(self) -> None:
        adapter = PulsePruneAdapter(core_type=PulseMiniReference)
        adapter.train_p8(repetitions=6, phase="warmup")
        branch = adapter.branch(score_method=ScoreMethod.S0)
        masks = branch.prune_score(commit_id=1)

        self.assertEqual(masks, (0b0011, 0b0011))
        before = tuple(branch.network.hidden[0].weights)
        branch.train_hidden_once(neuron=0, feature=0b1000, phase="finetune")
        self.assertEqual(tuple(branch.network.hidden[0].weights), before)
        self.assertGreater(branch.controllers[0].reads_saved_by_structure, 0)

    def test_l_and_l2_share_adapter_and_retain_p8_accuracy(self) -> None:
        samples = make_shared_network_evaluation_data()
        for core_type in (PulseMiniReference, PulseMiniL2Reference):
            adapter = PulsePruneAdapter(core_type=core_type)
            adapter.train_p8(repetitions=6, phase="warmup")
            scores = [adapter.infer_counts(events) for events, _, _, _ in samples]
            predictions = [
                0 if value[0] > 0 and value[1] == 0 else
                1 if value[1] > 0 and value[0] == 0 else None
                for value in scores
            ]
            self.assertEqual(predictions, [label for _, label, _, _ in samples])

    def test_replayed_evidence_is_exactly_once_and_branches_share_parent(self) -> None:
        adapter = PulsePruneAdapter(core_type=PulseMiniL2Reference)
        adapter.train_p8(repetitions=3, phase="warmup")
        s1 = adapter.branch(score_method=ScoreMethod.S1)
        s2 = adapter.branch(score_method=ScoreMethod.S2)

        self.assertEqual(s1.controllers[0].last_observation_id, 2)
        self.assertEqual(s2.controllers[0].last_observation_id, 2)
        # 当前 P8 对 L2 也只产生一级方向，S1/S2 同值是任务事实，不伪造差异。
        self.assertEqual(tuple(s1.controllers[0].utility), tuple(s2.controllers[0].utility))
        self.assertEqual(s1.parent_checkpoint_sha256, s2.parent_checkpoint_sha256)

    def test_inference_flushes_only_the_pending_hidden_route(self) -> None:
        adapter = PulsePruneAdapter(core_type=PulseMiniReference)
        adapter.network.hidden[0].weights = [6, 0, 0, 0]
        adapter.network.output[0].weights = [6, 0, 0, 0]
        events = ((), (), ((0,)))

        self.assertEqual(adapter.infer_counts(events), (1, 0))

    def test_refractory_tick_does_not_claim_a_weight_read_or_prune_saving(self) -> None:
        warmup = PulsePruneAdapter(core_type=PulseMiniReference)
        branch = warmup.branch(score_method=ScoreMethod.S0)
        branch.network.hidden[0].weights = [6, 0, 0, 0]
        branch.network.hidden[1].weights = [6, 0, 0, 0]

        branch.infer_counts((((0,)), ((0,))))

        self.assertEqual(branch.controllers[0].dense_weight_reads_requested, 1)
        self.assertEqual(branch.controllers[0].weight_reads_issued, 1)
        self.assertEqual(branch.controllers[0].reads_saved_by_structure, 0)

    def test_direct_weight_write_is_derived_from_real_core_logs(self) -> None:
        adapter = PulsePruneAdapter(core_type=PulseMiniReference)
        response = adapter.network.hidden[0].execute(Command(Opcode.WEIGHT_WRITE, 0, 3))
        self.assertIs(response.status, Status.OK)
        self.assertEqual(adapter.direct_weight_write_count, 1)

    def test_checkpoint_hash_binds_controller_mask_and_utility_state(self) -> None:
        warmup = PulsePruneAdapter(core_type=PulseMiniReference)
        branch = warmup.branch(score_method=ScoreMethod.S0)
        before = branch.checkpoint_sha256()
        branch.install_random_masks((0b0011, 0b1100))
        after = branch.checkpoint_sha256()

        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()

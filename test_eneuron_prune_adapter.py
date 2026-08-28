"""ENeuron B1 局部 2:4 剪枝薄适配器测试。"""

from __future__ import annotations

import unittest

from eneuron_prune_adapter import ENeuronB1PruneAdapter, quantize_eligibility
from local_prune_reference import ScoreMethod


class ENeuronPruneAdapterTests(unittest.TestCase):
    def test_quantize_eligibility_preserves_small_nonzero_evidence(self) -> None:
        self.assertEqual(
            tuple(quantize_eligibility(value) for value in (0, 1, -16, 17, -32, 33, 2047)),
            (0, 1, 1, 2, 2, 3, 3),
        )

    def test_each_hidden_neuron_filters_input_with_its_own_mask(self) -> None:
        adapter = ENeuronB1PruneAdapter(score_method=ScoreMethod.S0)
        adapter.hidden_gates[0].mask_write(0b0011)
        adapter.hidden_gates[1].mask_write(0b1100)

        result = adapter.run_sample(((0, 2),), label=0, train=True)

        self.assertEqual(result.hidden_issue_masks, ((0b0001, 0b0100),))
        self.assertEqual(adapter.network.hidden[0].pre_trace, [8, 0, 0, 0])
        self.assertEqual(adapter.network.hidden[1].pre_trace, [0, 0, 8, 0])

    def test_training_sample_quantizes_snapshot_and_observes_only_nonzero_mod(self) -> None:
        adapter = ENeuronB1PruneAdapter(score_method=ScoreMethod.S1)
        before = tuple(tuple(neuron.weights) for neuron in adapter.network.hidden)

        result = adapter.train_sample(
            ((0,),),
            label=0,
            hidden_modulator=(1, 0),
            output_modulator=(0, 0),
            commit_id=3,
        )

        self.assertEqual(
            result.snapshot.hidden_evidence_levels,
            ((1, 0, 0, 0), (1, 0, 0, 0)),
        )
        self.assertEqual(adapter.hidden_gates[0].utility, [1, 0, 0, 0])
        self.assertEqual(adapter.hidden_gates[1].utility, [0, 0, 0, 0])
        self.assertGreater(adapter.network.hidden[0].weights[0], before[0][0])
        self.assertEqual(tuple(adapter.network.hidden[1].weights), before[1])

    def test_prune_commit_clears_hidden_history_and_masks_future_weight_updates(self) -> None:
        adapter = ENeuronB1PruneAdapter(score_method=ScoreMethod.S0)
        adapter.run_sample((), label=0, train=True)
        for neuron in adapter.network.hidden:
            neuron.weights = [7, 6, 1, 0]
            neuron.pre_trace = [9, 8, 7, 6]
            neuron.eligibility = [64, 48, 128, 96]
        adapter.hidden_eligibility_snapshot = ([64, 48, 128, 96], [64, 48, 128, 96])

        results = adapter.prune_hidden(commit_id=10)

        self.assertEqual(tuple(result.mask for result in results), (0b0011, 0b0011))
        for neuron in adapter.network.hidden:
            self.assertEqual(neuron.pre_trace, [9, 8, 0, 0])
            self.assertEqual(neuron.eligibility, [64, 48, 0, 0])
        self.assertEqual(adapter.hidden_eligibility_snapshot, ([64, 48, 0, 0], [64, 48, 0, 0]))

        before = tuple(tuple(neuron.weights) for neuron in adapter.network.hidden)
        for neuron in adapter.network.hidden:
            neuron.eligibility = [0, 0, 256, 256]
        snapshot = adapter.capture_commit(11)
        adapter.apply_modulator(
            hidden_modulator=(1, 1),
            output_modulator=(0, 0),
            commit_id=11,
        )

        self.assertEqual(snapshot.pending.hidden_eligibility, ((0, 0, 0, 0), (0, 0, 0, 0)))
        self.assertEqual(tuple(tuple(neuron.weights) for neuron in adapter.network.hidden), before)

    def test_score_and_random_branches_share_checkpoint_and_replay_preupdate_evidence(self) -> None:
        source = ENeuronB1PruneAdapter(score_method=ScoreMethod.S0)
        source.train_sample(
            ((0,),),
            label=0,
            hidden_modulator=(1, 1),
            output_modulator=(0, 0),
            commit_id=4,
        )
        checkpoint_weights = tuple(tuple(neuron.weights) for neuron in source.network.neurons)

        score_branches = {
            method: source.branch_for_score(method)
            for method in ScoreMethod
        }
        random_left = source.random_mask_branch(seed=19)
        random_right = source.random_mask_branch(seed=19)

        self.assertEqual(source.observation_ledger[0].hidden_weights_before[0], (2, 2, 2, 2))
        observe_events = [
            event
            for event in source.hidden_gates[0].event_log
            if event["event"] == "observe" and event["accepted"]
        ]
        self.assertEqual(observe_events[-1]["weights"], [2, 2, 2, 2])
        self.assertEqual(score_branches[ScoreMethod.S0].hidden_gates[0].utility, [0, 0, 0, 0])
        for method in (ScoreMethod.S1, ScoreMethod.S2, ScoreMethod.S3):
            self.assertEqual(score_branches[method].hidden_gates[0].utility, [1, 0, 0, 0])
        for branch in score_branches.values():
            self.assertEqual(
                tuple(result.mask for result in branch.prune_hidden(commit_id=5)),
                (0b0011, 0b0011),
            )
            self.assertEqual(
                tuple(tuple(neuron.weights) for neuron in branch.network.neurons),
                checkpoint_weights,
            )
        self.assertEqual(
            tuple(gate.mask_read(log_event=False) for gate in random_left.hidden_gates),
            tuple(gate.mask_read(log_event=False) for gate in random_right.hidden_gates),
        )
        self.assertTrue(
            all(gate.mask_read(log_event=False).bit_count() == 2 for gate in random_left.hidden_gates)
        )
        self.assertTrue(all(not gate.mask_valid for gate in source.hidden_gates))

    def test_pending_snapshot_blocks_prune_without_changing_masks(self) -> None:
        adapter = ENeuronB1PruneAdapter(score_method=ScoreMethod.S0)
        adapter.run_sample(((0,),), label=0, train=True)
        adapter.capture_commit(2)
        before = tuple(gate.mask_read(log_event=False) for gate in adapter.hidden_gates)

        with self.assertRaises(RuntimeError):
            adapter.prune_hidden(commit_id=3)

        self.assertEqual(
            tuple(gate.mask_read(log_event=False) for gate in adapter.hidden_gates),
            before,
        )
        self.assertTrue(all(not gate.mask_valid for gate in adapter.hidden_gates))

    def test_output_layer_snapshot_and_weight_update_remain_dense(self) -> None:
        adapter = ENeuronB1PruneAdapter(score_method=ScoreMethod.S0)
        adapter.run_sample((), label=0, train=True)
        for neuron in adapter.network.output:
            neuron.eligibility = [64, 32]
        before = tuple(tuple(neuron.weights) for neuron in adapter.network.output)

        snapshot = adapter.capture_commit(8)
        adapter.apply_modulator(
            hidden_modulator=(0, 0),
            output_modulator=(1, 1),
            commit_id=8,
        )

        self.assertEqual(snapshot.pending.output_eligibility, ((64, 32), (64, 32)))
        for old, neuron in zip(before, adapter.network.output):
            self.assertGreater(neuron.weights[0], old[0])
            self.assertGreater(neuron.weights[1], old[1])

    def test_refractory_tick_does_not_claim_hidden_weight_reads(self) -> None:
        adapter = ENeuronB1PruneAdapter(score_method=ScoreMethod.S0)
        adapter.network.hidden[0].weights = [7, 0, 0, 0]
        adapter.network.hidden[1].weights = [7, 0, 0, 0]

        adapter.run_sample(((0,), (0,)), label=0, train=False)

        self.assertEqual(adapter.hidden_gates[0].dense_weight_reads_requested, 1)
        self.assertEqual(adapter.hidden_gates[0].weight_reads_issued, 1)
        self.assertEqual(adapter.hidden_gates[0].reads_saved_by_structure, 0)

    def test_mask_branch_accepts_explicit_cross_model_random_masks(self) -> None:
        adapter = ENeuronB1PruneAdapter(score_method=ScoreMethod.S0)
        branch = adapter.mask_branch((0b0011, 0b1100))

        self.assertEqual(
            tuple(gate.mask_read(log_event=False) for gate in branch.hidden_gates),
            (0b0011, 0b1100),
        )

    def test_learning_fingerprint_excludes_dynamic_inference_state(self) -> None:
        adapter = ENeuronB1PruneAdapter(score_method=ScoreMethod.S0)
        before = adapter.learning_fingerprint()
        adapter.run_sample(((0,),), label=0, train=False)
        self.assertEqual(adapter.learning_fingerprint(), before)

    def test_work_counter_scope_includes_dense_output_layer(self) -> None:
        adapter = ENeuronB1PruneAdapter(score_method=ScoreMethod.S0)
        adapter.run_sample(((0,), (0,)), label=0, train=False)
        counters = adapter.work_counters()

        self.assertEqual(
            counters["scope"],
            "full_4x2x2_hidden_structural_output_dense",
        )
        self.assertGreaterEqual(counters["network_weight_reads_issued"], 1)


if __name__ == "__main__":
    unittest.main()

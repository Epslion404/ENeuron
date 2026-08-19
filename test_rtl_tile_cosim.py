"""4->2->2 数字 SNN tile 的事务级回归。"""

import unittest

from rtl_tile_cosim import (
    TileOracle,
    apply_transaction,
    make_transactions,
    run,
    run_priority_conflict_regression,
    run_route_flush_regression,
)


class RtlTileCosimTests(unittest.TestCase):
    def test_route_flush_is_output_only_and_preserves_hidden_state(self) -> None:
        run_route_flush_regression()

    def test_invalid_high_priority_command_blocks_lower_priority_requests(self) -> None:
        run_priority_conflict_regression()

    def test_clear_preserves_snapshot_commit_metadata_and_weights(self) -> None:
        oracle = TileOracle.create()
        _, oracle = apply_transaction(
            oracle,
            make_transactions(seed=0, count=20)[4],
            transaction_id=0,
        )
        snapshot = make_transactions(seed=0, count=20)[7]
        _, oracle = apply_transaction(oracle, snapshot, transaction_id=1)
        weights_before = tuple(tuple(neuron.weights) for neuron in oracle.neurons)
        snapshots_before = tuple(
            tuple(neuron.eligibility_snapshot) for neuron in oracle.neurons
        )

        clear = make_transactions(seed=0, count=20)[18]
        _, oracle = apply_transaction(oracle, clear, transaction_id=2)

        self.assertTrue(oracle.snapshot_valid)
        self.assertTrue(oracle.last_commit_valid)
        self.assertEqual(oracle.pending_commit_id, snapshot.commit_id)
        self.assertEqual(oracle.pending_episode_id, snapshot.episode_id)
        self.assertEqual(oracle.last_commit_id, snapshot.commit_id)
        self.assertEqual(
            tuple(tuple(neuron.weights) for neuron in oracle.neurons),
            weights_before,
        )
        self.assertEqual(
            tuple(tuple(neuron.eligibility_snapshot) for neuron in oracle.neurons),
            snapshots_before,
        )

    def test_directed_prefix_exercises_learning_and_freeze(self) -> None:
        """用固定黄金值证明协同仿真流确实触发学习和推理冻结。"""
        oracle = TileOracle.create()
        transactions = make_transactions(seed=0, count=20)

        for transaction_id, transaction in enumerate(transactions):
            weights_before = tuple(tuple(neuron.weights) for neuron in oracle.neurons)
            state, oracle = apply_transaction(oracle, transaction, transaction_id)

            if transaction_id == 4:
                self.assertEqual(state[6:8], (0b11, 0b00))
                self.assertEqual(oracle.pending_hidden, 0b11)
            elif transaction_id == 5:
                self.assertEqual(state[6:8], (0b00, 0b11))
                self.assertEqual(oracle.pending_hidden, 0b00)
            elif transaction_id == 7:
                self.assertTrue(oracle.snapshot_valid)
                self.assertEqual(oracle.hidden[0].eligibility_snapshot, [28, 28, 22, 22])
                self.assertEqual(oracle.output[0].eligibility_snapshot, [24, 24])
            elif transaction_id == 9:
                self.assertEqual(state[8], 1)
                self.assertTrue(oracle.snapshot_valid)
                self.assertEqual(
                    tuple(tuple(neuron.weights) for neuron in oracle.neurons),
                    weights_before,
                )
            elif transaction_id == 10:
                self.assertEqual(state[8], 0)
                self.assertFalse(oracle.snapshot_valid)
                self.assertEqual(oracle.weight_epoch, 1)
                self.assertEqual(
                    tuple(tuple(neuron.weights) for neuron in oracle.neurons),
                    ((5, 5, 4, 4), (-2, -2, -1, -1), (5, 4), (-2, -1)),
                )
            elif transaction_id in (11, 15):
                self.assertEqual(state[8], 1)
                self.assertEqual(
                    tuple(tuple(neuron.weights) for neuron in oracle.neurons),
                    weights_before,
                )
            elif transaction_id == 14:
                self.assertEqual(state[8], 0)
                self.assertEqual(oracle.weight_epoch, 2)
                self.assertEqual(
                    tuple(tuple(neuron.weights) for neuron in oracle.neurons),
                    weights_before,
                )

    def test_random_tile_transactions(self) -> None:
        for seed in (0, 1, 7, 19, 31):
            run(seed=seed, transaction_count=160)


if __name__ == "__main__":
    unittest.main()

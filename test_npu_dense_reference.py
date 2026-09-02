import unittest
import random

from npu_dense_reference import (
    ACC_MAX,
    HIDDEN_DIM,
    INPUT_DIM,
    OUTPUT_DIM,
    DenseInt8MLP64x32x10,
    DenseInt8Layer,
)


class DenseInt8LayerTests(unittest.TestCase):
    def test_ledger_counts_dense_groups_and_lanes(self):
        layer = DenseInt8Layer([[1] * INPUT_DIM for _ in range(HIDDEN_DIM)],
                               [0] * HIDDEN_DIM, name="hidden")
        expected_cycles = {1: 512, 2: 256, 4: 128, 8: 64}
        for lane_count, cycles in expected_cycles.items():
            _, ledger = layer.run([1] * INPUT_DIM, lane_count=lane_count)
            self.assertEqual(ledger.weight_reads, 1024)
            self.assertEqual(ledger.synapse_ops, 2048)
            self.assertEqual(ledger.cycles, cycles)

    def test_accumulator_saturates_before_relu(self):
        layer = DenseInt8Layer([[127] * 4], [ACC_MAX], name="sat")
        values, _ = layer.run([127] * 4, lane_count=1, relu=True)
        self.assertEqual(values, (127,))

    def test_random_signed_vectors_keep_lane_invariant(self):
        rng = random.Random(0x4E5055)
        weights = [[rng.randint(-128, 127) for _ in range(INPUT_DIM)]
                   for _ in range(HIDDEN_DIM)]
        biases = [rng.randint(-1000, 1000) for _ in range(HIDDEN_DIM)]
        layer = DenseInt8Layer(weights, biases, name="random")
        inputs = [rng.randint(-128, 127) for _ in range(INPUT_DIM)]
        reference, _ = layer.run(inputs, lane_count=1, relu=True)
        for lane_count in (2, 4, 8):
            candidate, _ = layer.run(inputs, lane_count=lane_count, relu=True)
            self.assertEqual(candidate, reference)

    def test_boundary_values_are_saturated_not_wrapped(self):
        layer = DenseInt8Layer([[127] * INPUT_DIM], [ACC_MAX], name="boundary")
        values, _ = layer.run([127] * INPUT_DIM, lane_count=8, relu=False)
        self.assertEqual(values, (ACC_MAX,))


class DenseInt8MlpTests(unittest.TestCase):
    def test_fixed_topology_and_total_ledger(self):
        model = DenseInt8MLP64x32x10.zeros()
        result = model.infer([0] * INPUT_DIM, lane_count=8)
        self.assertEqual(len(result.hidden), HIDDEN_DIM)
        self.assertEqual(len(result.logits), OUTPUT_DIM)
        self.assertEqual(result.prediction, 0)
        self.assertEqual(result.one_hot, (1,) + (0,) * 9)
        self.assertEqual(result.total_weight_reads, 1184)
        self.assertEqual(result.total_synapse_ops, 2368)
        self.assertEqual(result.total_cycles, 74)

    def test_signed_values_and_deterministic_argmax(self):
        hidden_weights = [[0] * INPUT_DIM for _ in range(HIDDEN_DIM)]
        hidden_weights[0][0] = 1
        output_weights = [[0] * HIDDEN_DIM for _ in range(OUTPUT_DIM)]
        output_weights[3][0] = 2
        output_weights[7][0] = -2
        model = DenseInt8MLP64x32x10(hidden_weights, [0] * HIDDEN_DIM,
                                     output_weights, [0] * OUTPUT_DIM)
        result = model.infer([-5] + [0] * (INPUT_DIM - 1), lane_count=4)
        self.assertEqual(result.hidden[0], 0)
        self.assertEqual(result.logits[3], 0)
        self.assertEqual(result.logits[7], 0)
        self.assertEqual(result.prediction, 0)

    def test_abstain_margin_returns_zero_one_hot(self):
        model = DenseInt8MLP64x32x10.zeros()
        result = model.infer([0] * INPUT_DIM, lane_count=1, abstain_margin=1)
        self.assertTrue(result.abstain)
        self.assertIsNone(result.prediction)
        self.assertEqual(result.one_hot, (0,) * OUTPUT_DIM)

    def test_lane_choice_does_not_change_numerical_result(self):
        model = DenseInt8MLP64x32x10.zeros()
        inputs = [index - 32 for index in range(INPUT_DIM)]
        baseline = model.infer(inputs, lane_count=1)
        expected_cycles = {1: 592, 2: 296, 4: 148, 8: 74}
        self.assertEqual(baseline.total_cycles, expected_cycles[1])
        for lane_count in (2, 4, 8):
            candidate = model.infer(inputs, lane_count=lane_count)
            self.assertEqual(candidate.hidden, baseline.hidden)
            self.assertEqual(candidate.logits, baseline.logits)
            self.assertEqual(candidate.total_weight_reads, baseline.total_weight_reads)
            self.assertEqual(candidate.total_synapse_ops, baseline.total_synapse_ops)
            self.assertEqual(candidate.total_cycles, expected_cycles[lane_count])

    def test_fixed_ten_way_codebook_is_solved_without_neurons(self):
        hidden_weights = [[0] * INPUT_DIM for _ in range(HIDDEN_DIM)]
        output_weights = [[0] * HIDDEN_DIM for _ in range(OUTPUT_DIM)]
        for label in range(OUTPUT_DIM):
            hidden_weights[label][label] = 127
            output_weights[label][label] = 127
        model = DenseInt8MLP64x32x10(hidden_weights, [0] * HIDDEN_DIM,
                                     output_weights, [0] * OUTPUT_DIM)
        for label in range(OUTPUT_DIM):
            sample = [0] * INPUT_DIM
            sample[label] = 1
            result = model.infer(sample, lane_count=8)
            self.assertEqual(result.prediction, label)
            self.assertFalse(result.abstain)


if __name__ == "__main__":
    unittest.main()

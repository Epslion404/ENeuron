"""传统 INT8 NPU 旁路/门控参考模型的行为测试。"""

import unittest

from npu_eneuron_reference import NpuConfig, NpuReference, quantize_input
from npu_eneuron_protocol import NpuEpochRuntime


class NpuReferenceTest(unittest.TestCase):
    def test_full_open_matches_dense_integer_result(self):
        config = NpuConfig()
        model = NpuReference(config)
        weights0 = [[1] * config.input_size for _ in range(config.hidden_size)]
        bias0 = [0] * config.hidden_size
        weights1 = [[1] * config.hidden_size for _ in range(config.output_size)]
        bias1 = list(range(config.output_size))
        model.load_weights(weights0, bias0, weights1, bias1)

        image = [1] * config.input_size
        result = model.infer(image, mode="bypass")

        total = sum(quantize_input(value) for value in image)
        self.assertEqual(result.logits, [total * config.hidden_size + i for i in range(config.output_size)])
        self.assertEqual(result.prediction, config.output_size - 1)
        self.assertEqual(result.mac_count, config.input_size * config.hidden_size + config.hidden_size * config.output_size)

    def test_all_closed_skips_groups_but_keeps_biases(self):
        config = NpuConfig()
        model = NpuReference(config)
        model.load_weights(
            [[2] * config.input_size for _ in range(config.hidden_size)],
            [3] * config.hidden_size,
            [[4] * config.hidden_size for _ in range(config.output_size)],
            list(range(config.output_size)),
        )
        mask0 = [False] * (config.hidden_size * (config.input_size // config.group_size))
        mask1 = [False] * (config.output_size * (config.hidden_size // config.group_size))

        result = model.infer([7] * config.input_size, mode="gated", group_mask0=mask0, group_mask1=mask1)

        self.assertEqual(result.logits, list(range(config.output_size)))
        self.assertEqual(result.mac_count, 0)
        self.assertEqual(result.group_reads, 0)

    def test_full_open_gated_mode_is_bit_exact_with_bypass(self):
        config = NpuConfig()
        model = NpuReference(config)
        model.load_weights(
            [[-3 if index % 2 else 5 for index in range(config.input_size)] for _ in range(config.hidden_size)],
            [2] * config.hidden_size,
            [[4 if index % 3 else -2 for index in range(config.hidden_size)] for _ in range(config.output_size)],
            [index - 4 for index in range(config.output_size)],
        )
        mask0 = [True] * (config.hidden_size * (config.input_size // config.group_size))
        mask1 = [True] * (config.output_size * (config.hidden_size // config.group_size))
        image = [index % 16 for index in range(config.input_size)]

        bypass = model.infer(image, mode="bypass")
        gated = model.infer(image, mode="gated", group_mask0=mask0, group_mask1=mask1)

        self.assertEqual(gated, bypass)

    def test_hidden_relu_saturates_before_output_layer(self):
        config = NpuConfig()
        model = NpuReference(config)
        model.load_weights(
            [[127] * config.input_size for _ in range(config.hidden_size)],
            [0] * config.hidden_size,
            [[1] * config.hidden_size for _ in range(config.output_size)],
            [0] * config.output_size,
        )

        result = model.infer([15] * config.input_size)

        self.assertEqual(result.logits, [127 * config.hidden_size] * config.output_size)
        self.assertTrue(result.abstain)

    def test_input_values_are_clipped_to_four_bit_range(self):
        config = NpuConfig()
        model = NpuReference(config)
        model.load_weights(
            [[1] * config.input_size for _ in range(config.hidden_size)],
            [0] * config.hidden_size,
            [[1] * config.hidden_size for _ in range(config.output_size)],
            list(range(config.output_size)),
        )

        image = [-9, 99] + [0] * (config.input_size - 2)
        result = model.infer(image)

        self.assertEqual(result.logits, [15 * config.hidden_size + index for index in range(config.output_size)])

    def _runtime(self):
        config = NpuConfig()
        model = NpuReference(config)
        model.load_weights(
            [[1] * config.input_size for _ in range(config.hidden_size)],
            [0] * config.hidden_size,
            [[1] * config.hidden_size for _ in range(config.output_size)],
            list(range(config.output_size)),
        )
        return config, NpuEpochRuntime(model, config)

    def test_pending_epoch_switches_only_at_sample_boundary(self):
        config, runtime = self._runtime()
        closed0 = [False] * (config.hidden_size * (config.input_size // config.group_size))
        closed1 = [False] * (config.output_size * (config.hidden_size // config.group_size))

        old_epoch, old_result = runtime.begin_sample([1] * config.input_size)
        runtime.stage_masks(1, closed0, closed1)
        self.assertEqual(old_epoch, 0)
        self.assertEqual(runtime.active_epoch, 0)
        runtime.complete_sample(old_result)
        self.assertEqual(runtime.active_epoch, 1)
        runtime.accept_result()
        new_epoch, new_result = runtime.begin_sample([1] * config.input_size)
        self.assertEqual(new_epoch, 1)
        self.assertNotEqual(new_result.logits, old_result.logits)
        runtime.complete_sample(new_result)
        runtime.accept_result()

    def test_result_backpressure_blocks_overwrite_until_accept(self):
        _, runtime = self._runtime()
        _, result = runtime.begin_sample([1] * runtime.config.input_size)
        runtime.complete_sample(result)
        with self.assertRaisesRegex(RuntimeError, "result backpressure"):
            runtime.begin_sample([1] * runtime.config.input_size)
        self.assertIs(runtime.result, result)
        self.assertIs(runtime.accept_result(), result)

    def test_state_clear_preserves_committed_epoch_and_mask(self):
        config, runtime = self._runtime()
        closed0 = [False] * (config.hidden_size * (config.input_size // config.group_size))
        closed1 = [False] * (config.output_size * (config.hidden_size // config.group_size))
        _, result = runtime.begin_sample([1] * config.input_size)
        runtime.stage_masks(1, closed0, closed1)
        runtime.complete_sample(result)
        runtime.accept_result()
        runtime.state_clear()
        self.assertEqual(runtime.active_epoch, 1)
        self.assertEqual(runtime.clear_count, 1)

    def test_infer_freeze_rejects_mask_update_and_clear(self):
        config, runtime = self._runtime()
        mask0 = [True] * (config.hidden_size * (config.input_size // config.group_size))
        mask1 = [True] * (config.output_size * (config.hidden_size // config.group_size))
        runtime.set_infer_freeze(True)
        with self.assertRaisesRegex(RuntimeError, "infer freeze"):
            runtime.stage_masks(1, mask0, mask1)
        with self.assertRaisesRegex(RuntimeError, "infer freeze"):
            runtime.state_clear()

    def test_epoch_and_mask_validation_is_fail_closed(self):
        config, runtime = self._runtime()
        mask0 = [True] * (config.hidden_size * (config.input_size // config.group_size))
        mask1 = [True] * (config.output_size * (config.hidden_size // config.group_size))
        with self.assertRaisesRegex(ValueError, "complete masks"):
            runtime.stage_masks(1, mask0[:-1], mask1)
        with self.assertRaisesRegex(ValueError, "epoch"):
            runtime.stage_masks(0, mask0, mask1)


if __name__ == "__main__":
    unittest.main()

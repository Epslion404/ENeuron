"""传统 INT8 NPU 旁路/门控参考模型的行为测试。"""

import unittest
from dataclasses import FrozenInstanceError

import npu_eneuron_protocol as protocol
from npu_eneuron_reference import NpuConfig, NpuReference
from npu_eneuron_protocol import NpuEpochRuntime


class NpuReferenceTest(unittest.TestCase):
    @staticmethod
    def _valid_model_data(config):
        return (
            [[1] * config.input_size for _ in range(config.hidden_size)],
            [0] * config.hidden_size,
            [[1] * config.hidden_size for _ in range(config.output_size)],
            list(range(config.output_size)),
        )

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

        total = sum(image)
        self.assertEqual(result.logits, tuple(total * config.hidden_size + i for i in range(config.output_size)))
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

        self.assertEqual(result.logits, tuple(range(config.output_size)))
        self.assertEqual(result.mac_count, 0)
        self.assertEqual(result.group_reads, 0)

    def test_single_mask_bits_use_canonical_layer_order(self):
        config = NpuConfig()
        model = NpuReference(config)
        weights0 = [[0] * config.input_size for _ in range(config.hidden_size)]
        weights1 = [[0] * config.hidden_size for _ in range(config.output_size)]
        weights0[5][28:32] = [1, 2, 3, 4]
        weights1[3][5] = 3
        model.load_weights(weights0, [0] * config.hidden_size, weights1, [0] * config.output_size)

        image = [0] * config.input_size
        image[28:32] = [1, 2, 3, 4]
        mask0 = [False] * 512
        mask1 = [False] * 80
        mask0[5 * 16 + 7] = True
        mask1[3 * 8 + 1] = True

        result = model.infer(image, mode="gated", group_mask0=mask0, group_mask1=mask1)

        expected = [0] * config.output_size
        expected[3] = 90
        self.assertEqual(result.logits, tuple(expected))
        self.assertEqual((result.group_reads, result.mac_count), (2, 8))

        mask0[5 * 16 + 7] = False
        mask0[5 * 16 + 8] = True
        adjacent = model.infer(image, mode="gated", group_mask0=mask0, group_mask1=mask1)
        self.assertEqual(adjacent.logits, (0,) * config.output_size)

    def test_mixed_masks_cover_first_and_last_linear_bits(self):
        config = NpuConfig()
        model = NpuReference(config)
        weights0 = [[0] * config.input_size for _ in range(config.hidden_size)]
        weights1 = [[0] * config.hidden_size for _ in range(config.output_size)]
        weights0[0][0:4] = [1] * 4
        weights0[31][60:64] = [2] * 4
        weights1[0][0] = 3
        weights1[9][31] = 5
        model.load_weights(weights0, [0] * config.hidden_size, weights1, [0] * config.output_size)

        mask0 = [False] * 512
        mask1 = [False] * 80
        mask0[0] = True
        mask0[511] = True
        mask1[0] = True
        mask1[79] = True
        result = model.infer([1] * config.input_size, mode="gated", group_mask0=mask0, group_mask1=mask1)

        expected = [0] * config.output_size
        expected[0] = 12
        expected[9] = 40
        self.assertEqual(result.logits, tuple(expected))
        self.assertEqual((result.group_reads, result.mac_count), (4, 16))

    def test_open_groups_with_zero_activations_keep_fixed_work_count(self):
        config = NpuConfig()
        model = NpuReference(config)
        model.load_weights(
            [[1] * config.input_size for _ in range(config.hidden_size)],
            [0] * config.hidden_size,
            [[1] * config.hidden_size for _ in range(config.output_size)],
            list(range(config.output_size)),
        )
        mask0 = [False] * 512
        mask1 = [False] * 80
        for index in (0, 17):
            mask0[index] = True
        for index in (0, 9, 79):
            mask1[index] = True

        result = model.infer([0] * config.input_size, mode="gated", group_mask0=mask0, group_mask1=mask1)

        self.assertEqual(result.logits, tuple(range(config.output_size)))
        self.assertEqual(result.group_reads, 5)
        self.assertEqual(result.mac_count, 20)
        self.assertEqual(result.mac_count, config.group_size * result.group_reads)

    def test_model_words_use_exact_segment_and_byte_mapping(self):
        words = [0] * 634
        for index in range(512):
            words[index] = 0x80000000 | (index << 8) | (index ^ 0x5A)
        for hidden in range(32):
            words[512 + hidden] = (-1000 + hidden) & 0xFFFFFFFF
        for offset in range(80):
            words[544 + offset] = 0x7F000000 | (offset << 8) | (offset ^ 0xA5)
        for output in range(10):
            words[624 + output] = 2000 + output

        words[0] = 0x7F00FF80
        words[511] = 0x04030201
        words[544] = 0xFFFEFDFC
        words[623] = 0x01020304

        decoded = protocol.decode_model_words(words)

        for hidden in range(32):
            for group in range(16):
                word = words[16 * hidden + group]
                expected = tuple(
                    raw - 256 if raw >= 128 else raw
                    for raw in ((word >> (8 * byte)) & 0xFF for byte in range(4))
                )
                self.assertEqual(decoded.weights0[hidden][4 * group : 4 * group + 4], expected)
            self.assertEqual(decoded.bias0[hidden], -1000 + hidden)

        for output in range(10):
            for group in range(8):
                word = words[544 + 8 * output + group]
                expected = tuple(
                    raw - 256 if raw >= 128 else raw
                    for raw in ((word >> (8 * byte)) & 0xFF for byte in range(4))
                )
                self.assertEqual(decoded.weights1[output][4 * group : 4 * group + 4], expected)
            self.assertEqual(decoded.bias1[output], 2000 + output)

        original = decoded.weights0[0][0]
        words[0] = 0
        self.assertEqual(decoded.weights0[0][0], original)

    def test_model_word_image_requires_exact_uint32_domain(self):
        for length in (633, 635):
            with self.subTest(length=length):
                with self.assertRaisesRegex(ValueError, "634"):
                    protocol.decode_model_words([0] * length)

        for index in (0, 317, 633):
            for invalid in (-1, 0x100000000, 1.0, "0", None, True):
                with self.subTest(index=index, invalid=invalid):
                    words = [0] * 634
                    words[index] = invalid
                    with self.assertRaisesRegex(ValueError, "uint32"):
                        protocol.decode_model_words(words)

    def test_model_word_load_is_atomic_for_invalid_bias(self):
        config = NpuConfig()
        unsafe_biases = (
            (512, -2147360769 & 0xFFFFFFFF),
            (543, 2147361728),
            (624, -2146963457 & 0xFFFFFFFF),
            (633, 2146967520),
        )
        for index, word in unsafe_biases:
            with self.subTest(index=index):
                model = NpuReference(config)
                model.load_weights(*self._valid_model_data(config))
                before = tuple(model.infer([value] * config.input_size) for value in (0, 1))
                words = [0] * 634
                words[index] = word
                with self.assertRaisesRegex(ValueError, "bias"):
                    protocol.load_model_words(model, words)
                after = tuple(model.infer([value] * config.input_size) for value in (0, 1))
                self.assertEqual(after, before)

        unloaded = NpuReference(config)
        words = [0] * 634
        words[633] = 2146967520
        with self.assertRaisesRegex(ValueError, "bias"):
            protocol.load_model_words(unloaded, words)
        with self.assertRaisesRegex(RuntimeError, "not loaded"):
            unloaded.infer([0] * config.input_size)

        protocol.load_model_words(unloaded, [0] * 634)
        result = unloaded.infer([0] * config.input_size)
        self.assertEqual(result.logits, (0,) * config.output_size)
        self.assertTrue(result.abstain)

        for invalid in (None, 0x100000000):
            with self.subTest(late_invalid=invalid):
                model = NpuReference(config)
                model.load_weights(*self._valid_model_data(config))
                before = tuple(model.infer([value] * config.input_size) for value in (0, 1))
                words = [0] * 634
                words[633] = invalid
                with self.assertRaisesRegex(ValueError, "uint32"):
                    protocol.load_model_words(model, words)
                after = tuple(model.infer([value] * config.input_size) for value in (0, 1))
                self.assertEqual(after, before)

    def test_mask_words_use_canonical_lsb_first_mapping(self):
        words = [((index * 0x9E3779B1) ^ 0xA5A55A5A) & 0xFFFFFFFF for index in range(19)]
        words[18] &= 0xFFFF
        decoded = protocol.decode_mask_words(words)

        expected0 = tuple(bool((words[index // 32] >> (index % 32)) & 1) for index in range(512))
        expected1 = tuple(bool((words[16 + index // 32] >> (index % 32)) & 1) for index in range(80))
        self.assertEqual(decoded.mask0, expected0)
        self.assertEqual(decoded.mask1, expected1)
        self.assertIsInstance(decoded.mask0, tuple)
        self.assertIsInstance(decoded.mask1, tuple)
        self.assertTrue(all(type(value) is bool for value in decoded.mask0 + decoded.mask1))
        self.assertEqual((decoded.mask0[0], decoded.mask0[511]), (bool(words[0] & 1), bool(words[15] >> 31)))
        self.assertEqual((decoded.mask1[0], decoded.mask1[79]), (bool(words[16] & 1), bool((words[18] >> 15) & 1)))

        with self.assertRaises(TypeError):
            decoded.mask0[0] = not decoded.mask0[0]

        original = decoded.mask0[0]
        words[0] ^= 1
        self.assertEqual(decoded.mask0[0], original)

        landmarks = [0] * 19
        landmarks[0] = 0x80000001
        landmarks[7] = 1 << 13
        landmarks[15] = 0x80000000
        landmarks[16] = 0x80000001
        landmarks[17] = 1
        landmarks[18] = 0x00008001
        landmark_masks = protocol.decode_mask_words(landmarks)
        self.assertEqual({index for index, value in enumerate(landmark_masks.mask0) if value}, {0, 31, 237, 511})
        self.assertEqual({index for index, value in enumerate(landmark_masks.mask1) if value}, {0, 31, 32, 64, 79})

    def test_mask_word_image_is_exact_uint32_and_rejects_reserved_bits(self):
        for length in (18, 20):
            with self.subTest(length=length):
                with self.assertRaisesRegex(ValueError, "19"):
                    protocol.decode_mask_words([0] * length)

        for index in (0, 9, 18):
            for invalid in (-1, 0x100000000, 1.0, "0", None, True):
                with self.subTest(index=index, invalid=invalid):
                    words = [0] * 19
                    words[index] = invalid
                    with self.assertRaisesRegex(ValueError, "uint32"):
                        protocol.decode_mask_words(words)

        for reserved in (1 << 16, 1 << 31, 0xFFFF0000):
            with self.subTest(reserved=reserved):
                words = [0] * 19
                words[18] = reserved
                with self.assertRaisesRegex(ValueError, "reserved"):
                    protocol.decode_mask_words(words)

        decoded = protocol.decode_mask_words([0] * 18 + [0xFFFF])
        self.assertEqual(decoded.mask1[64:80], (True,) * 16)

        all_zero = protocol.decode_mask_words([0] * 19)
        all_one = protocol.decode_mask_words([0xFFFFFFFF] * 18 + [0xFFFF])
        self.assertFalse(any(all_zero.mask0 + all_zero.mask1))
        self.assertTrue(all(all_one.mask0 + all_one.mask1))

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

        self.assertEqual(result.logits, (127 * config.hidden_size,) * config.output_size)
        self.assertTrue(result.abstain)

    def test_core_uint4_domain_is_fail_closed(self):
        config = NpuConfig()
        model = NpuReference(config)
        model.load_weights(
            [[1] * config.input_size for _ in range(config.hidden_size)],
            [0] * config.hidden_size,
            [[1] * config.hidden_size for _ in range(config.output_size)],
            list(range(config.output_size)),
        )

        for valid in (0, 15):
            with self.subTest(valid=valid):
                model.infer([valid] * config.input_size)

        for invalid in (-1, 16, 1.5, "7", None, True):
            with self.subTest(invalid=invalid):
                image = [0] * config.input_size
                image[-1] = invalid
                with self.assertRaisesRegex(ValueError, "uint4"):
                    model.infer(image)

    def test_v1_rejects_noncanonical_configurations(self):
        fields = {
            "input_size": 64,
            "hidden_size": 32,
            "output_size": 10,
            "group_size": 4,
        }
        for name, expected in fields.items():
            for invalid in (expected - 1, expected + 1, float(expected), str(expected), None, True):
                with self.subTest(name=name, invalid=invalid):
                    candidate = dict(fields)
                    candidate[name] = invalid
                    with self.assertRaisesRegex(ValueError, "64.*32.*10.*4"):
                        NpuConfig(**candidate)

    def test_weights_require_strict_int8_and_failed_reload_is_atomic(self):
        config = NpuConfig()
        invalid_values = (-129, 128, 1.5, "7", None, True)
        for layer in (0, 1):
            for invalid in invalid_values:
                with self.subTest(layer=layer, invalid=invalid):
                    model = NpuReference(config)
                    model.load_weights(*self._valid_model_data(config))
                    before = tuple(model.infer([value] * config.input_size) for value in (0, 1))
                    weights0 = [[2] * config.input_size for _ in range(config.hidden_size)]
                    bias0 = [3] * config.hidden_size
                    weights1 = [[4] * config.hidden_size for _ in range(config.output_size)]
                    bias1 = [5] * config.output_size
                    (weights0 if layer == 0 else weights1)[-1][-1] = invalid
                    with self.assertRaisesRegex(ValueError, "INT8"):
                        model.load_weights(weights0, bias0, weights1, bias1)
                    after = tuple(model.infer([value] * config.input_size) for value in (0, 1))
                    self.assertEqual(after, before)

        unloaded = NpuReference(config)
        weights0, bias0, weights1, bias1 = self._valid_model_data(config)
        weights1[-1][-1] = None
        with self.assertRaisesRegex(ValueError, "INT8"):
            unloaded.load_weights(weights0, bias0, weights1, bias1)
        with self.assertRaisesRegex(RuntimeError, "not loaded"):
            unloaded.infer([0] * config.input_size)

        model = NpuReference(config)
        weights0, bias0, weights1, bias1 = self._valid_model_data(config)
        weights0[0][0] = -128
        weights0[0][1] = 127
        weights1[0][0] = -128
        weights1[0][1] = 127
        model.load_weights(weights0, bias0, weights1, bias1)

    def test_bias_safe_windows_and_failed_reload_is_atomic(self):
        config = NpuConfig()
        safe0 = (-2147360768, 2147361727)
        safe1 = (-2146963456, 2146967519)

        model = NpuReference(config)
        weights0, bias0, weights1, bias1 = self._valid_model_data(config)
        bias0[:4] = [safe0[0], safe0[0] + 1, safe0[1] - 1, safe0[1]]
        bias1[:4] = [safe1[0], safe1[0] + 1, safe1[1] - 1, safe1[1]]
        model.load_weights(weights0, bias0, weights1, bias1)

        weights0 = [[0] * config.input_size for _ in range(config.hidden_size)]
        bias0 = [127] * config.hidden_size
        weights1 = [[0] * config.hidden_size for _ in range(config.output_size)]
        weights1[0] = [-128] * config.hidden_size
        weights1[1] = [127] * config.hidden_size
        bias1 = [0] * config.output_size
        bias1[0], bias1[1] = safe1
        model.load_weights(weights0, bias0, weights1, bias1)
        result = model.infer([0] * config.input_size)
        self.assertEqual(result.logits[:2], (-2147483648, 2147483647))

        invalid_cases = (
            (0, safe0[0] - 1),
            (0, safe0[1] + 1),
            (0, 1.5),
            (0, "7"),
            (0, None),
            (0, True),
            (1, safe1[0] - 1),
            (1, safe1[1] + 1),
            (1, 1.5),
            (1, "7"),
            (1, None),
            (1, True),
        )
        for layer, invalid in invalid_cases:
            with self.subTest(layer=layer, invalid=invalid):
                model = NpuReference(config)
                model.load_weights(*self._valid_model_data(config))
                before = tuple(model.infer([value] * config.input_size) for value in (0, 1))
                weights0 = [[2] * config.input_size for _ in range(config.hidden_size)]
                bias0 = [3] * config.hidden_size
                weights1 = [[4] * config.hidden_size for _ in range(config.output_size)]
                bias1 = [5] * config.output_size
                (bias0 if layer == 0 else bias1)[-1] = invalid
                with self.assertRaisesRegex(ValueError, "bias"):
                    model.load_weights(weights0, bias0, weights1, bias1)
                after = tuple(model.infer([value] * config.input_size) for value in (0, 1))
                self.assertEqual(after, before)

    def test_logits_are_immutable_during_result_backpressure(self):
        config, runtime = self._runtime()
        transaction = runtime.begin_sample([1] * config.input_size)
        runtime.complete_sample()

        self.assertIs(runtime.result, transaction)
        self.assertIsInstance(transaction.inference.logits, tuple)
        with self.assertRaises(TypeError):
            transaction.inference.logits[0] = -1
        with self.assertRaises(FrozenInstanceError):
            transaction.inference.logits = ()
        self.assertIs(runtime.result, transaction)

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

        old_result = runtime.begin_sample([1] * config.input_size)
        runtime.stage_masks(1, closed0, closed1)
        self.assertEqual(old_result.epoch, 0)
        self.assertEqual(runtime.active_epoch, 0)
        runtime.complete_sample()
        self.assertEqual(runtime.active_epoch, 0)
        runtime.accept_result()
        new_result = runtime.begin_sample([1] * config.input_size)
        self.assertEqual(new_result.epoch, 1)
        self.assertEqual(runtime.active_epoch, 1)
        self.assertNotEqual(new_result.inference.logits, old_result.inference.logits)
        runtime.complete_sample()
        runtime.accept_result()

    def test_result_backpressure_blocks_overwrite_until_accept(self):
        _, runtime = self._runtime()
        result = runtime.begin_sample([1] * runtime.config.input_size)
        runtime.complete_sample()
        with self.assertRaisesRegex(RuntimeError, "result backpressure"):
            runtime.begin_sample([1] * runtime.config.input_size)
        self.assertIs(runtime.result, result)
        self.assertIs(runtime.accept_result(), result)

    def test_state_clear_preserves_committed_epoch_and_mask(self):
        config, runtime = self._runtime()
        closed0 = [False] * (config.hidden_size * (config.input_size // config.group_size))
        closed1 = [False] * (config.output_size * (config.hidden_size // config.group_size))
        runtime.begin_sample([1] * config.input_size)
        runtime.stage_masks(1, closed0, closed1)
        runtime.complete_sample()
        runtime.accept_result()
        result = runtime.begin_sample([1] * config.input_size)
        self.assertEqual(result.epoch, 1)
        runtime.complete_sample()
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

    def test_invalid_sample_has_no_runtime_or_epoch_side_effect(self):
        config, runtime = self._runtime()
        mask0 = [False] * (config.hidden_size * (config.input_size // config.group_size))
        mask1 = [False] * (config.output_size * (config.hidden_size // config.group_size))
        runtime.stage_masks(1, mask0, mask1)

        with self.assertRaisesRegex(ValueError, "image shape"):
            runtime.begin_sample([1] * (config.input_size - 1))

        self.assertFalse(runtime.running)
        self.assertIsNone(runtime.result)
        self.assertEqual(runtime.active_epoch, 0)
        accepted = runtime.begin_sample([1] * config.input_size)
        self.assertEqual(accepted.epoch, 1)

    def test_invalid_pixel_preserves_pending_epoch_and_runtime_state(self):
        config, runtime = self._runtime()
        size0 = config.hidden_size * (config.input_size // config.group_size)
        size1 = config.output_size * (config.hidden_size // config.group_size)
        runtime.stage_masks(1, [False] * size0, [False] * size1)

        invalid_image = [1] * config.input_size
        invalid_image[-1] = 16
        with self.assertRaisesRegex(ValueError, "uint4"):
            runtime.begin_sample(invalid_image)

        self.assertEqual(runtime.active_epoch, 0)
        self.assertFalse(runtime.running)
        self.assertIsNone(runtime.result)

        accepted = runtime.begin_sample([1] * config.input_size)
        self.assertEqual(accepted.epoch, 1)
        self.assertEqual(accepted.inference.mac_count, 0)

    def test_zero_activity_with_closed_gate_emits_no_reads_or_macs(self):
        config, runtime = self._runtime()
        mask0 = [False] * (config.hidden_size * (config.input_size // config.group_size))
        mask1 = [False] * (config.output_size * (config.hidden_size // config.group_size))
        runtime.stage_masks(1, mask0, mask1)

        accepted = runtime.begin_sample([0] * config.input_size)

        self.assertEqual(accepted.epoch, 1)
        self.assertEqual(accepted.inference.group_reads, 0)
        self.assertEqual(accepted.inference.mac_count, 0)
        self.assertEqual(accepted.inference.logits, tuple(range(config.output_size)))

    def test_frequent_epoch_switches_never_mix_masks(self):
        config, runtime = self._runtime()
        size0 = config.hidden_size * (config.input_size // config.group_size)
        size1 = config.output_size * (config.hidden_size // config.group_size)
        observed = []
        for epoch, opened in ((1, False), (2, True), (3, False)):
            runtime.stage_masks(epoch, [opened] * size0, [opened] * size1)
            transaction = runtime.begin_sample([1] * config.input_size)
            observed.append((transaction.epoch, transaction.inference.mac_count))
            runtime.complete_sample()
            runtime.accept_result()

        dense_macs = config.input_size * config.hidden_size + config.hidden_size * config.output_size
        self.assertEqual(observed, [(1, 0), (2, dense_macs), (3, 0)])

    def test_pending_slot_backpressure_rejects_overwrite(self):
        config, runtime = self._runtime()
        size0 = config.hidden_size * (config.input_size // config.group_size)
        size1 = config.output_size * (config.hidden_size // config.group_size)
        runtime.stage_masks(1, [False] * size0, [False] * size1)

        with self.assertRaisesRegex(RuntimeError, "pending mask slot is full"):
            runtime.stage_masks(2, [True] * size0, [True] * size1)

        accepted = runtime.begin_sample([1] * config.input_size)
        self.assertEqual(accepted.epoch, 1)
        self.assertEqual(accepted.inference.mac_count, 0)


class MaskConfigProtocolRedTest(unittest.TestCase):
    """OF4b2 RED：冻结 19-word mask 逐拍配置口的最小行为合同。"""

    @staticmethod
    def _new_port():
        required = ("MaskCommand", "MaskCommandKind", "MaskConfigPort", "MaskStepResult")
        missing = [name for name in required if not hasattr(protocol, name)]
        if missing:
            raise AssertionError(
                "OF4b2 RED: protocol is missing " + ", ".join(missing)
            )
        return protocol.MaskConfigPort()

    @staticmethod
    def _command(kind: str, **fields):
        command_kind = getattr(protocol.MaskCommandKind, kind)
        return protocol.MaskCommand(command_kind, **fields)

    @staticmethod
    def _field(result, name):
        """允许测试在 dataclass 属性上工作，同时给出清晰的 RED 失败。"""
        if not hasattr(result, name):
            raise AssertionError(f"OF4b2 RED: MaskStepResult missing field {name}")
        return getattr(result, name)

    def _step(self, port, command=None, response_ready=False):
        result = port.step(command is not None, command, response_ready)
        self.assertIsInstance(result, protocol.MaskStepResult)
        return result

    def test_empty_loading_complete_published_state_machine(self):
        """19 个合法 word 后进入 complete，合法 commit 后进入 published。"""
        port = self._new_port()

        initial = self._step(port)
        self.assertEqual(self._field(initial, "state"), "empty")
        self.assertEqual(self._field(initial, "word_index"), 0)
        self.assertEqual(self._field(initial, "active_epoch"), 0)

        begun = self._step(
            port,
            self._command("MASK_BEGIN", epoch=1),
        )
        self.assertTrue(self._field(begun, "cmd_ready"))
        self.assertTrue(self._field(begun, "cmd_accepted"))
        self.assertFalse(self._field(begun, "error_valid"))
        self.assertEqual(self._field(begun, "state"), "loading")
        self.assertEqual(self._field(begun, "word_index"), 0)

        for index in range(18):
            loaded = self._step(
                port,
                self._command("DATA", word=0),
            )
            self.assertTrue(self._field(loaded, "cmd_accepted"), index)
            self.assertEqual(self._field(loaded, "state"), "loading")
            self.assertEqual(self._field(loaded, "word_index"), index + 1)

        complete = self._step(
            port,
            self._command("DATA", word=0x0000FFFF),
        )
        self.assertTrue(self._field(complete, "cmd_accepted"))
        self.assertFalse(self._field(complete, "error_valid"))
        self.assertEqual(self._field(complete, "state"), "complete")
        self.assertEqual(self._field(complete, "word_index"), 19)

        published = self._step(
            port,
            self._command("MASK_COMMIT", epoch=1),
        )
        self.assertTrue(self._field(published, "cmd_accepted"))
        self.assertFalse(self._field(published, "error_valid"))
        self.assertEqual(self._field(published, "state"), "published")
        # Publishing stages the next epoch; active_epoch changes only at a sample boundary.
        self.assertEqual(self._field(published, "active_epoch"), 0)

    def test_error_response_is_stable_and_blocks_new_command_until_accepted(self):
        """非法命令仍握手一次；错误响应背压时稳定且不再接受配置事务。"""
        port = self._new_port()

        # DATA 在 empty 状态非法，但必须完成一次命令握手并产生一个错误。
        rejected = self._step(
            port,
            self._command("DATA", word=0),
            response_ready=False,
        )
        self.assertTrue(self._field(rejected, "cmd_ready"))
        self.assertTrue(self._field(rejected, "cmd_accepted"))
        self.assertTrue(self._field(rejected, "error_valid"))
        error_code = self._field(rejected, "error_code")
        self.assertTrue(error_code)
        self.assertEqual(self._field(rejected, "state"), "empty")
        self.assertEqual(self._field(rejected, "word_index"), 0)
        self.assertEqual(self._field(rejected, "active_epoch"), 0)

        # 下游继续背压：错误码和所有状态字段必须保持稳定，并拒绝新命令。
        blocked = self._step(
            port,
            self._command("MASK_BEGIN", epoch=1),
            response_ready=False,
        )
        self.assertFalse(self._field(blocked, "cmd_ready"))
        self.assertFalse(self._field(blocked, "cmd_accepted"))
        self.assertTrue(self._field(blocked, "error_valid"))
        self.assertEqual(self._field(blocked, "error_code"), error_code)
        self.assertEqual(self._field(blocked, "state"), "empty")
        self.assertEqual(self._field(blocked, "word_index"), 0)
        self.assertEqual(self._field(blocked, "active_epoch"), 0)

        # 接受错误响应后，端口恢复可用；之前的非法命令没有推进任何索引。
        self._step(port, response_ready=True)
        resumed = self._step(
            port,
            self._command("MASK_BEGIN", epoch=1),
        )
        self.assertTrue(self._field(resumed, "cmd_accepted"))
        self.assertEqual(self._field(resumed, "state"), "loading")
        self.assertEqual(self._field(resumed, "word_index"), 0)

    def test_reserved_bits_error_has_zero_side_effect_and_retries_same_index(self):
        """word18 高 16 位非零只报错；修正后仍在同一隐式索引重试。"""
        port = self._new_port()
        self._step(port, self._command("MASK_BEGIN", epoch=1))

        for _ in range(18):
            loaded = self._step(port, self._command("DATA", word=0))
            self.assertTrue(self._field(loaded, "cmd_accepted"))

        invalid_last = self._step(
            port,
            self._command("DATA", word=0x00010000),
            response_ready=False,
        )
        self.assertTrue(self._field(invalid_last, "cmd_accepted"))
        self.assertTrue(self._field(invalid_last, "error_valid"))
        self.assertEqual(self._field(invalid_last, "state"), "loading")
        self.assertEqual(self._field(invalid_last, "word_index"), 18)
        self.assertEqual(self._field(invalid_last, "active_epoch"), 0)

        # 错误响应排空后，同一 word index 接受合法低 16 位，进入 complete。
        self._step(port, response_ready=True)
        retried = self._step(port, self._command("DATA", word=0x0000FFFF))
        self.assertTrue(self._field(retried, "cmd_accepted"))
        self.assertFalse(self._field(retried, "error_valid"))
        self.assertEqual(self._field(retried, "state"), "complete")
        self.assertEqual(self._field(retried, "word_index"), 19)

    def test_mask_abort_clears_loading_and_complete_staging(self):
        """MASK_ABORT 在 loading/complete 均清空 staging，不改变 active epoch。"""
        port = self._new_port()
        self._step(port, self._command("MASK_BEGIN", epoch=1))
        self._step(port, self._command("DATA", word=0))

        aborted_loading = self._step(port, self._command("MASK_ABORT"))
        self.assertTrue(self._field(aborted_loading, "cmd_accepted"))
        self.assertFalse(self._field(aborted_loading, "error_valid"))
        self.assertEqual(self._field(aborted_loading, "state"), "empty")
        self.assertEqual(self._field(aborted_loading, "word_index"), 0)
        self.assertEqual(self._field(aborted_loading, "active_epoch"), 0)

        self._step(port, self._command("MASK_BEGIN", epoch=1))
        for _ in range(19):
            self._step(port, self._command("DATA", word=0))
        self.assertEqual(port.state, "complete")

        aborted_complete = self._step(port, self._command("MASK_ABORT"))
        self.assertTrue(self._field(aborted_complete, "cmd_accepted"))
        self.assertFalse(self._field(aborted_complete, "error_valid"))
        self.assertEqual(self._field(aborted_complete, "state"), "empty")
        self.assertEqual(self._field(aborted_complete, "word_index"), 0)
        self.assertEqual(self._field(aborted_complete, "active_epoch"), 0)

    def test_invalid_epoch_reports_once_without_state_progress(self):
        """MASK_BEGIN/COMMIT 的非法 epoch 只报错，不推进状态或 word index。"""
        port = self._new_port()

        invalid_begin = self._step(
            port,
            self._command("MASK_BEGIN", epoch=-1),
            response_ready=False,
        )
        self.assertTrue(self._field(invalid_begin, "cmd_accepted"))
        self.assertTrue(self._field(invalid_begin, "error_valid"))
        self.assertEqual(self._field(invalid_begin, "state"), "empty")
        self.assertEqual(self._field(invalid_begin, "word_index"), 0)
        self.assertEqual(self._field(invalid_begin, "active_epoch"), 0)
        self._step(port, response_ready=True)

        self._step(port, self._command("MASK_BEGIN", epoch=1))
        for _ in range(19):
            self._step(port, self._command("DATA", word=0))
        self.assertEqual(port.state, "complete")

        invalid_commit = self._step(
            port,
            self._command("MASK_COMMIT", epoch=3),
            response_ready=False,
        )
        self.assertTrue(self._field(invalid_commit, "cmd_accepted"))
        self.assertTrue(self._field(invalid_commit, "error_valid"))
        self.assertEqual(self._field(invalid_commit, "state"), "complete")
        self.assertEqual(self._field(invalid_commit, "word_index"), 19)
        self.assertEqual(self._field(invalid_commit, "active_epoch"), 0)
        self._step(port, response_ready=True)

        valid_commit = self._step(port, self._command("MASK_COMMIT", epoch=1))
        self.assertTrue(self._field(valid_commit, "cmd_accepted"))
        self.assertEqual(self._field(valid_commit, "state"), "published")

    def test_published_mask_activates_at_sample_boundary(self):
        """published 只在样本边界交换为 active，并清空 staging 状态。"""
        port = self._new_port()
        self._step(port, self._command("MASK_BEGIN", epoch=1))
        words = [0] * 19
        words[0] = 1 << 0
        words[16] = 1 << 0
        for word in words:
            self._step(port, self._command("DATA", word=word))
        self._step(port, self._command("MASK_COMMIT", epoch=1))

        self.assertEqual(port.state, "published")
        self.assertEqual(port.active_epoch, 0)
        activated_epoch = port.accept_sample_boundary()

        self.assertEqual(activated_epoch, 1)
        self.assertEqual(port.active_epoch, 1)
        self.assertEqual(port.state, "empty")
        self.assertEqual(port.word_index, 0)
        self.assertTrue(port.active_masks.mask0[0])
        self.assertFalse(port.active_masks.mask0[1])
        self.assertTrue(port.active_masks.mask1[0])
        self.assertFalse(port.active_masks.mask1[1])



if __name__ == "__main__":
    unittest.main()

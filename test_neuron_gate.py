"""NeuronGate V1 黄金模型回归。"""

from __future__ import annotations

import unittest

from neuron_gate_reference import INFER_MODE, TRAIN_MODE, NeuronGateV1


class NeuronGateReferenceTests(unittest.TestCase):
    def test_initial_state_and_mask(self) -> None:
        gate = NeuronGateV1()
        self.assertEqual(gate.mode, TRAIN_MODE)
        self.assertEqual(gate.keep_mask, 0xF)
        self.assertEqual(gate.candidate_mask, 0xF)
        self.assertFalse(gate.candidate_valid)
        self.assertEqual(gate.state.scores, (128, 128, 128, 128))
        self.assertEqual(gate.state.cooldowns, (0, 0, 0, 0))

    def test_active_score_and_idle_decay(self) -> None:
        gate = NeuronGateV1()
        for _ in range(8):
            gate.observe(0x1)
        self.assertEqual(gate.state.scores, (136, 127, 127, 127))

        for _ in range(8):
            gate.observe(0x0)
        self.assertEqual(gate.state.scores, (135, 126, 126, 126))

    def test_coincidence_and_local_feedback_boost(self) -> None:
        gate = NeuronGateV1()
        gate.observe(0x1, post_event=True, feedback_valid=True, feedback_correct=True)
        self.assertEqual(gate.state.scores[0], 136)

    def test_incorrect_feedback_penalizes_active_connection(self) -> None:
        gate = NeuronGateV1()
        gate.observe(0x1, feedback_valid=True, feedback_correct=False)
        self.assertEqual(gate.state.scores[0], 127)

    def test_candidate_is_committed_only_at_epoch_end(self) -> None:
        gate = NeuronGateV1(initial_scores=(10, 128, 128, 128), max_keep=0)
        candidate = gate.image_end()
        self.assertEqual(candidate, 0xE)
        self.assertEqual(gate.keep_mask, 0xF)

        committed = gate.epoch_end()
        self.assertEqual(committed, 0xE)
        self.assertEqual(gate.keep_mask, 0xE)
        self.assertFalse(gate.candidate_valid)

    def test_structured_2_of_4_keeps_highest_scores(self) -> None:
        gate = NeuronGateV1(initial_scores=(10, 20, 30, 40), max_keep=2)
        candidate = gate.image_end()
        self.assertEqual(candidate, 0xC)
        self.assertEqual(gate.epoch_end(), 0xC)

    def test_cooldown_blocks_immediate_regrow(self) -> None:
        gate = NeuronGateV1(initial_scores=(10, 128, 128, 128), max_keep=0)
        self.assertEqual(gate.image_end(), 0xE)
        self.assertEqual(gate.epoch_end(), 0xE)

        gate.scores[0] = 200
        self.assertEqual(gate.image_end(), 0xE)
        self.assertEqual(gate.state.cooldowns[0], 3)

        for _ in range(3):
            gate.epoch_end()
        self.assertEqual(gate.state.cooldowns[0], 0)
        self.assertEqual(gate.image_end(), 0xF)

    def test_infer_mode_freezes_learning_and_mask(self) -> None:
        gate = NeuronGateV1(initial_scores=(10, 20, 30, 40))
        gate.image_end()
        gate.epoch_end()
        gate.set_mode(INFER_MODE)

        with self.assertRaises(RuntimeError):
            gate.observe(0x1)
        with self.assertRaises(RuntimeError):
            gate.image_end()
        with self.assertRaises(RuntimeError):
            gate.epoch_end()
        self.assertEqual(gate.keep_mask, 0xC)

    def test_score_saturation(self) -> None:
        gate = NeuronGateV1(initial_scores=(255, 0, 128, 128))
        gate.observe(0x3, post_event=True, feedback_valid=True, feedback_correct=True)
        self.assertEqual(gate.state.scores[0], 255)
        self.assertEqual(gate.state.scores[1], 8)

        lower_gate = NeuronGateV1(initial_scores=(128, 0, 128, 128))
        lower_gate.observe(0x2, feedback_valid=True, feedback_correct=False)
        self.assertEqual(lower_gate.state.scores[1], 0)


if __name__ == "__main__":
    unittest.main()

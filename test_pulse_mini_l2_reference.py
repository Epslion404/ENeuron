"""Pulse-Mini-L2 PN evidence regression."""

from __future__ import annotations

import unittest

from pulse_mini_l2_reference import PulseMiniL2Reference
from pulse_mini_reference import Command, Mode, Opcode, Status


def send(model: PulseMiniL2Reference, opcode: Opcode, arg0: int = 0, arg1: int = 0):
    return model.execute(Command(opcode, arg0, arg1))


class PulseMiniL2ReferenceTests(unittest.TestCase):
    def train(self, model: PulseMiniL2Reference) -> None:
        self.assertTrue(send(model, Opcode.MODE_SET, Mode.TRAIN).ok)
        self.assertTrue(send(model, Opcode.STATE_CLEAR).ok)

    def test_repeated_positive_evidence_saturates_and_changes_magnitude(self) -> None:
        model = PulseMiniL2Reference(leak_period=8)
        self.train(model)
        for _ in range(4):
            # 一个证据段：输入 -> 教师 post -> 三个空 tick 释放窗口。
            send(model, Opcode.TICK, 1)
            send(model, Opcode.TICK, 0, 1)
            send(model, Opcode.TICK, 0)
            send(model, Opcode.TICK, 0)
            send(model, Opcode.TICK, 0)
        self.assertEqual(model.positive_evidence, [2, 0, 0, 0])
        self.assertEqual(model.negative_evidence, [0, 0, 0, 0])
        self.assertEqual(send(model, Opcode.CAPTURE).status, Status.OK)
        self.assertEqual(model.captured_direction, [2, 0, 0, 0])
        self.assertEqual(send(model, Opcode.FEEDBACK, 1).status, Status.OK)
        self.assertEqual(model.weights, [2, 0, 0, 0])

    def test_positive_and_negative_evidence_preserve_net_value(self) -> None:
        model = PulseMiniL2Reference()
        self.train(model)
        send(model, Opcode.TICK, 1, 1)
        send(model, Opcode.TICK, 1, 0)
        send(model, Opcode.TICK, 1, 1)
        send(model, Opcode.TICK, 1, 0)
        self.assertEqual(model.positive_evidence[0], 2)
        self.assertEqual(model.negative_evidence[0], 2)
        send(model, Opcode.CAPTURE)
        self.assertEqual(model.captured_direction[0], 0)

    def test_same_tick_positive_source_is_counted_once(self) -> None:
        model = PulseMiniL2Reference()
        self.train(model)
        send(model, Opcode.TICK, 1, 1)
        self.assertEqual(model.positive_evidence[0], 1)
        send(model, Opcode.TICK, 0, 1)
        self.assertEqual(model.positive_evidence[0], 2)

    def test_window_endpoint_counts_each_tick_once(self) -> None:
        model = PulseMiniL2Reference()
        self.train(model)
        send(model, Opcode.TICK, 0, 1)
        send(model, Opcode.TICK, 1)
        send(model, Opcode.TICK, 1)
        send(model, Opcode.TICK, 1)
        send(model, Opcode.TICK, 1)
        self.assertEqual(model.negative_evidence[0], 2)

    def test_capture_and_feedback_consume_evidence(self) -> None:
        model = PulseMiniL2Reference()
        self.train(model)
        send(model, Opcode.TICK, 1, 1)
        send(model, Opcode.CAPTURE)
        self.assertEqual(send(model, Opcode.FEEDBACK, 1).status, Status.OK)
        self.assertFalse(model.pending_valid)
        self.assertEqual(model.positive_evidence, [0, 0, 0, 0])
        self.assertEqual(model.negative_evidence, [0, 0, 0, 0])
        self.assertEqual(send(model, Opcode.FEEDBACK, 1).status, Status.NO_PENDING)
        self.assertEqual(model.weights[0], 1)

    def test_state_clear_preserves_weights_but_clears_pn(self) -> None:
        model = PulseMiniL2Reference()
        self.train(model)
        send(model, Opcode.TICK, 1, 1)
        send(model, Opcode.CAPTURE)
        send(model, Opcode.FEEDBACK, 1)
        self.assertEqual(send(model, Opcode.STATE_CLEAR).status, Status.OK)
        self.assertEqual(model.weights[0], 1)
        self.assertEqual(model.positive_evidence, [0, 0, 0, 0])
        self.assertEqual(model.negative_evidence, [0, 0, 0, 0])

    def test_infer_freezes_learning_fields(self) -> None:
        model = PulseMiniL2Reference(initial_weights=(1, -1, 0, 0))
        self.train(model)
        send(model, Opcode.TICK, 1, 1)
        before = model.state
        send(model, Opcode.MODE_SET, Mode.INFER)
        send(model, Opcode.TICK, 1)
        after = model.state
        self.assertEqual(after.weights, before.weights)
        self.assertEqual(after.positive_evidence, before.positive_evidence)
        self.assertEqual(after.negative_evidence, before.negative_evidence)
        self.assertEqual(after.pre_age, before.pre_age)
        self.assertEqual(after.post_age, before.post_age)
        self.assertEqual(after.captured_direction, before.captured_direction)
        self.assertNotEqual(after.leak_timer, before.leak_timer)

    def test_pending_blocks_state_changes(self) -> None:
        model = PulseMiniL2Reference()
        self.train(model)
        send(model, Opcode.TICK, 1, 1)
        send(model, Opcode.CAPTURE)
        before = model.state
        self.assertEqual(send(model, Opcode.TICK, 1, 1).status, Status.BUSY_PENDING)
        self.assertEqual(send(model, Opcode.STATE_CLEAR).status, Status.BUSY_PENDING)
        self.assertEqual(model.state, before)


if __name__ == "__main__":
    unittest.main()

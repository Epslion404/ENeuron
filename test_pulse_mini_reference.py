"""Pulse-Mini P2 黄金模型回归。

测试同时覆盖手算行为向量和 valid/ready 事务边界；这些测试在 RTL 出现前
冻结状态转移语义，避免 Python 与 SystemVerilog 各自发明窗口端点。
"""

from __future__ import annotations

import copy
import itertools
import unittest

from pulse_mini_reference import (
    Command,
    INPUT_MASK_GOLDEN_VECTORS,
    Mode,
    Opcode,
    PulseMiniReference,
    Status,
    decode_weight,
    encode_signed4,
    saturate,
)


def send(model: PulseMiniReference, opcode: Opcode, arg0: int = 0, arg1: int = 0):
    return model.execute(Command(opcode, arg0, arg1))


class PulseMiniReferenceTests(unittest.TestCase):
    def train(self, model: PulseMiniReference) -> None:
        self.assertTrue(send(model, Opcode.MODE_SET, Mode.TRAIN).ok)
        self.assertTrue(send(model, Opcode.STATE_CLEAR).ok)

    def infer(self, model: PulseMiniReference) -> None:
        self.assertTrue(send(model, Opcode.MODE_SET, Mode.INFER).ok)
        self.assertTrue(send(model, Opcode.STATE_CLEAR).ok)

    def test_contract_constants_and_signed_weight_encoding(self) -> None:
        self.assertEqual((PulseMiniReference.N_INPUTS, PulseMiniReference.THRESHOLD), (4, 6))
        self.assertEqual(PulseMiniReference.WINDOW, 3)
        self.assertEqual(PulseMiniReference.REFRACTORY_LENGTH, 1)
        for value in range(-7, 8):
            self.assertEqual(decode_weight(encode_signed4(value)), value)
        self.assertEqual(decode_weight(-7), -7)
        with self.assertRaises(ValueError):
            decode_weight(0x8)
        with self.assertRaises(ValueError):
            decode_weight(16)

    def test_all_sixteen_masks_are_direct_signed_accumulation(self) -> None:
        # 这些权重保证所有掩码都不会越过阈值，便于直接观察胞体贡献。
        model = PulseMiniReference(initial_weights=(-7, -3, 0, 2))
        self.infer(model)
        self.assertEqual(tuple(INPUT_MASK_GOLDEN_VECTORS), tuple(
            (mask, sum((-7, -3, 0, 2)[i] for i in range(4) if mask & (1 << i)))
            for mask in range(16)
        ))
        for mask, expected in INPUT_MASK_GOLDEN_VECTORS:
            self.assertTrue(send(model, Opcode.STATE_CLEAR).ok)
            response = send(model, Opcode.TICK, mask)
            self.assertTrue(response.ok, mask)
            self.assertEqual(response.spike, 0, mask)
            self.assertEqual(model.soma, expected, mask)
            self.assertEqual(model.event_log[-1]["details"]["input_mask"], mask)

    def test_all_input_permutations_collapse_to_the_same_mask(self) -> None:
        weights = (-2, 1, -1, 2)
        for mask in range(16):
            active = tuple(index for index in range(4) if mask & (1 << index))
            expected = sum(weights[index] for index in active)
            observations = []
            for ordered in itertools.permutations(active):
                # 接口是掩码采样；不同总线到达顺序必须编码为同一个掩码。
                encoded = sum(1 << index for index in ordered)
                model = PulseMiniReference(initial_weights=weights)
                self.infer(model)
                send(model, Opcode.TICK, encoded)
                observations.append(model.soma)
            self.assertEqual(observations, [expected] * max(1, len(observations)), mask)

    def test_positive_negative_and_zero_connections(self) -> None:
        model = PulseMiniReference(initial_weights=(7, -7, 0, 0))
        self.infer(model)
        self.assertEqual(send(model, Opcode.TICK, 1).spike, 1)  # 正连接促进发放
        self.assertEqual(send(model, Opcode.STATE_CLEAR).status, Status.OK)
        self.assertEqual(send(model, Opcode.TICK, 2).spike, 0)  # 负连接抑制
        self.assertEqual(model.soma, -7)
        self.assertEqual(send(model, Opcode.STATE_CLEAR).status, Status.OK)
        self.assertEqual(send(model, Opcode.TICK, 4).spike, 0)  # 零连接断开
        self.assertEqual(model.soma, 0)

    def test_positive_and_negative_soma_saturation_is_not_wraparound(self) -> None:
        model = PulseMiniReference(initial_weights=(7, 7, 7, 7))
        self.infer(model)
        model.soma = 120
        positive = send(model, Opcode.TICK, 0xF)
        self.assertEqual(positive.spike, 1)
        self.assertEqual(model.event_log[-1]["details"]["candidate"], 127)
        self.assertEqual(model.soma, 0)

        send(model, Opcode.STATE_CLEAR)
        model.weights = [-7, -7, -7, -7]
        model.soma = -120
        negative = send(model, Opcode.TICK, 0xF)
        self.assertEqual(negative.spike, 0)
        self.assertEqual(model.event_log[-1]["details"]["candidate"], -128)
        self.assertEqual(model.soma, -128)
        self.assertEqual(saturate(1000, -128, 127), 127)
        self.assertEqual(saturate(-1000, -128, 127), -128)

    def test_input_order_and_same_tick_presence_are_order_independent(self) -> None:
        # 掩码一次性采样，因而四条输入没有 RTL 语句顺序差异。
        left = PulseMiniReference(initial_weights=(2, 3, 0, 0))
        right = PulseMiniReference(initial_weights=(2, 3, 0, 0))
        self.infer(left)
        self.infer(right)
        send(left, Opcode.TICK, 0b0011)
        send(right, Opcode.TICK, 0b0011)
        self.assertEqual(left.state, right.state)

        for model in (left, right):
            model.reset()
            self.train(model)
            self.assertEqual(send(model, Opcode.TICK, 0b0001, 1).spike, 0)
            self.assertEqual(send(model, Opcode.CAPTURE).status, Status.OK)
            self.assertEqual(model.captured_direction, [1, 0, 0, 0])

    def test_window_endpoint_and_presence_conflict(self) -> None:
        # post_age=1 仍然有效；过一个无事件 tick 后端点失效。
        model = PulseMiniReference(initial_weights=(0, 0, 0, 0))
        self.train(model)
        send(model, Opcode.TICK, 0, 1)  # post_age = 3
        send(model, Opcode.TICK, 0)      # 2
        send(model, Opcode.TICK, 0)      # 1
        response = send(model, Opcode.TICK, 1)  # old post_age=1，负证据
        self.assertTrue(response.ok)
        self.assertTrue(model.negative_evidence[0])
        send(model, Opcode.TICK, 0)      # post_age=0
        self.assertEqual(model.post_age, 0)

        beyond = PulseMiniReference(initial_weights=(0, 0, 0, 0))
        self.train(beyond)
        send(beyond, Opcode.TICK, 0, 1)
        send(beyond, Opcode.TICK, 0)
        send(beyond, Opcode.TICK, 0)
        send(beyond, Opcode.TICK, 0)
        self.assertEqual(send(beyond, Opcode.TICK, 1).status, Status.OK)
        self.assertFalse(beyond.negative_evidence[0])

        # 同一输入既见过输入先于 post，又见过 post 先于输入，capture 必须中性。
        conflict = PulseMiniReference(initial_weights=(0, 0, 0, 0))
        self.train(conflict)
        send(conflict, Opcode.TICK, 1)
        send(conflict, Opcode.TICK, 0, 1)
        send(conflict, Opcode.TICK, 1)
        self.assertTrue(conflict.positive_evidence[0])
        self.assertTrue(conflict.negative_evidence[0])
        self.assertEqual(send(conflict, Opcode.CAPTURE).status, Status.OK)
        self.assertEqual(conflict.captured_direction[0], 0)

    def test_feedback_step_zero_consume_and_both_saturate(self) -> None:
        model = PulseMiniReference(initial_weights=(6, -6, 7, -7))
        self.train(model)
        model.positive_evidence = [True, False, True, False]
        model.negative_evidence = [False, True, False, True]
        self.assertEqual(send(model, Opcode.CAPTURE).status, Status.OK)
        self.assertEqual(model.captured_direction, [1, -1, 1, -1])
        self.assertEqual(send(model, Opcode.FEEDBACK, 1).status, Status.OK)
        self.assertEqual(model.weights, [7, -7, 7, -7])
        self.assertFalse(model.pending_valid)
        self.assertEqual(send(model, Opcode.FEEDBACK, 1).status, Status.NO_PENDING)

        model.positive_evidence = [True, False, True, False]
        model.negative_evidence = [False, True, False, True]
        send(model, Opcode.CAPTURE)
        before = list(model.weights)
        self.assertEqual(send(model, Opcode.FEEDBACK, 0).status, Status.OK)
        self.assertEqual(model.weights, before)

        model.positive_evidence = [True, False, True, False]
        model.negative_evidence = [False, True, False, True]
        send(model, Opcode.CAPTURE)
        self.assertEqual(send(model, Opcode.FEEDBACK, 3).status, Status.OK)
        self.assertEqual(model.weights, [6, -6, 6, -6])

    def test_pending_backpressure_and_exactly_once_response(self) -> None:
        model = PulseMiniReference()
        first = model.cycle(cmd_valid=True, command=Command(Opcode.MODE_SET, Mode.TRAIN))
        self.assertTrue(first.cmd_ready)
        self.assertFalse(first.rsp_valid)
        blocked = model.cycle(cmd_valid=True, command=Command(Opcode.STATE_CLEAR))
        self.assertFalse(blocked.cmd_ready)
        self.assertFalse(blocked.rsp_accepted)
        delivered = model.cycle(rsp_ready=True)
        self.assertTrue(delivered.rsp_valid)
        self.assertTrue(delivered.rsp_accepted)
        self.assertEqual(delivered.response.sequence, 0)
        accepted = model.cycle(cmd_valid=True, command=Command(Opcode.STATE_CLEAR))
        self.assertTrue(accepted.cmd_ready)
        self.assertEqual(model.event_log[-1]["sequence"], 1)
        model.cycle(rsp_ready=True)

        model.positive_evidence[0] = True
        self.assertEqual(send(model, Opcode.CAPTURE).status, Status.OK)
        self.assertEqual(send(model, Opcode.CAPTURE).status, Status.BUSY_PENDING)
        self.assertEqual(send(model, Opcode.TICK, 1).status, Status.BUSY_PENDING)
        self.assertEqual(send(model, Opcode.STATE_CLEAR).status, Status.BUSY_PENDING)

    def test_illegal_mode_feedback_and_weight_commands_are_non_mutating(self) -> None:
        model = PulseMiniReference(initial_weights=(1, 2, 3, 4))
        before = model.state
        self.assertEqual(send(model, Opcode.MODE_SET, 3).status, Status.BAD_ARG)
        self.assertEqual(model.state, before)
        self.assertEqual(send(model, Opcode.FEEDBACK, 2).status, Status.BAD_ARG)
        self.assertEqual(model.state, before)
        self.assertEqual(send(model, Opcode.WEIGHT_WRITE, 0, 8).status, Status.BAD_ARG)
        self.assertEqual(model.state, before)

        self.assertEqual(send(model, Opcode.WEIGHT_WRITE, 0, encode_signed4(-5)).status, Status.OK)
        self.assertEqual(send(model, Opcode.WEIGHT_READ, 0).data, -5)
        self.assertEqual(send(model, Opcode.WEIGHT_READ, 0).raw_data, encode_signed4(-5))
        self.assertEqual(send(model, Opcode.MODE_SET, Mode.TRAIN).status, Status.OK)
        locked = model.state
        self.assertEqual(send(model, Opcode.WEIGHT_WRITE, 1, 7).status, Status.BAD_MODE)
        self.assertEqual(model.state, locked)
        self.assertEqual(send(model, Opcode.MODE_SET, Mode.INFER).status, Status.OK)
        self.assertEqual(send(model, Opcode.WEIGHT_WRITE, 1, 7).status, Status.BAD_MODE)

    def test_state_clear_preserves_weights_and_hard_reset_restores_initial(self) -> None:
        model = PulseMiniReference(initial_weights=(1, -2, 3, -4))
        send(model, Opcode.WEIGHT_WRITE, 0, 7)
        send(model, Opcode.MODE_SET, Mode.TRAIN)
        send(model, Opcode.TICK, 1, 1)
        self.assertEqual(send(model, Opcode.STATE_CLEAR).status, Status.OK)
        self.assertEqual(model.weights, [7, -2, 3, -4])
        self.assertEqual(model.soma, 0)
        self.assertEqual(model.pre_age, [0, 0, 0, 0])
        model.reset()
        self.assertEqual(model.weights, [1, -2, 3, -4])
        self.assertEqual(model.mode, Mode.CONFIG)

    def test_infer_freezes_all_learning_fields_but_updates_dynamic_soma(self) -> None:
        model = PulseMiniReference(initial_weights=(1, -1, 0, 0))
        self.train(model)
        send(model, Opcode.TICK, 1)
        send(model, Opcode.TICK, 0, 1)
        before = model.state
        self.assertEqual(send(model, Opcode.MODE_SET, Mode.INFER).status, Status.OK)
        response = send(model, Opcode.TICK, 1)
        self.assertTrue(response.ok)
        after = model.state
        self.assertEqual(after.weights, before.weights)
        self.assertEqual(after.pre_age, before.pre_age)
        self.assertEqual(after.post_age, before.post_age)
        self.assertEqual(after.positive_evidence, before.positive_evidence)
        self.assertEqual(after.negative_evidence, before.negative_evidence)
        self.assertEqual(after.captured_direction, before.captured_direction)
        self.assertFalse(after.pending_valid)

    def test_train_post_never_fabricates_spike(self) -> None:
        model = PulseMiniReference(initial_weights=(0, 0, 0, 0))
        self.train(model)
        response = send(model, Opcode.TICK, 0, 1)
        self.assertEqual(response.spike, 0)
        self.assertEqual(model.last_spike, 0)
        self.assertEqual(model.post_age, PulseMiniReference.WINDOW)

    def test_every_accepted_command_has_ordered_structured_log(self) -> None:
        model = PulseMiniReference()
        commands = [
            Command(Opcode.WEIGHT_READ, 0),
            Command(Opcode.MODE_SET, Mode.TRAIN),
            Command(Opcode.STATE_CLEAR),
            Command(Opcode.TICK, 0, 1),
            Command(Opcode.CAPTURE),
            Command(Opcode.FEEDBACK, 0),
        ]
        for command in commands:
            response = send(model, command.opcode, command.arg0, command.arg1)
            self.assertEqual(response.sequence, len(model.event_log) - 1)
        self.assertEqual([entry["sequence"] for entry in model.event_log], list(range(len(commands))))
        for entry in model.event_log:
            self.assertIn("before", entry)
            self.assertIn("after", entry)
            self.assertIn("details", entry)
            self.assertIn("status", entry)


if __name__ == "__main__":
    unittest.main()

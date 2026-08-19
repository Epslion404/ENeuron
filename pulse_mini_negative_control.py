"""P4 负向控制：去掉 pending exactly-once 门后可构造重复反馈反例。"""

from pulse_mini_reference import Command, Mode, Opcode, PulseMiniReference


def main() -> None:
    model = PulseMiniReference()
    model.execute(Command(Opcode.MODE_SET, int(Mode.TRAIN)))
    model.positive_evidence[0] = True
    model.execute(Command(Opcode.CAPTURE))
    model.execute(Command(Opcode.FEEDBACK, 1))
    first_weight = model.weights[0]

    # 模拟错误实现：重复反馈没有检查 pending，而是重新消费旧方向。
    model.captured_direction[0] = 1
    model.pending_valid = True
    model.execute(Command(Opcode.FEEDBACK, 1))
    duplicate_weight = model.weights[0]
    assert first_weight == 1
    assert duplicate_weight == 2
    print("PULSE_MINI_NEGATIVE_CONTROL_PASS duplicate_feedback_counterexample=1")


if __name__ == "__main__":
    main()

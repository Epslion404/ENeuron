import unittest

from pulse_mini_reference import Command, Mode, Opcode, PulseMiniReference, Status


class PulseMiniNegativeControlTests(unittest.TestCase):
    def test_duplicate_feedback_is_rejected_by_real_contract(self) -> None:
        model = PulseMiniReference()
        model.execute(Command(Opcode.MODE_SET, int(Mode.TRAIN)))
        model.positive_evidence[0] = True
        self.assertEqual(model.execute(Command(Opcode.CAPTURE)).status, Status.OK)
        self.assertEqual(model.execute(Command(Opcode.FEEDBACK, 1)).status, Status.OK)
        self.assertEqual(model.execute(Command(Opcode.FEEDBACK, 1)).status, Status.NO_PENDING)
        self.assertEqual(model.weights[0], 1)


if __name__ == "__main__":
    unittest.main()

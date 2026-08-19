"""Pulse-Mini P5 最小监督任务与训练账本。"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Iterable

from pulse_mini_reference import Command, Mode, Opcode, PulseMiniReference, Status


@dataclass(frozen=True)
class Sample:
    label: int
    masks: tuple[int, ...]


def issue(model: PulseMiniReference, opcode: Opcode, arg0: int = 0, arg1: int = 0):
    return model.execute(Command(opcode, arg0, arg1))


def configure_train(model: PulseMiniReference) -> None:
    assert issue(model, Opcode.MODE_SET, int(Mode.TRAIN)).ok


def train_sample(model: PulseMiniReference, mask: int, feedback: int, ledger: list[dict]) -> None:
    assert issue(model, Opcode.STATE_CLEAR).status is Status.OK
    before = list(model.weights)
    tick = issue(model, Opcode.TICK, mask, 1)
    capture = issue(model, Opcode.CAPTURE)
    commit = issue(model, Opcode.FEEDBACK, 1 if feedback > 0 else 3)
    after = list(model.weights)
    assert tick.status is Status.OK and capture.status is Status.OK and commit.status is Status.OK
    assert before != after or feedback == 0
    ledger.append({
        "mask": mask,
        "feedback": feedback,
        "captured_direction": list(capture and model.event_log[-2]["details"].get("captured_direction", [])),
        "before_weights": before,
        "after_weights": after,
        "weight_write_count": 0,
    })


def run_training(*, positive_feedback: int = 1, negative_feedback: int = -1,
                 repetitions: int = 6) -> tuple[PulseMiniReference, list[dict]]:
    model = PulseMiniReference()
    configure_train(model)
    ledger: list[dict] = []
    for _ in range(repetitions):
        train_sample(model, 0b0001, positive_feedback, ledger)
        train_sample(model, 0b0010, negative_feedback, ledger)
    assert all(entry["weight_write_count"] == 0 for entry in ledger)
    return model, ledger


def classify(model: PulseMiniReference, sample: Sample) -> int:
    assert issue(model, Opcode.STATE_CLEAR).status is Status.OK
    for mask in sample.masks:
        response = issue(model, Opcode.TICK, mask)
        assert response.status is Status.OK
        if response.spike:
            return 1
    return 0


def heldout_samples() -> tuple[Sample, ...]:
    samples: list[Sample] = []
    # A 类始终包含至少六次正连接事件，插入无效通道作为扰动。
    for index in range(10):
        masks = tuple(0b0001 if ((index + tick) % 3) else 0b1001 for tick in range(8))
        samples.append(Sample(1, masks))
    # B 类只出现抑制通道，长度和 A 类相同。
    for index in range(10):
        masks = tuple(0b0010 if ((index + tick) % 2) else 0b1010 for tick in range(8))
        samples.append(Sample(0, masks))
    return tuple(samples)


def evaluate(model: PulseMiniReference, samples: Iterable[Sample]) -> tuple[int, int]:
    correct = 0
    total = 0
    for sample in samples:
        assert issue(model, Opcode.STATE_CLEAR).status is Status.OK
        before = copy.deepcopy(model.state)
        for mask in sample.masks:
            response = issue(model, Opcode.TICK, mask)
            assert response.status is Status.OK
            if response.spike:
                prediction = 1
                break
        else:
            prediction = 0
        after = model.state
        assert after.weights == before.weights
        assert after.positive_evidence == before.positive_evidence
        assert after.negative_evidence == before.negative_evidence
        assert after.captured_direction == before.captured_direction
        assert not after.pending_valid
        correct += int(prediction == sample.label)
        total += 1
    return correct, total


def run_p5() -> dict:
    baseline = PulseMiniReference()
    issue(baseline, Opcode.MODE_SET, int(Mode.INFER))
    before = evaluate(baseline, heldout_samples())
    model, ledger = run_training()
    issue(model, Opcode.MODE_SET, int(Mode.INFER))
    after = evaluate(model, heldout_samples())
    no_feedback, _ = run_training(positive_feedback=0, negative_feedback=0)
    issue(no_feedback, Opcode.MODE_SET, int(Mode.INFER))
    no_feedback_score = evaluate(no_feedback, heldout_samples())
    reversed_model, _ = run_training(positive_feedback=-1, negative_feedback=1)
    issue(reversed_model, Opcode.MODE_SET, int(Mode.INFER))
    reversed_score = evaluate(reversed_model, heldout_samples())
    shuffled_model, _ = run_training(positive_feedback=-1, negative_feedback=-1)
    issue(shuffled_model, Opcode.MODE_SET, int(Mode.INFER))
    shuffled_score = evaluate(shuffled_model, heldout_samples())
    result = {
        "before": {"correct": before[0], "total": before[1]},
        "after": {"correct": after[0], "total": after[1]},
        "no_feedback": {"correct": no_feedback_score[0], "total": no_feedback_score[1]},
        "reversed_feedback": {"correct": reversed_score[0], "total": reversed_score[1]},
        "label_shuffled": {"correct": shuffled_score[0], "total": shuffled_score[1]},
        "final_weights": model.weights,
        "ledger": ledger,
        "train_weight_write_count": sum(entry["weight_write_count"] for entry in ledger),
    }
    return result


def main() -> None:
    result = run_p5()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    if result["before"]["correct"] != 10:
        raise SystemExit("baseline did not abstain")
    if result["after"]["correct"] < 19:
        raise SystemExit("trained score below P5 threshold")
    if result["no_feedback"]["correct"] >= 19 or result["reversed_feedback"]["correct"] >= 19:
        raise SystemExit("negative control unexpectedly passed")
    print("PULSE_MINI_P5_PASS clean=20/20 heldout=20 train_weight_writes=0")


if __name__ == "__main__":
    main()

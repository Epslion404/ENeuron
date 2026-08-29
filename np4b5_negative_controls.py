"""NP4B5 负向控制：用最小错误模型证明验收器不是“永远通过”。"""

from __future__ import annotations

from dataclasses import dataclass
import re


class AcceptanceError(AssertionError):
    """候选实现违反 NP4B5 合同时抛出。"""


@dataclass(frozen=True)
class EvidenceRun:
    captured: tuple[int, int, int, int]
    utility: tuple[int, int, int, int]


class SnapshotBeforeModModel:
    """正确模型：MOD/FEEDBACK 消费开始前锁存 evidence。"""

    def run(self) -> EvidenceRun:
        live = [1, 2, 3, 0]
        captured = tuple(live)
        live[:] = [0, 0, 0, 0]  # MOD 完成会清 live 历史。
        return EvidenceRun(captured, captured)


class ReadEvidenceAfterModModel:
    """错误模型：先完成 MOD/FEEDBACK，再读取已被清除的 evidence。"""

    def run(self) -> EvidenceRun:
        live = [1, 2, 3, 0]
        live[:] = [0, 0, 0, 0]
        captured = tuple(live)
        return EvidenceRun(captured, captured)


def accept_preupdate_evidence(model: object) -> None:
    run = model.run()
    expected = (1, 2, 3, 0)
    if run.captured != expected or run.utility != expected:
        raise AcceptanceError("MOD/FEEDBACK 后读 evidence 导致漏观察或 utility 错误")


@dataclass(frozen=True)
class FreezeRun:
    issue_mask: int
    weights_before: tuple[int, int, int, int]
    weights_after: tuple[int, int, int, int]
    history_before: tuple[int, int, int, int]
    history_after: tuple[int, int, int, int]


class FullPrunedLaneFreezeModel:
    """正确模型：结构掩码同时冻结数值路径与学习历史。"""

    def run(self) -> FreezeRun:
        return FreezeRun(0b0101, (4, 5, 6, 7), (5, 5, 7, 7),
                         (8, 9, 10, 11), (9, 9, 11, 11))


class TickOnlyMaskModel:
    """错误模型：只掩 TICK 数值，仍更新 lane 1/3 的学习历史。"""

    def run(self) -> FreezeRun:
        return FreezeRun(0b0101, (4, 5, 6, 7), (5, 5, 7, 7),
                         (8, 9, 10, 11), (9, 10, 11, 12))


def accept_pruned_lane_freeze(model: object) -> None:
    run = model.run()
    pruned = (~run.issue_mask) & 0xF
    for lane in range(4):
        if pruned & (1 << lane):
            if run.weights_after[lane] != run.weights_before[lane]:
                raise AcceptanceError(f"被剪 lane {lane} 的权重发生变化")
            if run.history_after[lane] != run.history_before[lane]:
                raise AcceptanceError(f"被剪 lane {lane} 仍积累学习历史")


@dataclass(frozen=True)
class EpochSample:
    runtime_blocked: bool
    tick_accepted: bool
    mask_valids: int
    public_epoch: int


class AtomicTenGateBarrierModel:
    """正确模型：十 gate 汇合并 clear 后才统一发布 epoch。"""

    def trace(self) -> tuple[EpochSample, ...]:
        return (
            EpochSample(True, False, 0x001, 0),
            EpochSample(True, False, 0x1FF, 0),
            EpochSample(True, False, 0x3FF, 0),
            EpochSample(False, False, 0x3FF, 1),
            EpochSample(False, True, 0x3FF, 1),
        )


class SequentialPublicGateModel:
    """错误模型：gate 逐个公开，且中途允许普通 TICK。"""

    def trace(self) -> tuple[EpochSample, ...]:
        return (
            EpochSample(True, False, 0x001, 0),
            EpochSample(False, True, 0x01F, 0),
            EpochSample(False, True, 0x1FF, 0),
            EpochSample(False, True, 0x3FF, 1),
        )


def accept_atomic_ten_gate_epoch(model: object) -> None:
    full = 0x3FF
    for sample in model.trace():
        partial = sample.mask_valids not in (0, full)
        if sample.tick_accepted and (sample.runtime_blocked or partial):
            raise AcceptanceError("部分 mask epoch 中接受了 TICK")
        if sample.public_epoch and sample.mask_valids != full:
            raise AcceptanceError("十 gate 完成前公开了 epoch")


def accept_four_input_output_groups(source: str) -> None:
    """静态拒绝 output 神经元 fan-in 不是 4 的伪 2:4 网络。"""

    bus = re.search(r"logic\s*\[(\d+)\s*:\s*0\]\s+scheduler_output_inputs_flat", source)
    stride = re.search(
        r"scheduler_output_inputs_flat\s*\[\s*\(neuron_index-8\)\s*\*\s*(\d+)\s*\+:\s*(\d+)\s*\]",
        source,
    )
    wrapper = re.search(r"wrapper_inputs_flat\[neuron_index\*4\s*\+:\s*4\]", source)
    if bus is None or stride is None or wrapper is None:
        raise AcceptanceError("无法证明 output 使用四输入分组")
    bus_width = int(bus.group(1)) + 1
    group_stride, group_width = map(int, stride.groups())
    if (bus_width, group_stride, group_width) != (8, 4, 4):
        raise AcceptanceError("output fan-in 不是两组独立四输入，不能宣称 2:4")


__all__ = [name for name in globals() if name.startswith("accept_") or name.endswith("Model") or name == "AcceptanceError"]

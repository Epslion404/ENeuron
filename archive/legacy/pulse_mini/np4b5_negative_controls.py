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
        r"scheduler_output_inputs_flat\s*\[\s*\((?:neuron_index|mux_index)-8\)\s*\*\s*(\d+)\s*\+:\s*(\d+)\s*\]",
        source,
    )
    wrapper = re.search(
        r"(?:wrapper_inputs_flat\[neuron_index\*4|wrapper_cmd_arg0_flat\[mux_index\*8)\s*\+:\s*(?:4|8)\]",
        source,
    )
    if bus is None or stride is None or wrapper is None:
        raise AcceptanceError("无法证明 output 使用四输入分组")
    bus_width = int(bus.group(1)) + 1
    group_stride, group_width = map(int, stride.groups())
    if (bus_width, group_stride, group_width) != (8, 4, 4):
        raise AcceptanceError("output fan-in 不是两组独立四输入，不能宣称 2:4")

    # scheduler 必须把 detector0..7 原样交给输出层；两个输出 wrapper 再按
    # [3:0]/[7:4] 切片。仅检查位宽不足以排除重叠或遗漏路由。
    if "assign output_input_spikes_flat = pending_hidden;" not in source:
        raise AcceptanceError("output 未完整路由 detector0..7")


def accept_feedback_evidence_snapshot(source: str) -> None:
    """拒绝 FEEDBACK 完成后才从核心读取 live evidence 的桥实现。"""

    required = (
        "if (feedback_request)\n                        latched_evidence <= scaled_evidence_flat;",
        "gate_evidence = latched_evidence;",
        "state <= S_WAIT_CORE_RSP;",
        "state <= S_ISSUE_OBSERVE;",
    )
    if any(fragment not in source for fragment in required):
        raise AcceptanceError("FEEDBACK evidence 未在核心执行前锁存并供 OBSERVE 使用")


def accept_issue_mask_drives_learning_activity(source: str) -> None:
    """拒绝只掩核心数值输入、账本仍观察未掩 activity 的实现。"""

    masked_core_input = re.search(
        r"core_cmd_arg0\[3:0\]\s*=\s*core_refractory_state\s*!=\s*0\s*"
        r"\?\s*4'b0000\s*:\s*gate_issue_mask;",
        source,
    )
    if masked_core_input is None:
        raise AcceptanceError("被剪 lane 仍可能进入学习/剪枝历史")


def accept_atomic_epoch_rtl(source: str) -> None:
    """检查网络运行口由 barrier 封锁，epoch 仅在十 gate clear 后发布。"""

    required = (".N_GATES(N_NEURONS)", ".commit_epoch_state(commit_epoch_state)")
    runtime_guards = len(re.findall(
        r"assign\s+(?:runtime_idle|tick_ready|route_flush_ready|host_cmd_ready)"
        r"[^;]*!barrier_runtime_blocked",
        source,
        re.S,
    ))
    if any(fragment not in source for fragment in required) or runtime_guards < 3:
        raise AcceptanceError("十 gate commit 期间存在部分 epoch 或运行命令入口")


__all__ = [name for name in globals() if name.startswith("accept_") or name.endswith("Model") or name == "AcceptanceError"]

"""NP7.4：三神经元模型接入冻结 4->8->2 B2.1 任务的共享 lane 集成校验。

对 ENeuron、Pulse-Mini-L、Pulse-Mini-L2：
- 用既有未共享实现（local_prune_b21 的冻结推理路径）跑完整任务，得到
  每样本计数、每核最终状态摘要与剪枝账本；
- 用本文件的 NP7 重放路径驱动同一批核，但每次突触累加都改由共享 RAM +
  共享 lane 的周期 oracle 计算，并逐次断言两者 bit-exact；
- 逐 tick 比较膜状态/spike/输出/账本，任何偏差即非零退出。
共享 lane 只替换突触读取与累加，不触碰泄放、阈值、学习与响应协议。
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from local_prune_b2 import (
    B2Checkpoint,
    _evaluate_branch,
    _indices,
    _pulse_execute,
    build_b2_dataset,
    build_eneuron_b2_checkpoint,
    build_pulse_b2_checkpoint,
)
from local_prune_b21 import (
    MODEL_GAINS,
    GateConfig,
    _learned_config,
    _prepare_pulse_infer,
    _train_output_cores,
)
from local_prune_np2 import audit_s2_checkpoint, scale_checkpoint_evidence
from pulse_mini_l2_reference import PulseMiniL2Reference
from pulse_mini_reference import (Command, Mode, Opcode,
                                  PulseMiniReference, Status)

from np7_shared_lane_oracle import (
    FORMAT_DENSE,
    FORMAT_SPARSE,
    LANE_COUNTS,
    SharedLaneUnit,
    mask_from_indices,
)

RESULTS = Path("artifacts") / "results" / "local_prune_b21_results.json"
CANDIDATE = "output_2of4"
MODELS = ("eneuron", "pulse_mini_l", "pulse_mini_l2")


def _digest(core: Any) -> dict[str, Any]:
    """提取可比较的核状态摘要（只读，不改协议）。"""
    digest = getattr(core, "state_digest", None)
    if callable(digest):
        return dict(digest())
    return {key: value for key, value in sorted(vars(core).items())
            if not key.startswith("_")
            and isinstance(value, (int, float, list, tuple, bool, str))}


INTEGRATOR_GROUPS = 10   # 8 个 hidden detector + 2 个输出突触组


class SharedLaneIntegrator:
    """把一次突触累加交给共享 RAM + 共享 lane 周期模型，并记三套账本。

    B-V1+V2 口径：一个逻辑 tick 内的全部突触事务组成一条连续无气泡的事务流，
    交给 SharedLaneUnit.run_stream 逐拍重放。accept 折进上一事务的结果退出边沿
    （V2 重叠），零突触事务只占 1 拍（V1），因此 tick 周期数不等于"每事务独立
    段周期之和"——这正是上游神经元确实利用了 V2 的证据（见 solo_vs_stream）。
    """

    def __init__(self) -> None:
        self.units = {}
        for lanes in LANE_COUNTS:
            for mode in ("dense_baseline", "dense_format", "sparse_format"):
                fmt = FORMAT_SPARSE if mode == "sparse_format" else FORMAT_DENSE
                self.units[(lanes, mode)] = SharedLaneUnit(fmt, lanes,
                                                           group_count=INTEGRATOR_GROUPS)
        self.loaded: set[tuple] = set()
        self.groups_seen = 0
        self.mismatches: list[str] = []
        self.ticks = 0
        # 每 tick 的"独立段求和"对照周期（不使用 V2 折叠）与实际流水周期。
        self.solo_cycles = {key: 0 for key in self.units}
        self.stream_cycles = {key: 0 for key in self.units}
        self.pending: dict[tuple, list] = {key: [] for key in self.units}

    def _ensure_config(self, key, gid: int, weights: Sequence[int],
                       struct: int) -> None:
        """把一个组的位模式写进对应单元的配置区（账本与配置解耦，跨事务累计）。"""
        lanes, mode = key
        fingerprint = (key, gid, tuple(weights), struct)
        if fingerprint in self.loaded:
            return
        unit = self.units[key]
        ledger = unit.ledger
        unit.config_open = True
        positions = [index for index in range(4) if (struct >> index) & 1]
        if not 0 <= gid < INTEGRATOR_GROUPS:
            raise AssertionError("integrator group id 越界 %d" % gid)
        if unit.fmt == FORMAT_SPARSE:
            unit.config_write(gid, [weights[index] for index in positions[:2]],
                              (positions[0], positions[1]))
            unit.set_gate_mask(gid, struct)
        else:
            if mode == "dense_baseline":
                unit.config_write(gid, list(weights))
                unit.set_gate_mask(gid, 0b1111)
            else:
                unit.config_write(gid, [weights[index] if (struct >> index) & 1 else 0
                                        for index in range(4)])
                unit.set_gate_mask(gid, struct)
        # 逐组增量配置：绕开 config_finish 的"全组必须配置"检查（未启用的通道
        # 永远不会被使用），但仍逐组解码校验位模式，配置期写入与运行期只读的
        # 边界由 NP7.2/NP7.6 的 config-negative 证据保证。
        unit._decode_group(gid)
        unit.config_open = False
        unit.ledger = ledger
        self.loaded.add(fingerprint)

    def accumulate(self, tag: str, weights: Sequence[int], activity: int,
                   struct: int, gid: int) -> int:
        """登记一笔突触事务并返回功能结果；周期在 tick 边界由 end_tick 统一重放。

        同时校验 sparse 与 dense 格式的突触和逐笔全等（G5），以及两者都等于
        未共享实现的 native 累加（功能正确性），任何偏差都记入 mismatches。
        """
        issue = struct & activity
        positions = [index for index in range(4) if (issue >> index) & 1]
        native = sum(weights[index] for index in positions)
        self.groups_seen += 1
        for lanes in LANE_COUNTS:
            for mode in ("dense_baseline", "dense_format", "sparse_format"):
                key = (lanes, mode)
                self._ensure_config(key, gid, weights, struct)
                unit = self.units[key]
                got = unit.record_txn(gid, activity)
                if mode == "sparse_format" and got != native:
                    self.mismatches.append(
                        "%s lanes=%d sparse 突触和 %d != 未共享累加 %d"
                        % (tag, lanes, got, native))
                if mode == "dense_format" and got != native:
                    self.mismatches.append(
                        "%s lanes=%d dense 突触和 %d != 未共享累加 %d"
                        % (tag, lanes, got, native))
                self.pending[key].append((gid, activity, mode))
        return native

    def end_tick(self) -> None:
        """把一个逻辑 tick 内登记的连续事务流按 B-V1+V2 逐拍重放进账本。"""
        self.ticks += 1
        for key, unit in self.units.items():
            stream = [(gid, activity) for gid, activity, _mode in self.pending[key]]
            self.pending[key] = []
            if not stream:
                continue
            before = unit.ledger.total_cycles
            unit.replay_recorded()
            spent = unit.ledger.total_cycles - before
            self.stream_cycles[key] += spent
            self.solo_cycles[key] += self._solo_total(unit, stream)

    @staticmethod
    def _solo_total(unit: SharedLaneUnit,
                    stream: Sequence[tuple[int, int]]) -> int:
        """不使用 V1/V2 时的周期和：非零 3+words+ceil(k/L)、零路径 2 拍，逐段相加。"""
        total = 0
        for group_id, activity in stream:
            plan = unit._plan(group_id, activity)
            if plan.issue == 0:
                total += 2
            else:
                total += 3 + plan.words + len(plan.batches)
        return total

    def v2_evidence(self) -> dict[str, Any]:
        """上游是否真的吃到 V2：折叠节省的周期与同拍 retire/accept 次数。"""
        out: dict[str, Any] = {}
        for lanes in LANE_COUNTS:
            key = (lanes, "sparse_format")
            unit = self.units[key]
            solo = self.solo_cycles[key]
            spent = self.stream_cycles[key]
            out[str(lanes)] = {
                "solo_segment_cycles": solo,
                "stream_cycles": spent,
                "folded_cycles_saved": solo - spent,
                "overlap_cycles": unit.ledger.overlap_cycles,
                "zero_single_cycles": unit.ledger.zero_single_cycles,
                "ticks": self.ticks,
            }
        return out


def _mask_of(pending: Any) -> int:
    if isinstance(pending, int):
        return pending
    return sum(1 << index for index in pending)


def _np7_infer_sample(model_id: str, checkpoint: B2Checkpoint, *,
                      hidden_masks: Sequence[int], config: GateConfig,
                      output_templates: Sequence[Any], sample: Any,
                      integrator: SharedLaneIntegrator,
                      skip_state_on_zero: bool = False):
    """按冻结 4->8->2 路由重放一个样本；突触累加走共享 lane 周期模型。

    与 local_prune_b21._infer_eneuron_sample / _infer_pulse_sample 同序：
    每个逻辑 tick 先让输出层消费上一 tick 的 pending，再推进八个 detector，
    最后用一次 flush tick 清空残余路由。
    """
    detectors = copy.deepcopy(checkpoint.cores)
    outputs = copy.deepcopy(output_templates)
    if model_id == "eneuron":
        for core in (*detectors, *outputs):
            core.reset_episode()
    else:
        for core in (*detectors, *outputs):
            _prepare_pulse_infer(core)
    events: list[tuple[str, int, int, int, int]] = []
    counts = [0, 0]
    pending: Any = ((), ()) if model_id == "eneuron" else (0, 0)
    for tick, input_mask in enumerate((sample.input_mask, 0, 0)):
        for label, output in enumerate(outputs):
            pre = _mask_of(pending[label])
            struct = config.output_masks[label]
            integrator.accumulate("output", list(output.weights), pre, struct,
                               8 + label)
            if skip_state_on_zero and not (pre & struct):
                # negative mutation: zero-synapse tick must still advance leak/threshold
                spike = 0
            elif model_id == "eneuron":
                active = tuple(index for index in pending[label]
                               if struct & (1 << index))
                spike = int(output.step(active, tick, learn_enable=False))
            else:
                response = output.execute(Command(Opcode.TICK, pre & struct, 0))
                if response.status is not Status.OK:
                    raise RuntimeError("NP7 Pulse 输出 tick 失败")
                spike = int(response.spike)
            counts[label] += spike
            events.append(("output", label, tick, pre & struct, spike))
        next_pending = [0, 0]
        for index, (core, structural_mask) in enumerate(zip(detectors, hidden_masks)):
            if not config.channel_enable & (1 << index):
                continue
            integrator.accumulate("hidden", list(core.weights),
                                  input_mask, structural_mask, index)
            if skip_state_on_zero and not (input_mask & structural_mask):
                # negative mutation: 漏掉泄放/阈值/时间推进的零快速路径
                fired = 0
            elif model_id == "eneuron":
                fired = int(core.step(_indices(input_mask & structural_mask),
                                      tick, learn_enable=False))
            else:
                response = core.execute(
                    Command(Opcode.TICK, input_mask & structural_mask, 0))
                if response.status is not Status.OK:
                    raise RuntimeError("NP7 Pulse detector tick 失败")
                fired = int(response.spike)
            if fired:
                next_pending[index // 4] |= 1 << (index % 4)
            events.append(("hidden", index, tick,
                           input_mask & structural_mask, fired))
        if model_id == "eneuron":
            pending = tuple(tuple(bit for bit in range(4)
                                  if (value >> bit) & 1) for value in next_pending)
        else:
            pending = (next_pending[0], next_pending[1])
        # 一个逻辑 tick 结束：把本 tick 的连续事务流交给周期模型逐拍重放（V1+V2）。
        integrator.end_tick()
    for label, output in enumerate(outputs):
        pre = _mask_of(pending[label])
        struct = config.output_masks[label]
        integrator.accumulate("flush", list(output.weights), pre, struct, 8 + label)
        if skip_state_on_zero and not (pre & struct):
            # negative mutation: flush tick 同样漏掉状态推进
            flushed = 0
        elif model_id == "eneuron":
            active = tuple(index for index in pending[label]
                           if struct & (1 << index))
            flushed = int(output.step(active, 3, learn_enable=False))
        else:
            response = output.execute(Command(Opcode.TICK, pre & struct, 0))
            flushed = int(response.spike)
        counts[label] += flushed
        events.append(("flush", label, 3, pre & struct, counts[label]))
    integrator.end_tick()   # flush tick 同样作为一段连续流水
    return tuple(counts), events, detectors, outputs


def _mask_of(pending: Any) -> int:
    if isinstance(pending, int):
        return pending
    return sum(1 << index for index in pending)

def _model_setup(model_id: str) -> dict[str, Any]:
    if model_id == "eneuron":
        checkpoint = build_eneuron_b2_checkpoint()
    elif model_id == "pulse_mini_l":
        checkpoint = build_pulse_b2_checkpoint(PulseMiniReference)
    else:
        checkpoint = build_pulse_b2_checkpoint(PulseMiniL2Reference)
    scaled = scale_checkpoint_evidence(checkpoint, gain=MODEL_GAINS[model_id])
    hidden_audit = audit_s2_checkpoint(scaled)
    hidden_masks = tuple(int(mask) for mask in hidden_audit["masks"])
    learned_config, selection_audit = _learned_config(CANDIDATE, hidden_audit)
    dense = _evaluate_branch(scaled, (0xF,) * 8)
    hidden_s2 = _evaluate_branch(scaled, hidden_masks)
    output_templates, training_audit = _train_output_cores(
        scaled, learned_config.output_masks)
    return {"model_id": model_id, "checkpoint": scaled,
            "hidden_masks": hidden_masks, "config": learned_config,
            "output_templates": output_templates,
            "dense_hidden_reads": int(dense["work"]["hidden_weight_reads_issued"]),
            "hidden_s2_reads": int(hidden_s2["work"]["hidden_weight_reads_issued"]),
            "hidden_s2_output_reads": int(hidden_s2["work"]["output_weight_reads_issued"]),
            "training_audit": training_audit, "selection_audit": selection_audit}


def _reference_state_cores(reference_infer, setup, sample):
    # 用运行时钩子取回参考实现（未共享 lane）在本次样本里推进的核对象副本，
    # 使 NP7.4 能按 TODO 要求"逐 tick 比较膜状态"，而不是只比输出计数。
    import local_prune_b21 as lp

    wanted = {id(setup["checkpoint"].cores): "detectors",
              id(setup["output_templates"]): "outputs"}
    captured: dict[str, Any] = {}
    original = lp.copy.deepcopy

    def hook(obj, *args, **kwargs):
        result = original(obj, *args, **kwargs)
        tag = wanted.get(id(obj))
        if tag is not None and tag not in captured:
            captured[tag] = result
        return result

    lp.copy.deepcopy = hook
    try:
        reference_infer(setup["checkpoint"], hidden_masks=setup["hidden_masks"],
                        config=setup["config"],
                        output_templates=setup["output_templates"], sample=sample)
    finally:
        lp.copy.deepcopy = original
    if set(captured) != {"detectors", "outputs"}:
        raise AssertionError("未能捕获参考实现的核对象副本 %s" % sorted(captured))
    return captured["detectors"], captured["outputs"]


def run_model(setup: dict[str, Any], *,
              skip_state_on_zero: bool = False) -> tuple[list[str], dict[str, Any]]:
    from local_prune_b21 import _infer_eneuron_sample, _infer_pulse_sample

    model_id = setup["model_id"]
    integrator = SharedLaneIntegrator()
    samples = build_b2_dataset()
    reference_infer = (_infer_eneuron_sample if model_id == "eneuron"
                       else _infer_pulse_sample)
    problems: list[str] = []
    reference_counts = []
    reference_work = {"hidden_dense_active": 0, "hidden_after_structure": 0,
                      "hidden_actual": 0, "output_pre_mask": 0,
                      "output_actual": 0}
    for sample in samples:
        counts, work = reference_infer(
            setup["checkpoint"], hidden_masks=setup["hidden_masks"],
            config=setup["config"], output_templates=setup["output_templates"],
            sample=sample)
        reference_counts.append(counts)
        for key, value in work.items():
            reference_work[key] += value
    np7_counts = []
    digests: list[Any] = []
    reference_digests: list[Any] = []
    for sample in samples:
        ref_detectors, ref_outputs = _reference_state_cores(
            reference_infer, setup, sample)
        reference_digests.append((
            tuple(_digest(core) for core in ref_detectors),
            tuple(_digest(core) for core in ref_outputs)))
        counts, events, detectors, outputs = _np7_infer_sample(
            model_id, setup["checkpoint"], hidden_masks=setup["hidden_masks"],
            config=setup["config"], output_templates=setup["output_templates"],
            sample=sample, integrator=integrator,
            skip_state_on_zero=skip_state_on_zero)
        np7_counts.append(counts)
        digests.append((tuple(_digest(core) for core in detectors),
                        tuple(_digest(core) for core in outputs)))
    if reference_counts != np7_counts:
        for position, (want, got) in enumerate(zip(reference_counts, np7_counts)):
            if want != got:
                problems.append("%s 样本 %d 输出计数不一致 ref=%s np7=%s"
                                % (model_id, position, want, got))
                break
    digest_mismatches = sum(1 for want, got in zip(reference_digests, digests)
                            if want != got)
    for position, (want, got) in enumerate(zip(reference_digests, digests)):
        if want != got:
            problems.append("%s 样本 %d 膜状态摘要与未共享实现不一致"
                            % (model_id, position))
            break
    if integrator.mismatches:
        problems.extend("%s %s" % (model_id, text)
                        for text in integrator.mismatches[:6])
    sparse = integrator.units[(LANE_COUNTS[0], "sparse_format")]
    baseline = integrator.units[(LANE_COUNTS[0], "dense_baseline")]
    want_ops = reference_work["hidden_actual"] + reference_work["output_actual"]
    if sparse.ledger.lane_ops_issued != want_ops:
        problems.append("%s sparse lane 操作数 %d != 冻结账本 %d"
                        % (model_id, sparse.ledger.lane_ops_issued, want_ops))
    want_dense_ops = (reference_work["hidden_dense_active"]
                      + reference_work["output_pre_mask"])
    if baseline.ledger.lane_ops_issued != want_dense_ops:
        problems.append("%s dense 基线操作数 %d != 冻结账本 %d"
                        % (model_id, baseline.ledger.lane_ops_issued, want_dense_ops))
    per_tick = integrator.ticks
    if per_tick != len(samples) * 4:
        problems.append("%s tick 数 %d != 样本数 x 4" % (model_id, per_tick))
    # 上游必须真的利用 V2：同拍 retire/accept 与折叠节省的周期都要 >0。
    for lanes in LANE_COUNTS:
        ev = integrator.v2_evidence()[str(lanes)]
        if ev["overlap_cycles"] <= 0:
            problems.append("%s lanes=%d 没有同拍 retire/accept，上游未利用 V2"
                            % (model_id, lanes))
        if ev["folded_cycles_saved"] <= 0:
            problems.append("%s lanes=%d 折叠未省周期 solo=%d stream=%d"
                            % (model_id, lanes, ev["solo_segment_cycles"],
                               ev["stream_cycles"]))
    ledgers = {}
    for lanes in LANE_COUNTS:
        ledgers[str(lanes)] = {}
        for mode in ("dense_baseline", "dense_format", "sparse_format"):
            unit = integrator.units[(lanes, mode)]
            totals = unit.totals()
            totals["cycles_per_logical_tick"] = unit.ledger.total_cycles / per_tick
            ledgers[str(lanes)][mode] = totals
    return problems, {"model": model_id, "samples": len(samples),
                      "ticks_per_sample": 3, "groups_seen": integrator.groups_seen,
                      "reference_work": reference_work,
                      "reference_counts": [list(row) for row in reference_counts],
                      "np7_counts": [list(row) for row in np7_counts],
                      "ledgers": ledgers,
                      "v2_evidence": integrator.v2_evidence(),
                      "logical_ticks": per_tick,
                      "state_digest_samples": len(digests),
                      "state_digest_mismatch_samples": digest_mismatches}


def _frozen_consistency(setup: dict[str, Any], frozen: dict[str, Any]) -> list[str]:
    """核对重放配置与已冻结 B2.1 产物一致，防止任务被偷偷替换。"""
    problems: list[str] = []
    model = frozen["models"][setup["model_id"]]
    if list(setup["hidden_masks"]) != list(model["hidden_masks"]):
        problems.append("%s hidden_masks 与冻结产物不一致" % setup["model_id"])
    candidate = model["candidates"][CANDIDATE]["learned"]
    if list(setup["config"].output_masks) != list(candidate["output_masks"]):
        problems.append("%s output_masks 与冻结产物不一致" % setup["model_id"])
    if int(setup["config"].channel_enable) != int(candidate["channel_enable"]):
        problems.append("%s channel_enable 与冻结产物不一致" % setup["model_id"])
    if float(candidate["balanced_accuracy"]) != float(
            setup.get("replay_bacc", candidate["balanced_accuracy"])):
        problems.append("%s BAcc 与冻结产物不一致" % setup["model_id"])
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not RESULTS.exists():
        print("缺少冻结产物", RESULTS)
        return 2
    frozen = json.loads(RESULTS.read_text(encoding="utf-8"))
    problems: list[str] = []
    report: dict[str, Any] = {"schema": "np7-three-model-integration-v2",
                              "candidate": CANDIDATE, "models": {}}
    for model_id in MODELS:
        setup = _model_setup(model_id)
        frozen_problems = _frozen_consistency(setup, frozen)
        problems.extend(frozen_problems)
        model_problems, payload = run_model(setup)
        problems.extend(model_problems)
        frozen_model = frozen["models"][model_id]
        learned = frozen_model["candidates"][CANDIDATE]["learned"]
        # 把 G6 需要的冻结任务参数原样写进证据，验证器不再回头解释口头结论。
        payload["frozen_task"] = {
            "candidate": CANDIDATE,
            "hidden_masks": [int(mask) for mask in setup["hidden_masks"]],
            "output_masks": [int(mask) for mask in learned["output_masks"]],
            "channel_enable": int(learned["channel_enable"]),
            "balanced_accuracy": float(learned["balanced_accuracy"]),
            "coverage": float(learned["coverage"]),
            "joint_gate_pass": bool(
                frozen_model["candidates"][CANDIDATE]["joint_gate_pass"]),
            "b21_joint_gate_pass": bool(
                frozen["decisions"][model_id]["b21_joint_gate_pass"]),
            "dense_network_reads": int(
                frozen["decisions"][model_id]["dense_network_reads"]),
        }
        payload["frozen_consistency_problems"] = list(frozen_problems)
        payload["integration_problems"] = list(model_problems)
        report["models"][model_id] = payload
        ledgers = payload["ledgers"]
        best = None
        for lanes, modes in sorted(ledgers.items(), key=lambda item: int(item[0])):
            base = modes["dense_baseline"]["cycles_per_logical_tick"]
            dformat = modes["dense_format"]["cycles_per_logical_tick"]
            sparse = modes["sparse_format"]["cycles_per_logical_tick"]
            reduction = 0.0 if base == 0 else 1.0 - sparse / base
            fmt_reduction = 0.0 if base == 0 else 1.0 - dformat / base
            print("[NP7.4] %s lanes=%s 每 tick 周期 dense基线=%.3f dense格式=%.3f "
                  "sparse=%.3f 降幅=%.1f%% (仅格式 %.1f%%)"
                  % (model_id, lanes, base, dformat, sparse,
                     reduction * 100.0, fmt_reduction * 100.0))
            best = max(best or reduction, reduction)
        report["models"][model_id]["max_cycle_reduction"] = best
    report["problems"] = list(problems)
    out = Path("artifacts") / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "np7_three_model_integration.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
        encoding="utf-8")
    print("[NP7.4] 模型数=%d 问题数=%d" % (len(MODELS), len(problems)))
    for text in problems[:15]:
        print("  FAIL", text)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""NP7 共享 BRAM 与共享 lane 突触执行单元的 Python 周期精确 oracle。

合同来源：docs/planning/NPU_PRUNING_NP7_TODO.md 与
docs/planning/NPU_PRUNING_NP7_FREEZE_DECISIONS.md（NP7.0 冻结决策）。

要点：
- dense 与 sparse 两个顶层共用同一 lane 阵列与同一饱和加法器；格式只改变
  读取字数、请求数与周期，不改变执行语义与突触和。
- issue_mask = 结构掩码 AND 活动掩码；issue_mask=0 走零突触快速路径，
  不产生 RAM 请求与 lane 发射，但仍产生恰好一个 done。
- 账本严格分账：结构跳过、输入为零、背压等待互不重复计入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

WEIGHT_BITS = 8
WEIGHT_MIN = -(1 << (WEIGHT_BITS - 1))
WEIGHT_MAX = (1 << (WEIGHT_BITS - 1)) - 1
GROUP_WIDTH = 4
ACC_BITS = 12
ACC_MIN = -(1 << (ACC_BITS - 1))
ACC_MAX = (1 << (ACC_BITS - 1)) - 1
WORD_BITS = 20
WEIGHTS_PER_WORD = 2
WEIGHT_PAD_BITS = WORD_BITS - WEIGHTS_PER_WORD * WEIGHT_BITS
RAM_DEPTH = 32
ADDR_BITS = 5
LANE_COUNTS = (1, 2, 4, 8)
DENSE_WORDS_PER_GROUP = 2
SPARSE_WORDS_PER_GROUP = 1

FORMAT_DENSE = "dense"
FORMAT_SPARSE = "sparse"


class ConfigError(ValueError):
    """CONFIG 装载期非法：越界索引、重复索引、非规范顺序或保留位非零。"""


def sat_add(acc: int, operand: int) -> int:
    """signed 12-bit 饱和加法；溢出钳位到端点，不做模回绕。"""
    total = acc + operand
    if total > ACC_MAX:
        return ACC_MAX
    if total < ACC_MIN:
        return ACC_MIN
    return total

def check_weight(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"{name} must be an integer")
    if not WEIGHT_MIN <= value <= WEIGHT_MAX:
        raise ConfigError(f"{name} must fit signed {WEIGHT_BITS} bits")
    return value


def legal_structural_indices(indices: Sequence[int]) -> bool:
    """稀疏位置索引必须恰好两个、落在 0..3、互异且严格升序。"""
    if len(indices) != 2:
        return False
    for value in indices:
        if not isinstance(value, int) or isinstance(value, bool):
            return False
        if not 0 <= value < GROUP_WIDTH:
            return False
    return indices[0] < indices[1]


def mask_from_indices(indices: Sequence[int]) -> int:
    """结构掩码唯一真值是位置索引；掩码按需重建，不单独存储。"""
    if not legal_structural_indices(indices):
        raise ConfigError("indices must be two distinct ascending 2-bit values")
    return (1 << indices[0]) | (1 << indices[1])


def _to_word_bits(signed_value: int) -> int:
    return signed_value & ((1 << WEIGHT_BITS) - 1)


def _from_word_bits(bits: int) -> int:
    if bits & (1 << (WEIGHT_BITS - 1)):
        return bits - (1 << WEIGHT_BITS)
    return bits


def encode_dense_group(weights: Sequence[int]) -> list[int]:
    """dense 一组 4 权重切成两字：每字 2 权重 + 4 bit 保留必须为 0。"""
    if len(weights) != GROUP_WIDTH:
        raise ConfigError("dense group needs four weights")
    checked = [check_weight(value, f"weights[{index}]")
               for index, value in enumerate(weights)]
    words = []
    for word_index in range(DENSE_WORDS_PER_GROUP):
        low = _to_word_bits(checked[2 * word_index])
        high = _to_word_bits(checked[2 * word_index + 1])
        words.append(low | (high << WEIGHT_BITS))
    return words


def decode_dense_group(words: Sequence[int]) -> tuple[int, int, int, int]:
    if len(words) != DENSE_WORDS_PER_GROUP:
        raise ConfigError("dense group needs two words")
    values: list[int] = []
    for word_index, word in enumerate(words):
        if not isinstance(word, int) or isinstance(word, bool):
            raise ConfigError("dense word must be an integer")
        if not 0 <= word < (1 << WORD_BITS):
            raise ConfigError("dense word out of range")
        if word >> (2 * WEIGHT_BITS) != 0:
            raise ConfigError(f"dense word {word_index} reserved bits nonzero")
        values.append(_from_word_bits(word & ((1 << WEIGHT_BITS) - 1)))
        values.append(_from_word_bits((word >> WEIGHT_BITS) & ((1 << WEIGHT_BITS) - 1)))
    return values[0], values[1], values[2], values[3]

def encode_sparse_group(weights: Sequence[int],
                        indices: Sequence[int]) -> list[int]:
    """sparse 一组 = 2 权重 + 2 个 2-bit 位置索引 = 20 bit 一字。"""
    if len(weights) != WEIGHTS_PER_WORD:
        raise ConfigError("sparse group needs exactly two weights")
    if not legal_structural_indices(indices):
        raise ConfigError("sparse indices must be distinct ascending 2-bit values")
    low = _to_word_bits(check_weight(weights[0], "weights[0]"))
    high = _to_word_bits(check_weight(weights[1], "weights[1]"))
    return [low | (high << WEIGHT_BITS)
            | (indices[0] << 16) | (indices[1] << 18)]


def decode_sparse_group(words: Sequence[int]) -> tuple[tuple[int, int], tuple[int, int], int]:
    if len(words) != SPARSE_WORDS_PER_GROUP:
        raise ConfigError("sparse group needs one word")
    word = words[0]
    if not isinstance(word, int) or isinstance(word, bool):
        raise ConfigError("sparse word must be an integer")
    if not 0 <= word < (1 << WORD_BITS):
        raise ConfigError("sparse word out of range")
    w0 = _from_word_bits(word & ((1 << WEIGHT_BITS) - 1))
    w1 = _from_word_bits((word >> WEIGHT_BITS) & ((1 << WEIGHT_BITS) - 1))
    idx0 = (word >> 16) & 0b11
    idx1 = (word >> 18) & 0b11
    indices = (idx0, idx1)
    if not legal_structural_indices(indices):
        raise ConfigError("stored sparse indices are illegal; CONFIG must reject")
    return (w0, w1), indices, mask_from_indices(indices)


def group_word_count(fmt: str) -> int:
    if fmt == FORMAT_DENSE:
        return DENSE_WORDS_PER_GROUP
    if fmt == FORMAT_SPARSE:
        return SPARSE_WORDS_PER_GROUP
    raise ValueError("fmt must be dense or sparse")


def group_base_address(fmt: str, group_id: int) -> int:
    if not isinstance(group_id, int) or isinstance(group_id, bool):
        raise ConfigError("group_id must be an integer")
    words = group_word_count(fmt)
    if not 0 <= group_id * words + words - 1 < RAM_DEPTH:
        raise ConfigError("group address exceeds RAM depth")
    return group_id * words

LEDGER_CLASS_ORDER = ("RAM", "LANE", "LAT", "LANE_STALL", "BACKPRESSURE",
                 "HOLD_RETIRE", "ZERO", "ACCEPT", "IDLE")


@dataclass
class Ledger:
    """NP7 逐拍执行账本（B-V1+V2 口径，PR #6 评论 5498372499 裁定）。

    旧恒等式 total = accept + latency + busy + stall + done 自本轮起作废。新口径把流水窗
    内的每一拍归入互斥类别 RAM/LANE/LAT/LANE_STALL/BACKPRESSURE/HOLD_RETIRE/ZERO/ACCEPT
    （其余为 IDLE），并有

        total_cycles = busy_cycles + latency_cycles + lane_stall_cycles
                     + backpressure_cycles + hold_retire_cycles + zero_cycles
                     + accept_cycles + idle_cycles

    其中 busy=RAM 请求拍+lane 发射拍；lane_stall=lane 被 lane_stall 挡住的拍；
    backpressure=结果已就绪但 result_ready=0 的锁存保持拍；hold_retire=锁存结果退出的拍
    （可与下一事务 accept 同拍）；zero=V1 零路径单拍；accept=未能与前一事务退出同拍合并的
    accept 拍（冷启动或上游气泡）。accept_events/retire_events/overlap_cycles/
    zero_single_cycles 是逐拍事件计数，允许与类别计数重叠，不进恒等式。
    """

    group_read_requests: int = 0
    weight_values_fetched: int = 0
    lane_ops_issued: int = 0
    zero_fast_paths: int = 0
    busy_cycles: int = 0
    stall_cycles: int = 0
    completed_groups: int = 0
    structural_skips: int = 0
    input_zero_groups: int = 0
    activity_zero_after_structure: int = 0
    saturation_events: int = 0
    total_cycles: int = 0
    latency_cycles: int = 0
    lane_stall_cycles: int = 0
    backpressure_cycles: int = 0
    hold_retire_cycles: int = 0
    zero_cycles: int = 0
    accept_cycles: int = 0
    idle_cycles: int = 0
    retire_latch_cycles: int = 0
    accept_events: int = 0
    retire_events: int = 0
    overlap_cycles: int = 0
    zero_single_cycles: int = 0
    startup_cycles: int = 0
    drain_cycles: int = 0

    def merge(self, other: "Ledger") -> "Ledger":
        fields = [name for name in self.__dict__]
        return Ledger(**{name: getattr(self, name) + getattr(other, name)
                         for name in fields})

    def as_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dict__}

    def identity_violations(self, name: str = "ledger") -> list[str]:
        """新恒等式与不变量自检：任何一类漏记/重记都在这里暴露。"""
        bad = []
        want = (self.busy_cycles + self.latency_cycles + self.lane_stall_cycles
                + self.backpressure_cycles + self.hold_retire_cycles
                + self.zero_cycles + self.accept_cycles + self.idle_cycles)
        if want != self.total_cycles:
            bad.append("%s 恒等式 total=%d != 各类之和 %d"
                       % (name, self.total_cycles, want))
        if self.stall_cycles != self.lane_stall_cycles + self.backpressure_cycles:
            bad.append("%s stall=%d != lane_stall=%d + backpressure=%d"
                       % (name, self.stall_cycles, self.lane_stall_cycles,
                          self.backpressure_cycles))
        if self.retire_events != self.completed_groups:
            bad.append("%s retire=%d != completed=%d"
                       % (name, self.retire_events, self.completed_groups))
        if self.accept_events != self.completed_groups:
            bad.append("%s accept=%d != completed=%d（每 accept 必须恰好一个 result）"
                       % (name, self.accept_events, self.completed_groups))
        if self.zero_single_cycles > self.zero_fast_paths:
            bad.append("%s 零路径单拍 %d 超过零路径事务 %d"
                       % (name, self.zero_single_cycles, self.zero_fast_paths))
        if self.overlap_cycles > self.accept_events:
            bad.append("%s 同拍 retire/accept %d 超过 accept 数 %d"
                       % (name, self.overlap_cycles, self.accept_events))
        return bad


@dataclass(frozen=True)
class CycleEvent:
    """流水窗内的一拍观测；cls 是按优先级得到的互斥类别。"""

    cycle: int
    cls: str
    state: str
    ram_ce: int
    ram_addr: int
    lane_count: int
    lane_positions: tuple[int, ...]
    acc_next: int
    accepted: int
    result_valid: int
    result_ready: int
    retire: int
    overlap: int
    zero_single: int
    backpressure: int
    busy: int
    stall: int
    result_sum: int = 0
    result_zero: int = 0
    txn: int = -1


@dataclass(frozen=True)
class GroupResult:
    group_id: int
    fmt: str
    structural_mask: int
    activity_mask: int
    issue_mask: int
    ops: tuple[tuple[int, int], ...]
    skip_count: int
    synapse_sum: int
    cycles: int
    events: tuple[CycleEvent, ...]
    ledger: Ledger
    accept_cycle: int = -1
    retire_cycle: int = -1
    zero_path: int = 0
    folded_accept: int = 0
    txn_index: int = -1


def tree_sum(values: Sequence[int]) -> int:
    """平衡二叉饱和加法树；与共享 lane 阵列的组合结构逐节点一致。"""
    if not values:
        return 0
    level = list(values)
    while len(level) > 1:
        nxt: list[int] = []
        for index in range(0, len(level), 2):
            if index + 1 < len(level):
                nxt.append(sat_add(level[index], level[index + 1]))
            else:
                nxt.append(level[index])
        level = nxt
    return level[0]


def classify(signals: dict[str, int]) -> str:
    """把一拍观测量归入互斥类别；oracle、tb 与验证器共用这一份优先级。"""
    if signals.get("ram_ce"):
        return "RAM"
    if signals.get("lane_count"):
        return "LANE"
    if signals.get("latency"):
        return "LAT"
    if signals.get("lane_stall_block"):
        return "LANE_STALL"
    if signals.get("backpressure"):
        return "BACKPRESSURE"
    if signals.get("hold_retire"):
        return "HOLD_RETIRE"
    if signals.get("zero_single"):
        return "ZERO"
    if signals.get("accept_own"):
        return "ACCEPT"
    return "IDLE"



class _Plan:
    """一条已解码事务的发射计划（READ/LAT/BATCH 三段）。"""

    __slots__ = ("group_id", "activity", "issue", "structural", "ops", "values",
                 "base", "words", "batches", "skip", "input_zero", "azero")

    def __init__(self, group_id, activity, issue, structural, ops, values, base,
                 words, batches, skip, input_zero, azero):
        self.group_id = group_id
        self.activity = activity
        self.issue = issue
        self.structural = structural
        self.ops = ops
        self.values = values
        self.base = base
        self.words = words
        self.batches = batches
        self.skip = skip
        self.input_zero = input_zero
        self.azero = azero


class SharedLaneUnit:
    """共享 RAM + 共享 lane 的单槽弹性流水执行单元周期模型（B-V1+V2）。

    CONFIG 阶段唯一写入路径是 config_write/config_finish；运行期只读，任何运行期写尝试
    都会抛错，且非法记录字在装载期就被拒绝（与 RTL 的 cfg_wr_ok 硬件门同口径）。

    周期合同（PR #6 评论 5498372499 裁定 B-V1+V2，替换旧的五段式）：

    V1 零路径单拍：issue_valid && issue_ready && issue_mask==0 时不发 RAM 请求、不发 lane
      操作，结果为 0 且 result_zero_path=1；当拍 result_ready=1 时 accept 与 result 在同一
      边沿完成，整笔只计 1 拍；result_ready=0 时结果锁存并稳定保持，不得丢失/重复/覆盖。
      零突触不改变上层神经元的泄放、阈值、睡眠与时间状态推进。
    V2 退出与接受重叠：非零事务最后一批 BATCH 发射并得到最终 acc_next 的当拍，若
      result_ready=1 则当拍完成结果，不再进入独立 DONE 拍；同一边沿允许 issue_ready=1 并
      接受下一事务，当前结果与下一事务元数据严格分离。任意时刻最多一个未退出结果（单槽
      弹性流水，不是多事务队列）。结果背压时锁存旧结果并停止接收，只有旧结果退出的同一
      边沿才可接收下一事务。lane_stall=1 时不得提前完成或接受下一事务。
    """

    def __init__(self, fmt: str, lane_count: int, group_count: int = 10) -> None:
        if fmt not in (FORMAT_DENSE, FORMAT_SPARSE):
            raise ValueError("fmt must be dense or sparse")
        if lane_count not in LANE_COUNTS:
            raise ValueError("lane_count must be one of 1/2/4/8")
        if not 1 <= group_count <= RAM_DEPTH // group_word_count(fmt):
            raise ValueError("group_count exceeds RAM depth")
        self.fmt = fmt
        self.lane_count = lane_count
        self.group_count = group_count
        self.ram: list[int | None] = [None] * RAM_DEPTH
        self.structural_mask: list[int] = [0] * group_count
        self.config_open = True
        self.configured_groups: set[int] = set()
        self.ledger = Ledger()
        self.skip_count = 0
        self.gate_mask = [0b1111] * group_count
        self.txn_log: list[dict[str, object]] = []
        self.stream_events: tuple[CycleEvent, ...] = ()
        self.recorded: list[tuple[int, int]] = []

    # ------------------------------------------------------------------ CONFIG
    def set_gate_mask(self, group_id: int, mask: int) -> None:
        """上层 gate 提交的结构掩码；sparse 必须与索引重建的掩码全等。"""
        if not 0 <= group_id < self.group_count:
            raise ConfigError("group_id out of range")
        if not isinstance(mask, int) or isinstance(mask, bool):
            raise ConfigError("gate mask must be an integer")
        if not 0 <= mask <= 0b1111:
            raise ConfigError("gate mask must be a four-bit value")
        if self.fmt == FORMAT_SPARSE:
            rebuilt = self.structural_mask[group_id]
            if rebuilt and rebuilt != mask:
                raise ConfigError("gate mask disagrees with record indices")
            self.structural_mask[group_id] = mask
        self.gate_mask[group_id] = mask

    def config_write(self, group_id: int, weights: Sequence[int],
                     indices: Sequence[int] | None = None) -> None:
        if not self.config_open:
            raise RuntimeError("runtime weight write is forbidden (read-only RAM)")
        if not 0 <= group_id < self.group_count:
            raise ConfigError("group_id out of range")
        if self.fmt == FORMAT_DENSE:
            if indices is not None:
                raise ConfigError("dense format has no position indices")
            words = encode_dense_group(weights)
            self.structural_mask[group_id] = 0b1111
            self.gate_mask[group_id] = 0b1111
        else:
            if indices is None:
                raise ConfigError("sparse format requires two position indices")
            words = encode_sparse_group(weights, indices)
            self.structural_mask[group_id] = mask_from_indices(indices)
        base = group_base_address(self.fmt, group_id)
        for offset, word in enumerate(words):
            self.ram[base + offset] = word
        self.configured_groups.add(group_id)

    def config_load_words(self, words: Sequence[int]) -> None:
        """直接装载 RAM 位模式（与 RTL 的 np7_cfg.hex 同源），随后解码校验。"""
        if not self.config_open:
            raise RuntimeError("runtime weight write is forbidden (read-only RAM)")
        per_group = group_word_count(self.fmt)
        if len(words) != per_group * self.group_count:
            raise ConfigError("config word count mismatch")
        for index, word in enumerate(words):
            self.ram[index] = word
        for group in range(self.group_count):
            self.configured_groups.add(group)

    def config_finish(self) -> None:
        missing = [gid for gid in range(self.group_count)
                   if gid not in self.configured_groups]
        if missing:
            raise ConfigError(f"unconfigured groups: {missing}")
        for gid in range(self.group_count):
            self._decode_group(gid)
        self.config_open = False

    def _decode_group(self, group_id: int) -> tuple[dict[int, int], int]:
        base = group_base_address(self.fmt, group_id)
        words = [self.ram[base + offset]
                 for offset in range(group_word_count(self.fmt))]
        if any(word is None for word in words):
            raise ConfigError("uninitialized RAM word read")
        if self.fmt == FORMAT_DENSE:
            four = decode_dense_group(words)
            slots = {position: four[position] for position in range(GROUP_WIDTH)}
            return slots, 0b1111
        pair, indices, mask = decode_sparse_group(words)
        slots = {indices[0]: pair[0], indices[1]: pair[1]}
        return slots, mask

    # ---------------------------------------------------------------- function
    def synapse_sum(self, group_id: int, activity_mask: int) -> int:
        """只算功能结果（不计时），供集成侧记录流水后统一重放周期。"""
        plan = self._plan(group_id, activity_mask)
        return tree_sum([plan.values[position] for position in plan.ops])

    def _plan(self, group_id: int, activity_mask: int) -> _Plan:
        if self.config_open:
            raise RuntimeError("config_finish must run before issue")
        if not isinstance(activity_mask, int) or isinstance(activity_mask, bool):
            raise TypeError("activity_mask must be an integer")
        if not 0 <= activity_mask <= 0b1111:
            raise ValueError("activity_mask must be a four-bit value")
        if not 0 <= group_id < self.group_count:
            raise ValueError("group_id out of range")
        slots, decoded = self._decode_group(group_id)
        structural = (decoded if self.fmt == FORMAT_SPARSE
                      else self.gate_mask[group_id])
        issue = structural & activity_mask
        ops = tuple(position for position in sorted(slots)
                    if (issue >> position) & 1)
        batches = [ops[index:index + self.lane_count]
                   for index in range(0, len(ops), self.lane_count)]
        skip = bin(activity_mask & ~structural & 0b1111).count("1")
        return _Plan(group_id, activity_mask, issue, structural, ops, slots,
                     group_base_address(self.fmt, group_id),
                     group_word_count(self.fmt), batches, skip,
                     int(activity_mask == 0), int(activity_mask != 0 and issue == 0))


    def run_stream(self, trace: Sequence[tuple[int, int]], lane_stall=None,
                   result_ready=None, issue_valid=None,
                   acc_seed: int = 0) -> list[GroupResult]:
        """按 B-V1+V2 连续重放事务流（每逻辑 tick 一条流，段内无气泡）。

        trace 是 (group_id, activity_mask) 序列；lane_stall/result_ready/issue_valid 都以
        绝对拍号取值，因此背压、气泡与同拍 retire/accept 可以直接和 RTL 逐拍观测比对。
        """
        stall_fn = lane_stall if lane_stall is not None else (lambda cycle: 0)
        ready_fn = result_ready if result_ready is not None else (lambda cycle: 1)
        valid_fn = issue_valid if issue_valid is not None else (lambda cycle: 1)
        plans = [self._plan(group, activity) for group, activity in trace]
        total = len(plans)
        if total == 0:
            return []
        events: list[CycleEvent] = []
        led = Ledger()
        records: dict[int, dict[str, int]] = {}
        order: list[int] = []
        sat_cycles: set[int] = set()
        cycle = 0
        state = "IDLE"
        cur: _Plan | None = None
        cur_index = -1
        word_index = 0
        batch_index = 0
        acc = 0
        hold_active = False
        hold_val = 0
        hold_zero = 0
        hold_index = -1
        next_index = 0
        last_work_cycle = -1
        while not (next_index == total and cur is None and not hold_active):
            if cycle > 64 * total + 4096:
                raise AssertionError("run_stream 未在有限拍内收敛")
            ls = 1 if stall_fn(cycle) else 0
            rr = 1 if ready_fn(cycle) else 0
            ce = ad = lf = lat = lstall = 0
            lpos: tuple[int, ...] = ()
            rv = zp = sum_out = 0
            acc_next = acc
            retire_index = -1
            retire_val = 0
            retire_from_hold = 0
            batch_last = 0
            latch_now = 0
            if hold_active:
                rv = 1
                zp = hold_zero
                sum_out = hold_val
                if rr:
                    retire_index = hold_index
                    retire_val = hold_val
                    retire_from_hold = 1
            elif state == "BATCH" and cur is not None:
                if ls:
                    lstall = 1
                else:
                    batch = cur.batches[batch_index]
                    lf = len(batch)
                    lpos = tuple(batch)
                    total_now = tree_sum([cur.values[position] for position in batch])
                    acc_next = sat_add(acc, total_now)
                    batch_last = (batch_index + 1 == len(cur.batches))
                    if acc_next != acc + total_now:
                        led.saturation_events += 1
                        sat_cycles.add(cycle)
                    if batch_last:
                        rv = 1
                        sum_out = acc_next
                        if rr:
                            retire_index = cur_index
                            retire_val = acc_next
                        else:
                            latch_now = 1
                    if ce or lf or lat:
                        last_work_cycle = cycle
            elif state == "READ" and cur is not None:
                ce = 1
                ad = cur.base + word_index
                last_work_cycle = cycle
            elif state == "LAT":
                lat = 1
                last_work_cycle = cycle
            elif state == "IDLE":
                pass
            retired_before = retire_index >= 0
            accept_index = -1
            plan = plans[next_index] if next_index < total else None
            if plan is not None and valid_fn(cycle):
                if (state == "IDLE" and not hold_active) or retired_before:
                    accept_index = next_index
                    next_index += 1
            zero_single = 0
            if accept_index >= 0 and plans[accept_index].issue == 0:
                if not retired_before and rr:
                    zero_single = 1
                    retire_index = accept_index
                    retire_val = 0
                    # 与 RTL 的 result_valid = hold||batch_last||zero_now 对齐：
                    # V1 单拍零路径在同一边沿同时给出 accept 与 result。
                    rv = 1
                    zp = 1
                    sum_out = 0
            cls = classify({
                "ram_ce": ce, "lane_count": lf, "latency": lat,
                "lane_stall_block": lstall,
                "backpressure": 1 if (rv and not rr) else 0,
                "hold_retire": 1 if retire_from_hold else 0,
                "zero_single": zero_single,
                "accept_own": 1 if (accept_index >= 0 and retired_before == 0
                                    and zero_single == 0 and not (ce or lf or lat)) else 0})
            if cls == "RAM" or cls == "LANE":
                led.busy_cycles += 1
            elif cls == "LAT":
                led.latency_cycles += 1
            elif cls == "LANE_STALL":
                led.lane_stall_cycles += 1
                led.stall_cycles += 1
            elif cls == "BACKPRESSURE":
                led.backpressure_cycles += 1
                led.stall_cycles += 1
            elif cls == "HOLD_RETIRE":
                led.hold_retire_cycles += 1
            elif cls == "ZERO":
                led.zero_cycles += 1
            elif cls == "ACCEPT":
                led.accept_cycles += 1
                if cycle == 0:
                    led.startup_cycles += 1
            else:
                led.idle_cycles += 1
            if ce:
                led.group_read_requests += 1
            if lf:
                led.lane_ops_issued += lf
            if batch_last and not rr:
                led.retire_latch_cycles += 1
            if accept_index >= 0:
                new_plan = plans[accept_index]
                led.accept_events += 1
                self.skip_count = new_plan.skip
                if new_plan.input_zero:
                    led.input_zero_groups += 1
                if new_plan.azero:
                    led.activity_zero_after_structure += 1
                led.structural_skips += new_plan.skip
                if new_plan.issue == 0:
                    led.zero_fast_paths += 1
                else:
                    led.weight_values_fetched += new_plan.words * WEIGHTS_PER_WORD
                records[accept_index] = {"accept": cycle, "retire": -1, "value": 0,
                                         "folded": 1 if retired_before else 0,
                                         "zero": 1 if new_plan.issue == 0 else 0}
                order.append(accept_index)
                if retired_before:
                    led.overlap_cycles += 1
            if zero_single:
                led.zero_single_cycles += 1
            if retire_index >= 0:
                led.retire_events += 1
                led.completed_groups += 1
                slot = records[retire_index]
                slot["retire"] = cycle
                slot["value"] = retire_val
            events.append(CycleEvent(
                cycle=cycle, cls=cls, state=state, ram_ce=ce, ram_addr=ad,
                lane_count=lf, lane_positions=lpos, acc_next=acc_next,
                accepted=1 if accept_index >= 0 else 0, result_valid=rv,
                result_ready=rr, retire=1 if retire_index >= 0 else 0,
                overlap=1 if (retired_before and accept_index >= 0) else 0,
                zero_single=zero_single,
                backpressure=1 if (rv and not rr) else 0,
                busy=1 if (ce or lf) else 0,
                stall=1 if (lstall or (rv and not rr)) else 0,
                result_sum=sum_out, result_zero=zp,
                txn=(accept_index if accept_index >= 0 else
                     (retire_index if retire_index >= 0 else cur_index))))
            if retire_from_hold:
                hold_active = False
            if lf:
                acc = acc_next
                batch_index += 1
                if batch_last:
                    if latch_now:
                        hold_active = True
                        hold_val = acc_next
                        hold_zero = 0
                        hold_index = cur_index
                    cur = None
                    cur_index = -1
                    state = "IDLE"
            elif state == "READ" and ce:
                word_index += 1
                if word_index == cur.words:
                    state = "LAT"
            elif state == "LAT":
                state = "BATCH"
                batch_index = 0
                acc = acc_seed
            if accept_index >= 0:
                new_plan = plans[accept_index]
                if new_plan.issue == 0:
                    if not zero_single:
                        hold_active = True
                        hold_val = 0
                        hold_zero = 1
                        hold_index = accept_index
                else:
                    cur = new_plan
                    cur_index = accept_index
                    word_index = 0
                    batch_index = 0
                    acc = acc_seed
                    state = "READ"
            cycle += 1
        led.total_cycles = cycle
        if last_work_cycle < cycle - 1:
            led.drain_cycles = cycle - 1 - last_work_cycle
        self.ledger = self.ledger.merge(led)
        self.stream_events = tuple(events)
        results: list[GroupResult] = []
        for index in order:
            slot = records[index]
            item = plans[index]
            window = tuple(event for event in events
                           if slot["accept"] <= event.cycle <= slot["retire"])
            results.append(GroupResult(
                group_id=item.group_id, fmt=self.fmt, structural_mask=item.structural,
                activity_mask=item.activity, issue_mask=item.issue,
                ops=tuple((position, item.values[position]) for position in item.ops),
                skip_count=item.skip, synapse_sum=slot["value"],
                cycles=slot["retire"] - slot["accept"] + 1, events=window,
                ledger=self._txn_ledger(item, window, sat_cycles, slot),
                accept_cycle=slot["accept"],
                retire_cycle=slot["retire"], zero_path=slot["zero"],
                folded_accept=slot["folded"], txn_index=index))
            self.txn_log.append({
                "group_id": item.group_id, "fmt": self.fmt,
                "activity_mask": item.activity, "structural_mask": item.structural,
                "issue_mask": item.issue, "ops": list(item.ops),
                "synapse_sum": slot["value"], "cycles": slot["retire"] - slot["accept"] + 1,
                "accept_cycle": slot["accept"], "retire_cycle": slot["retire"]})
        return results

    def run_group(self, group_id: int, activity_mask: int,
                  issue_mask: int | None = None, lane_stall=None,
                  result_ready=None, acc_seed: int = 0) -> GroupResult:
        """执行单笔事务；issue_mask 必须等于结构 AND 活动，否则视为合同违约。"""
        plan = self._plan(group_id, activity_mask)
        if issue_mask is not None:
            if not isinstance(issue_mask, int) or isinstance(issue_mask, bool):
                raise TypeError("issue_mask must be an integer")
            if issue_mask & ~activity_mask:
                raise ValueError("issue_mask must be a subset of activity_mask")
            if issue_mask != plan.issue:
                raise ValueError("issue_mask must equal structural AND activity")
        return self.run_stream([(group_id, activity_mask)], lane_stall=lane_stall,
                               result_ready=result_ready, acc_seed=acc_seed)[0]

    def run_trace(self, trace: Sequence[tuple[int, int]], lane_stall=None,
                  result_ready=None, issue_valid=None) -> list[GroupResult]:
        return self.run_stream(trace, lane_stall=lane_stall,
                               result_ready=result_ready, issue_valid=issue_valid)

    def identity_violations(self, name: str = "unit") -> list[str]:
        return self.ledger.identity_violations(name)

    def totals(self) -> dict[str, float]:
        """导出每事务平均周期等派生指标（周期取自流水重放）。"""
        completed = self.ledger.completed_groups
        cycles = self.ledger.total_cycles
        return {
            "format": self.fmt,
            "lane_count": self.lane_count,
            "group_read_requests": self.ledger.group_read_requests,
            "weight_values_fetched": self.ledger.weight_values_fetched,
            "lane_ops_issued": self.ledger.lane_ops_issued,
            "zero_fast_paths": self.ledger.zero_fast_paths,
            "busy_cycles": self.ledger.busy_cycles,
            "stall_cycles": self.ledger.stall_cycles,
            "completed_groups": completed,
            "total_cycles": self.ledger.total_cycles,
            "latency_cycles": self.ledger.latency_cycles,
            "lane_stall_cycles": self.ledger.lane_stall_cycles,
            "backpressure_cycles": self.ledger.backpressure_cycles,
            "hold_retire_cycles": self.ledger.hold_retire_cycles,
            "zero_cycles": self.ledger.zero_cycles,
            "accept_cycles": self.ledger.accept_cycles,
            "idle_cycles": self.ledger.idle_cycles,
            "retire_latch_cycles": self.ledger.retire_latch_cycles,
            "accept_events": self.ledger.accept_events,
            "retire_events": self.ledger.retire_events,
            "overlap_cycles": self.ledger.overlap_cycles,
            "zero_single_cycles": self.ledger.zero_single_cycles,
            # B-V1+V2 恒等式里"未被前一事务退出边沿合并的 accept 拍"即 ACCEPT 类，
            # NP7.3 观测侧重建时叫 accept_own_cycles，这里保持同一字段名。
            "accept_own_cycles": self.ledger.accept_cycles,
            "startup_cycles": self.ledger.startup_cycles,
            "drain_cycles": self.ledger.drain_cycles,
            "groups_per_cycle": (completed / cycles) if cycles else 0.0,
            "cycles_per_group": (cycles / completed) if completed else 0.0,
        }


    def _txn_ledger(self, item: "_Plan", window, sat_cycles,
                    slot) -> Ledger:
        """把一笔事务的流水窗折算成逐拍账本。

        V2 的同拍 retire/accept 边沿同时属于前一事务的退出窗与本事务的接受窗，
        因此逐笔账本在该边沿各记一次；流水级账本（self.ledger）不重复计数，
        两者的差额正好等于 overlap_cycles。
        """
        led = Ledger()
        for event in window:
            if event.cls == "RAM":
                led.busy_cycles += 1
                led.group_read_requests += 1
            elif event.cls == "LANE":
                led.busy_cycles += 1
                led.lane_ops_issued += event.lane_count
            elif event.cls == "LAT":
                led.latency_cycles += 1
            elif event.cls == "LANE_STALL":
                led.lane_stall_cycles += 1
                led.stall_cycles += 1
            elif event.cls == "BACKPRESSURE":
                led.backpressure_cycles += 1
                led.stall_cycles += 1
            elif event.cls == "HOLD_RETIRE":
                led.hold_retire_cycles += 1
            elif event.cls == "ZERO":
                led.zero_cycles += 1
                led.zero_single_cycles += 1
            elif event.cls == "ACCEPT":
                led.accept_cycles += 1
            else:
                led.idle_cycles += 1
            if event.cycle in sat_cycles:
                led.saturation_events += 1
        led.total_cycles = sum(1 for event in window if event.cls != "IDLE")
        led.completed_groups = 1
        led.accept_events = 1
        led.retire_events = 1
        led.overlap_cycles = 1 if slot.get("folded") else 0
        led.weight_values_fetched = led.group_read_requests * WEIGHTS_PER_WORD
        led.lane_ops_issued = len(item.ops)
        led.zero_fast_paths = 1 if item.issue == 0 else 0
        led.structural_skips = item.skip
        led.input_zero_groups = item.input_zero
        led.activity_zero_after_structure = item.azero
        led.startup_cycles = 1 if (slot["accept"] == 0 and not slot.get("folded")) else 0
        return led

    def record_txn(self, group_id: int, activity_mask: int) -> int:
        """记录一笔突触事务并立即返回功能结果；周期由所属 tick 统一重放。"""
        self.recorded.append((group_id, activity_mask))
        return self.synapse_sum(group_id, activity_mask)

    def replay_recorded(self) -> None:
        """把 record_txn 记录的序列按 B-V1+V2 连续流水重放进账本。"""
        stream = self.recorded
        self.recorded = []
        if stream:
            self.run_stream(stream)
def exhaustive_structures() -> list[tuple[int, int]]:
    """六个合法 2:4 结构（4 选 2 且严格升序）。"""
    return [(a, b) for a in range(GROUP_WIDTH) for b in range(a + 1, GROUP_WIDTH)]


def illegal_index_samples() -> list[tuple[int, int]]:
    """越界、重复与降序三类非法索引。"""
    bad = [(0, 0), (1, 1), (2, 2), (3, 3)]
    bad += [(2, 1), (3, 0), (3, 2)]
    bad += [(-1, 1), (0, 4), (4, 5), (0, 8)]
    return bad


__all__ = [
    "ACC_BITS", "ACC_MAX", "ACC_MIN", "ADDR_BITS", "ConfigError", "CycleEvent",
    "DENSE_WORDS_PER_GROUP", "GROUP_WIDTH", "LANE_COUNTS", "Ledger", "RAM_DEPTH",
    "SPARSE_WORDS_PER_GROUP", "WEIGHT_BITS", "WEIGHT_MAX", "WEIGHT_MIN",
    "FORMAT_DENSE", "FORMAT_SPARSE", "GroupResult", "SharedLaneUnit", "check_weight", "decode_dense_group",
    "decode_sparse_group", "encode_dense_group", "encode_sparse_group",
    "exhaustive_structures", "group_base_address", "group_word_count",
    "illegal_index_samples", "legal_structural_indices", "classify", "mask_from_indices",
    "LEDGER_CLASS_ORDER",
    "sat_add", "tree_sum",
]
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

@dataclass
class Ledger:
    """NP7 执行账本；每接受事务恰好一个 done，字段口径见 NP7.0 冻结决策。"""

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
    accept_cycles: int = 0
    latency_cycles: int = 0
    done_cycles: int = 0
    total_cycles: int = 0
    saturation_events: int = 0
    done_assertions: int = 0

    def merge(self, other: "Ledger") -> "Ledger":
        fields = [name for name in self.__dict__]
        return Ledger(**{name: getattr(self, name) + getattr(other, name)
                         for name in fields})

    def as_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dict__}


@dataclass(frozen=True)
class CycleEvent:
    cycle: int
    state: str
    ram_ce: int
    ram_addr: int
    lane_count: int
    lane_positions: tuple[int, ...]
    acc_next: int
    result_valid: int
    accepted: int
    busy: int
    stall: int


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




class SharedLaneUnit:
    """共享 RAM + 共享 lane 的单槽突触执行单元周期模型。

    CONFIG 阶段唯一写入路径是 config_write/config_finish；运行期只读，
    任何运行期写尝试都会抛错（对应"RAM 为 CONFIG 写入、运行时只读"裁定）。
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
        self.txn_log: list[dict[str, object]] = []

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
        else:
            if indices is None:
                raise ConfigError("sparse format requires two position indices")
            words = encode_sparse_group(weights, indices)
            self.structural_mask[group_id] = mask_from_indices(indices)
        base = group_base_address(self.fmt, group_id)
        for offset, word in enumerate(words):
            self.ram[base + offset] = word
        self.configured_groups.add(group_id)

    def config_finish(self) -> None:
        missing = [gid for gid in range(self.group_count)
                   if gid not in self.configured_groups]
        if missing:
            raise ConfigError(f"unconfigured groups: {missing}")
        # 解码回读一遍，确保入库的位模式在运行期可解且合法。
        for gid in range(self.group_count):
            self._decode_group(gid)
        self.config_open = False

    def _decode_group(self, group_id: int) -> tuple[dict[int, int], int]:
        base = group_base_address(self.fmt, group_id)
        words = [self.ram[base + offset] for offset in range(group_word_count(self.fmt))]
        if any(word is None for word in words):
            raise ConfigError("uninitialized RAM word read")
        if self.fmt == FORMAT_DENSE:
            four = decode_dense_group(words)
            slots = {position: four[position] for position in range(GROUP_WIDTH)}
            return slots, 0b1111
        pair, indices, mask = decode_sparse_group(words)
        slots = {indices[0]: pair[0], indices[1]: pair[1]}
        return slots, mask

    def run_group(self, group_id: int, activity_mask: int,
                  issue_mask: int | None = None,
                  lane_stall: Callable[[int], int] | None = None,
                  result_ready: Callable[[int], int] | None = None,
                  acc_seed: int = 0) -> GroupResult:
        """执行一个突触组事务，返回逐拍事件序列与账本增量。"""
        if self.config_open:
            raise RuntimeError("config_finish must run before issue")
        if not isinstance(activity_mask, int) or isinstance(activity_mask, bool):
            raise TypeError("activity_mask must be an integer")
        if not 0 <= activity_mask <= 0b1111:
            raise ValueError("activity_mask must be a four-bit value")
        if not 0 <= group_id < self.group_count:
            raise ValueError("group_id out of range")
        stall_fn = lane_stall if lane_stall is not None else (lambda cycle: 0)
        ready_fn = result_ready if result_ready is not None else (lambda cycle: 1)
        slots, structural = self._decode_group(group_id)
        expected_issue = structural & activity_mask
        if issue_mask is None:
            issue_mask = expected_issue
        else:
            # 上游 gate 传入的发射掩码必须与本单元的账本口径一致，否则视为合同
            # 违约：dense 不得借外部掩码偷偷做结构跳过。
            if not isinstance(issue_mask, int) or isinstance(issue_mask, bool):
                raise TypeError("issue_mask must be an integer")
            if issue_mask & ~activity_mask:
                raise ValueError("issue_mask must be a subset of activity_mask")
            if issue_mask != expected_issue:
                raise ValueError("issue_mask must equal structural AND activity")
        self.skip_count = bin(activity_mask & ~structural & 0b1111).count("1")
        ops = tuple((position, slots[position]) for position in sorted(slots)
                    if (issue_mask >> position) & 1)
        dense_ops = tuple((position, slots[position]) for position in sorted(slots)
                          if (activity_mask >> position) & 1)
        events: list[CycleEvent] = []
        led = Ledger()
        cycle = 0
        events.append(CycleEvent(cycle, "ACCEPT", 0, 0, 0, (), acc_seed, 0, 1, 0, 0))
        led.accept_cycles += 1
        cycle += 1
        if not ops:
            led.zero_fast_paths += 1
            if activity_mask == 0:
                led.input_zero_groups += 1
            else:
                led.activity_zero_after_structure += 1
                led.structural_skips += bin(
                    activity_mask & ~structural & 0b1111).count("1")
            while not ready_fn(cycle):
                events.append(CycleEvent(cycle, "DONE", 0, 0, 0, (), acc_seed, 1, 0, 0, 1))
                led.stall_cycles += 1
                cycle += 1
            events.append(CycleEvent(cycle, "DONE", 0, 0, 0, (), acc_seed, 1, 1, 0, 0))
            led.done_cycles += 1
            led.done_assertions += 1
            led.completed_groups += 1
            cycle += 1
            synapse_sum = acc_seed
        else:
            base = group_base_address(self.fmt, group_id)
            for offset in range(group_word_count(self.fmt)):
                events.append(CycleEvent(cycle, "READ", 1, base + offset, 0, (), acc_seed, 0, 1, 1, 0))
                led.group_read_requests += 1
                led.busy_cycles += 1
                cycle += 1
            led.weight_values_fetched += len(slots)
            events.append(CycleEvent(cycle, "LATENCY", 0, 0, 0, (), acc_seed, 0, 1, 0, 0))
            led.latency_cycles += 1
            cycle += 1
            acc = acc_seed
            index = 0
            while index < len(ops):
                batch = ops[index:index + self.lane_count]
                if stall_fn(cycle):
                    events.append(CycleEvent(cycle, "LANE_STALL", 0, 0, 0, (), acc, 0, 1, 0, 1))
                    led.stall_cycles += 1
                    cycle += 1
                    continue
                values = [value for _, value in batch]
                total = tree_sum(values)
                nxt = sat_add(acc, total)
                if nxt != acc + total:
                    led.saturation_events += 1
                acc = nxt
                positions = tuple(position for position, _ in batch)
                events.append(CycleEvent(cycle, "LANE_BATCH", 0, 0, len(batch), positions, acc, 0, 1, 1, 0))
                led.lane_ops_issued += len(batch)
                led.busy_cycles += 1
                index += len(batch)
                cycle += 1
            led.structural_skips += bin(
                activity_mask & ~structural & 0b1111).count("1")
            while not ready_fn(cycle):
                events.append(CycleEvent(cycle, "DONE", 0, 0, 0, (), acc, 1, 0, 0, 1))
                led.stall_cycles += 1
                cycle += 1
            events.append(CycleEvent(cycle, "DONE", 0, 0, 0, (), acc, 1, 1, 0, 0))
            led.done_cycles += 1
            led.done_assertions += 1
            led.completed_groups += 1
            cycle += 1
            synapse_sum = acc
        led.total_cycles += cycle
        self.ledger = self.ledger.merge(led)
        record = {"group_id": group_id, "fmt": self.fmt, "activity_mask": activity_mask,
                  "structural_mask": structural, "issue_mask": issue_mask,
                  "ops": list(ops), "synapse_sum": synapse_sum, "cycles": cycle}
        self.txn_log.append(record)
        return GroupResult(group_id, self.fmt, structural, activity_mask, issue_mask,
                           ops, led.structural_skips, synapse_sum, cycle,
                           tuple(events), led)
    def run_trace(self, trace: Sequence[tuple[int, int]],
                  lane_stall: Callable[[int], int] | None = None,
                  result_ready: Callable[[int], int] | None = None) -> list[GroupResult]:
        """按给定 (group_id, activity_mask) 序列串行执行，单槽协议天然互斥。"""
        results = []
        for group_id, activity_mask in trace:
            results.append(self.run_group(group_id, activity_mask,
                                          lane_stall=lane_stall,
                                          result_ready=result_ready))
        return results

    def totals(self) -> dict[str, float]:
        """导出 groups/cycle 与每事务平均周期等派生指标。"""
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
            "groups_per_cycle": (completed / cycles) if cycles else 0.0,
            "cycles_per_group": (cycles / completed) if completed else 0.0,
        }


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
    "illegal_index_samples", "legal_structural_indices", "mask_from_indices",
    "sat_add", "tree_sum",
]
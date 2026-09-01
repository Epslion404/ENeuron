"""NP7 性能账本的"逐拍观测重建"规则（NP7.5 / NP7.6 共用）。

冻结合同（NP7.0 §2.2）要求账本严格分账且可追溯。只在结束时读一次计数器快照
是不够的：任何实现都可以在发射之后清零、在读取之后门控，然后把自报数字写成
剪枝后的值。因此本模块规定：**账本的每一个字段都必须能由逐拍观测重建**，
自报数字与观测不一致即拒绝，与实现的身份无关。

逐拍观测来自 tb_np7_exec_unit.sv / tb_np7_negative.sv 的 CYC 行：

    st  状态机编码（0=IDLE 1=RD0 2=RD1 3=LAT 4=BATCH 5=DONE）
    ce  当拍 RAM 读请求
    lf  当拍占用的 lane 槽位数
    rv/rr  done  valid/ready
    ap  接受拍
    ls  lane_stall

观测口径：
- 读请求数 = Σce；权重槽 = 读请求数 × 每字权重槽数；
- lane 操作数 = Σlf（当拍真实占用的 lane 槽位，发射后清零不算减少）；
- busy = Σ[ce 或 lf>0]；stall = Σ[S_BATCH 且有 pending 且 lane_stall] + Σ[DONE 等待]；
- total = Σ[接受拍 或 st!=IDLE]；零快速路径数 = 接受时 issue_mask==0 的事务数。
"""

from __future__ import annotations

import re
from typing import Any, Sequence

SLOTS_PER_WORD = 2
STATE_IDLE = 0
STATE_BATCH = 4
STATE_DONE = 5

CYC_RE = re.compile(
    r"CYC (\d+) st=(\d) ce=(\d) ad=(\d+) lf=(\d) bm=(\S+) rv=(\d) rr=(\d) "
    r"ap=(\d) zp=(\d) sum=(-?\d+) ls=(\d) cmp=(\d+)")
LEDGER_RE = re.compile(
    r"LEDGER req=(\d+) val=(\d+) ops=(\d+) zero=(\d+) busy=(\d+) stall=(\d+) "
    r"done=(\d+) skip=(\d+) inzero=(\d+) azero=(\d+) sat=(\d+) total=(\d+) "
    r"proto=(\d) cfgerr=(\d) completed=(\d+)")
LEDGER_FIELDS = ("group_read_requests", "weight_values_fetched", "lane_ops_issued",
                 "zero_fast_paths", "busy_cycles", "stall_cycles",
                 "completed_groups", "structural_skips", "input_zero_groups",
                 "activity_zero_after_structure", "saturation_events",
                 "total_cycles")


def parse_rows(stdout: str) -> tuple[list[dict[str, int]], dict[str, int]]:
    """解析 tb 的 CYC 行与 LEDGER 行。"""
    rows = []
    for match in CYC_RE.finditer(stdout):
        values = match.groups()
        rows.append({"cycle": int(values[0]), "st": int(values[1]),
                     "ce": int(values[2]), "ad": int(values[3]),
                     "lf": int(values[4]), "bm": int(values[5], 16),
                     "rv": int(values[6]), "rr": int(values[7]),
                     "ap": int(values[8]), "zp": int(values[9]),
                     "sum": int(values[10]), "lf_stall": int(values[11]),
                     "cmp": int(values[12])})
    ledger_match = LEDGER_RE.search(stdout)
    if ledger_match is None:
        raise AssertionError("仿真输出缺少 LEDGER 行")
    claimed = {}
    for index, name in enumerate(LEDGER_FIELDS):
        claimed[name] = int(ledger_match.group(index + 1))
    tail = ledger_match.groups()[-3:]  # proto/cfgerr/completed
    claimed["protocol_error"] = int(tail[0])
    claimed["config_error"] = int(tail[1])
    claimed["completed"] = int(tail[2])
    return rows, claimed


def observe(rows: Sequence[dict[str, int]],
            accepted_masks: Sequence[int] | None = None,
            slots_per_word: int = SLOTS_PER_WORD) -> dict[str, int]:
    """只从逐拍观测重建账本，不使用任何自报数字。"""
    reads = sum(row["ce"] for row in rows)
    observed = {
        "group_read_requests": reads,
        "weight_values_fetched": reads * slots_per_word,
        "lane_ops_issued": sum(row["lf"] for row in rows),
        "zero_fast_paths": 0,
        "busy_cycles": sum(1 for row in rows if row["ce"] or row["lf"]),
        "stall_cycles": sum(
            1 for row in rows
            if (row["st"] == STATE_BATCH and row["lf"] == 0 and row["lf_stall"])
            or (row["st"] == STATE_DONE and row["rv"] and not row["rr"])),
        "completed_groups": sum(1 for row in rows if row["rv"] and row["rr"]),
        "structural_skips": 0,
        "input_zero_groups": 0,
        "activity_zero_after_structure": 0,
        "saturation_events": 0,
        "total_cycles": sum(1 for row in rows
                            if row["ap"] or row["st"] != STATE_IDLE),
    }
    if accepted_masks is not None:
        accepts = [row for row in rows if row["ap"]]
        if len(accepts) != len(accepted_masks):
            raise AssertionError("接受拍数与事务数不一致 %d != %d"
                                 % (len(accepts), len(accepted_masks)))
        observed["zero_fast_paths"] = sum(1 for mask in accepted_masks if mask == 0)
    return observed


def accepted_issue_masks(rows: Sequence[dict[str, int]],
                         txns: Sequence[tuple[int, int, int, int]]) -> list[int]:
    """按接受顺序取出每个事务的 issue_mask（观测到的接受拍计数）。"""
    accepts = sum(1 for row in rows if row["ap"])
    return [txn[2] for txn in txns[:accepts]]


def result_sums(rows: Sequence[dict[str, int]]) -> list[int]:
    """每个被接受的 done 的突触和，按序返回。"""
    return [row["sum"] for row in rows if row["rv"] and row["rr"]]


def reconstruct_violations(claimed: dict[str, int], observed: dict[str, int],
                           name: str) -> list[str]:
    """自报账本 vs 逐拍观测：任何不可重建的字段都是拒绝理由。"""
    violations = []
    for field in LEDGER_FIELDS:
        if field in ("structural_skips", "input_zero_groups",
                     "activity_zero_after_structure", "saturation_events"):
            continue  # 这些字段观测侧不可见，由 NP7.3 的逐拍 oracle 比对覆盖
        want = observed[field]
        got = claimed.get(field)
        if got != want:
            violations.append("%s %s 自报 %s 与逐拍观测 %d 不一致"
                              % (name, field, got, want))
    return violations


def reduction(claimed_baseline: dict[str, int], candidate: dict[str, int],
              field: str) -> float:
    """相对基线的下降比例；基线为零时返回 0（不得记为收益）。"""
    base = claimed_baseline[field]
    if base <= 0:
        return 0.0
    return (base - candidate[field]) / float(base)


__all__ = ["CYC_RE", "LEDGER_RE", "LEDGER_FIELDS", "SLOTS_PER_WORD",
           "accepted_issue_masks", "observe", "parse_rows", "reconstruct_violations",
           "reduction", "result_sums"]
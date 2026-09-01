"""NP7 性能账本的"逐拍观测重建"规则（NP7.5 / NP7.6 共用）。

冻结合同要求账本的每一个字段都必须能由逐拍观测重建，自报数字与观测不一致即拒绝，
与实现的身份无关。B-V1+V2（PR #6 评论 5498372499）之后，旧恒等式
`total = accept + latency + busy + stall + done` 作废，改为按互斥类别逐拍分类求和：

    RAM > LANE > LAT > LANE_STALL > BACKPRESSURE > HOLD_RETIRE > ZERO > ACCEPT > IDLE

    total_cycles = busy(RAM+LANE) + latency + lane_stall + backpressure
                 + hold_retire + zero_single + accept_own

逐拍观测来自 tb_np7_exec_unit.sv / tb_np7_negative.sv 的 CYC 行：

    st  状态机编码（0=IDLE 1=RD0 2=RD1 3=LAT 4=BATCH 5=HOLD 结果锁存待退出）
    ce  当拍 RAM 读请求        lf  当拍占用的 lane 槽位数
    rv/rr 结果 valid/ready     ap  当拍接受新事务（V2 允许与退出同拍）
    zp  结果来自零路径         ls  lane_stall
"""

from __future__ import annotations

import re
from typing import Sequence

SLOTS_PER_WORD = 2
STATE_IDLE = 0
STATE_RD0 = 1
STATE_RD1 = 2
STATE_LAT = 3
STATE_BATCH = 4
STATE_HOLD = 5
CLASS_ORDER = ("RAM", "LANE", "LAT", "LANE_STALL", "BACKPRESSURE", "HOLD_RETIRE",
               "ZERO", "ACCEPT", "IDLE")

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
# DUT 自报账本里可以由逐拍观测复算的字段（B-V1+V2 口径）。
OBSERVABLE_FIELDS = ("group_read_requests", "weight_values_fetched",
                     "lane_ops_issued", "zero_fast_paths", "busy_cycles",
                     "stall_cycles", "completed_groups", "total_cycles")


def parse_rows(stdout):
    """解析 tb 的 CYC 行与 LEDGER 行。"""
    rows = []
    for match in CYC_RE.finditer(stdout):
        values = match.groups()
        rows.append({"cycle": int(values[0]), "st": int(values[1]),
                     "ce": int(values[2]), "ad": int(values[3]),
                     "lf": int(values[4]), "bm": int(values[5], 16),
                     "rv": int(values[6]), "rr": int(values[7]),
                     "ap": int(values[8]), "zp": int(values[9]),
                     "sum": int(values[10]), "ls": int(values[11]),
                     "cmp": int(values[12])})
    ledger_match = LEDGER_RE.search(stdout)
    if ledger_match is None:
        raise AssertionError("仿真输出缺少 LEDGER 行")
    claimed = {}
    for index, name in enumerate(LEDGER_FIELDS):
        claimed[name] = int(ledger_match.group(index + 1))
    tail = ledger_match.groups()[-3:]
    claimed["protocol_error"] = int(tail[0])
    claimed["config_error"] = int(tail[1])
    claimed["completed"] = int(tail[2])
    return rows, claimed


def classify_row(row):
    """把一拍观测归入互斥类别；优先级与 oracle.classify 完全一致。"""
    if row["ce"]:
        return "RAM"
    if row["lf"]:
        return "LANE"
    if row["st"] == STATE_LAT:
        return "LAT"
    if row["st"] == STATE_BATCH and row["ls"]:
        return "LANE_STALL"
    if row["rv"] and not row["rr"]:
        return "BACKPRESSURE"
    if row["st"] == STATE_HOLD and row["rv"] and row["rr"]:
        return "HOLD_RETIRE"
    if row["ap"] and row["zp"] and row["rv"] and row["rr"]:
        return "ZERO"
    if row["ap"]:
        return "ACCEPT"
    return "IDLE"


def stream_window(rows):
    """流水窗 = 第一次 accept 到最后一次结果退出（含端点）。"""
    accepts = [index for index, row in enumerate(rows) if row["ap"]]
    retires = [index for index, row in enumerate(rows)
               if row["rv"] and row["rr"]]
    if not accepts or not retires:
        return (0, 0)
    return (accepts[0], max(retires))


def observe(rows, accepted_masks=None, slots_per_word=SLOTS_PER_WORD):
    """只从逐拍观测重建 B-V1+V2 账本，不使用任何自报数字。"""
    lo, hi = stream_window(rows)
    window = list(rows[lo:hi + 1])
    counts = dict((name, 0) for name in CLASS_ORDER)
    for row in window:
        counts[classify_row(row)] += 1
    reads = sum(row["ce"] for row in window)
    observed = {
        "group_read_requests": reads,
        "weight_values_fetched": reads * slots_per_word,
        "lane_ops_issued": sum(row["lf"] for row in window),
        "zero_fast_paths": 0,
        "busy_cycles": counts["RAM"] + counts["LANE"],
        "stall_cycles": counts["LANE_STALL"] + counts["BACKPRESSURE"],
        "completed_groups": sum(1 for row in window if row["rv"] and row["rr"]),
        "structural_skips": 0,
        "input_zero_groups": 0,
        "activity_zero_after_structure": 0,
        "saturation_events": 0,
        "total_cycles": len(window) - counts["IDLE"],
        "latency_cycles": counts["LAT"],
        "lane_stall_cycles": counts["LANE_STALL"],
        "backpressure_cycles": counts["BACKPRESSURE"],
        "hold_retire_cycles": counts["HOLD_RETIRE"],
        "zero_single_cycles": counts["ZERO"],
        "accept_own_cycles": counts["ACCEPT"],
        "accept_events": sum(1 for row in window if row["ap"]),
        "retire_events": sum(1 for row in window if row["rv"] and row["rr"]),
        "overlap_cycles": sum(1 for row in window
                              if row["ap"] and row["rv"] and row["rr"]
                              and not (row["zp"] and row["st"] == STATE_IDLE)),
        "accept_cycles": counts["ACCEPT"],
        "retire_latch_cycles": sum(1 for row in window
                                   if row["lf"] and row["rv"] and not row["rr"]),
        "window_cycles": len(window),
    }
    work = [index for index, row in enumerate(window)
            if row["ce"] or row["lf"] or row["st"] == STATE_LAT]
    observed["startup_cycles"] = 1 if window and classify_row(window[0]) == "ACCEPT" else 0
    observed["drain_cycles"] = (len(window) - 1 - work[-1]) if work else 0
    if accepted_masks is not None:
        accepts = observed["accept_events"]
        if accepts != len(accepted_masks):
            raise AssertionError("接受拍数与事务数不一致 %d != %d"
                                 % (accepts, len(accepted_masks)))
        observed["zero_fast_paths"] = sum(1 for mask in accepted_masks if mask == 0)
    return observed


def identity_violations(ledger, name="ledger"):
    """B-V1+V2 新恒等式与单槽不变量；任何漏记/重记都在此处暴露。"""
    bad = []
    want = (ledger["busy_cycles"] + ledger["latency_cycles"]
            + ledger["lane_stall_cycles"] + ledger["backpressure_cycles"]
            + ledger["hold_retire_cycles"] + ledger["zero_single_cycles"]
            + ledger["accept_own_cycles"])
    if want != ledger["total_cycles"]:
        bad.append("%s 恒等式 total=%d != 各类之和 %d"
                   % (name, ledger["total_cycles"], want))
    if ledger["stall_cycles"] != (ledger["lane_stall_cycles"]
                                  + ledger["backpressure_cycles"]):
        bad.append("%s stall=%d != lane_stall+backpressure=%d"
                   % (name, ledger["stall_cycles"],
                      ledger["lane_stall_cycles"] + ledger["backpressure_cycles"]))
    if ledger["retire_events"] != ledger["completed_groups"]:
        bad.append("%s retire=%d != completed=%d"
                   % (name, ledger["retire_events"], ledger["completed_groups"]))
    if ledger["accept_events"] != ledger["completed_groups"]:
        bad.append("%s accept=%d != completed=%d（每 accept 必须恰好一个 result）"
                   % (name, ledger["accept_events"], ledger["completed_groups"]))
    if ledger["zero_single_cycles"] > ledger["zero_fast_paths"]:
        bad.append("%s 零路径单拍 %d 超过零路径事务 %d"
                   % (name, ledger["zero_single_cycles"], ledger["zero_fast_paths"]))
    if ledger["overlap_cycles"] > ledger["accept_events"]:
        bad.append("%s 同拍 retire/accept %d 超过 accept 数 %d"
                   % (name, ledger["overlap_cycles"], ledger["accept_events"]))
    return bad


def accepted_issue_masks(rows, txns):
    """按接受顺序取出每个事务的 issue_mask（观测到的接受拍计数）。"""
    lo, hi = stream_window(rows)
    accepts = sum(1 for row in rows[lo:hi + 1] if row["ap"])
    return [txn[2] for txn in txns[:accepts]]


def result_sums(rows):
    """每个退出结果的突触和，按序返回（V2 下退出可与接受同拍）。"""
    return [row["sum"] for row in rows if row["rv"] and row["rr"]]


def reconstruct_violations(claimed, observed, name):
    """自报账本 vs 逐拍观测：任何不可重建的字段都是拒绝理由。"""
    violations = []
    for field in OBSERVABLE_FIELDS:
        want = observed[field]
        got = claimed.get(field)
        if got != want:
            violations.append("%s %s 自报 %s 与逐拍观测 %d 不一致"
                              % (name, field, got, want))
    violations += identity_violations(observed, name + "(观测)")
    return violations


def reduction(claimed_baseline, candidate, field):
    """相对基线的下降比例；基线为零时返回 0（不得记为收益）。"""
    base = claimed_baseline[field]
    if base <= 0:
        return 0.0
    return (base - candidate[field]) / float(base)


__all__ = ["CYC_RE", "CLASS_ORDER", "LEDGER_RE", "LEDGER_FIELDS", "OBSERVABLE_FIELDS",
           "SLOTS_PER_WORD", "STATE_HOLD", "STATE_LAT", "accepted_issue_masks",
           "classify_row",
           "identity_violations", "observe", "parse_rows", "reconstruct_violations",
           "reduction", "result_sums", "stream_window"]

"""NP7.3：共享 lane 执行单元的 Python/Icarus 逐拍协同仿真。

对 dense 与 sparse 两个顶层各扫描 1/2/4/8 lane，每个配置跑 >=20 seeds x 1000
混合事务；逐拍比较 RAM 请求、lane 发射、批量掩码、done 与累加和，并核对全部
计数器账本。任何偏差都会让本脚本以非零码退出。
"""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from rtl_tile_cosim import find_tool

from np7_shared_lane_oracle import (
    FORMAT_DENSE,
    FORMAT_SPARSE,
    LANE_COUNTS,
    SharedLaneUnit,
    encode_dense_group,
    encode_sparse_group,
    exhaustive_structures,
    mask_from_indices,
)
from np7_ledger_reconstruction import (OBSERVABLE_FIELDS,
                                       accepted_issue_masks, classify_row,
                                       identity_violations, observe, parse_rows,
                                       reconstruct_violations, result_sums,
                                       stream_window)

# B-V1+V2 里所有能从 CYC 逐拍行重建的账本字段（其余为激励派生或与 DUT 自报交叉核对）。
OBSERVABLE_V2_FIELDS = OBSERVABLE_FIELDS + (
    "latency_cycles", "lane_stall_cycles", "backpressure_cycles",
    "hold_retire_cycles", "zero_single_cycles", "accept_events",
    "retire_events", "overlap_cycles", "accept_cycles", "startup_cycles",
    "drain_cycles", "retire_latch_cycles")

ROOT = Path(__file__).resolve().parent
RTL_SOURCES = [
    str(ROOT / "np7_weight_ram.sv"),
    str(ROOT / "np7_shared_synapse_lane.sv"),
    str(ROOT / "np7_exec_unit_dense.sv"),
    str(ROOT / "np7_exec_unit_sparse.sv"),
    str(ROOT / "tb_np7_exec_unit.sv"),
]
TXN_PER_SEED = 1000
SEEDS_PER_CONFIG = 20
# NP7.3 每次运行都留一份"原始账本 + 逐拍观测"副本，供 NP7.6 重新计算硬门。
# 只认自报数字的实现（例如 NP7.5 的两个负向控制）在这份证据里会露出马脚。
RAW_LEDGERS: list[dict] = []
GROUP_COUNT = 10
CYC_RE = re.compile(
    r"CYC (\d+) st=(\d) ce=(\d) ad=(\d+) lf=(\d) bm=(\S+) rv=(\d) rr=(\d) "
    r"ap=(\d) zp=(\d) sum=(-?\d+) ls=(\d) cmp=(\d+)"
)
LEDGER_RE = re.compile(
    r"LEDGER req=(\d+) val=(\d+) ops=(\d+) zero=(\d+) busy=(\d+) stall=(\d+) "
    r"done=(\d+) skip=(\d+) inzero=(\d+) azero=(\d+) sat=(\d+) total=(\d+) "
    r"proto=(\d) cfgerr=(\d) completed=(\d+)"
)

def build_case(fmt: str, lanes: int, seed: int):
    rng = random.Random(lanes * 100003 + seed)
    structures = [rng.choice(exhaustive_structures()) for _ in range(GROUP_COUNT)]
    sem: list[list[int]] = []
    for group in range(GROUP_COUNT):
        real = [rng.randint(-128, 127) for _ in range(4)]
        struct = mask_from_indices(structures[group])
        sem.append([real[position] if (struct >> position) & 1 else 0
                    for position in range(4)])
    words: list[int] = []
    for group in range(GROUP_COUNT):
        if fmt == FORMAT_DENSE:
            words.extend(encode_dense_group(sem[group]))
        else:
            indices = structures[group]
            words.extend(encode_sparse_group(
                [sem[group][indices[0]], sem[group][indices[1]]], indices))
    txns = []
    for _ in range(TXN_PER_SEED):
        group = rng.randrange(GROUP_COUNT)
        activity = rng.randint(0, 15)
        struct = 0b1111 if fmt == FORMAT_DENSE else mask_from_indices(structures[group])
        issue = struct & activity
        skip = bin(activity & ~struct & 0b1111).count("1")
        txns.append((group, activity, issue, skip))
    bp = []
    for _ in range(TXN_PER_SEED * 12 + 2000):
        stall = 1 if rng.random() < 0.2 else 0
        ready = 0 if rng.random() < 0.15 else 1
        bp.append((stall & 1) | ((ready & 1) << 1))
    return structures, sem, words, txns, bp


def compile_tb(fmt: str, lanes: int, work: Path) -> Path:
    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("Icarus Verilog 工具不可用")
    binary = work / ("sim_%s_%d.out" % (fmt, lanes))
    command = [os.fspath(iverilog), "-g2012", "-s", "tb",
               "-Ptb.LANES=%d" % lanes,
               "-Ptb.SPARSE=%s" % ("1'b1" if fmt == FORMAT_SPARSE else "1'b0"),
               "-o", os.fspath(binary)] + RTL_SOURCES
    done = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
    if done.returncode != 0:
        raise AssertionError("NP7 RTL 编译失败 (%s/%d lane):\n%s%s"
                             % (fmt, lanes, done.stdout, done.stderr))
    return binary


def run_case(binary: Path, fmt: str, lanes: int, seed: int,
             work: Path) -> tuple[int, list[str]]:
    structures, sem, words, txns, bp = build_case(fmt, lanes, seed)
    case_dir = work / ("case_%s_%d_%d" % (fmt, lanes, seed))
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "np7_cfg.hex").write_text(
        "".join("%05x\n" % word for word in words), encoding="ascii")
    (case_dir / "np7_txn.hex").write_text("".join(
        "%08x\n" % ((group) | (activity << 4) | (issue << 8) | (skip << 12))
        for group, activity, issue, skip in txns), encoding="ascii")
    (case_dir / "np7_bp.hex").write_text(
        "".join("%02x\n" % value for value in bp), encoding="ascii")
    done = subprocess.run(
        [os.fspath(find_tool("vvp")), os.fspath(binary),
         "+NTXN=%d" % len(txns), "+NWORD=%d" % len(words)],
        cwd=str(case_dir), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False)
    failures: list[str] = []
    if done.returncode != 0 or "TB_FAIL" in done.stdout:
        failures.append("vvp 运行失败 rc=%d\n%s%s"
                        % (done.returncode, done.stdout[:400], done.stderr[:400]))
        return 0, failures, []
    failures, sums = compare_case(done.stdout, fmt, lanes, structures,
                                   sem, words, txns, bp)
    record_raw_ledger(done.stdout, fmt, lanes, seed, txns, sums)
    return len(txns), failures, sums


def record_raw_ledger(stdout, fmt, lanes, seed, txns, sums):
    """NP7.3 每次运行都留一份"原始逐拍观测 + 自报账本"副本，供 NP7.6 重新计算硬门。

    只认自报数字的实现（例如 NP7.5 的两个负向实现）会在这份证据里露出马脚：
    B-V1+V2 之后连 total/busy/stall 都必须由逐拍类别重建，旧恒等式不再成立。
    """
    import hashlib
    rows, claimed = parse_rows(stdout)
    observed = observe(rows, accepted_issue_masks(rows, txns))
    RAW_LEDGERS.append({
        "format": fmt, "lanes": lanes, "seed": seed, "transactions": len(txns),
        "cycles_logged": len(rows), "contract": "B-V1+V2",
        "claimed": claimed, "observed": observed,
        "reconstruction_violations": reconstruct_violations(
            claimed, observed, "%s/%d/%d" % (fmt, lanes, seed)),
        "identity_violations": identity_violations(
            observed, "%s/%d/%d" % (fmt, lanes, seed)),
        # 逐笔突触和的指纹：dense 与 sparse 必须逐笔全等（G5），但证据文件里
        # 不放原始向量，避免把 160000 个整数写进仓库。
        "result_sums_sha256": hashlib.sha256(
            ",".join(str(value) for value in sums).encode("ascii")).hexdigest(),
        "result_sums_count": len(sums),
    })


def compare_case(stdout, fmt, lanes, structures, sem, words, txns, bp):
    """逐拍比对 RTL 流水与 B-V1+V2 oracle 流水，并核对三方账本。

    三方 = DUT 自报 LEDGER 计数器、tb CYC 行的观测重建、oracle 流水模型。旧口径按
    "每事务独立段"切窗；V2 的同拍 retire/accept 会让事务窗口重叠，因此改成整条流一次比。
    """
    failures = []
    rows, claimed = parse_rows(stdout)
    if not rows:
        return ["没有任何 CYC 观测行"], []
    base = rows[0]["cycle"]
    for position, row in enumerate(rows):
        if row["cycle"] != base + position:
            return ["CYC 序号不连续 at %d" % position], []
    lo, hi = stream_window(rows)
    window = rows[lo:hi + 1]
    unit = SharedLaneUnit(fmt, lanes, GROUP_COUNT)
    unit.config_load_words(words)
    unit.config_finish()
    results = unit.run_stream(
        [(txn[0], txn[1]) for txn in txns],
        lane_stall=lambda tick: window[tick]["ls"],
        result_ready=lambda tick: window[tick]["rr"],
        issue_valid=lambda tick: 1)
    if len(results) != len(txns):
        return ["oracle 完成事务数 %d != %d" % (len(results), len(txns))], []
    events = unit.stream_events
    if len(events) != len(window):
        failures.append("流水窗长度不等 rtl=%d oracle=%d（%s/%d lane）"
                        % (len(window), len(events), fmt, lanes))
    else:
        for offset, event in enumerate(events):
            seen = window[offset]
            want_bm = sum(1 << pos for pos in event.lane_positions)
            mismatch = (seen["ce"], seen["rv"], seen["rr"], seen["ap"],
                        seen["zp"], seen["ls"]) != (
                           event.ram_ce, event.result_valid, event.result_ready,
                           event.accepted, event.result_zero, seen["ls"])
            if not mismatch and seen["ce"] and seen["ad"] != event.ram_addr:
                mismatch = True
            if not mismatch and seen["lf"] != event.lane_count:
                mismatch = True
            if not mismatch and event.lane_count and seen["bm"] != want_bm:
                mismatch = True
            if not mismatch and event.result_valid and seen["sum"] != event.result_sum:
                mismatch = True
            if not mismatch and classify_row(seen) != event.cls:
                mismatch = True
            if mismatch:
                failures.append(
                    "第 %d 拍不等 rtl ce=%d ad=%d lf=%d bm=%x rv=%d rr=%d ap=%d zp=%d "
                    "sum=%d st=%d / oracle ce=%d ad=%d lf=%d bm=%d rv=%d ap=%d zp=%d "
                    "sum=%d cls=%s"
                    % (offset, seen["ce"], seen["ad"], seen["lf"], seen["bm"],
                       seen["rv"], seen["rr"], seen["ap"], seen["zp"], seen["sum"],
                       seen["st"], event.ram_ce, event.ram_addr, event.lane_count,
                       want_bm, event.result_valid, event.accepted,
                       event.result_zero, event.result_sum, event.cls))
                break
    sums = [result.synapse_sum for result in results]
    rtl_sums = result_sums(rows)
    if rtl_sums != sums:
        first_bad = next((index for index in range(min(len(rtl_sums), len(sums)))
                          if rtl_sums[index] != sums[index]), min(len(rtl_sums), len(sums)))
        failures.append("突触和序列第 %d 笔不一致 rtl=%d oracle=%d"
                        % (first_bad,
                           rtl_sums[first_bad] if first_bad < len(rtl_sums) else -1,
                           sums[first_bad] if first_bad < len(sums) else -1))
    observed = observe(rows, accepted_issue_masks(rows, txns))
    # (a) 逐拍可观测字段：oracle 流水模型 vs 从 CYC 行重建的观测账本。
    for field in OBSERVABLE_V2_FIELDS:
        if not hasattr(unit.ledger, field):
            failures.append("oracle 账本缺少字段 %s" % field)
            continue
        if field not in observed:
            failures.append("观测账本缺少字段 %s" % field)
            continue
        want = getattr(unit.ledger, field)
        got = observed[field]
        if want != got:
            failures.append("%s oracle=%d rtl观测=%d" % (field, want, got))
    # (b) 激励派生字段：CYC 行看不出"结构跳过/输入为零/结构化后为零"这类语义，
    # 只能把 oracle、DUT 自报计数器和激励真值三边对齐。
    truth = {
        "structural_skips": sum(txn[3] for txn in txns),
        "input_zero_groups": sum(1 for txn in txns if txn[1] == 0),
        "activity_zero_after_structure": sum(
            1 for txn in txns if txn[1] != 0 and txn[2] == 0),
    }
    for field, want in truth.items():
        if not hasattr(unit.ledger, field):
            failures.append("oracle 账本缺少字段 %s" % field)
            continue
        if getattr(unit.ledger, field) != want:
            failures.append("%s oracle=%d 激励真值=%d"
                            % (field, getattr(unit.ledger, field), want))
        if claimed.get(field, -1) != want:
            failures.append("%s DUT自报=%d 激励真值=%d"
                            % (field, claimed.get(field, -1), want))
    if unit.ledger.saturation_events != claimed["saturation_events"]:
        failures.append("saturation_events oracle=%d DUT自报=%d"
                        % (unit.ledger.saturation_events,
                           claimed["saturation_events"]))
    failures += identity_violations(observed, "%s/%d lane 观测" % (fmt, lanes))
    failures += unit.identity_violations("%s/%d lane oracle" % (fmt, lanes))
    failures += reconstruct_violations(claimed, observed, "%s/%d lane 自报" % (fmt, lanes))
    if claimed["protocol_error"] != 0:
        failures.append("protocol_error 被置位")
    if claimed["config_error"] != 0:
        failures.append("cfg_error 被置位")
    if claimed["completed"] != len(txns):
        failures.append("完成事务数 %s != %d" % (claimed["completed"], len(txns)))
    if not any(result.zero_path for result in results[1:]) and fmt == FORMAT_DENSE:
        pass
    return failures, sums


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    seeds = int(args[0]) if len(args) >= 1 else SEEDS_PER_CONFIG
    self_module = sys.modules[__name__]
    self_module.TXN_PER_SEED = int(args[1]) if len(args) >= 2 else TXN_PER_SEED
    failures: list[str] = []
    runs = 0
    with tempfile.TemporaryDirectory(prefix="np7_cosim_") as temp_dir:
        work = Path(temp_dir)
        for lanes in LANE_COUNTS:
            binaries = {fmt: compile_tb(fmt, lanes, work)
                        for fmt in (FORMAT_DENSE, FORMAT_SPARSE)}
            sums: dict[str, list[list[int]]] = {}
            for fmt in (FORMAT_DENSE, FORMAT_SPARSE):
                per_seed: list[list[int]] = []
                for seed in range(seeds):
                    count, case_failures, case_sums = run_case(
                        binaries[fmt], fmt, lanes, seed, work)
                    runs += 1
                    per_seed.append(case_sums)
                    if count != self_module.TXN_PER_SEED and not case_failures:
                        case_failures = ["事务数不完整: %d" % count]
                    for text in case_failures[:4]:
                        failures.append("[lanes=%d %s seed=%d] %s"
                                        % (lanes, fmt, seed, text))
                sums[fmt] = per_seed
            for seed in range(seeds):
                if sums[FORMAT_DENSE][seed] != sums[FORMAT_SPARSE][seed]:
                    failures.append("[lanes=%d seed=%d] dense 与 sparse 突触和序列不一致"
                                    % (lanes, seed))
            print("[NP7.3] lanes=%d 完成 %d seeds x %d txns 逐拍比对"
                  % (lanes, seeds, self_module.TXN_PER_SEED))
    print("[NP7.3] 运行数=%d 失败数=%d" % (runs, len(failures)))
    for text in failures[:20]:
        print("  FAIL", text)
    results = Path("artifacts") / "results"
    results.mkdir(parents=True, exist_ok=True)
    bad = sum(1 for entry in RAW_LEDGERS if entry["reconstruction_violations"])
    (results / "np7_cosim_ledgers.json").write_text(json.dumps(
        {"schema": "np7-cosim-ledgers-v2", "configs": runs,
         "transactions": sum(e["transactions"] for e in RAW_LEDGERS),
         "per_tick_failures": len(failures),
         "reconstruction_dirty_configs": bad, "ledgers": RAW_LEDGERS},
        indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print("[NP7.3] 原始账本=%d 组，逐拍观测不一致=%d"
          % (len(RAW_LEDGERS), bad))
    return 1 if (failures or bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())

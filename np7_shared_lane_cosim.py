"""NP7.3：共享 lane 执行单元的 Python/Icarus 逐拍协同仿真。

对 dense 与 sparse 两个顶层各扫描 1/2/4/8 lane，每个配置跑 >=20 seeds x 1000
混合事务；逐拍比较 RAM 请求、lane 发射、批量掩码、done 与累加和，并核对全部
计数器账本。任何偏差都会让本脚本以非零码退出。
"""

from __future__ import annotations

import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

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
    return len(txns), failures, sums

def unit_group_was_zero(txn, structures, fmt):
    """该事务是否走零突触快速路径（与 oracle 判据一致）。"""
    group, activity, _issue, _skip = txn
    struct = 0b1111 if fmt == FORMAT_DENSE else mask_from_indices(structures[group])
    return (struct & activity) == 0


def parse_fields(match):
    return {"cycle": int(match.group(1)), "st": int(match.group(2)),
            "ce": int(match.group(3)), "ad": int(match.group(4)),
            "lf": int(match.group(5)), "bm": int(match.group(6), 16),
            "rv": int(match.group(7)), "rr": int(match.group(8)),
            "ap": int(match.group(9)), "zp": int(match.group(10)),
            "sum": int(match.group(11))}


def compare_case(stdout: str, fmt: str, lanes: int, structures, sem,
                 words, txns, bp) -> tuple[list[str], list[int]]:
    """逐拍比对 RTL 与 oracle，并核对最终账本。"""
    failures: list[str] = []
    cycles = []
    ledger_line = None
    for raw in stdout.splitlines():
        match = CYC_RE.match(raw.strip())
        if match:
            cycles.append(match)
            continue
        if LEDGER_RE.match(raw.strip()):
            ledger_line = LEDGER_RE.match(raw.strip())
    if ledger_line is None:
        return ["输出缺少 LEDGER 行: " + stdout[-300:]], []
    base = int(cycles[0].group(1)) if cycles else 0
    for position, match in enumerate(cycles):
        if int(match.group(1)) != base + position:
            failures.append("CYC 序号不连续 at %d" % position)
            break
    if failures:
        return failures, []
    unit = SharedLaneUnit(fmt, lanes, GROUP_COUNT)
    unit.config_load_words(words)
    unit.config_finish()
    accepts = [int(m.group(1)) - base for m in cycles
               if m.group(9) == "1"]
    if len(accepts) != len(txns):
        failures.append("接受事务数 %d != 激励数 %d" % (len(accepts), len(txns)))
        return failures, []
    sums: list[int] = []
    for position, accept in enumerate(accepts):
        group, activity, _issue, _skip = txns[position]
        stop = accepts[position + 1] if position + 1 < len(accepts) else len(cycles)
        origin = base + accept
        result = unit.run_group(
            group, activity,
            lane_stall=lambda cycle, start=origin: (
                (bp[start + cycle] & 1) if start + cycle < len(bp) else 0),
            result_ready=lambda cycle, start=origin: (
                ((bp[start + cycle] >> 1) & 1) if start + cycle < len(bp) else 1))
        sums.append(result.synapse_sum)
        observed = cycles[accept:stop]
        if position + 1 < len(accepts) and len(observed) != result.cycles:
            failures.append("事务 %d 周期 %d != oracle %d (%s/%d lane seed case)"
                            % (position, len(observed), result.cycles, fmt, lanes))
            continue
        if len(observed) < result.cycles:
            failures.append("事务 %d 观测周期不足 %d < %d"
                            % (position, len(observed), result.cycles))
            continue
        for offset, event in enumerate(result.events):
            seen = parse_fields(observed[offset])
            want_bm = sum(1 << pos for pos in event.lane_positions)
            seen_bm = seen["bm"] if event.lane_count else want_bm
            if (seen["ce"], seen["lf"], seen_bm, seen["rv"]) != (
                    event.ram_ce, event.lane_count, want_bm, event.result_valid):
                failures.append(
                    "事务 %d 第 %d 拍不等: rtl ce=%d lf=%d bm=%d rv=%d / "
                    "oracle ce=%d lf=%d bm=%d rv=%d"
                    % (position, offset, seen["ce"], seen["lf"], seen["bm"],
                       seen["rv"], event.ram_ce, event.lane_count, want_bm,
                       event.result_valid))
                break
            if event.ram_ce and seen["ad"] != event.ram_addr:
                failures.append("事务 %d 第 %d 拍地址 %d != %d"
                                % (position, offset, seen["ad"], event.ram_addr))
                break
            if offset == len(result.events) - 1 and seen["sum"] != result.synapse_sum:
                failures.append("事务 %d 突触和 %d != %d"
                                % (position, seen["sum"], result.synapse_sum))
                break
            if offset == len(result.events) - 1 and seen["zp"] != int(
                    bool(event.state == "DONE" and
                         unit_group_was_zero(txns[position], structures, fmt))):
                failures.append("事务 %d 零路径标志与 oracle 不一致" % position)
                break
    observed_ledger = [int(ledger_line.group(index)) for index in range(1, 13)]
    want_ledger = [unit.ledger.group_read_requests, unit.ledger.weight_values_fetched,
                   unit.ledger.lane_ops_issued, unit.ledger.zero_fast_paths,
                   unit.ledger.busy_cycles, unit.ledger.stall_cycles,
                   unit.ledger.completed_groups, unit.ledger.structural_skips,
                   unit.ledger.input_zero_groups,
                   unit.ledger.activity_zero_after_structure,
                   unit.ledger.saturation_events, unit.ledger.total_cycles]
    if observed_ledger != want_ledger:
        failures.append("账本不等 rtl=%s oracle=%s" % (observed_ledger, want_ledger))
    if ledger_line.group(13) != "0":
        failures.append("protocol_error 被置位")
    if ledger_line.group(14) != "0":
        failures.append("cfg_error 被置位")
    if int(ledger_line.group(15)) != len(txns):
        failures.append("完成事务数 %s != %d" % (ledger_line.group(15), len(txns)))
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
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

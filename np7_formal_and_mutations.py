# NP7.5 形式验证 + 负向控制 + 泄漏 mutation 套件（fail-closed）。
#
# 覆盖 TODO 5 节 NP7.5 的四条：
#   1) 有限深度形式检查：单槽协议、恰好一次完成、地址边界、无重复发射、计数守恒；
#   2) issue_mask=0 的零突触快速路径不发 RAM/lane 请求但仍产生 done（P5 断言 + 可达性 witness）；
#   3) 两个"伪收益"负向实现必须被性能账本 verifier 拒绝（自报口径 + 纯观测口径双重拒绝）；
#   4) 遗漏泄放推进的零快速路径 mutation 必须被三模型状态等价检查抓到。
#
# 任何一条不成立都以非零退出码结束，并写出 artifacts/results/np7_formal_and_mutations.json。

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

import np7_shared_lane_cosim as cosim
from np7_shared_lane_oracle import FORMAT_DENSE, FORMAT_SPARSE
from np7_ledger_reconstruction import (accepted_issue_masks, observe,
                                       reconstruct_violations, reduction,
                                       result_sums, parse_rows)

YOSYS = r"C:\msys64\ucrt64\bin\yosys.exe"
IVERILOG = r"C:\iverilog\bin\iverilog.exe"
VVP = r"C:\iverilog\bin\vvp.exe"
NEG_SOURCES = ["np7_weight_ram.sv", "np7_shared_synapse_lane.sv",
               "np7_exec_unit_dense.sv", "np7_exec_unit_sparse.sv",
               "np7_negative_controls.sv", "tb_np7_negative.sv"]
FORMAL_SOURCES = ["np7_weight_ram.sv", "np7_shared_synapse_lane.sv",
                  "np7_exec_unit_dense.sv", "np7_exec_unit_sparse.sv",
                  "formal_np7_exec_unit.sv", "formal_np7_config_reject.sv"]
CFGNEG_SOURCES = ["np7_weight_ram.sv", "np7_shared_synapse_lane.sv",
                  "np7_exec_unit_dense.sv", "np7_exec_unit_sparse.sv",
                  "tb_np7_config_negative.sv"]
CFGNEG_BYPASS = {
    FORMAT_SPARSE: ("np7_exec_unit_sparse.sv",
                    "    wire cfg_wr_ok = !sparse_record_illegal_next;",
                    "    wire cfg_wr_ok = 1'b1; // MUTATION bypass"),
    FORMAT_DENSE: ("np7_exec_unit_dense.sv",
                   "    wire cfg_wr_ok = !dense_record_illegal_next;",
                   "    wire cfg_wr_ok = 1'b1; // MUTATION bypass"),
}
LANES_LIST = (1, 2, 4, 8)
SEEDS = (1, 2, 3)

PROBLEMS = []
CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})
    if not ok:
        PROBLEMS.append("%s: %s" % (name, detail))
    print("%-46s %s %s" % (name, "PASS" if ok else "FAIL", str(detail)[:120]))
    return bool(ok)

def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_yosys(ys_text, workdir, tag):
    path = Path(workdir) / (tag + ".ys")
    path.write_text(ys_text, encoding="utf-8")
    done = subprocess.run([YOSYS, "-Q", "-s", path.name], cwd=str(workdir),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False, timeout=900)
    return done.returncode, done.stdout + done.stderr


FORMAL_SCRIPTS = [
    ("sparse_protocol", "formal_np7_exec_unit.ys", "proof"),
    ("dense_protocol", "formal_np7_exec_unit_dense.ys", "proof"),
    ("config_reject", "formal_np7_config_reject.ys", "proof"),
    ("zero_path_reach", "formal_np7_exec_unit_zero.ys", "model"),
    ("sparse_reach", "formal_np7_exec_unit_reach.ys", "model"),
    ("dense_reach", "formal_np7_exec_unit_dense_reach.ys", "model"),
]


def formal_verdict(output):
    # Yosys 0.68 的 sat 结论行：
    #   证明成立 -> "SAT proof finished - no model found: SUCCESS!"
    #   证明被推翻 -> "Status: FAILED"（并给出反例）
    #   可达性 witness -> "SAT solving finished - model found:"
    if "SAT proof finished - no model found: SUCCESS!" in output:
        return "proof"
    if "proof did fail" in output or "Status: FAILED" in output:
        return "counterexample"
    if "SAT solving finished - model found:" in output:
        return "model"
    if "ERROR" in output:
        return "error"
    return "unknown"


def run_formal_suite():
    results = {}
    for tag, script, need in FORMAL_SCRIPTS:
        text = (ROOT / script).read_text(encoding="utf-8")
        rc, output = run_yosys(text, ROOT, "np75_tmp_" + tag)
        Path("np75_tmp_" + tag + ".ys").unlink(missing_ok=True)
        verdict = formal_verdict(output)
        want = "proof" if need == "proof" else "model"
        ok = (verdict == want)
        results[tag] = {"script": script, "expected": want, "verdict": verdict,
                        "returncode": rc, "sha256": sha256_text(text)}
        check("formal_%s(%s)" % (tag, want), ok,
              "verdict=%s rc=%s" % (verdict, rc))
    return results
RTL_MUTATIONS = [
    ("fake_weight_slots", "np7_exec_unit_sparse.sv",
     "weight_values_fetched_state <= weight_values_fetched_state + 32'd2;",
     "weight_values_fetched_state <= weight_values_fetched_state + 32'd1;",
     "sparse_protocol", "自报权重槽减半但读请求不变"),
    ("fake_lane_ops", "np7_exec_unit_sparse.sv",
     "pending_mask <= pending_mask & ~batch_mask;",
     "pending_mask <= pending_mask;",
     "sparse_protocol", "发射后不清 pending，掩码可重复发射"),
    ("extra_read_burst", "np7_exec_unit_sparse.sv",
     "assign ram_ce = (state == S_RD0);",
     "assign ram_ce = (state == S_RD0) || (state == S_BATCH);",
     "sparse_protocol", "BATCH 期多发读请求"),
    ("dense_fake_val", "np7_exec_unit_dense.sv",
     "weight_values_fetched_state <= weight_values_fetched_state + 32'd4;",
     "weight_values_fetched_state <= weight_values_fetched_state + 32'd2;",
     "dense_protocol", "稠密自报权重槽与读请求脱钩"),
    ("config_rejection_bypass", "np7_weight_ram.sv",
     "assign cfg_write_en = cfg_valid && cfg_open && cfg_wr_ok;",
     "assign cfg_write_en = cfg_valid && cfg_open;",
     "config_reject", "写使能不受 cfg_wr_ok 门控：非法字可进 RAM"),
    # PR #6 评论 5498372499（裁定 B-V1+V2）新增的两类造假：
    #   (a) retire/accept 同一边沿时，用新事务的元数据覆盖正在退出的旧结果；
    #   (b) 结果背压（旧结果未退出）时仍然接受下一事务。
    # 两者都必须被 P1/P9 形式性质给出反例，两格式各测一次。
    ("sparse_same_edge_metadata_overwrite", "np7_exec_unit_sparse.sv",
     '    assign result_zero_path = hold_active ? hold_zero : zero_now;',
     "    assign result_zero_path = accept_pulse ? (issue_mask == 4\'d0) : (hold_active ? hold_zero : zero_now); // MUTATION same-edge overwrite",
     "sparse_protocol", "同拍覆盖：退出结果的 zero_path 标志被新事务覆盖"),
    ("dense_same_edge_metadata_overwrite", "np7_exec_unit_dense.sv",
     '    assign result_zero_path = hold_active ? hold_zero : zero_now;',
     "    assign result_zero_path = accept_pulse ? (issue_mask == 4\'d0) : (hold_active ? hold_zero : zero_now); // MUTATION same-edge overwrite",
     "dense_protocol", "同拍覆盖（稠密基线）"),
    ("sparse_accept_under_backpressure", "np7_exec_unit_sparse.sv",
     '    assign issue_ready = !cfg_open && ((state == S_IDLE) || retire_prev);',
     '    assign issue_ready = !cfg_open; // MUTATION 在途/背压时仍接受下一事务',
     "sparse_protocol", "背压时错误接受：hold/在途期间 issue_ready 仍为 1"),
    ("dense_accept_under_backpressure", "np7_exec_unit_dense.sv",
     '    assign issue_ready = !cfg_open && ((state == S_IDLE) || retire_prev);',
     '    assign issue_ready = !cfg_open; // MUTATION 在途/背压时仍接受下一事务',
     "dense_protocol", "背压时错误接受（稠密基线）"),
    # P1 周期合同（PR #6 裁定 5085536010 §一第 5 项）：lane 一拍流水的三个造假点。
    #   lane_hold_ignored  —— lane 无视 lane_stall，被停住的折叠拍照样出结果；
    #   *_fold_last_early  —— 顶层回到"发射拍即出结果"的旧口径，比流水真实时刻早 1 拍。
    # 三者都必须被 P10/P11（或 P9 的 result_sum 对照）抓住，否则流水时序证明是空的。
    ("lane_hold_ignored", "np7_shared_synapse_lane.sv",
     "    assign fold_valid = valid_q && !fold_hold;",
     "    assign fold_valid = valid_q; // MUTATION lane_stall 期间照样折叠出结果",
     "sparse_protocol", "lane 无视 hold，被停住的折叠拍提前完成"),
    ("sparse_fold_last_early", "np7_exec_unit_sparse.sv",
     "    wire fold_last = drain_active && lane_fold_valid;",
     "    wire fold_last = (state == S_BATCH) && lane_fire && batch_last; // MUTATION",
     "sparse_protocol", "sparse 在发射拍就出结果，比 Stage B 折叠早 1 拍"),
    ("dense_fold_last_early", "np7_exec_unit_dense.sv",
     "    wire fold_last = drain_active && lane_fold_valid;",
     "    wire fold_last = (state == S_BATCH) && lane_fire && batch_last; // MUTATION",
     "dense_protocol", "dense 在发射拍就出结果，比 Stage B 折叠早 1 拍"),
]


MUTATION_SCRIPTS = {"sparse_protocol": "formal_np7_exec_unit.ys",
                    "dense_protocol": "formal_np7_exec_unit_dense.ys",
                    "config_reject": "formal_np7_config_reject.ys"}


def run_rtl_mutations():
    out = {}
    work = Path(tempfile.mkdtemp(prefix="np7_mut_"))
    try:
        for name in FORMAL_SOURCES:
            shutil.copyfile(ROOT / name, work / name)
        for script in ("formal_np7_exec_unit.ys",
                       "formal_np7_exec_unit_dense.ys",
                       "formal_np7_config_reject.ys"):
            shutil.copyfile(ROOT / script, work / script)
        for tag, target, needle, repl, script_tag, note in RTL_MUTATIONS:
            original = (work / target).read_text(encoding="utf-8")
            if needle not in original:
                check("mutation_%s_applicable" % tag, False, "锚点缺失 %s" % target)
                continue
            (work / target).write_text(original.replace(needle, repl, 1),
                                       encoding="utf-8", newline="\n")
            script = MUTATION_SCRIPTS.get(script_tag,
                                          "formal_np7_exec_unit_dense.ys")
            rc, output = run_yosys((work / script).read_text(encoding="utf-8"),
                                   work, "mut_" + tag)
            verdict = formal_verdict(output)
            check("mutation_%s_caught" % tag, verdict == "counterexample",
                  "verdict=%s rc=%s note=%s" % (verdict, rc, note))
            out[tag] = {"file": target, "script": script, "verdict": verdict,
                        "note": note}
            (work / target).write_text(original, encoding="utf-8", newline="\n")
    finally:
        shutil.rmtree(str(work), ignore_errors=True)
    return out
GATE_READS = 0.45
GATE_OPS = 0.45
GATE_CYCLES = 0.25


def prepare_stimulus(fmt, lanes, seed, word_fmt=None):
    structures, sem, words, txns, bp = cosim.build_case(fmt, lanes, seed)
    if word_fmt and word_fmt != fmt:
        _, _, alt_words, _, _ = cosim.build_case(word_fmt, lanes, seed)
        words = alt_words
    return structures, sem, words, txns, bp


def write_stimulus(case_dir, words, txns, bp):
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "np7_cfg.hex").write_text(
        "".join("%05x\n" % word for word in words), encoding="ascii")
    (case_dir / "np7_txn.hex").write_text(
        "".join("%08x\n" % (group | (activity << 4) | (issue << 8) | (skip << 12))
                for group, activity, issue, skip in txns), encoding="ascii")
    (case_dir / "np7_bp.hex").write_text(
        "".join("%02x\n" % value for value in bp), encoding="ascii")


def sim_run(binary, label, lanes, seed, words, txns, bp, work,
            slots_per_word=2):
    case_dir = work / ("sim_%s_%d_%d" % (label, lanes, seed))
    write_stimulus(case_dir, words, txns, bp)
    done = subprocess.run([VVP, os.fspath(binary), "+NTXN=%d" % len(txns),
                           "+NWORD=%d" % len(words)], cwd=str(case_dir),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)
    out = done.stdout + done.stderr
    if done.returncode != 0 or "TB_FAIL" in out:
        check("sim_%s_runs" % label, False, "rc=%d %s" % (done.returncode,
                                                          out[:200]))
        return None
    rows, claimed = parse_rows(out)
    observed = observe(rows, accepted_issue_masks(rows, txns),
                       slots_per_word=slots_per_word)
    violations = reconstruct_violations(claimed, observed, label)
    if claimed["protocol_error"] or claimed["config_error"]:
        violations.append("%s 协议/配置错误 proto=%d cfg=%d"
                          % (label, claimed["protocol_error"],
                             claimed["config_error"]))
    if claimed["completed"] != len(txns):
        violations.append("%s 完成数 %d != 事务数 %d"
                          % (label, claimed["completed"], len(txns)))
    return {"label": label, "lanes": lanes, "seed": seed,
            "txns": len(txns), "claimed": claimed, "observed": observed,
            "violations": violations, "sums": result_sums(rows),
            "rows": len(rows)}


def compile_negative(neg, lanes, work):
    binary = work / ("neg%d_%d.out" % (neg, lanes))
    command = [IVERILOG, "-g2012", "-s", "tb", "-Ptb.LANES=%d" % lanes,
               "-Ptb.NEG=%d" % neg, "-o", os.fspath(binary)] + NEG_SOURCES
    done = subprocess.run(command, cwd=str(ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          check=False)
    if done.returncode != 0:
        raise AssertionError("负向控制编译失败 NEG=%d LANES=%d: %s%s"
                             % (neg, lanes, done.stdout, done.stderr))
    return binary

def run_ledger_matrix(work):
    results = {}
    for lanes in LANES_LIST:
        binaries = {fmt: cosim.compile_tb(fmt, lanes, work)
                    for fmt in (FORMAT_DENSE, FORMAT_SPARSE)}
        for seed in SEEDS:
            stim = {}
            for fmt in (FORMAT_DENSE, FORMAT_SPARSE):
                _st, _sem, words, txns, bp = prepare_stimulus(fmt, lanes, seed)
                stim[fmt] = (words, txns, bp)
                entry = sim_run(binaries[fmt], "%s_L%d_s%d" % (fmt, lanes, seed),
                                lanes, seed, words, txns, bp, work)
                if entry is None:
                    continue
                results["%s_L%d_s%d" % (fmt, lanes, seed)] = entry
                check("reconstruct_%s_L%d_s%d" % (fmt, lanes, seed),
                      not entry["violations"], "; ".join(entry["violations"])[:200])
            key_d = "dense_L%d_s%d" % (lanes, seed)
            key_s = "sparse_L%d_s%d" % (lanes, seed)
            if key_d in results and key_s in results:
                same = results[key_d]["sums"] == results[key_s]["sums"]
                check("bitexact_sums_L%d_s%d" % (lanes, seed), same,
                      "dense=%d sparse=%d done" % (len(results[key_d]["sums"]),
                                                   len(results[key_s]["sums"])))
    return results


def run_negative_controls(work, matrix):
    rejected = {}
    for lanes in (1, 4):
        neg_binaries = {0: compile_negative(0, lanes, work),
                        1: compile_negative(1, lanes, work)}
        for seed in (1, 3):
            _, _, sparse_txns_words, txns, bp = prepare_stimulus(
                FORMAT_SPARSE, lanes, seed)
            _, _, dense_words, _, _ = prepare_stimulus(FORMAT_DENSE, lanes, seed)
            cases = {
                "negA_read_all_then_gate": (neg_binaries[0], dense_words),
                "negB_mac_then_clear": (neg_binaries[1], sparse_txns_words),
            }
            gold_sums = matrix["sparse_L%d_s%d" % (lanes, seed)]["sums"]
            gold_dense = matrix["dense_L%d_s%d" % (lanes, seed)]["observed"]
            for name, (binary, words) in cases.items():
                key = "%s_L%d_s%d" % (name, lanes, seed)
                entry = sim_run(binary, key, lanes, seed, words, txns, bp, work)
                if entry is None:
                    continue
                rejected[key] = entry
                functional = entry["sums"] == gold_sums
                check("%s_functionally_identical" % key, functional,
                      "负向实现必须与 golden 逐笔同和，才能证明功能测试不足以拒绝")
                check("%s_rejected_by_reconstruction" % key,
                      bool(entry["violations"]),
                      "自报账本应无法由逐拍观测重建；violations=%d"
                      % len(entry["violations"]))
                obs = entry["observed"]
                fake_reads = reduction(gold_dense, obs, "group_read_requests")
                fake_ops = reduction(gold_dense, obs, "lane_ops_issued")
                fake_cycles = reduction(gold_dense, obs, "total_cycles")
                observed_gates_met = (fake_reads >= GATE_READS
                                      and fake_ops >= GATE_OPS
                                      and fake_cycles >= GATE_CYCLES)
                check("%s_rejected_by_gates" % key, not observed_gates_met,
                      "obs reads=%.1f%% ops=%.1f%% cycles=%.1f%% (任一未达门即拒绝)"
                      % (100 * fake_reads, 100 * fake_ops, 100 * fake_cycles))
                print("   %s viol=%d self=%s obs=%s" % (
                    key, len(entry["violations"]),
                    {k: entry["claimed"][k] for k in ("group_read_requests",
                                                      "lane_ops_issued",
                                                      "total_cycles")},
                    {k: obs[k] for k in ("group_read_requests",
                                         "lane_ops_issued", "total_cycles")}))
    return rejected

def run_leak_mutation():
    # TODO NP7.5 第 4 条：遗漏"零突触快速路径仍要推进泄放/阈值/时间状态"的 mutation，
    # 必须被 NP7.4 的三模型状态等价检查抓到（这里直接复用 run_model 作为判据）。
    import np7_three_model_integration_cosim as np74
    results = {}
    for model_id in np74.MODELS:
        setup = np74._model_setup(model_id)
        clean_problems, clean_payload = np74.run_model(setup)
        check("leak_control_model_clean_%s" % model_id, not clean_problems,
              "; ".join(clean_problems)[:200])
        mutant_problems, mutant_payload = np74.run_model(
            setup, skip_state_on_zero=True)
        check("leak_mutation_detected_%s" % model_id, bool(mutant_problems),
              "; ".join(mutant_problems)[:200])
        results[model_id] = {
            "samples": clean_payload.get("samples"),
            "clean_problems": list(clean_problems),
            "mutant_problems": list(mutant_problems),
            "mutant_cycle_reduction_max": mutant_payload.get(
                "max_cycle_reduction", clean_payload.get("max_cycle_reduction")),
        }
    return results

def compile_config_negative(fmt, lanes, work, sources=None):
    binary = work / ("cfgneg_%s_%d.out" % (fmt, lanes))
    command = [IVERILOG, "-g2012", "-s", "tb", "-Ptb.LANES=%d" % lanes,
               "-Ptb.SPARSE=%s" % ("1'b1" if fmt == FORMAT_SPARSE else "1'b0"),
               "-o", os.fspath(binary)] + (sources or CFGNEG_SOURCES)
    done = subprocess.run(command, cwd=str(ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          check=False)
    if done.returncode != 0:
        raise AssertionError("config-negative 编译失败 %s/%d: %s%s"
                             % (fmt, lanes, done.stdout, done.stderr))
    return binary


def vvp_cfgneg(binary, work, tag):
    case_dir = work / ("cfgneg_run_%s" % tag)
    case_dir.mkdir(parents=True, exist_ok=True)
    done = subprocess.run([VVP, os.fspath(binary)], cwd=str(case_dir),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)
    text = done.stdout + done.stderr
    lines = text.splitlines()
    summary = [l for l in lines if l.startswith("CFGNEG SUMMARY")]
    fails = [l for l in lines if "CFGNEG FAIL" in l]
    return {"rc": done.returncode, "summary": summary[0] if summary else "",
            "fail_checks": [l.split("check=")[-1].strip() for l in fails],
            "phases": [l for l in lines if l.startswith("CFGNEG PHASE")]}


def run_config_negative(work):
    # PR #6 评审意见 2：非法 CONFIG 字不得改变 RAM、错误必须锁存、合法字仍可执行。
    # 正向：两格式 x 两个 lane 数的四相位测试台必须 8/8 PASS。
    # 反向：把拒绝旁路成常 1 之后，同一测试台必须 FAIL（证明测试台有牙齿）。
    out = {"runs": {}, "bypass_mutation": {}}
    for fmt in (FORMAT_SPARSE, FORMAT_DENSE):
        for lanes in (1, 4):
            tag = "%s_L%d" % (fmt, lanes)
            entry = vvp_cfgneg(compile_config_negative(fmt, lanes, work),
                               work, tag)
            ok = (entry["rc"] == 0 and entry["summary"].endswith("RESULT=PASS")
                  and "FAILED=0" in entry["summary"] and not entry["fail_checks"]
                  and len(entry["phases"]) == 4)
            out["runs"][tag] = entry
            check("config_rejection_tb_%s" % tag, ok,
                  "%s fails=%s" % (entry["summary"][:150], entry["fail_checks"]))
    for fmt in (FORMAT_SPARSE, FORMAT_DENSE):
        target, needle, repl = CFGNEG_BYPASS[fmt]
        mut = work / ("cfgneg_mut_%s" % fmt)
        mut.mkdir(parents=True, exist_ok=True)
        for name in CFGNEG_SOURCES:
            shutil.copyfile(ROOT / name, mut / name)
        original = (mut / target).read_text(encoding="utf-8")
        if needle not in original:
            check("config_rejection_bypass_%s_anchor" % fmt, False,
                  "锚点缺失 " + target)
            continue
        (mut / target).write_text(original.replace(needle, repl, 1),
                                 encoding="utf-8", newline="\n")
        sources = [str(mut / name) for name in CFGNEG_SOURCES]
        entry = vvp_cfgneg(compile_config_negative(fmt, 4, mut, sources),
                           mut, "bypass_%s" % fmt)
        caught = (entry["summary"].endswith("RESULT=FAIL")
                  and bool(entry["fail_checks"]))
        out["bypass_mutation"][fmt] = {"file": target, "note": repl.strip(),
                                       "summary": entry["summary"],
                                       "fail_checks": entry["fail_checks"]}
        check("config_rejection_bypass_caught_%s" % fmt, caught,
              "%s fails=%s" % (entry["summary"][:150], entry["fail_checks"]))
    return out


TOOLS = {"yosys": YOSYS, "iverilog": IVERILOG, "vvp": VVP}


def tool_versions():
    versions = {}
    for name, path in TOOLS.items():
        flags = ["-V"] if name == "iverilog" else ["--version"]
        try:
            done = subprocess.run([path] + flags, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace",
                                  check=False, timeout=120)
            text = [line for line in (done.stdout + done.stderr).splitlines()
                    if line.strip()]
            versions[name] = text[0][:160] if text else "?"
        except OSError as error:
            versions[name] = "missing: %s" % error
    iv = versions.get("iverilog", "")
    vvp = versions.get("vvp", "")
    if iv and not vvp.startswith("Icarus"):
        # vvp 无版本开关，取同安装目录的 iverilog 版本行作为口径。
        versions["vvp"] = iv + " (same install)"
    return versions


def git_head():
    done = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          check=False)
    return done.stdout.strip() or "unknown"


def main(argv=None):
    stamp = {}
    formal = {}
    mutations = {}
    matrix = {}
    negatives = {}
    leak = {}
    cfgneg = {}
    with tempfile.TemporaryDirectory(prefix="np75_") as temp_dir:
        work = Path(temp_dir)
        formal = run_formal_suite()
        mutations = run_rtl_mutations()
        matrix = run_ledger_matrix(work)
        negatives = run_negative_controls(work, matrix)
        cfgneg = run_config_negative(work)
        leak = run_leak_mutation()
    observed = {}
    for lanes in LANES_LIST:
        key = "sparse_L%d_s1" % lanes
        dkey = "dense_L%d_s1" % lanes
        if key in matrix and dkey in matrix:
            base = matrix[dkey]["observed"]
            cand = matrix[key]["observed"]
            observed["lanes_%d" % lanes] = {
                "read_reduction": round(100 * reduction(
                    base, cand, "group_read_requests"), 2),
                "op_reduction": round(100 * reduction(
                    base, cand, "lane_ops_issued"), 2),
                "cycle_reduction": round(100 * reduction(
                    base, cand, "total_cycles"), 2),
            }
    report = {
        "schema": "np7-formal-mutations-v1",
        "git_head": git_head(),
        "tool_versions": tool_versions(),
        "formal": formal,
        "rtl_mutations": mutations,
        "ledger_matrix": {name: {"lanes": entry["lanes"], "seed": entry["seed"],
                                 "txns": entry["txns"],
                                 "violations": entry["violations"],
                                 "observed": entry["observed"],
                                 "claimed": entry["claimed"]}
                          for name, entry in sorted(matrix.items())},
        "negative_controls": {name: {"violations": entry["violations"],
                                     "sums_match_golden": entry["sums"] ==
                                     matrix["sparse_L%d_s%d" % (entry["lanes"],
                                                                entry["seed"])]["sums"],
                                     "observed": entry["observed"],
                                     "claimed": entry["claimed"]}
                              for name, entry in sorted(negatives.items())},
        "leak_mutation": leak,
        "config_rejection": cfgneg,
        "observed_random_traffic_reductions": observed,
        "checks": CHECKS,
        "problems": PROBLEMS,
    }
    out = ROOT / "artifacts" / "results"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "np7_formal_and_mutations.json"
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                 sort_keys=True) + "\n", encoding="utf-8")
    passed = sum(1 for c in CHECKS if c["ok"])
    print("NP7.5 形式=%d/%d 负向拒绝=%d 泄漏mutation=%d 问题数=%d 证据=%s"
          % (passed, len(CHECKS), len(negatives), len(leak), len(PROBLEMS),
             target.relative_to(ROOT)))
    for problem in PROBLEMS[:10]:
        print("  FAIL " + problem[:200])
    return 1 if PROBLEMS else 0


if __name__ == "__main__":
    sys.exit(main())

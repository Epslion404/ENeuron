# NP7 Vivado XSim 行为仿真回归（PR #6 评审意见 1 的可复现证据）。
#
# 对每个用例执行 xvlog -> xelab -> xsim，并在同一激励目录里用 Icarus 复跑同一个
# testbench，逐行比对两台仿真器的 CYC/LEDGER/CFGNEG 观测流：这就是"Vivado 仿真结果
# 与既有协同仿真证据同源"的机器判据。本脚本不做任何综合，不越 G3 停止门。
#
# 用法（不硬编码机器路径）：
#   set VIVADO_ROOT=C:/Xilinx/Vivado/2024.2
#   python run_np7_vivado_xsim.py --transactions 200
#   python run_np7_vivado_xsim.py --groups golden --lanes 1 4 --transactions 100
# 产物：
#   vivado_np7_xsim_reports/<case>/{xvlog.log,xelab.log,xsim.log,icarus.log}
#   vivado_np7_xsim_reports/commands.log         全部命令与退出码
#   vivado_np7_xsim_reports/signoff_summary.txt  人读摘要（每用例一行 PASS/FAIL）
#   artifacts/results/np7_vivado_xsim_summary.json 机读证据（进 NP7.6 清单）
#
# 参数注入方式：xelab.bat/xsim.bat 经 cmd 转发会把 NAME=VALUE 拆成两个参数，因此本
# runner 不用 --generic_top / --testplusarg，而是为每个用例生成一个只做参数覆盖的薄
# 封装模块 xsim_top（tb #(.LANES(4), .SPARSE(1'b1), .NTXN(200), .NWORD(20)) ...）。
# testbench 本体不改逻辑：plusarg 优先、实例参数其次、默认值兜底。

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import np7_shared_lane_cosim as cosim
from np7_shared_lane_oracle import FORMAT_DENSE, FORMAT_SPARSE

RTL = [ROOT / name for name in (
    "np7_weight_ram.sv", "np7_shared_synapse_lane.sv",
    "np7_exec_unit_dense.sv", "np7_exec_unit_sparse.sv")]
GOLDEN_TB = ROOT / "tb_np7_exec_unit.sv"
NEG_RTL = RTL + [ROOT / "np7_negative_controls.sv"]
NEG_TB = ROOT / "tb_np7_negative.sv"
CFG_TB = ROOT / "tb_np7_config_negative.sv"
REPORT_DIR = ROOT / "vivado_np7_xsim_reports"
SUMMARY_JSON = ROOT / "artifacts" / "results" / "np7_vivado_xsim_summary.json"
IVERILOG = os.environ.get("IVERILOG", "iverilog")
VVP = os.environ.get("VVP", "vvp")
SCHEMA = "np7-vivado-xsim-v1"
OBSERVED_PREFIX = ("CYC ", "LEDGER ", "CFGNEG ")
KEEP_CYC_EDGES = 40   # 提交进仓库的日志只保留首尾各这么多行 CYC，中间用 sha256 钉死


class StepFailure(Exception):
    pass


def canon(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sha256_text(text):
    return hashlib.sha256(canon(text).encode("utf-8")).hexdigest()


def sha256_file(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def git_output(*args):
    done = subprocess.run(["git", "-C", str(ROOT)] + list(args),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)
    return done.returncode, canon(done.stdout + done.stderr).strip()


def resolve_vivado_root(value):
    candidates = []
    if value:
        candidates.append(pathlib.Path(value))
    for env in ("VIVADO_ROOT", "XILINX_VIVADO"):
        if os.environ.get(env):
            candidates.append(pathlib.Path(os.environ[env]))
    found = shutil.which("xvlog")
    if found:
        candidates.append(pathlib.Path(found).resolve().parent.parent)
    for root in candidates:
        if (root / "bin" / "xvlog.bat").exists() or (root / "bin" / "xvlog").exists():
            return root
    raise StepFailure("找不到 Vivado：请设 --vivado-root 或 VIVADO_ROOT（试过 %s）"
                      % ", ".join(str(c) for c in candidates))


class Flow:
    # 包住 xvlog/xelab/xsim/iverilog/vvp，记录每一条命令与退出码。

    def __init__(self, vivado_root):
        self.root = pathlib.Path(vivado_root)
        self.commands = []

    def tool(self, name):
        for candidate in (self.root / "bin" / (name + ".bat"),
                          self.root / "bin" / name, shutil.which(name)):
            if candidate and pathlib.Path(candidate).exists():
                return pathlib.Path(candidate).as_posix()
        raise StepFailure("找不到 Vivado 工具 " + name)

    def step(self, label, argv, cwd, require=(), forbidden=()):
        argv = [str(item) for item in argv]
        completed = subprocess.run(argv, cwd=str(cwd), capture_output=True,
                                   text=True, encoding="utf-8", errors="replace",
                                   check=False, timeout=1800)
        output = (completed.stdout or "") + (completed.stderr or "")
        self.commands.append({"step": label, "command": " ".join(argv),
                              "exit_code": completed.returncode,
                              "cwd": pathlib.Path(cwd).as_posix()})
        if completed.returncode:
            raise StepFailure("%s 退出码 %d:\n%s" % (label, completed.returncode,
                                                     output[-2500:]))
        for marker in require:
            if marker not in output:
                raise StepFailure("%s 缺少判据 %r" % (label, marker))
        for marker in forbidden:
            if marker in output:
                raise StepFailure("%s 出现禁止标记 %r" % (label, marker))
        return output

    def version(self):
        with tempfile.TemporaryDirectory(prefix="np7xs_probe_") as probe:
            output = self.step("xvlog-version", [self.tool("xvlog"), "-version"],
                               pathlib.Path(probe))
        for line in output.splitlines():
            if line.startswith("Vivado Simulator"):
                return line.strip()
        return "unknown"
def write_stimulus(case_dir, words, txns, bp):
    (case_dir / "np7_cfg.hex").write_text(
        "".join("%05x\n" % word for word in words), encoding="ascii", newline="\n")
    (case_dir / "np7_txn.hex").write_text("".join(
        "%08x\n" % (group | (activity << 4) | (issue << 8) | (skip << 12))
        for group, activity, issue, skip in txns), encoding="ascii", newline="\n")
    (case_dir / "np7_bp.hex").write_text(
        "".join("%02x\n" % value for value in bp), encoding="ascii", newline="\n")


def wrapper_text(params):
    return canon("\n".join([
        "// 本文件由 run_np7_vivado_xsim.py 自动生成：只做参数覆盖，不含任何测试语义。",
        "`timescale 1ns/1ps",
        "module xsim_top;",
        "    tb #(%s) tb_i ();" % (", ".join(params)),
        "endmodule",
        ""]))


def truncate_log(text):
    # 逐拍流可能上千行；提交进仓库的日志保留首尾各 KEEP_CYC_EDGES 行 CYC 与全部非 CYC
    # 行，中间用一行标记给出被省略的行数与"完整观测流 sha256"，重跑 runner 可逐字节复核。
    lines = canon(text).splitlines()
    cyc = [i for i, line in enumerate(lines) if line.startswith("CYC ")]
    if len(cyc) <= 2 * KEEP_CYC_EDGES:
        return "\n".join(lines) + "\n"
    drop = set(cyc[KEEP_CYC_EDGES:len(cyc) - KEEP_CYC_EDGES])
    marker = ("[NP7_XSIM_OMITTED cyc_rows=%d of %d full_stream_sha256=%s]"
              % (len(drop), len(cyc),
                 sha256_text("\n".join(observed_lines(text)))))
    out = []
    replaced = False
    for i, line in enumerate(lines):
        if i in drop:
            if not replaced:
                out.append(marker)
                replaced = True
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def observed_lines(text):
    return [line.rstrip() for line in canon(text).splitlines()
            if line.startswith(OBSERVED_PREFIX)]


def sources_for(case):
    if case["kind"] == "golden":
        return RTL + [GOLDEN_TB]
    if case["kind"] == "negative":
        return NEG_RTL + [NEG_TB]
    return RTL + [CFG_TB]


def tb_params_for(case, words):
    if case["kind"] == "golden" or case["kind"] == "negative":
        base = [".LANES(%d)" % case["lanes"]]
        if case["kind"] == "golden":
            base.append(".SPARSE(1'b1)" if case["fmt"] == FORMAT_SPARSE
                        else ".SPARSE(1'b0)")
        else:
            base.append(".NEG(%d)" % case["neg"])
        base.append(".NTXN(%d)" % case["ntxn"])
        base.append(".NWORD(%d)" % len(words))
        return base
    return [".LANES(%d)" % case["lanes"],
            ".SPARSE(1'b1)" if case["fmt"] == FORMAT_SPARSE else ".SPARSE(1'b0)"]


def icarus_params(case):
    params = ["-Ptb.LANES=%d" % case["lanes"]]
    if case["kind"] == "golden" or case["kind"] == "cfgneg":
        params.append("-Ptb.SPARSE=%s" % ("1'b1" if case["fmt"] == FORMAT_SPARSE
                                          else "1'b0"))
    if case["kind"] == "negative":
        params.append("-Ptb.NEG=%d" % case["neg"])
    return params


def judge(case, xsim_text, icarus_text, words):
    problems = []
    xsim_rows = observed_lines(xsim_text)
    icarus_rows = observed_lines(icarus_text)
    if not xsim_rows:
        problems.append("xsim 没有任何观测行")
    if xsim_rows != icarus_rows:
        delta = next((i for i in range(max(len(xsim_rows), len(icarus_rows)))
                      if (xsim_rows[i:i + 1] or [None]) !=
                         (icarus_rows[i:i + 1] or [None])), -1)
        problems.append("xsim 与 Icarus 观测流不一致（首个差异行 %d：xsim=%r icarus=%r）"
                        % (delta, xsim_rows[delta:delta + 1],
                           icarus_rows[delta:delta + 1]))
    ledgers = [line for line in xsim_rows if line.startswith("LEDGER ")]
    if case["kind"] in ("golden", "negative"):
        if len(ledgers) != 1:
            problems.append("LEDGER 行数=%d" % len(ledgers))
        else:
            if "completed=%d" % case["ntxn"] not in ledgers[0]:
                problems.append("完成数不等于注入事务数：" + ledgers[0][-60:])
            if case["kind"] == "golden":
                if "proto=0" not in ledgers[0] or "cfgerr=0" not in ledgers[0]:
                    problems.append("golden 用例报告协议/配置错误：" + ledgers[0][-60:])
    if case["kind"] == "cfgneg":
        summaries = [line for line in xsim_rows
                     if line.startswith("CFGNEG SUMMARY")]
        fails = [line for line in xsim_rows if "CFGNEG FAIL" in line]
        if len(summaries) != 1 or "RESULT=PASS" not in summaries[0] or fails:
            problems.append("config-negative 未通过：%s fails=%d"
                            % (summaries[:1], len(fails)))
    return problems, {"cyc_rows": len([r for r in xsim_rows
                                       if r.startswith("CYC ")]),
                      "ledger": ledgers[0] if ledgers else "",
                      "summary": next((s for s in xsim_rows
                                       if s.startswith("CFGNEG SUMMARY")), ""),
                      "observed_rows": len(xsim_rows),
                      "observed_sha256": sha256_text("\n".join(xsim_rows)),
                      "icarus_observed_sha256": sha256_text("\n".join(icarus_rows))}


def run_case(flow, case, out_root):
    work = out_root / "work" / case["id"]
    if work.exists():
        shutil.rmtree(str(work), ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    logs_dir = out_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    words, txns, bp = (cosim_stimulus(case)
                       if case["kind"] in ("golden", "negative") else ([], [], []))
    stimulus = {}
    if words:
        write_stimulus(work, words, txns, bp)
        stimulus = {"cfg_words": len(words), "txns": len(txns),
                    "np7_cfg.hex": sha256_file(work / "np7_cfg.hex"),
                    "np7_txn.hex": sha256_file(work / "np7_txn.hex"),
                    "np7_bp.hex": sha256_file(work / "np7_bp.hex")}
    sources = sources_for(case)
    params = tb_params_for(case, words)
    top = work / "xsim_top.sv"
    top.write_text(wrapper_text(params), encoding="utf-8", newline="\n")
    paths = [path.as_posix() for path in sources] + [top.as_posix()]
    outputs = {}
    outputs["xvlog"] = flow.step("xvlog:" + case["id"],
                                 [flow.tool("xvlog"), "-sv"] + paths, work)
    outputs["xelab"] = flow.step("xelab:" + case["id"],
                                 [flow.tool("xelab"), "--relax", "--debug",
                                  "typical", "--snapshot", "np7sim",
                                  "work.xsim_top"], work)
    outputs["xsim"] = flow.step("xsim:" + case["id"],
                                [flow.tool("xsim"), "np7sim", "-R"], work)
    binary = work / "icarus.out"
    command = ([IVERILOG, "-g2012", "-s", "tb"] + icarus_params(case)
               + ["-o", binary.as_posix()] + [path.as_posix() for path in sources])
    outputs["iverilog"] = flow.step("iverilog:" + case["id"], command, ROOT)
    plus = (["+NTXN=%d" % len(txns), "+NWORD=%d" % len(words)] if words else [])
    outputs["icarus"] = flow.step("vvp:" + case["id"],
                                  [VVP, binary.as_posix()] + plus, work)
    problems, metrics = judge(case, outputs["xsim"], outputs["icarus"], words)
    sections = []
    for name in ("xvlog", "xelab", "xsim", "iverilog", "icarus"):
        body = (truncate_log(outputs[name]) if name in ("xsim", "icarus")
                else canon(outputs[name]))
        sections.append("#### %s (exit 0) ####\n%s" % (name, body))
    handle = logs_dir / (case["id"] + ".log")
    handle.write_text(canon("\n".join(sections)), encoding="utf-8", newline="\n")
    metrics["log_file"] = "logs/" + handle.name
    return {"status": "PASS" if not problems else "FAIL",
            "problems": problems, "metrics": metrics,
            "kind": case["kind"], "fmt": case["fmt"], "lanes": case["lanes"],
            "ntxn": case.get("ntxn", 0), "seed": case.get("seed", 0),
            "neg": case.get("neg", -1), "tb_params": params,
            "stimulus": stimulus,
            "logs": {handle.name: sha256_file(handle)},
            "compiled_sources": [path.relative_to(ROOT).as_posix()
                                 for path in sources] + ["work/%s/xsim_top.sv"
                                                         % case["id"]],
            "work_dir": "work/" + case["id"]}



def cosim_stimulus(case):
    # 与 np7_formal_and_mutations.prepare_stimulus 同一口径：位流取自 txn_fmt，
    # RAM 字取自 word_fmt（负向控制 negA 用 dense 字 + sparse 事务流）。
    _s, _sem, words, _t, _b = cosim.build_case(case["word_fmt"], case["lanes"],
                                               case["seed"])
    _s2, _sem2, _w2, txns, bp = cosim.build_case(case["txn_fmt"], case["lanes"],
                                                 case["seed"])
    ntxn = case["ntxn"]
    return words, txns[:ntxn], bp[:ntxn * 12 + 500]


def make_cases(groups, lanes_list, ntxn, seed):
    cases = []
    if "golden" in groups:
        for fmt in (FORMAT_SPARSE, FORMAT_DENSE):
            for lanes in lanes_list:
                cases.append({"id": "golden_%s_L%d" % (fmt, lanes),
                              "kind": "golden", "fmt": fmt, "txn_fmt": fmt,
                              "word_fmt": fmt, "lanes": lanes, "ntxn": ntxn,
                              "seed": seed})
    if "negative" in groups:
        for neg in (0, 1):
            for lanes in (1, 4):
                cases.append({"id": "neg%d_L%d" % (neg, lanes),
                              "kind": "negative", "fmt": FORMAT_SPARSE,
                              "txn_fmt": FORMAT_SPARSE,
                              "word_fmt": FORMAT_DENSE if neg == 0 else FORMAT_SPARSE,
                              "neg": neg, "lanes": lanes, "ntxn": ntxn,
                              "seed": seed})
    if "config" in groups:
        for fmt in (FORMAT_SPARSE, FORMAT_DENSE):
            for lanes in (1, 4):
                cases.append({"id": "cfgneg_%s_L%d" % (fmt, lanes),
                              "kind": "cfgneg", "fmt": fmt, "txn_fmt": fmt,
                              "word_fmt": fmt, "lanes": lanes, "ntxn": 0,
                              "seed": 0})
    return cases


def source_identity(cases):
    names = set()
    for case in cases:
        for path in sources_for(case):
            names.add(path.relative_to(ROOT).as_posix())
    names.add(pathlib.Path(__file__).name)
    out = {}
    for name in sorted(names):
        path = ROOT / name
        out[name] = sha256_file(path) if path.exists() else "missing"
    return out


def write_outputs(out_root, flow, report, started):
    commands = out_root / "commands.log"
    commands.write_text(canon("".join(
        "%s exit=%d cwd=%s :: %s\n" % (c["step"], c["exit_code"], c["cwd"],
                                        c["command"])
        for c in flow.commands)), encoding="utf-8", newline="\n")
    report["commands_log_sha256"] = sha256_file(commands)
    lines = ["NP7_VIVADO_XSIM_SIGNOFF schema=" + SCHEMA,
             "RESULT=" + report["overall_status"],
             "VIVADO_VERSION=" + report["vivado"]["version"],
             "VIVADO_ROOT=" + report["vivado"]["root"],
             "VERSION_NOTE=" + report["vivado"]["version_note"],
             "CODE_GIT_HEAD=" + report["code_git_head"],
             "RUNNER=" + report["runner"],
             "ICARUS=" + report["tools"]["iverilog_line"],
             "VVP=" + report["tools"]["vvp_line"],
             "CASES=%d PASS=%d FAIL=%d" % (
                 len(report["cases"]),
                 sum(1 for c in report["cases"].values() if c["status"] == "PASS"),
                 sum(1 for c in report["cases"].values() if c["status"] != "PASS")),
             "XSIM_VS_ICARUS_EQUAL=%d/%d" % (
                 sum(1 for c in report["cases"].values()
                     if c["metrics"].get("observed_sha256") ==
                     c["metrics"].get("icarus_observed_sha256")),
                 len(report["cases"])),
             "SOURCE_BYTES"]
    for name, digest in sorted(report["source_sha256"].items()):
        lines.append("  %s %s" % (digest, name))
    for case_id, entry in sorted(report["cases"].items()):
        metrics = entry["metrics"]
        lines.append("CASE %s %s kind=%s fmt=%s lanes=%d ntxn=%d rows=%d "
                     "observed_sha256=%s icarus_sha256=%s logs=%s%s"
                     % (case_id, entry["status"], entry["kind"], entry["fmt"],
                        entry["lanes"], entry["ntxn"], metrics.get("observed_rows", 0),
                        metrics.get("observed_sha256", "")[:16],
                        metrics.get("icarus_observed_sha256", "")[:16],
                        ",".join(sorted(metrics.get("log_sha256", {}))) or
                        ",".join("%s:%s" % (k, v[:8]) for k, v in
                                 sorted(entry.get("logs", {}).items())),
                         "" if entry["status"] == "PASS" else
                         " PROBLEMS=" + " | ".join(entry["problems"])[:300]))
    lines.append("DURATION_S=%.1f" % (time.time() - started))
    (out_root / "signoff_summary.txt").write_text(canon("\n".join(lines) + "\n"),
                                                  encoding="utf-8", newline="\n")


def tool_lines():
    out = {}
    for name, path in (("iverilog", IVERILOG), ("vvp", VVP)):
        try:
            done = subprocess.run([path, "-V"], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", check=False,
                                  timeout=120)
            text = (done.stdout + done.stderr).strip().splitlines()
            out[name.lower() + "_line"] = (text[0] if text else "?")[:160]
        except OSError as error:
            out[name.lower() + "_line"] = "missing: %s" % error
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vivado-root", default=None)
    parser.add_argument("--transactions", type=int, default=120)
    parser.add_argument("--lanes", nargs="+", type=int, default=[1, 2, 4, 8])
    parser.add_argument("--groups", nargs="+",
                        default=["golden", "negative", "config"])
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", default=str(REPORT_DIR))
    parser.add_argument("--json-out", default=str(SUMMARY_JSON))
    args = parser.parse_args(argv)
    started = time.time()
    root = resolve_vivado_root(args.vivado_root)
    flow = Flow(root)
    version = flow.version()
    out_root = pathlib.Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    cases = make_cases(args.groups, args.lanes, args.transactions, args.seed)
    entries = {}
    for case in cases:
        try:
            entry = run_case(flow, case, out_root)
        except StepFailure as error:
            entry = {"status": "FAIL", "problems": [str(error)], "metrics": {},
                     "kind": case["kind"], "fmt": case["fmt"],
                     "lanes": case["lanes"], "ntxn": case.get("ntxn", 0),
                     "seed": case.get("seed", 0), "neg": case.get("neg", -1),
                     "tb_params": [], "stimulus": {}, "logs": {},
                     "case_dir": case["id"]}
        except (OSError, subprocess.SubprocessError) as error:
            entry = {"status": "FAIL", "problems": ["工具异常 %s" % error],
                     "metrics": {}, "kind": case["kind"], "fmt": case["fmt"],
                     "lanes": case["lanes"], "ntxn": case.get("ntxn", 0),
                     "seed": case.get("seed", 0), "neg": case.get("neg", -1),
                     "tb_params": [], "stimulus": {}, "logs": {},
                     "case_dir": case["id"]}
        entries[case["id"]] = entry
        print("%-24s %s rows=%s %s" % (case["id"], entry["status"],
                                       entry["metrics"].get("observed_rows", 0),
                                       "; ".join(entry["problems"])[:160]),
              flush=True)
    problems = sorted("%s: %s" % (name, text)
                      for name, entry in sorted(entries.items())
                      for text in entry["problems"])
    report = {
        "schema": SCHEMA,
        "overall_status": "PASS" if not problems else "FAIL",
        "runner": pathlib.Path(__file__).name,
        "vivado": {"root": root.as_posix(), "version": version,
                   "version_note": ("证据只绑定本机 Vivado 版本，不外推到评审者使用的 "
                                    "2024.1（NP6 决策 9 同口径）")},
        "tools": tool_lines(),
        "code_git_head": git_head_text(),
        "worktree_dirty": [line for line in git_status_porcelain_text()
                           if line.endswith((".sv", ".py", ".ys", ".tcl"))],
        "transactions_per_case": args.transactions,
        "seed": args.seed,
        "groups": list(args.groups),
        "source_sha256": source_identity(cases),
        "cases": entries,
        "problems": problems,
    }
    write_outputs(out_root, flow, report, started)
    json_path = pathlib.Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                    sort_keys=True) + "\n",
                         encoding="utf-8", newline="\n")
    print("NP7_XSIM_SUMMARY cases=%d problems=%d overall=%s json=%s"
          % (len(entries), len(problems), report["overall_status"],
             json_path))
    return 0 if report["overall_status"] == "PASS" else 1


def git_head_text():
    return git_output("rev-parse", "HEAD")[1] or "unknown"


def git_status_porcelain_text():
    return git_output("status", "--porcelain")[1].splitlines()


if __name__ == "__main__":
    sys.exit(main())
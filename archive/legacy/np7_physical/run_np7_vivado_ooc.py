# -*- coding: utf-8 -*-
"""NP7.7：共享突触执行单元的 Vivado OOC 综合+实现驱动（8 配置）。

冻结口径（PR #6 评论 5498372499 决定 8 + TODO NP7.7）：
  * 器件 xc7z020clg400-1、100 MHz、out_of_context；
  * dense 与 sparse 两个顶层各扫 1/2/4/8 lane，共 8 个配置；
  * 每份证据绑定准确 Vivado 版本 / SW Build / 执行机，不跨版本外推；
  * 100 MHz 不满足的配置不得用软件周期收益补偿（本脚本只如实记录 WNS/WHS）。

本脚本不判门、不改任何 RTL：它生成逐配置顶层、跑 Vivado、解析报告并写出
`artifacts/results/np7_vivado_ooc_summary.json`。判定由只读的
`verify_np7_physical_cost.py` 完成。
"""
import argparse
import concurrent.futures
import hashlib
import io
import json
import os
import pathlib
import platform
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
RTL_SOURCES = ("np7_weight_ram.sv", "np7_shared_synapse_lane.sv",
               "np7_exec_unit_dense.sv", "np7_exec_unit_sparse.sv")
TCL = ROOT / "vivado_np7_ooc_synth.tcl"
LANES = (1, 2, 4, 8)
FORMATS = ("sparse", "dense")
PART = "xc7z020clg400-1"
CLOCK_MHZ = "100.000"
SUMMARY_JSON = ROOT / "artifacts" / "results" / "np7_vivado_ooc_summary.json"
SCHEMA = "np7-vivado-ooc-v1"


def canon(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sha256_file(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(canon(handle.read().decode("utf-8", "replace"))
                              .encode("utf-8")).hexdigest()


def module_ports(source):
    # 从 RTL 顶层的 ANSI 端口表里取端口，保证封装与实现逐口一致（不手抄）。
    text = canon(io.open(source, encoding="utf-8").read())
    start = text.index(") (")
    end = text.index("\n);", start)
    ports = []
    pattern = re.compile(r"^\s*(input|output)\s+logic\s+(signed\s+)?(\[[^\]]+\]\s+)?"
                         r"(\w+)\s*,?\s*$")
    for line in text[start + 3:end].splitlines():
        found = pattern.match(line)
        if not found:
            if line.strip():
                raise AssertionError("无法解析端口行: %r (%s)" % (line, source.name))
            continue
        ports.append({"dir": found.group(1), "signed": bool(found.group(2)),
                      "range": (found.group(3) or "").strip(),
                      "name": found.group(4)})
    if len(ports) < 30:
        raise AssertionError("端口数异常 %d (%s)" % (len(ports), source.name))
    return ports


def wrapper_text(fmt, lanes, ports):
    top = "np7_ooc_%s_L%d" % (fmt, lanes)
    lines = ["// 由 run_np7_vivado_ooc.py 自动生成的 NP7.7 OOC 顶层封装。",
             "// 作用只有两个：把 LANES 参数钉成常量、把全部端口引出到顶层，",
             "// 以免综合把未连接逻辑优化掉；不含任何测试或协议语义。",
             "`timescale 1ns/1ps",
             "module %s (" % top]
    for index, port in enumerate(ports):
        comma = "," if index + 1 < len(ports) else ""
        decl = "    %-6s logic %s%s%s%s" % (port["dir"],
                                           "signed " if port["signed"] else "",
                                           port["range"] + " " if port["range"] else "",
                                           port["name"], comma)
        lines.append(decl.rstrip())
    lines.append(");")
    lines.append("    np7_exec_unit_%s #(.LANES(%d)) dut (" % (fmt, lanes))
    for index, port in enumerate(ports):
        comma = "," if index + 1 < len(ports) else ""
        lines.append("        .%s(%s)%s" % (port["name"], port["name"], comma))
    lines.append("    );")
    lines.append("endmodule")
    return top, "\n".join(lines) + "\n"


def resolve_vivado_root(argument):
    candidates = []
    if argument:
        candidates.append(pathlib.Path(argument))
    if os.environ.get("VIVADO_ROOT"):
        candidates.append(pathlib.Path(os.environ["VIVADO_ROOT"]))
    found = None
    try:
        found = subprocess.run(["where", "vivado"], capture_output=True, text=True,
                               check=False).stdout.strip().splitlines()
    except OSError:
        found = []
    if found:
        candidates.append(pathlib.Path(found[0]).resolve().parent.parent)
    for root in candidates:
        if (root / "bin" / "vivado.bat").exists() or (root / "bin" / "vivado").exists():
            return root
    raise SystemExit("找不到 Vivado：请给 --vivado-root 或设 VIVADO_ROOT")


def vivado_binary(root):
    candidate = root / "bin" / "vivado.bat"
    return candidate if candidate.exists() else root / "bin" / "vivado"


def probe_version(root):
    try:
        done = subprocess.run([str(vivado_binary(root)), "-version"],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", check=False, timeout=900)
    except (OSError, subprocess.SubprocessError) as error:
        return "unknown", "unknown"
    text = (done.stdout or "") + (done.stderr or "")
    version = next((line.strip() for line in text.splitlines()
                    if line.lower().startswith("vivado v")), "unknown")
    build = re.search(r"SW Build (\d+)", text)
    return version, ("SW Build " + build.group(1)) if build else "unknown"


def git_head():
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def run_one(binary, head, config, keep_logs):
    out_dir = ROOT / ("vivado_np7_ooc_%s_L%d_reports" % (config["fmt"],
                                                          config["lanes"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    wrapper = out_dir / (config["top"] + ".sv")
    io.open(str(wrapper), "w", encoding="utf-8", newline="\n").write(
        config["source"])
    command = [str(binary), "-mode", "batch", "-notrace", "-nojournal",
               "-source", str(TCL), "-tclargs", head, str(wrapper),
               config["top"], str(out_dir), config["fmt"],
               str(config["lanes"]), config["sw_build"], config["host"]]
    started = time.time()
    try:
        done = subprocess.run(command, cwd=str(out_dir), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              check=False, timeout=7200)
        code, text = done.returncode, (done.stdout or "") + (done.stderr or "")
    except (OSError, subprocess.SubprocessError) as error:
        code, text = 124, "工具异常 %s" % error
    summary_path = out_dir / "signoff_summary.txt"
    fields = {}
    if summary_path.exists():
        for line in summary_path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                fields[key.strip()] = value.strip()
    reports = {}
    for name in ("utilization_synth.rpt", "timing_synth.rpt", "drc_synth.rpt",
                 "utilization_impl.rpt", "timing_impl.rpt", "drc_impl.rpt",
                 "power_impl.rpt", "route_status_impl.rpt",
                 "signoff_summary.txt"):
        path = out_dir / name
        reports[name] = sha256_file(path) if path.exists() else "missing"
    routed = ("VIVADO_NP7_ROUTED" in text and code == 0
              and fields.get("RESULT") == "ROUTED")
    entry = {"config": "%s/L%d" % (config["fmt"], config["lanes"]),
             "top": config["top"], "fmt": config["fmt"], "lanes": config["lanes"],
             "status": "PASS" if routed else "FAIL", "exit_code": code,
             "elapsed_s": round(time.time() - started, 1),
             "wrapper": wrapper.relative_to(ROOT).as_posix(),
             "wrapper_sha256": sha256_file(wrapper),
             "report_dir": out_dir.name, "reports_sha256": reports,
             "summary": fields,
             "command": " ".join(command),
             "log_tail": text[-1500:]}
    if not routed:
        entry["problems"] = ["vivado rc=%d RESULT=%s" % (code, fields.get("RESULT"))]
    print("%-14s %s rc=%d lut=%s ff=%s bram36=%s dsp=%s wns=%s whs=%s"
          % (entry["config"], entry["status"], code, fields.get("LUT"),
             fields.get("FF"), fields.get("BRAM36"), fields.get("DSP"),
             fields.get("WNS_NS"), fields.get("WHS_NS")), flush=True)
    return entry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vivado-root", default=None)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--keep-logs", action="store_true")
    args = parser.parse_args(argv)
    root = resolve_vivado_root(args.vivado_root)
    binary = vivado_binary(root)
    version, sw_build = probe_version(root)
    host = platform.node()
    head = git_head()
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                           capture_output=True, text=True).stdout.splitlines()
    # 报告目录里的东西是本次运行的产物（含自动生成的 OOC 封装），不算"代码偏离"；
    # 其它任何 .sv/.py/.ys/.tcl 游离改动都会让证据作废。
    dirty_code = [line for line in dirty
                  if line.rstrip().endswith((".sv", ".py", ".ys", ".tcl"))
                  and "/vivado_np7_ooc_" not in (line.split()[-1] if line.split()
                                                 else "")]
    ports = module_ports(ROOT / "np7_exec_unit_sparse.sv")
    dense_ports = module_ports(ROOT / "np7_exec_unit_dense.sv")
    if [(p["dir"], p["signed"], p["range"], p["name"]) for p in ports] != \
            [(p["dir"], p["signed"], p["range"], p["name"]) for p in dense_ports]:
        raise SystemExit("dense 与 sparse 顶层端口表不一致，拒绝继续（NP7 合同要求同一接口）")
    configs = []
    for fmt in FORMATS:
        for lanes in LANES:
            top, source = wrapper_text(fmt, lanes, ports)
            configs.append({"fmt": fmt, "lanes": lanes, "top": top,
                            "source": source, "sw_build": sw_build, "host": host})
    started = time.time()
    entries = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(run_one, binary, head, config, args.keep_logs)
                   for config in configs]
        for future in concurrent.futures.as_completed(futures):
            entry = future.result()
            entries[entry["config"]] = entry
    problems = sorted("%s: %s" % (name, entry["problems"][0])
                      for name, entry in sorted(entries.items())
                      if entry.get("problems"))
    report = {
        "schema": SCHEMA,
        "overall_status": "PASS" if not problems and not dirty_code else "FAIL",
        "part": PART, "clock_mhz": CLOCK_MHZ, "jobs": args.jobs,
        "vivado": {"root": root.as_posix(), "version": version,
                   "sw_build": sw_build, "host": host,
                   "machine": "%s %s %s" % (platform.system(), platform.release(),
                                            platform.machine()),
                   "python": sys.version.split()[0],
                   "version_note": ("证据只绑定本机 Vivado 版本；评审者若用 2024.1 "
                                    "需自行复跑，不跨版本外推（决定 8）")},
        "rtl_sources": {name.relative_to(ROOT).as_posix(): sha256_file(name)
                        for name in (ROOT / item for item in RTL_SOURCES)},
        "tcl": {"runner": TCL.name, "sha256": sha256_file(TCL)},
        "code_git_head": head,
        "worktree_dirty": dirty_code,
        "configs": entries,
        "elapsed_s": round(time.time() - started, 1),
        "problems": problems,
    }
    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    io.open(str(SUMMARY_JSON), "w", encoding="utf-8", newline="\n").write(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print("NP7_OOC_SUMMARY configs=%d problems=%d overall=%s json=%s"
          % (len(entries), len(problems), report["overall_status"], SUMMARY_JSON))
    if dirty_code:
        print("NP7_OOC_WARN 代码工作树不干净：" + ",".join(dirty_code)[:200])
    return 0 if report["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

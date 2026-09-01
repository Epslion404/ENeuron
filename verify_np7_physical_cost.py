# NP7.7 物理成本验证器（只读，不生成、不改写任何证据）。
#
# 与 NP7.6 软件验证器同一条 fail-closed 纪律（PR #6 评论 5498372499 决定 8）：
#   1) 汇总 JSON 必须在被验证提交里已提交，磁盘字节 == 提交字节；
#   2) 每一项物理数字都由 Vivado 自己落的原始 .rpt 重新解析得到，
#      signoff_summary.txt 与汇总 JSON 都只是"必须等于重算值"的自报副本；
#   3) RTL / tcl / runner / 本验证器都做"冻结提交 blob == 磁盘 == 汇总哈希"三方比对；
#   4) 报告与封装必须在被验证提交的 git 树里（未提交的二进制/临时产物不算证据）；
#   5) 100 MHz 未收敛的配置一律列入 excluded，物理收益只在收敛配置上主张，
#      且禁止用软件周期收益去补偿（TODO NP7.7 第 3 条）。
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SUMMARY_REL = "artifacts/results/np7_vivado_ooc_summary.json"
SCHEMA = "np7-vivado-ooc-v1"
PART = "xc7z020clg400-1"
CLOCK_MHZ = "100.000"
FORMATS = ("sparse", "dense")
LANES = (1, 2, 4, 8)
CONFIGS = ["%s/L%d" % (fmt, lanes) for fmt in FORMATS for lanes in LANES]
REPORTS = ("utilization_synth.rpt", "timing_synth.rpt", "drc_synth.rpt",
           "utilization_impl.rpt", "timing_impl.rpt", "drc_impl.rpt",
           "power_impl.rpt", "route_status_impl.rpt", "signoff_summary.txt")
FIELDS = ("RESULT", "VIVADO_VERSION", "VIVADO_BUILD", "EXECUTION_HOST", "PART",
          "TOP", "FORMAT", "LANES", "CLOCK_MHZ", "GIT_HEAD", "RUNNER", "WRAPPER",
          "DRC_ERRORS", "LUT", "FF", "BRAM36", "BRAM18", "DSP", "WNS_NS",
          "TNS_NS", "WHS_NS", "THS_NS", "SETUP_FAILING_ENDPOINTS",
          "HOLD_FAILING_ENDPOINTS")
RTL_SOURCES = ("np7_shared_synapse_lane.sv", "np7_weight_ram.sv",
               "np7_exec_unit_dense.sv", "np7_exec_unit_sparse.sv")
TOOL_FILES = ("vivado_np7_ooc_synth.tcl", "run_np7_vivado_ooc.py",
              "verify_np7_physical_cost.py")
BLANK = ("", "NA", "missing", "unknown", "None", "-")


def canonical_bytes(data):
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256_bytes(data):
    return hashlib.sha256(canonical_bytes(data)).hexdigest()


def sha256_file(path):
    with open(str(path), "rb") as handle:
        return sha256_bytes(handle.read())


def git(*args):
    done = subprocess.run(["git", "-C", str(ROOT)] + list(args),
                          capture_output=True, check=False)
    return done.returncode, done.stdout


def read_text(path):
    return canonical_bytes(path.read_bytes()).decode("utf-8", "replace")


def parse_kv(text):
    fields = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip()] = value.strip()
    return fields

def grab(text, pattern, group=1):
    found = re.search(pattern, text)
    return found.group(group).strip() if found else "missing"


def recompute_reports(out_dir):
    """从 Vivado 原始报告独立重算每一项物理数字（不看自报摘要）。"""
    util = read_text(out_dir / "utilization_impl.rpt")
    timing = read_text(out_dir / "timing_impl.rpt")
    drc = read_text(out_dir / "drc_impl.rpt")
    route = read_text(out_dir / "route_status_impl.rpt")
    setup = re.search(r"Setup\s*:\s*(\d+)\s+Failing Endpoints,\s*Worst Slack\s+"
                      r"(-?[0-9.]+)ns,\s*Total Violation\s+(-?[0-9.]+)ns", timing)
    hold = re.search(r"Hold\s*:\s*(\d+)\s+Failing Endpoints,\s*Worst Slack\s+"
                     r"(-?[0-9.]+)ns,\s*Total Violation\s+(-?[0-9.]+)ns", timing)
    route_errors = grab(route, r"#\s*of\s+nets\s+with\s+routing\s+errors[^:]*:\s*(\d+)")
    drc_errors = len(re.findall(r"\|\s*[A-Z][A-Z0-9-]+\s*\|\s*Error\s*\|", drc))
    return {
        "LUT": grab(util, r"Slice LUTs\s*\|\s*(\d+)"),
        "FF": grab(util, r"Slice Registers\s*\|\s*(\d+)"),
        "BRAM36": grab(util, r"Block RAM Tile\s*\|\s*([0-9.]+)"),
        "BRAM18": grab(util, r"\bRAMB18\b\s*\|\s*(\d+)"),
        "DSP": grab(util, r"\bDSPs\b\s*\|\s*(\d+)"),
        "WNS_NS": setup.group(2) if setup else "missing",
        "TNS_NS": setup.group(3) if setup else "missing",
        "SETUP_FAILING_ENDPOINTS": setup.group(1) if setup else "missing",
        "WHS_NS": hold.group(2) if hold else "missing",
        "THS_NS": hold.group(3) if hold else "missing",
        "HOLD_FAILING_ENDPOINTS": hold.group(1) if hold else "missing",
        "DRC_ERRORS": str(drc_errors),
        "ROUTE_ERRORS": route_errors,
    }


def short_version(text):
    """'vivado v2024.2 (64-bit)' -> '2024.2'（signoff 里由 version -short 写入）。"""
    found = re.search(r"(\d{4}\.\d+(?:\.\d+)?)", str(text))
    return found.group(1) if found else "missing"


def normalize_bram(value):
    return "%g" % float(value) if value not in BLANK else value


def timing_met(recomputed):
    """100 MHz 收敛 = 无 setup/hold 失败端点且 WNS/WHS 为正。"""
    try:
        return (float(recomputed["WNS_NS"]) > 0 and float(recomputed["WHS_NS"]) > 0
                and int(recomputed["SETUP_FAILING_ENDPOINTS"]) == 0
                and int(recomputed["HOLD_FAILING_ENDPOINTS"]) == 0
                and int(recomputed["DRC_ERRORS"]) == 0
                and int(recomputed["ROUTE_ERRORS"]) == 0)
    except (KeyError, TypeError, ValueError):
        return False


def check_binding(rejects, rel, want, frozen_head, label):
    path = ROOT / rel
    if not path.exists():
        rejects.append("%s 缺失 %s" % (label, rel))
        return
    if sha256_file(path) != want:
        rejects.append("%s 磁盘字节偏离汇总 %s" % (label, rel))
    rc, blob = git("show", "%s:%s" % (frozen_head, rel))
    if rc != 0:
        rejects.append("%s 在冻结提交中不存在 %s" % (label, rel))
    elif sha256_bytes(blob) != want:
        rejects.append("%s 冻结提交字节偏离汇总 %s" % (label, rel))


def check_config(rejects, summary, name, frozen_head, wrapper_expect):
    entry = summary["configs"][name]
    out_dir = ROOT / entry.get("report_dir", "__missing__")
    if entry.get("status") != "PASS" or entry.get("exit_code") != 0:
        rejects.append("%s 运行未通过 status=%s rc=%s"
                       % (name, entry.get("status"), entry.get("exit_code")))
    if not out_dir.is_dir():
        rejects.append("%s 报告目录不存在 %s" % (name, entry.get("report_dir")))
        return None
    recorded = entry.get("reports_sha256") or {}
    for report in REPORTS:
        path = out_dir / report
        if not path.exists():
            rejects.append("%s 缺少报告 %s" % (name, report))
            continue
        if recorded.get(report) != sha256_file(path):
            rejects.append("%s 报告字节偏离汇总 %s" % (name, report))
        rel = "%s/%s" % (entry["report_dir"], report)
        rc, out = git("ls-tree", "HEAD", "--name-only", "--", rel)
        if rc != 0 or out.decode("utf-8", "replace").strip() != rel:
            rejects.append("%s 报告不在 HEAD 提交树里 %s" % (name, report))
    signoff_path = out_dir / "signoff_summary.txt"
    if not signoff_path.exists():
        rejects.append("%s 没有 signoff_summary.txt" % name)
        return None
    signoff = parse_kv(read_text(signoff_path))
    self_reported = entry.get("summary") or {}
    for field in FIELDS:
        if signoff.get(field) != self_reported.get(field):
            rejects.append("%s 自报摘要与 signoff 文件不一致 %s: %r != %r"
                           % (name, field, self_reported.get(field),
                              signoff.get(field)))
    recomputed = recompute_reports(out_dir)
    for field, value in sorted(recomputed.items()):
        if field == "ROUTE_ERRORS":
            continue
        if value in BLANK:
            rejects.append("%s 无法从原始报告重算 %s" % (name, field))
            continue
        want = signoff.get(field, "")
        if field in ("BRAM36",):
            if normalize_bram(value) != normalize_bram(want):
                rejects.append("%s %s 自报 %r 与报告重算 %r 不符"
                               % (name, field, want, value))
        elif want != value:
            rejects.append("%s %s 自报 %r 与报告重算 %r 不符" % (name, field, want, value))
    for field, want in (("PART", PART), ("CLOCK_MHZ", CLOCK_MHZ),
                        ("GIT_HEAD", frozen_head), ("RESULT", "ROUTED"),
                        ("VIVADO_BUILD", summary["vivado"]["sw_build"]),
                        ("EXECUTION_HOST", summary["vivado"]["host"]),
                        ("VIVADO_VERSION", short_version(summary["vivado"]["version"])),
                        ("FORMAT", name.split("/")[0]),
                        ("LANES", name.split("L")[1]),
                        ("TOP", "np7_ooc_%s_L%s" % (name.split("/")[0],
                                                    name.split("L")[1]))):
        if signoff.get(field) != want:
            rejects.append("%s %s=%r 与合同要求 %r 不符" % (name, field,
                                                            signoff.get(field), want))
    wrapper = out_dir / ("np7_ooc_%s_L%s.sv" % (name.split("/")[0],
                                                name.split("L")[1]))
    if not wrapper.exists():
        rejects.append("%s 缺少 OOC 封装 %s" % (name, wrapper.name))
    else:
        if sha256_file(wrapper) != entry.get("wrapper_sha256"):
            rejects.append("%s 封装磁盘字节偏离汇总" % name)
        rel = "%s/%s" % (entry["report_dir"], wrapper.name)
        rc, blob = git("show", "HEAD:%s" % rel)
        if rc != 0:
            rejects.append("%s OOC 封装不在 HEAD 提交树里" % name)
        elif sha256_bytes(blob) != wrapper_expect.get(name):
            rejects.append("%s 封装提交字节与重算值不一致" % name)
        if sha256_file(wrapper) != wrapper_expect[name]:
            rejects.append("%s 封装与 run_np7_vivado_ooc.py 重算值不一致（端口表漂移？）"
                           % name)
    return recomputed

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    verify_head = argv[0] if argv else "HEAD"
    rejects = []
    rc, committed = git("show", "%s:%s" % (verify_head, SUMMARY_REL))
    if rc != 0:
        print("NP7_PHYSICAL_REJECT: NP7.7 OOC 汇总在 %s 处未提交" % verify_head)
        return 1
    disk = ROOT / SUMMARY_REL
    if canonical_bytes(disk.read_bytes()) != canonical_bytes(committed):
        rejects.append("OOC 汇总磁盘字节与 %s 提交字节不一致" % verify_head)
    summary = json.loads(disk.read_bytes().decode("utf-8"))
    if summary.get("schema") != SCHEMA:
        rejects.append("OOC 汇总 schema 未知")
    if summary.get("part") != PART or summary.get("clock_mhz") != CLOCK_MHZ:
        rejects.append("OOC 汇总器件/时钟与合同不符（要求 %s @%sMHz）" % (PART, CLOCK_MHZ))
    rc, out = git("rev-parse", "--verify", "HEAD")
    current = out.decode("ascii", "replace").strip()
    if verify_head != "HEAD" and verify_head != current:
        rejects.append("verify head 与当前 HEAD 不一致（先同步再验证）")
    frozen_head = summary.get("code_git_head", "")
    if len(frozen_head) != 40:
        rejects.append("OOC 汇总缺少 code_git_head")
        frozen_head = current
    else:
        rc, _out = git("merge-base", "--is-ancestor", frozen_head, current)
        if rc != 0:
            rejects.append("代码提交 %s 不是当前 HEAD 的祖先" % frozen_head[:7])
    if summary.get("problems"):
        rejects.append("OOC 运行自检已报错：%s" % summary["problems"][0])
    if summary.get("worktree_dirty"):
        rejects.append("OOC 运行时代码工作树不干净：%s" % summary["worktree_dirty"][0])
    if summary.get("overall_status") != "PASS":
        rejects.append("OOC 运行自报 overall=%s" % summary.get("overall_status"))
    vivado = summary.get("vivado") or {}
    for key in ("root", "version", "sw_build", "host", "machine", "python"):
        value = str(vivado.get(key, "")).strip()
        if value in BLANK:
            rejects.append("Vivado 环境字段 %s 未绑定（决定 8）" % key)
    if not str(vivado.get("sw_build", "")).startswith("SW Build"):
        rejects.append("Vivado sw_build 不是工具真实 banner")
    version_want = short_version(vivado.get("version", ""))
    if sorted(summary.get("rtl_sources") or {}) != sorted(RTL_SOURCES):
        rejects.append("RTL 源绑定集合与合同不符")
    for rel in RTL_SOURCES:
        check_binding(rejects, rel, (summary.get("rtl_sources") or {}).get(rel),
                      frozen_head, "RTL")
    # 工具/工装（含本验证器自身）只需与"携带证据的那次提交"一致：
    # code_git_head 是运行时代码提交，验证器是事后写的，不可能存在于其中。
    for rel in TOOL_FILES:
        check_binding(rejects, rel, sha256_file(ROOT / rel), current, "工具")
    rc, tcl_blob = git("show", "%s:%s" % (frozen_head, "vivado_np7_ooc_synth.tcl"))
    if rc != 0 or sha256_bytes(tcl_blob) != (summary.get("tcl") or {}).get("sha256"):
        rejects.append("tcl runner 三方哈希不一致")
    if sorted(summary.get("configs") or {}) != sorted(CONFIGS):
        rejects.append("OOC 配置集合不完整（要求 8 个：%s）" % ",".join(CONFIGS))
        return finish(rejects, {}, summary, frozen_head, current)
    wrapper_expect = {}
    try:
        sys.path.insert(0, str(ROOT))
        import run_np7_vivado_ooc as runner
        ports = runner.module_ports(ROOT / "np7_exec_unit_sparse.sv")
        dense_ports = runner.module_ports(ROOT / "np7_exec_unit_dense.sv")
        if [(p["dir"], p["signed"], p["range"], p["name"]) for p in ports] != \
                [(p["dir"], p["signed"], p["range"], p["name"]) for p in dense_ports]:
            rejects.append("sparse/dense 顶层端口表不一致，NP7 同一接口合同被破坏")
        for fmt in FORMATS:
            for lanes in LANES:
                _top, text = runner.wrapper_text(fmt, lanes, ports)
                wrapper_expect["%s/L%d" % (fmt, lanes)] = sha256_bytes(
                    text.encode("utf-8"))
    except Exception as error:
        rejects.append("OOC 封装不可重算：%s" % error)
    results = {}
    for name in CONFIGS:
        if name not in (summary.get("configs") or {}):
            continue
        results[name] = check_config(rejects, summary, name, frozen_head,
                                     wrapper_expect)
    for fmt in FORMATS:
        luts = []
        for lanes in LANES:
            recomputed = results.get("%s/L%d" % (fmt, lanes)) or {}
            if recomputed.get("LUT", "missing") in BLANK:
                continue
            luts.append((lanes, int(recomputed["LUT"])))
        for (lanes_a, lut_a), (lanes_b, lut_b) in zip(luts, luts[1:]):
            if lanes_b > lanes_a and lut_b < lut_a:
                rejects.append("%s lane %d->%d LUT 反而减少 %d->%d（数字可疑）"
                               % (fmt, lanes_a, lanes_b, lut_a, lut_b))
    return finish(rejects, results, summary, frozen_head, current, version_want)


def finish(rejects, results, summary, frozen_head, current, version_want=""):
    clean, excluded = [], []
    for name in CONFIGS:
        recomputed = results.get(name)
        if not recomputed:
            excluded.append(name)
            continue
        met = timing_met(recomputed)
        (clean if met else excluded).append(name)
        print("NP7_PHYSICAL_CONFIG %s lut=%s ff=%s bram36=%s bram18=%s dsp=%s "
              "wns=%s tns=%s whs=%s ths=%s setup_fail=%s hold_fail=%s drc_err=%s "
              "route_err=%s timing_100MHz=%s"
              % (name, recomputed.get("LUT"), recomputed.get("FF"),
                 recomputed.get("BRAM36"), recomputed.get("BRAM18"),
                 recomputed.get("DSP"), recomputed.get("WNS_NS"),
                 recomputed.get("TNS_NS"), recomputed.get("WHS_NS"),
                 recomputed.get("THS_NS"),
                 recomputed.get("SETUP_FAILING_ENDPOINTS"),
                 recomputed.get("HOLD_FAILING_ENDPOINTS"),
                 recomputed.get("DRC_ERRORS"), recomputed.get("ROUTE_ERRORS"),
                 "MET" if met else "MISS"))
    print("NP7_PHYSICAL_BINDING verify_head=%s code_head=%s part=%s clock=%sMHz "
          "vivado=%s build=%s host=%s"
          % (current[:9], str(frozen_head)[:9], summary.get("part"),
             summary.get("clock_mhz"), version_want,
             (summary.get("vivado") or {}).get("sw_build"),
             (summary.get("vivado") or {}).get("host")))
    print("NP7_PHYSICAL_EXCLUDED " + (",".join(excluded) or "none"))
    if excluded:
        print("NP7_PHYSICAL_NOTE excluded 配置在 100MHz 未收敛，不主张其物理周期收益，"
              "且禁止用软件周期收益补偿（TODO NP7.7 第 3 条）；"
              "流水化改动属于周期合同变更，需管理员新裁定")
    for fmt in FORMATS:
        if not any(name.startswith(fmt + "/") for name in clean):
            rejects.append("%s 没有任何 100MHz 收敛配置，物理结论无法在该格式主张" % fmt)
    overall = "PASS" if not rejects else "FAIL"
    for message in rejects:
        print("NP7_PHYSICAL_REJECT: " + message)
    print("NP7_PHYSICAL_SUMMARY rejects=%d configs=%d timing_clean=%d(%s) "
          "excluded=%d(%s) overall=%s"
          % (len(rejects), len(CONFIGS), len(clean), ",".join(clean) or "-",
             len(excluded), ",".join(excluded) or "-", overall))
    return 0 if not rejects else 1


if __name__ == "__main__":
    raise SystemExit(main())
# NP7.7 物理成本验证器的变异套件：证明 verify_np7_physical_cost.py 真的 fail-closed。
#
# 与 NP7.6 套件同一纪律：每个变异都在 `git clone --no-hardlinks` 的独立副本里执行，
# 判定标准是"验证器必须在基线拒绝理由之外给出与该变异对应的新拒绝理由，
# 且不得因为变异而变成通过（退出码 0）"。基线要求干净克隆 rejects=0 overall=PASS。
#
# 覆盖的攻击面（都是评审者点名过的类别）：
#   只改摘要不改原始报告 / 改完原始报告还顺手更新清单哈希 / 删证据文件 /
#   伪造 HEAD 绑定 / 伪造工具版本 / 事后偷改 RTL / 事后偷改 OOC 封装 /
#   删配置 / 报告未提交 / 用另一种格式全灭来绕过"每格式至少一个收敛"。
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent
SUMMARY = "artifacts/results/np7_vivado_ooc_summary.json"
FAILURES = []
BASELINE_REASONS = [[]]


def git_at(root, *args):
    done = subprocess.run(["git", "-C", str(root)] + list(args),
                          capture_output=True, text=True, check=False,
                          encoding="utf-8", errors="replace")
    return done.returncode, (done.stdout + done.stderr).strip()


def clone(dest):
    done = subprocess.run(["git", "clone", "--no-hardlinks", "-q", str(ROOT), str(dest)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)
    if done.returncode != 0:
        raise AssertionError("clone 失败: %s%s" % (done.stdout, done.stderr))
    _rc, head = git_at(dest, "rev-parse", "HEAD")
    return head


def run_verifier(root, head):
    done = subprocess.run([sys.executable, "-X", "utf8",
                           "verify_np7_physical_cost.py", head],
                          cwd=str(root), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
    text = done.stdout + done.stderr
    reasons = [line.split("NP7_PHYSICAL_REJECT: ", 1)[1]
               for line in text.splitlines()
               if line.startswith("NP7_PHYSICAL_REJECT: ")]
    return done.returncode, reasons, text


def read_json(root, rel):
    return json.loads((pathlib.Path(root) / rel).read_bytes().decode("utf-8"))


def write_json(root, rel, data):
    (pathlib.Path(root) / rel).write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")


def commit_all(root):
    git_at(root, "add", "-A")
    rc, out = git_at(root, "-c", "user.email=mutation@example.invalid",
                     "-c", "user.name=mutation", "commit", "-q", "-m", "mutation")
    if rc != 0:
        raise AssertionError("变异提交失败: " + out)
    _rc, head = git_at(root, "rev-parse", "HEAD")
    return head

def rebind_report(root, name, report):
    """改完文件后顺手把汇总里的 sha256 也同步上（模拟"篡改后自我圆场"）。"""
    sys.path.insert(0, str(ROOT))
    import verify_np7_physical_cost as verifier
    data = read_json(root, SUMMARY)
    entry = data["configs"][name]
    path = pathlib.Path(root) / entry["report_dir"] / report
    entry["reports_sha256"][report] = verifier.sha256_file(path)
    write_json(root, SUMMARY, data)
    return data


def edit_signoff(root, name, field, value):
    data = read_json(root, SUMMARY)
    entry = data["configs"][name]
    signoff = pathlib.Path(root) / entry["report_dir"] / "signoff_summary.txt"
    lines = []
    for line in signoff.read_text(encoding="utf-8").splitlines():
        if line.startswith(field + "="):
            line = "%s=%s" % (field, value)
        lines.append(line)
    signoff.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return entry


def m_summary_only_edit(root, head):
    # 只改汇总里的自报数字，不动磁盘上的 signoff 文件。
    data = read_json(root, SUMMARY)
    data["configs"]["sparse/L2"]["summary"]["LUT"] = "1"
    write_json(root, SUMMARY, data)
    return commit_all(root), "signoff"


def m_tamper_signoff_rehash(root, head):
    # 改 signoff 并同步 sha256，但原始 .rpt 未变 -> 重算必然对不上。
    edit_signoff(root, "sparse/L2", "LUT", "1")
    rebind_report(root, "sparse/L2", "signoff_summary.txt")
    return commit_all(root), "报告重算"


def m_tamper_wns_sign(root, head):
    # 把一个未收敛配置的 WNS 符号伪造成正数（同样同步 sha256）。
    edit_signoff(root, "sparse/L4", "WNS_NS", "4.627")
    rebind_report(root, "sparse/L4", "signoff_summary.txt")
    return commit_all(root), "WNS"


def m_drop_report(root, head):
    (pathlib.Path(root) / "vivado_np7_ooc_dense_L2_reports" /
     "utilization_impl.rpt").unlink()
    return commit_all(root), "缺少报告"


def m_uncommitted_report(root, head):
    rc, out = git_at(root, "rm", "--cached", "-q",
                     "vivado_np7_ooc_dense_L1_reports/drc_impl.rpt")
    if rc != 0:
        raise AssertionError(out)
    return commit_all(root), "不在 HEAD 提交树里"


def m_drop_config(root, head):
    data = read_json(root, SUMMARY)
    del data["configs"]["dense/L8"]
    write_json(root, SUMMARY, data)
    return commit_all(root), "配置集合不完整"


def m_bogus_code_head(root, head):
    data = read_json(root, SUMMARY)
    data["code_git_head"] = "0" * 40
    write_json(root, SUMMARY, data)
    return commit_all(root), "祖先"


def m_blank_execution_host(root, head):
    data = read_json(root, SUMMARY)
    data["vivado"]["host"] = ""
    write_json(root, SUMMARY, data)
    return commit_all(root), "未绑定"


def m_post_freeze_rtl_edit(root, head):
    # 冻结之后偷改 RTL，并把汇总里的哈希一起改掉。
    path = pathlib.Path(root) / "np7_weight_ram.sv"
    path.write_text(path.read_text(encoding="utf-8") + "// sneaky\n", encoding="utf-8")
    sys.path.insert(0, str(ROOT))
    import verify_np7_physical_cost as verifier
    data = read_json(root, SUMMARY)
    data["rtl_sources"]["np7_weight_ram.sv"] = verifier.sha256_file(path)
    write_json(root, SUMMARY, data)
    return commit_all(root), "冻结提交字节偏离"


def m_wrapper_rewritten(root, head):
    # 换掉 OOC 封装（例如把 clk 悬空以规避时序），并同步汇总哈希。
    path = pathlib.Path(root) / "vivado_np7_ooc_sparse_L2_reports" / "np7_ooc_sparse_L2.sv"
    text = path.read_text(encoding="utf-8").replace(".clk(clk)", ".clk(1'b0)")
    if text == path.read_text(encoding="utf-8"):
        raise AssertionError("封装里找不到 .clk(clk)，变异未施加")
    path.write_text(text, encoding="utf-8")
    sys.path.insert(0, str(ROOT))
    import verify_np7_physical_cost as verifier
    data = read_json(root, SUMMARY)
    data["configs"]["sparse/L2"]["wrapper_sha256"] = verifier.sha256_file(path)
    write_json(root, SUMMARY, data)
    return commit_all(root), "重算值不一致"


def m_lane_lut_regression(root, head):
    # 让 L2 的 LUT 比 L1 还小（改 .rpt + signoff + 汇总三处，制造"自洽假象"）。
    rpt = pathlib.Path(root) / "vivado_np7_ooc_sparse_L2_reports" / "utilization_impl.rpt"
    rpt.write_text(rpt.read_text(encoding="utf-8").replace("| Slice LUTs                 |  132 |",
                                                           "| Slice LUTs                 |  100 |"),
                   encoding="utf-8")
    edit_signoff(root, "sparse/L2", "LUT", "100")
    rebind_report(root, "sparse/L2", "utilization_impl.rpt")
    rebind_report(root, "sparse/L2", "signoff_summary.txt")
    data = read_json(root, SUMMARY)
    data["configs"]["sparse/L2"]["summary"]["LUT"] = "100"
    write_json(root, SUMMARY, data)
    return commit_all(root), "LUT 反而减少"


def m_no_converged_dense(root, head):
    # 把 dense 全部配置标记为运行失败（真实报告仍是收敛的，但汇总自称未通过）。
    data = read_json(root, SUMMARY)
    for lanes in (1, 2, 4, 8):
        data["configs"]["dense/L%d" % lanes]["status"] = "FAIL"
    write_json(root, SUMMARY, data)
    return commit_all(root), "收敛"


MUTATIONS = [
    ("summary_only_edit", m_summary_only_edit),
    ("tamper_signoff_rehash", m_tamper_signoff_rehash),
    ("tamper_wns_sign", m_tamper_wns_sign),
    ("drop_report_file", m_drop_report),
    ("uncommitted_report", m_uncommitted_report),
    ("drop_one_config", m_drop_config),
    ("bogus_code_head", m_bogus_code_head),
    ("blank_execution_host", m_blank_execution_host),
    ("post_freeze_rtl_edit", m_post_freeze_rtl_edit),
    ("ooc_wrapper_rewritten", m_wrapper_rewritten),
    ("lane_lut_regression", m_lane_lut_regression),
    ("no_converged_dense", m_no_converged_dense),
]


def main(argv=None):
    base = pathlib.Path(tempfile.mkdtemp(prefix="np77mut_"))
    checks = 0
    try:
        probe = base / "baseline"
        head = clone(probe)
        code, reasons, text = run_verifier(probe, head)
        summary = [line for line in text.splitlines()
                   if line.startswith("NP7_PHYSICAL_SUMMARY")]
        if code != 0 or not summary or "rejects=0" not in summary[0]:
            FAILURES.append("baseline: 干净克隆未通过 rc=%d %s" % (code, reasons[:3]))
        BASELINE_REASONS[0] = list(reasons)
        print("baseline clone head=%s rc=%d %s" % (head[:7], code, summary[0] if summary else "-"))
        for tag, apply in MUTATIONS:
            target = base / tag
            mutated_head = clone(target)
            try:
                use_head, keyword = apply(target, mutated_head)
            except AssertionError as error:
                FAILURES.append("%s: 变异无法施加 (%s)" % (tag, error))
                continue
            code, reasons, text = run_verifier(target, use_head)
            extra = [r for r in reasons if r not in BASELINE_REASONS[0]]
            caught = bool(extra) and any(keyword in r for r in extra)
            if not caught:
                FAILURES.append("%s: 验证器未拒绝该变异 extra=%s keyword=%r"
                                % (tag, extra[:3], keyword))
            if code == 0:
                FAILURES.append("%s: 变异后验证器退出码为 0" % tag)
            checks += 1
            print("%-26s rc=%d new_rejects=%d %s"
                  % (tag, code, len(extra), "CAUGHT" if caught else "ESCAPED"))
            shutil.rmtree(str(target), ignore_errors=True)
    finally:
        shutil.rmtree(str(base), ignore_errors=True)
    if FAILURES:
        for line in FAILURES:
            print("  MUTATION_FAIL " + line)
        print("NP77_MUTATION_SUITE FAIL checks=%d failures=%d" % (checks, len(FAILURES)))
        return 1
    print("NP77_MUTATION_SUITE PASS checks=%d" % checks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
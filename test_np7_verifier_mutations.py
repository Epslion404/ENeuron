
# NP7.6 验证器变异套件：证明 verify_np7_software_cost.py 真的 fail-closed。
#
# 每个变异都在 `git clone --no-hardlinks` 的独立副本里执行（不污染工作树），
# 判定标准：验证器必须在基线拒绝理由之外，给出与该变异对应的新拒绝理由，
# 且不得因为变异而"变成通过"。基线本身允许因硬门未达标而非零退出。

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
MANIFEST = "artifacts/results/np7_software_cost_manifest.json"
FAILURES = []


def git_at(root, *args):
    done = subprocess.run(["git", "-C", str(root)] + list(args),
                          capture_output=True, text=True, check=False)
    return done.returncode, (done.stdout + done.stderr).strip()


def clone(dest):
    done = subprocess.run(["git", "clone", "--no-hardlinks", "-q", str(ROOT),
                           str(dest)], capture_output=True, text=True,
                          check=False)
    if done.returncode != 0:
        raise AssertionError("clone 失败: %s%s" % (done.stdout, done.stderr))
    _rc, head = git_at(dest, "rev-parse", "HEAD")
    return head


def run_verifier(root, head):
    done = subprocess.run([sys.executable, "verify_np7_software_cost.py", head],
                          cwd=str(root), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
    text = done.stdout + done.stderr
    reasons = [line.split("NP7_VERIFY_REJECT: ", 1)[1]
               for line in text.splitlines()
               if line.startswith("NP7_VERIFY_REJECT: ")]
    return done.returncode, reasons, text


def read_json(root, rel):
    return json.loads((pathlib.Path(root) / rel).read_bytes().decode("utf-8"))


def write_json(root, rel, data):
    (pathlib.Path(root) / rel).write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")


def touch(root, rel, marker):
    path = pathlib.Path(root) / rel
    path.write_text(path.read_text(encoding="utf-8") + marker, encoding="utf-8")


def rebind(root, rel):
    """把清单里某个文件的哈希改成当前磁盘值，模拟"改完还顺手更新清单"的攻击。"""
    sys.path.insert(0, str(ROOT))
    import verify_np7_software_cost as verifier
    manifest = read_json(root, MANIFEST)
    for group in ("input_files", "tool_files", "evidence_files"):
        if rel in manifest["bindings"].get(group, {}):
            manifest["bindings"][group][rel] = verifier.sha256_file(
                pathlib.Path(root) / rel)
    write_json(root, MANIFEST, manifest)


def commit_all(root):
    git_at(root, "add", "-A")
    rc, out = git_at(root, "-c", "user.email=mutation@example.invalid", "-c",
                     "user.name=mutation", "commit", "-q", "-m", "mutation")
    if rc != 0:
        raise AssertionError("变异提交失败: " + out)
    _rc, head = git_at(root, "rev-parse", "HEAD")
    return head

def m_missing_log(root, head):
    (pathlib.Path(root) / "artifacts/logs/np73_cosim.txt").unlink()
    return head, "缺失"


def m_tamper_gate_status(root, head):
    manifest = read_json(root, MANIFEST)
    manifest["gates"]["G3"]["status"] = "PASS"
    manifest["gates"]["G3"]["failures"] = []
    write_json(root, MANIFEST, manifest)
    return head, "重算"


def m_tamper_rtl_ledger(root, head):
    rel = "artifacts/results/np7_cosim_ledgers.json"
    data = read_json(root, rel)
    data["ledgers"][0]["observed"]["weight_values_fetched"] -= 2
    write_json(root, rel, data)
    return head, "claimed/observed"


def m_fake_cycle_gain(root, head):
    rel = "artifacts/results/np7_three_model_integration.json"
    data = read_json(root, rel)
    for model in data["models"].values():
        for lanes in model["ledgers"].values():
            sparse = lanes["sparse_format"]
            sparse["total_cycles"] = int(sparse["total_cycles"] * 0.6)
            sparse["cycles_per_logical_tick"] = (
                sparse["total_cycles"] / float(sparse["completed_groups"] * 4))
    write_json(root, rel, data)
    return head, "ledger identity"


def m_lower_threshold(root, head):
    path = pathlib.Path(root) / "verify_np7_software_cost.py"
    text = path.read_text(encoding="utf-8")
    assert "GATE_CYCLES = 0.25" in text
    path.write_text(text.replace("GATE_CYCLES = 0.25", "GATE_CYCLES = 0.20"),
                    encoding="utf-8", newline="\n")
    return head, "偏离清单"


def m_accept_negative_control(root, head):
    rel = "artifacts/results/np7_formal_and_mutations.json"
    data = read_json(root, rel)
    for entry in data["negative_controls"].values():
        entry["violations"] = []
    write_json(root, rel, data)
    return head, "negative control"


def m_weaken_formal_verdict(root, head):
    rel = "artifacts/results/np7_formal_and_mutations.json"
    data = read_json(root, rel)
    data["formal"]["sparse_protocol"]["verdict"] = "model"
    write_json(root, rel, data)
    return head, "formal"


def m_leak_escapes(root, head):
    rel = "artifacts/results/np7_formal_and_mutations.json"
    data = read_json(root, rel)
    data["leak_mutation"]["eneuron"]["mutant_problems"] = []
    write_json(root, rel, data)
    return head, "escaped state equivalence"


def m_tamper_frozen_accuracy(root, head):
    rel = "artifacts/results/local_prune_b21_results.json"
    data = read_json(root, rel)
    learned = data["models"]["eneuron"]["candidates"]["output_2of4"]["learned"]
    learned["balanced_accuracy"] = 0.5
    write_json(root, rel, data)
    return head, "冻结产物"


def m_post_freeze_rtl(root, head):
    touch(root, "np7_exec_unit_sparse.sv", "// 冻结后偷改，且同步更新清单哈希\n")
    rebind(root, "np7_exec_unit_sparse.sv")
    return commit_all(root), "冻结提交字节偏离清单"


def m_post_freeze_tool(root, head):
    touch(root, "verify_np7_software_cost.py", "# 冻结后偷改验证器\n")
    rebind(root, "verify_np7_software_cost.py")
    return commit_all(root), "冻结提交字节偏离清单"


def m_bogus_frozen_head(root, head):
    manifest = read_json(root, MANIFEST)
    manifest["frozen_git_head"] = "0" * 40
    write_json(root, MANIFEST, manifest)
    return head, "不是"


def m_integrity_not_empty(root, head):
    manifest = read_json(root, MANIFEST)
    manifest["integrity"] = ["生成时就已知的问题"]
    write_json(root, MANIFEST, manifest)
    return head, "证据自检"


MUTATIONS = [
    ("delete_run_log", m_missing_log),
    ("tamper_gate_status", m_tamper_gate_status),
    ("tamper_rtl_ledger", m_tamper_rtl_ledger),
    ("fake_cycle_gain", m_fake_cycle_gain),
    ("lower_gate_threshold", m_lower_threshold),
    ("accept_negative_control", m_accept_negative_control),
    ("weaken_formal_verdict", m_weaken_formal_verdict),
    ("leak_mutation_escapes", m_leak_escapes),
    ("tamper_frozen_accuracy", m_tamper_frozen_accuracy),
    ("post_freeze_rtl_rebind", m_post_freeze_rtl),
    ("post_freeze_tool_rebind", m_post_freeze_tool),
    ("bogus_frozen_head", m_bogus_frozen_head),
    ("manifest_integrity_flagged", m_integrity_not_empty),
]


def main(argv=None):
    base = pathlib.Path(tempfile.mkdtemp(prefix="np76mut_"))
    checks = 0
    try:
        probe = base / "baseline"
        head = clone(probe)
        code, reasons, text = run_verifier(probe, head)
        summary = [line for line in text.splitlines()
                   if line.startswith("NP7_VERIFY_SUMMARY")]
        if not summary or "rejects=0" not in summary[0]:
            FAILURES.append("baseline: 干净克隆仍有拒绝理由 %s" % reasons[:3])
        BASELINE_REASONS[0] = list(reasons)
        print("baseline clone head=%s rc=%d baseline_rejects=%d %s"
              % (head[:7], code, len(reasons), summary[0] if summary else "-"))
        for tag, apply in MUTATIONS:
            target = base / tag
            mutated_head = clone(target)
            try:
                use_head, keyword = apply(target, mutated_head)
            except AssertionError as error:
                FAILURES.append("%s: 变异无法施加 (%s)" % (tag, error))
                continue
            code, reasons, text = run_verifier(target, use_head)
            extra = [text_reason for text_reason in reasons
                     if text_reason not in BASELINE_REASONS[0]]
            caught = bool(extra) and any(keyword in text_reason for text_reason in extra)
            if not caught:
                FAILURES.append("%s: 验证器未拒绝该变异 extra=%s keyword=%r"
                                % (tag, extra[:3], keyword))
            if code == 0:
                FAILURES.append("%s: 变异后验证器退出码为 0" % tag)
            checks += 1
            print("%-28s rc=%d new_rejects=%d %s"
                  % (tag, code, len(extra), "CAUGHT" if caught else "ESCAPED"))
            shutil.rmtree(str(target), ignore_errors=True)
    finally:
        shutil.rmtree(str(base), ignore_errors=True)
    if FAILURES:
        for text in FAILURES:
            print("  MUTATION_FAIL " + text)
        print("MUTATION_SUITE FAIL checks=%d failures=%d" % (checks, len(FAILURES)))
        return 1
    print("MUTATION_SUITE PASS checks=%d" % checks)
    return 0


BASELINE_REASONS = [[]]

if __name__ == "__main__":
    sys.exit(main())

# NP7.6 证据清单生成器（一次性写入；验证器只读）。
#
# 与验证器的分工：本文件负责"在证据时点把字节钉死"，verify_np7_software_cost.py 负责
# "事后独立重算"。生成器同样 fail-closed：证据自检（integrity）非空即拒绝生成清单；
# 硬门未达标不阻止生成（那是要如实记录的结果，不是被隐藏的错误）。

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import verify_np7_software_cost as verifier

MANIFEST_REL = "artifacts/results/np7_software_cost_manifest.json"
TOOL_FILES = [
    "generate_np7_manifest.py",
    "verify_np7_software_cost.py",
    "test_np7_verifier_mutations.py",
]
INPUT_FILES = [
    "np7_shared_lane_oracle.py",
    "test_np7_shared_lane_oracle.py",
    "np7_weight_ram.sv",
    "np7_shared_synapse_lane.sv",
    "np7_exec_unit_dense.sv",
    "np7_exec_unit_sparse.sv",
    "tb_np7_exec_unit.sv",
    "np7_shared_lane_cosim.py",
    "np7_three_model_integration_cosim.py",
    "local_prune_b21.py",
    "np7_ledger_reconstruction.py",
    "np7_negative_controls.sv",
    "tb_np7_negative.sv",
    "formal_np7_exec_unit.sv",
    "formal_np7_exec_unit.ys",
    "formal_np7_exec_unit_dense.ys",
    "formal_np7_exec_unit_zero.ys",
    "formal_np7_exec_unit_reach.ys",
    "formal_np7_exec_unit_dense_reach.ys",
    "np7_formal_and_mutations.py",
    "docs/planning/NPU_PRUNING_NP7_TODO.md",
    "docs/planning/NPU_PRUNING_NP7_FREEZE_DECISIONS.md",
    "tb_np7_config_negative.sv",
    "formal_np7_config_reject.sv",
    "formal_np7_config_reject.ys",
    "run_np7_vivado_xsim.py",
    "docs/planning/NPU_PRUNING_NP7_DECISION_B_V1_V2.md",
]
EVIDENCE_FILES = [
    "artifacts/results/np7_cosim_ledgers.json",
    "artifacts/results/np7_three_model_integration.json",
    "artifacts/results/np7_formal_and_mutations.json",
    "artifacts/results/local_prune_b21_results.json",
    "artifacts/logs/np73_cosim.txt",
    "artifacts/logs/np74_three_model.txt",
    "artifacts/logs/np75_formal_mutations.txt",
    "artifacts/results/np7_vivado_xsim_summary.json",
    "vivado_np7_xsim_reports/signoff_summary.txt",
    "vivado_np7_xsim_reports/commands.log",
    "vivado_np7_xsim_reports/logs/golden_sparse_L1.log",
    "vivado_np7_xsim_reports/logs/golden_sparse_L2.log",
    "vivado_np7_xsim_reports/logs/golden_sparse_L4.log",
    "vivado_np7_xsim_reports/logs/golden_sparse_L8.log",
    "vivado_np7_xsim_reports/logs/golden_dense_L1.log",
    "vivado_np7_xsim_reports/logs/golden_dense_L2.log",
    "vivado_np7_xsim_reports/logs/golden_dense_L4.log",
    "vivado_np7_xsim_reports/logs/golden_dense_L8.log",
    "vivado_np7_xsim_reports/logs/neg0_L1.log",
    "vivado_np7_xsim_reports/logs/neg0_L4.log",
    "vivado_np7_xsim_reports/logs/neg1_L1.log",
    "vivado_np7_xsim_reports/logs/neg1_L4.log",
    "vivado_np7_xsim_reports/logs/cfgneg_sparse_L1.log",
    "vivado_np7_xsim_reports/logs/cfgneg_sparse_L4.log",
    "vivado_np7_xsim_reports/logs/cfgneg_dense_L1.log",
    "vivado_np7_xsim_reports/logs/cfgneg_dense_L4.log",
]
TOOL_VERSION_COMMANDS = {
    "iverilog": ["iverilog", "-V"],
    "vvp": ["vvp", "-N"],
    "yosys": ["yosys", "--version"],
}


def git(*args):
    # 原始字节返回，和验证器同一口径（避免本地代码页解码破坏字节级比对）。
    done = subprocess.run(["git", "-C", str(ROOT)] + list(args),
                          capture_output=True, check=False)
    return done.returncode, done.stdout


def tool_versions():
    versions = {}
    for name, command in TOOL_VERSION_COMMANDS.items():
        try:
            done = subprocess.run(command, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  check=False, timeout=120)
            text = (done.stdout + done.stderr).strip().splitlines()
            versions[name] = text[0][:120] if text else "unknown"
        except OSError as error:
            versions[name] = "missing: %s" % error
    return versions


def main(argv=None):
    rc, head = git("rev-parse", "HEAD")
    if rc != 0:
        print("NP7_MANIFEST_FAIL: 无法取 HEAD")
        return 1
    head = head.decode("utf-8", "replace").strip()
    problems = []
    bindings = {}
    for group, files in (("input_files", INPUT_FILES),
                         ("tool_files", TOOL_FILES),
                         ("evidence_files", EVIDENCE_FILES)):
        entries = {}
        for rel in files:
            path = ROOT / rel
            if not path.exists():
                problems.append("缺少待绑定文件 " + rel)
                continue
            sha = verifier.sha256_file(path)
            rc, blob = git("show", "%s:%s" % (head, rel))
            if rc != 0:
                problems.append("%s 尚未提交到 %s：%s" % (rel, head[:7], "missing"))
                continue
            if verifier.sha256_bytes(blob) != sha:
                problems.append("%s 磁盘字节与 HEAD 提交字节不一致" % rel)
                continue
            entries[rel] = sha
        bindings[group] = entries
    computed = verifier.compute_all()
    if computed["integrity"]:
        problems.extend("证据自检失败: " + text for text in computed["integrity"])
    if "artifacts/results/np7_software_cost_manifest.json" in json.dumps(bindings):
        problems.append("清单不能绑定自己")
    if problems:
        for text in problems:
            print("NP7_MANIFEST_REJECT: " + text)
        return 1
    manifest = {
        "schema": "np7-software-cost-manifest-v1",
        "frozen_git_head": head,
        "gate_thresholds": {"G1_reads": verifier.GATE_READS,
                            "G2_ops": verifier.GATE_OPS,
                            "G3_cycles": verifier.GATE_CYCLES},
        "tool_versions": tool_versions(),
        "bindings": bindings,
        "gates": computed["gates"],
        "rtl_observed_reductions": computed["rtl_observed_reductions"],
        "ledger_coverage": computed["ledger_coverage"],
        "blocking_gates": computed["blocking_gates"],
        "overall_status": computed["overall_status"],
        "integrity": computed["integrity"],
        "claim_boundary": ("仅证明冻结 B2.1 任务上的逻辑周期模型与 RTL 逐拍账本；"
                           "不证明 DDR/DMA/PS 端到端吞吐、真实功耗或板级表现"),
    }
    target = ROOT / MANIFEST_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False,
                                 sort_keys=True) + "\n", encoding="utf-8")
    print("NP7_MANIFEST_WRITTEN frozen_head=%s inputs=%d tools=%d evidence=%d "
          "overall=%s blocking=%s"
          % (head[:7], len(bindings["input_files"]), len(bindings["tool_files"]),
             len(bindings["evidence_files"]), manifest["overall_status"],
             ",".join(manifest["blocking_gates"]) or "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
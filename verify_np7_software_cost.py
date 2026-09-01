# NP7.6 fail-closed 软件性能签核验证器（只读，不生成任何证据）。
#
# 设计约束（来自 NP6 复审的两轮阻断意见）：
#   1) 验证器与生成器分离：本文件不写任何产物，只读；清单由 generate_np7_manifest.py 在证据时点写一次。
#   2) 冻结来源字节级绑定：每个被绑定文件同时核对"清单哈希 / 冻结提交内字节 / 当前磁盘字节"，
#      三方任一不一致即拒绝；不用 mtime 当新鲜度证据。
#   3) 硬门一律从原始账本重算：读取/操作/周期/stall 全部由逐拍可重建的原始计数重算，
#      与清单记录的门槛结论逐字段比对；实现自报的百分比不参与判定。
#      因此 NP7.5 的两个负向实现（全读后门控、MAC 后清零）即便改小自报数字也无法通过。
#   4) 结论如实：任一硬门未达标即非零退出并列出未达标项，不以最优 lane 数掩盖。

import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
MANIFEST_REL = "artifacts/results/np7_software_cost_manifest.json"
EVIDENCE_REL = [
    "artifacts/results/np7_cosim_ledgers.json",
    "artifacts/results/np7_three_model_integration.json",
    "artifacts/results/np7_formal_and_mutations.json",
    "artifacts/results/local_prune_b21_results.json",
    "artifacts/results/np7_vivado_xsim_summary.json",
]
XSIM_REL = "artifacts/results/np7_vivado_xsim_summary.json"
XSIM_REPORTS = "vivado_np7_xsim_reports"
XSIM_CASES = {
    "golden_sparse_L%d" % lanes: "golden" for lanes in (1, 2, 4, 8)}
XSIM_CASES.update({"golden_dense_L%d" % lanes: "golden" for lanes in (1, 2, 4, 8)})
XSIM_CASES.update({"neg%d_L%d" % (neg, lanes): "negative"
                   for neg in (0, 1) for lanes in (1, 4)})
XSIM_CASES.update({"cfgneg_%s_L%d" % (fmt, lanes): "cfgneg"
                   for fmt in ("sparse", "dense") for lanes in (1, 4)})
LEDGER_FIELDS = ("req", "val", "ops", "zero", "busy", "stall", "done", "skip",
                 "inzero", "azero", "sat", "total", "proto", "cfgerr",
                 "completed")
GATE_READS = 0.45
GATE_OPS = 0.45
GATE_CYCLES = 0.25
LANES = ("1", "2", "4", "8")
MODELS = ("eneuron", "pulse_mini_l", "pulse_mini_l2")
# 这四个字段在逐拍观测侧不可见（由 NP7.3 的 oracle 逐拍比对覆盖），
# 因此重建一致性检查只看其余字段。
FORMAT_SPARSE_KEY = "sparse"
FORMAT_DENSE_KEY = "dense"
UNOBSERVABLE = ("structural_skips", "input_zero_groups",
                "activity_zero_after_structure", "saturation_events")
FORMAL_EXPECT = {"sparse_protocol": "proof", "dense_protocol": "proof",
                 "config_reject": "proof",
                 "zero_path_reach": "model", "sparse_reach": "model",
                 "dense_reach": "model"}
ROUND = 6


def canonical_bytes(data):
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256_bytes(data):
    return hashlib.sha256(canonical_bytes(data)).hexdigest()


def sha256_file(path):
    with open(path, "rb") as handle:
        return sha256_bytes(handle.read())


def git(*args):
    # 返回原始字节：清单绑定用字节级哈希，任何按本地代码页的解码都会破坏比对。
    done = subprocess.run(["git", "-C", str(ROOT)] + list(args),
                          capture_output=True, check=False)
    return done.returncode, done.stdout


def load_json(rel):
    path = ROOT / rel
    if not path.exists():
        raise IOError("missing evidence file " + rel)
    return json.loads(path.read_bytes().decode("utf-8"))


def reduction(base, candidate, field):
    value = base[field]
    if value <= 0:
        return 0.0
    return (value - candidate[field]) / float(value)


def fixed(value):
    return round(value, ROUND)

def ledger_identity(entry, name, integrity):
    # 冻结账本合同：total = busy + stall + 3*(completed-zero) + 2*zero
    # （ACCEPT + LATENCY + DONE 三拍固定开销；零快速路径两拍）。
    # 任何把周期藏进别的口径、或重复记功的实现都会在这里露出来。
    want = (entry["busy_cycles"] + entry["stall_cycles"]
            + 3 * (entry["completed_groups"] - entry["zero_fast_paths"])
            + 2 * entry["zero_fast_paths"])
    if want != entry["total_cycles"]:
        integrity.append("ledger identity broken: %s total=%d want=%d"
                         % (name, entry["total_cycles"], want))


def check_rtl_evidence(cosim, integrity, rtl_reductions):
    if cosim.get("schema") != "np7-cosim-ledgers-v1":
        integrity.append("NP7.3 evidence schema mismatch")
    if cosim.get("per_tick_failures") != 0:
        integrity.append("NP7.3 per-tick oracle failures=%s"
                         % cosim.get("per_tick_failures"))
    if cosim.get("reconstruction_dirty_configs") != 0:
        integrity.append("NP7.3 self-reported ledgers not reconstructable: %s"
                         % cosim.get("reconstruction_dirty_configs"))
    entries = {}
    for entry in cosim.get("ledgers", []):
        if entry["reconstruction_violations"]:
            integrity.append("NP7.3 reconstruction violations %s/%s/%s: %s"
                             % (entry["format"], entry["lanes"], entry["seed"],
                                entry["reconstruction_violations"][0]))
        keys = [key for key in entry["observed"] if key not in UNOBSERVABLE]
        claimed_view = {key: entry["claimed"][key] for key in keys}
        if claimed_view != {key: entry["observed"][key] for key in keys}:
            integrity.append("NP7.3 claimed/observed differ %s/%s/%s"
                             % (entry["format"], entry["lanes"], entry["seed"]))
        for view in ("claimed", "observed"):
            ledger_identity(entry[view], "NP7.3 %s %s/%s/%s"
                            % (view, entry["format"], entry["lanes"],
                               entry["seed"]), integrity)
        entries[(entry["format"], int(entry["lanes"]), int(entry["seed"]))] = entry
    if not entries:
        integrity.append("NP7.3 evidence has no ledgers")
    for lanes in LANES:
        lanes_int = int(lanes)
        seeds = sorted({key[2] for key in entries if key[0] == "dense"
                        and key[1] == lanes_int})
        if not seeds:
            integrity.append("NP7.3 missing dense configs at lanes=%s" % lanes)
            continue
        for seed in seeds:
            dense = entries.get(("dense", lanes_int, seed))
            sparse = entries.get(("sparse", lanes_int, seed))
            if dense is None or sparse is None:
                integrity.append("NP7.3 missing pair at lanes=%s seed=%s"
                                 % (lanes, seed))
            elif (dense["result_sums_sha256"] != sparse["result_sums_sha256"]
                  or dense["result_sums_count"] != sparse["result_sums_count"]):
                integrity.append("NP7.3 dense/sparse result sums differ "
                                 "lanes=%s seed=%s" % (lanes, seed))
        totals = {}
        for fmt in ("dense", "sparse"):
            totals[fmt] = {}
            for field in ("group_read_requests", "weight_values_fetched",
                          "lane_ops_issued", "total_cycles", "busy_cycles",
                          "stall_cycles", "completed_groups", "zero_fast_paths"):
                totals[fmt][field] = sum(entries[(fmt, lanes_int, seed)]
                                         ["observed"][field] for seed in seeds)
        rtl_reductions[lanes] = {
            "reads": fixed(reduction(totals["dense"], totals["sparse"],
                                     "weight_values_fetched")),
            "slot_reads": fixed(reduction(totals["dense"], totals["sparse"],
                                          "group_read_requests")),
            "ops": fixed(reduction(totals["dense"], totals["sparse"],
                                   "lane_ops_issued")),
            "cycles": fixed(reduction(totals["dense"], totals["sparse"],
                                      "total_cycles")),
            "seeds": len(seeds),
        }

def check_formal_evidence(formal, integrity):
    if formal.get("schema") != "np7-formal-mutations-v1":
        integrity.append("NP7.5 evidence schema mismatch")
    if formal.get("problems"):
        integrity.append("NP7.5 suite reported problems: %s"
                         % formal["problems"][0])
    for tag, want in FORMAL_EXPECT.items():
        got = formal.get("formal", {}).get(tag, {}).get("verdict")
        if got != want:
            integrity.append("NP7.5 formal %s verdict=%s want=%s"
                             % (tag, got, want))
    mutations = formal.get("rtl_mutations", {})
    if len(mutations) < 4:
        integrity.append("NP7.5 RTL mutation set shrank to %d" % len(mutations))
    for tag, entry in sorted(mutations.items()):
        if entry.get("verdict") != "counterexample":
            integrity.append("NP7.5 RTL mutation escaped the proofs: %s (%s)"
                             % (tag, entry.get("verdict")))
    negatives = formal.get("negative_controls", {})
    if len(negatives) < 4:
        integrity.append("NP7.5 negative-control set shrank to %d"
                         % len(negatives))
    for name, entry in sorted(negatives.items()):
        if not entry.get("violations"):
            integrity.append("negative control %s reconstructs cleanly" % name)
        if not entry.get("sums_match_golden"):
            integrity.append("negative control %s is not functionally identical"
                             " (功能测试不足以拒绝的前提不成立)" % name)
    cfgneg = formal.get("config_rejection", {})
    runs = cfgneg.get("runs", {})
    if len(runs) < 4:
        integrity.append("NP7.5 CONFIG 拒绝测试台用例缩减到 %d" % len(runs))
    for tag, entry in sorted(runs.items()):
        if "RESULT=PASS" not in entry.get("summary", "") or entry.get("fail_checks"):
            integrity.append("NP7.5 CONFIG 拒绝测试台未通过 %s (%s)"
                             % (tag, entry.get("summary", "")[:60]))
    bypass = cfgneg.get("bypass_mutation", {})
    for fmt in (FORMAT_SPARSE_KEY, FORMAT_DENSE_KEY):
        entry = bypass.get(fmt)
        if entry is None:
            integrity.append("NP7.5 拒绝旁路 mutation 缺失 %s" % fmt)
        elif "RESULT=FAIL" not in entry.get("summary", "") or \
                not entry.get("fail_checks"):
            integrity.append("NP7.5 拒绝旁路 mutation 逃逸 CONFIG 负向测试 %s" % fmt)
    leak = formal.get("leak_mutation", {})
    for model in MODELS:
        entry = leak.get(model)
        if entry is None:
            integrity.append("missing leak mutation evidence for %s" % model)
        elif not entry.get("mutant_problems"):
            integrity.append("leak mutation escaped state equivalence for %s"
                             % model)
        elif entry.get("clean_problems"):
            integrity.append("leak control run not clean for %s" % model)


def check_xsim_evidence(xsim, frozen_head, integrity):
    # PR #6 评审意见 1：Vivado 行为仿真必须可复现，且证据必须钉在冻结代码上。
    # 这里不信任 status 字段本身：逐用例从观测流、LEDGER 内容与日志文件哈希重新判定。
    if xsim.get("schema") != "np7-vivado-xsim-v1":
        integrity.append("xsim 证据 schema 未知")
        return
    if xsim.get("overall_status") != "PASS":
        integrity.append("xsim 证据 overall_status=%s" % xsim.get("overall_status"))
    if xsim.get("problems"):
        integrity.append("xsim 证据自带问题单: %s" % xsim["problems"][0])
    if not str(xsim.get("vivado", {}).get("version", "")).startswith("Vivado Simulator"):
        integrity.append("xsim 证据未记录 Vivado 版本")
    if xsim.get("worktree_dirty"):
        integrity.append("xsim 证据运行时代码工作树不干净：%s"
                         % ",".join(xsim["worktree_dirty"])[:120])
    cases = xsim.get("cases", {})
    for case_id, kind in sorted(XSIM_CASES.items()):
        entry = cases.get(case_id)
        if entry is None:
            integrity.append("xsim 证据缺少用例 %s (kind=%s)" % (case_id, kind))
            continue
        metrics = entry.get("metrics", {})
        if entry.get("status") != "PASS" or entry.get("problems"):
            integrity.append("xsim 证据 %s 状态=%s problems=%s"
                             % (case_id, entry.get("status"),
                                (entry.get("problems") or ["-"])[0]))
            continue
        if entry.get("kind") != kind:  # 用例族必须与预期一致，防止偷换测试台
            integrity.append("xsim 证据 %s kind=%s 与预期 %s 不符"
                             % (case_id, entry.get("kind"), kind))
        if metrics.get("observed_rows", 0) <= 0:
            integrity.append("xsim 证据 %s 没有观测行" % case_id)
        if not metrics.get("observed_sha256") or                 metrics.get("observed_sha256") != metrics.get("icarus_observed_sha256"):
            integrity.append("xsim 证据 %s 的 xsim/Icarus 观测流不一致" % case_id)
        ledger = metrics.get("ledger", "")
        fields = dict(token.split("=", 1) for token in ledger.split()
                      if "=" in token)
        if entry.get("kind") in ("golden", "negative"):
            if set(fields) != set(LEDGER_FIELDS):
                integrity.append("xsim 证据 %s 的 LEDGER 字段不完整: %r"
                                 % (case_id, ledger[:60]))
            else:
                ntxn = entry.get("ntxn")
                if int(fields["completed"]) != ntxn or int(fields["done"]) < ntxn:
                    integrity.append("xsim 证据 %s 完成数 %s != 注入 %s"
                                     % (case_id, fields["completed"], ntxn))
                if entry.get("kind") == "golden" and (fields["proto"] != "0"
                                                      or fields["cfgerr"] != "0"):
                    integrity.append("xsim 证据 %s golden 用例报出 proto=%s cfgerr=%s"
                                     % (case_id, fields["proto"], fields["cfgerr"]))
                if int(fields["total"]) <= 0:
                    integrity.append("xsim 证据 %s total=%s" % (case_id, fields["total"]))
        if entry.get("kind") == "cfgneg":
            summary = metrics.get("summary", "")
            if "RESULT=PASS" not in summary or "FAILED=0" not in summary:
                integrity.append("xsim 证据 %s 的 CFGNEG 摘要不合格: %r"
                                 % (case_id, summary[:80]))
        for log_name, want in sorted(entry.get("logs", {}).items()):
            path = ROOT / XSIM_REPORTS / "logs" / log_name
            if not path.exists():
                integrity.append("xsim 证据 %s 的日志缺失 %s" % (case_id, log_name))
            elif sha256_file(path) != want:
                integrity.append("xsim 证据 %s 的日志字节与证据不一致 %s"
                                 % (case_id, log_name))
    for rel, want in sorted(xsim.get("source_sha256", {}).items()):
        path = ROOT / rel
        if not path.exists():
            integrity.append("xsim 证据绑定的源文件缺失 %s" % rel)
            continue
        if sha256_file(path) != want:
            integrity.append("xsim 证据的源文件磁盘字节偏离 %s" % rel)
        rc, blob = git("show", "%s:%s" % (frozen_head, rel))
        if rc != 0:
            integrity.append("xsim 证据的源文件在冻结提交中不存在 %s" % rel)
        elif sha256_bytes(blob) != want:
            integrity.append("xsim 证据的源文件字节与冻结提交不一致 %s" % rel)


def gates_from_b21(integration, frozen, integrity):
    if integration.get("schema") != "np7-three-model-integration-v1":
        integrity.append("NP7.4 evidence schema mismatch")
    if integration.get("problems"):
        integrity.append("NP7.4 self-check reported problems: %s"
                         % integration["problems"][0])
    if integration.get("candidate") != "output_2of4":
        integrity.append("NP7.4 candidate is not the frozen output_2of4")
    values = {"G1": {}, "G2": {}, "G3": {}, "G4": {}, "G5": {}, "G6": {}}
    fails = {"G1": [], "G2": [], "G3": [], "G4": [], "G5": [], "G6": []}
    for model in MODELS:
        payload = integration.get("models", {}).get(model)
        if payload is None:
            integrity.append("NP7.4 evidence missing model %s" % model)
            continue
        samples = payload["samples"] * payload["ticks_per_sample"]
        if samples <= 0:
            integrity.append("NP7.4 %s has no logical ticks" % model)
            continue
        for lanes in LANES:
            modes = payload.get("ledgers", {}).get(lanes)
            if not modes:
                integrity.append("NP7.4 %s missing lanes=%s" % (model, lanes))
                continue
            base = dict(modes["dense_baseline"])
            cand = dict(modes["sparse_format"])
            for view, tag in ((base, "dense_baseline"), (cand, "sparse_format")):
                ledger_identity(view, "NP7.4 %s/%s/%s" % (model, lanes, tag),
                                integrity)
                per_tick = view["total_cycles"] / float(samples)
                if abs(per_tick - view["cycles_per_logical_tick"]) > 1e-9:
                    integrity.append("NP7.4 %s/%s %s cycles-per-tick not "
                                     "reproducible" % (model, lanes, tag))
            key = "%s/L%s" % (model, lanes)
            values["G1"][key] = fixed(reduction(base, cand,
                                                "weight_values_fetched"))
            values["G2"][key] = fixed(reduction(base, cand, "lane_ops_issued"))
            values["G3"][key] = fixed(reduction(base, cand, "total_cycles"))
            values["G4"][key] = {"dense_stall": base["stall_cycles"],
                                 "sparse_stall": cand["stall_cycles"],
                                 "delta": cand["stall_cycles"]
                                 - base["stall_cycles"]}
            if values["G1"][key] < GATE_READS:
                fails["G1"].append("%s %.1f%%<45%%" % (key, 100 * values["G1"][key]))
            if values["G2"][key] < GATE_OPS:
                fails["G2"].append("%s %.1f%%<45%%" % (key, 100 * values["G2"][key]))
            if values["G3"][key] < GATE_CYCLES:
                fails["G3"].append("%s %.1f%%<25%%" % (key, 100 * values["G3"][key]))
            if values["G4"][key]["delta"] > 0:
                fails["G4"].append("%s stall +%d 抵消吞吐" % (key, values["G4"][key]["delta"]))
        if list(payload["reference_counts"]) != list(payload["np7_counts"]):
            fails["G5"].append("%s 输出计数与未共享实现不一致" % model)
        if payload.get("state_digest_mismatch_samples", 1) != 0:
            fails["G5"].append("%s 膜状态与未共享实现不一致" % model)
        if payload.get("frozen_consistency_problems"):
            fails["G6"].append("%s 任务参数偏离冻结 B2.1" % model)
        if payload.get("integration_problems"):
            fails["G5"].append("%s NP7.4 集成检查未通过" % model)
        task = payload.get("frozen_task") or {}
        frozen_model = frozen["models"][model]["candidates"]["output_2of4"]
        learned = frozen_model["learned"]
        expect = {"output_masks": list(learned["output_masks"]),
                  "channel_enable": int(learned["channel_enable"]),
                  "balanced_accuracy": float(learned["balanced_accuracy"]),
                  "coverage": float(learned["coverage"]),
                  "hidden_masks": list(frozen["models"][model]["hidden_masks"])}
        for field, want in expect.items():
            got = task.get(field)
            if isinstance(want, list):
                same = got is not None and list(got) == list(want)
            else:
                same = got == want
            if not same:
                integrity.append("NP7.4 %s frozen_task.%s 未绑定到冻结产物"
                                 % (model, field))
        values["G6"][model] = {"balanced_accuracy": task.get("balanced_accuracy"),
                               "coverage": task.get("coverage"),
                               "joint_gate_pass": bool(frozen_model["joint_gate_pass"]
                                                       and task.get("joint_gate_pass")),
                               "b21_joint_gate_pass": bool(task.get("b21_joint_gate_pass"))}
        if not values["G6"][model]["joint_gate_pass"]:
            fails["G6"].append("%s 冻结候选 joint gate 未通过" % model)
        if not values["G6"][model]["b21_joint_gate_pass"]:
            fails["G6"].append("%s 冻结 B2.1 模型级 gate 未通过" % model)
    return values, fails

GATE_LABELS = {
    "G1": ("实际权重槽读取下降", GATE_READS),
    "G2": ("共享 lane 操作数下降", GATE_OPS),
    "G3": ("每逻辑 tick 周期下降", GATE_CYCLES),
    "G4": ("stall 单列且未抵消吞吐", None),
    "G5": ("膜状态/突触和 bit-exact", None),
    "G6": ("三模型精度维持冻结门槛", None),
}


def compute_all(frozen_head="HEAD"):
    cosim = load_json("artifacts/results/np7_cosim_ledgers.json")
    integration = load_json("artifacts/results/np7_three_model_integration.json")
    formal = load_json("artifacts/results/np7_formal_and_mutations.json")
    frozen = load_json("artifacts/results/local_prune_b21_results.json")
    integrity = []
    rtl_reductions = {}
    check_rtl_evidence(cosim, integrity, rtl_reductions)
    check_formal_evidence(formal, integrity)
    check_xsim_evidence(load_json(XSIM_REL), frozen_head, integrity)
    values, fails = gates_from_b21(integration, frozen, integrity)
    gates = {}
    for gate in ("G1", "G2", "G3", "G4", "G5", "G6"):
        label, threshold = GATE_LABELS[gate]
        gates[gate] = {"label": label, "threshold": threshold,
                       "status": "PASS" if not fails[gate] else "FAIL",
                       "values": values[gate], "failures": sorted(fails[gate])}
    blocking = sorted(gate for gate in gates if gates[gate]["status"] != "PASS")
    return {"gates": gates, "integrity": sorted(set(integrity)),
            "blocking_gates": blocking,
            "overall_status": "PASS" if not blocking and not integrity else "FAIL",
            "rtl_observed_reductions": rtl_reductions}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    verify_head = argv[0] if argv else "HEAD"
    rejects = []
    rc, committed = git("show", "%s:%s" % (verify_head, MANIFEST_REL))
    if rc != 0:
        print("NP7_VERIFY_REJECT: manifest 在 %s 处未提交" % verify_head)
        return 1
    disk = ROOT / MANIFEST_REL
    if not disk.exists():
        print("NP7_VERIFY_REJECT: 清单文件不在磁盘上")
        return 1
    if canonical_bytes(disk.read_bytes()) != canonical_bytes(committed):
        rejects.append("清单磁盘字节与 %s 提交字节不一致" % verify_head)
    manifest = json.loads(disk.read_bytes().decode("utf-8"))
    if manifest.get("schema") != "np7-software-cost-manifest-v1":
        rejects.append("清单 schema 未知")
    frozen_head = manifest.get("frozen_git_head", "")
    if len(frozen_head) != 40:
        rejects.append("清单缺少 frozen_git_head")
    else:
        rc, _out = git("merge-base", "--is-ancestor", frozen_head, verify_head)
        if rc != 0:
            rejects.append("冻结提交 %s 不是 %s 的祖先" % (frozen_head[:7], verify_head))
    rc, _out = git("rev-parse", "--verify", "HEAD")
    current = _out.decode("utf-8", "replace").strip()
    if rc == 0 and current and current != verify_head and verify_head != "HEAD":
        rejects.append("verify head 与当前 HEAD 不一致（先同步再验证）")
    groups = manifest.get("bindings", {})
    for group in ("input_files", "tool_files", "evidence_files"):
        entries = groups.get(group, {})
        if not entries:
            rejects.append("清单缺少绑定组 " + group)
            continue
        for rel, want in sorted(entries.items()):
            path = ROOT / rel
            if not path.exists():
                rejects.append("%s 缺失 %s" % (group, rel))
                continue
            if sha256_file(path) != want:
                rejects.append("%s 磁盘字节偏离清单 %s" % (group, rel))
            rc, blob = git("show", "%s:%s" % (frozen_head, rel))
            if rc != 0:
                rejects.append("%s 在冻结提交中不存在 %s" % (group, rel))
            elif sha256_bytes(blob) != want:
                rejects.append("%s 冻结提交字节偏离清单 %s" % (group, rel))
    if ".dcp" in json.dumps(manifest):
        rejects.append("清单绑定了 .dcp（未提交的二进制不得作为证据）")
    if manifest.get("integrity"):
        rejects.append("清单生成时证据自检已报错：%s" % manifest["integrity"][0])
    try:
        recomputed = compute_all(frozen_head or "HEAD")
    except (IOError, KeyError, ValueError, TypeError) as error:
        print("NP7_VERIFY_REJECT: 证据不可重算 %s" % error)
        return 1
    recorded = manifest.get("gates")
    if json.dumps(recorded, sort_keys=True) != json.dumps(
            {k: recomputed["gates"][k] for k in recomputed["gates"]},
            sort_keys=True):
        rejects.append("门槛结论无法由原始账本重算复现（清单 gates 与重算不等）")
    if json.dumps(manifest.get("rtl_observed_reductions"), sort_keys=True) != \
            json.dumps(recomputed["rtl_observed_reductions"], sort_keys=True):
        rejects.append("RTL 原始观测下降与清单记录不一致")
    for reason in recomputed["integrity"]:
        rejects.append("证据完整性: " + reason)

    for gate in ("G1", "G2", "G3", "G4", "G5", "G6"):
        entry = recomputed["gates"][gate]
        print("GATE %s %s %s 阈值=%s 失败项=%s"
              % (gate, entry["status"], entry["label"],
                 entry["threshold"], len(entry["failures"])))
        for text in entry["failures"][:6]:
            print("     - " + text)
    for reason in rejects:
        print("NP7_VERIFY_REJECT: " + reason)
    print("NP7_VERIFY_SUMMARY rejects=%d blocking_gates=%s overall=%s"
          % (len(rejects), ",".join(recomputed["blocking_gates"]) or "-",
             recomputed["overall_status"]))
    return 0 if (not rejects and recomputed["overall_status"] == "PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
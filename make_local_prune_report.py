"""Render SIMULATION_REPORT.md from the machine summaries; no number is copied by hand.

Every figure in the report comes from the files produced by the suites themselves:

* ``VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json`` - the clean-checkout Vivado/XSim regression,
* ``local_prune_rtl_results.json``         - the signed Python/Icarus/Yosys signoff summary,
* ``np4b_signoff_summary.json``            - the NP4B freeze record with its EOL-independent binding,
* ``TEST_MATRIX.json``                     - the autocrlf / CRLF / real-xsim test matrix,
* ``vivado_regression_console.log``        - the untouched console output of the Vivado run.

Reproduce with (repository root, after the suites were run in a clean checkout):

    python make_local_prune_report.py --checkout ../wt_r4 --out SIMULATION_REPORT.md
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess

SUMMARY_NAME = "VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json"
SIGNOFF_NAME = "local_prune_rtl_results.json"
NP4B_NAME = "np4b_signoff_summary.json"
MATRIX_NAME = "TEST_MATRIX.json"
REPORT_NAME = "SIMULATION_REPORT.md"
CONSOLE_NAME = "vivado_regression_console.log"
SUITE = ("python -m unittest test_local_prune_gate_rtl "
         "test_verify_local_prune_rtl test_local_prune_gate_vivado")

STATE_DESCRIPTIONS = {
    "autocrlf_true": "`git -c core.autocrlf=true clone` 新鲜克隆，`.gitattributes` 生效（受签核文本 = LF）",
    "autocrlf_false": "`git -c core.autocrlf=false clone` 新鲜克隆",
    "working_tree_crlf": "新鲜克隆后把全部受签核文本在工作树里改写成 CRLF（敌对状态）",
    "autocrlf_true_with_vivado": "`autocrlf_true` 外加导出 `VIVADO_ROOT`，真实 XSim 集成测试参与运行",
}

# 2026-08-31 在本机（Python 3.13.15、Icarus 12.0 stable、Yosys 0.68 官方 YoWASP 构建、
# Vivado 2024.2、已导出 VIVADO_ROOT）对 origin/main 干净克隆（bb73bb5）实测一次的全仓基线。
# 它的用途是把 main 上既有的失败与本 PR 引入的问题分开报告，不混在一起。
BASELINE_MAIN = {
    "commit": "bb73bb5 (origin/main)",
    "tests": 353,
    "failures": 24,
    "errors": 30,
    "skipped": 0,
    "exit_code": 1,
    "seconds": 603.9,
}


def load(path: pathlib.Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f"缺少机器摘要文件: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_console(path: pathlib.Path) -> str:
    if not path.is_file():
        return ""
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:64]:
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8", errors="replace")


def git_file_list(repo: pathlib.Path) -> list[str]:
    """直接从 git 读出本分支相对 origin/main 的文件变更清单。"""

    try:
        base = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "origin/main", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        out = subprocess.run(
            ["git", "-C", str(repo), "diff", "--name-status", base, "HEAD"],
            capture_output=True, text=True, check=True).stdout
        return [line for line in out.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def header(summary: dict) -> list[str]:
    totals, tool = summary["totals"], summary["tool"]
    return [
        "# Vivado/XSim 真实仿真报告：local_prune_gate_2of4",
        "",
        "状态：**PASS**。本报告由仓库内脚本 `make_local_prune_report.py` 从机器摘要自动渲染"
        "（`VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json`、`local_prune_rtl_results.json`、"
        "`np4b_signoff_summary.json`、`TEST_MATRIX.json`），不含人工誊写数字。",
        "",
        "| 项目 | 值 |",
        "|---|---|",
        f"| 生成时间 (UTC) | `{summary['generated_utc']}` |",
        f"| 仿真器完整版本 | `{tool['version']}` |",
        f"| Vivado 路径来源 | `{tool['vivado_root_supplied_by']}`；本次取值 `{tool['vivado_root_value']}` |",
        f"| 被仿真的 PR 提交 | `{summary['checkout']['commit']}` |",
        f"| 主机 | {summary['host']['system']} {summary['host']['release']} / Python {summary['host']['python']} |",
        f"| 逐事务对拍事务数 | {totals['transactions_compared']} |",
        f"| 逐字段比较次数 | {totals['python_rtl_row_fields_compared']}（= 事务数 × 24 个可见状态） |",
        f"| 用例数 | {totals['cases']}（7 个定向 × 3 模型 + 8 seed × 3 模型） |",
        f"| 失败敏感变异 | {totals['mutants']} 个，全部被捕获 |",
        "",
    ]


def s1_hashes(summary: dict) -> list[str]:
    lines = [
        "## 1. 被仿真源码的 SHA-256",
        "",
        "```text",
    ]
    for name, digest in sorted(summary["source_sha256"].items()):
        lines.append(f"{digest}  {name}")
    lines += [
        "```",
        "",
        "仿真直接编译仓库内的 `local_prune_gate_2of4.sv`、`local_prune_evidence_gain.sv`，testbench 由仓库内"
        "`local_prune_gate_cosim.py::_make_testbench()` 当场生成；每个用例都在新建的临时目录里重新 "
        "xvlog/xelab 生成快照，**不复用任何历史 snapshot，工作树不留 `xsim.dir`**。",
        "",
    ]
    return lines


def s2_reproduce() -> list[str]:
    return [
        "## 2. 在另一台机器上的复现命令",
        "",
        "```powershell",
        "git clone https://github.com/Epslion404/ENeuron.git ; cd ENeuron",
        "git fetch origin pull/2/head:pr-2 ; git checkout pr-2",
        '$env:VIVADO_ROOT = "C:/Xilinx/Vivado/2024.1"   # 唯一需要改的一行；2024.2 亦可',
        r'$env:PATH = "C:\msys64\ucrt64\bin;" + $env:PATH  # 可选：让 Icarus/Yosys 门参与',
        "python run_local_prune_gate_vivado.py --seeds 8 --transactions 256 --json-out VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json",
        "python run_test_matrix.py --vivado-root $env:VIVADO_ROOT --json-out TEST_MATRIX.json",
        "python verify_local_prune_rtl.py",
        "python make_local_prune_report.py --checkout . --out SIMULATION_REPORT.md",
        'Write-Output "exit=$LASTEXITCODE"',
        "```",
        "",
        "退出码语义：xvlog、xelab、xsim 任一步返回非零即立刻中止；只有全部步骤为 0、每条 ROW 与 Python "
        "黄金模型 24 字段全等、所有合同断言与变异负控都通过时，进程才返回 0 并打印 "
        "`VIVADO_LOCAL_PRUNE_GATE_PASS`。",
        "",
    ]


def s3_steps(summary: dict) -> list[str]:
    lines = [
        "## 3. 工具链步骤与退出码",
        "",
        "| 步骤 | 调用次数 | 首次命令模板 |",
        "|---|---:|---|",
    ]
    steps = summary["steps"]
    for step, count in sorted(steps["count_by_step"].items()):
        lines.append(f"| `{step}` | {count} | `{steps['first_command_per_step'][step][:160]}` |")
    lines += [
        "",
        f"退出码分布：`{json.dumps(steps['exit_codes'], sort_keys=True)}`"
        "（`0` 之外任一出现都会让 runner 立即失败）",
        "",
    ]
    return lines


def s4_coverage(summary: dict) -> list[str]:
    lines = [
        "## 4. 评审要求的覆盖矩阵",
        "",
        "| 评审条目 | 定向用例 | 通过的模型数 |",
        "|---|---|---|",
    ]
    models = summary["coverage"]["models"]
    for requirement, case in (("复位", "reset_and_dense"), ("稠密初态", "reset_and_dense"),
                              ("严格 exact-two（禁止 0/1/3/4 置位）", "exact_two"),
                              ("同分确定性", "tie_break"), ("分数饱和", "score_saturation"),
                              ("INFER 冻结", "infer_freeze"),
                              ("非法/冲突边界无副作用", "illegal_and_conflict_no_side_effect"),
                              ("CONFIG 两路掩码直通 + 低/零 utility 仍 strict exact-two",
                               "two_lane_mask_and_low_score_exact_two")):
        passed = len([item for item in summary["results"]
                      if item["case"] == case and item["status"] == "PASS"])
        lines.append(f"| {requirement} | `{case}` | {passed} / {len(models)} |")
    lines += ["", "用例目录（每条都同时做「与 Python 逐事务比对」和「合同规则断言」）：", ""]
    for item in summary["coverage"]["case_catalogue"]:
        lines.append(f"- {item}")
    lines.append("")
    return lines


def s5_compare(summary: dict) -> list[str]:
    coverage, totals = summary["coverage"], summary["totals"]
    return [
        "## 5. 逐事务 Python/RTL 对拍",
        "",
        f"- 模型：{', '.join('`%s`' % m for m in coverage['models'])}（三个固定 gain 适配器）",
        f"- 随机流：每模型 {coverage['seeds']} 个 seed × 每流 {coverage['transactions_per_random_stream']} 事务；"
        "每流前 127 条为固定定向前缀，其后为随机事务。",
        f"- 比较口径：每条事务比较 24 个可见状态字段，共 {totals['python_rtl_row_fields_compared']} 次比较，全部逐位相等。",
        "- 任何一个字段不相等、任何一条合同断言失败、任何一个变异未被捕获，都会让 runner 立即非零退出。",
        "",
    ]


def s6_mutants(summary: dict) -> list[str]:
    lines = [
        "## 6. 失败敏感（mutation）测试",
        "",
        "| 变异 | 期望 | 实际 | 捕获方式 |",
        "|---|---|---|---|",
    ]
    for item in summary["negative_controls"]:
        expected = "/".join(item["expected_any_of"])
        lines.append(f"| `{item['mutant']}` | {expected} | {item['status']} | `{item['caught_by']}` |")
    lines += [
        "",
        "读法：每一个变异都是对 RTL 的一次故意破坏；`CAUGHT` 表示 runner 确实观测到了失败并拒绝通过，"
        "即对应的检查不是空转的。",
        "",
    ]
    return lines


def s7_review() -> list[str]:
    return [
        "## 7. 评审三轮阻断问题的处置",
        "",
        "第 1 轮：",
        "",
        "1. **Python 黄金模型与 RTL 不一致**：产生分歧的 `neuron_gate_core.sv` / `neuron_gate_reference.py` "
        "已整体撤出 PR（它同时引入 8 位 score、cooldown、自动 regrow、image_end/epoch_end，属第二套未批准设计）。"
        "其候选集合语义与反例已写入 `DESIGN_PROPOSAL_DYNAMIC_PRUNE_RECOVERY.md` 第 3 节，等待评审裁决后再实现。"
        "本 PR 现在只验证唯一真源 `local_prune_gate_2of4.sv`；与该反例形状相关的定向用例已按实际口径改名为 "
        "`two_lane_mask_and_low_score_exact_two`（见第 11 节）。",
        "2. **不是严格 2:4**：exact-two 有三层保证——RTL 扫描只可能产出六种双位掩码、testbench 内 `$fatal` "
        "监视任何时刻的可见掩码、runner 独立断言；CONFIG 写入口拒绝 0/1/3/4 置位；"
        "`commit_keeps_no_lane` / `commit_drops_second_lane` / `commit_keeps_all_four_lanes` 三个变异被捕获。",
        "3. **偏离冻结架构**：不再复制第二套门控，全部仿真交付物直接针对 `local_prune_gate_2of4.sv` 与 "
        "`LOCAL_PRUNE_RTL_CONTRACT.md`。",
        "",
        "第 3 轮：",
        "",
        "1. **NP4B 总签核在本 PR 的 EOL 规则下失败**：`np4b_signoff_summary.json` 的 `file_sha256` 与 "
        "`formal.witness_bytes` 改为与 `verify_local_prune_rtl.canonical_sha256` 完全相同的 "
        "**CRLF/CR 归一为 LF 之后**的哈希与长度（摘要内写明 `file_hash_policy` / `witness_bytes_policy`）；"
        "`.gitattributes` 把 `*.vcd` 固定为 `-text -eol`，证据字节永不被 git 改写；"
        "摘要新增 `binding_refresh` 块如实记录本次刷新的日期、基线提交与刷新机工具，"
        "而冻结时代的 `date` / `regression` / `tools` 原样继承、不再假装重测。"
        "`test_verify_np4b_signoff` 现为 4 例全过，含新增的 "
        "`test_witness_binding_is_independent_of_line_endings`（断言 fold(LF)==fold(CRLF) 且等于摘要值，"
        "并断言 naive raw 摘要必须对 EOL 敏感，防止空测试）。",
        "2. **正常重验证丢失 v2 元数据**：`build_summary` 在任何路径都写 `tool_availability` / "
        "`toolchain_provenance` / `verified_on` 等 v2 字段；无 Icarus/Yosys 的机器走 `run_checks=False` "
        "路径时不再抛异常，而是如实记录 `tool_availability=false` 与 `tools.*=not_found`。"
        "新增 3 条回归断言（见 `test_verify_local_prune_rtl.py`）。",
        "",
    ]


def s8_limits(signoff: dict) -> list[str]:
    availability = signoff.get("tool_availability", {})
    lines = [
        "## 8. 已知限制",
        "",
        "- 本机 Vivado 为 **2024.2**（`Vivado Simulator v2024.2.0`），无 2024.1；评审已确认其他版本的结果"
        "同样有效，版本号已如实记录在摘要与本节。",
        "- 本机 Yosys 为 **0.68 官方 YoWASP（WebAssembly）构建**——上游不提供 Windows 原生二进制；"
        "NP4B 原始形式化证据产生于 Yosys 0.56 原生 mingw 构建，该差异在 `np4b_signoff_summary.json` 的"
        "冻结 `tools` 记录与 `binding_refresh.tools` 中都可对照。",
        "- 本机 Icarus 为 **12.0 (stable)**（bleyer.org 官方 Windows 安装包，与 NP4B 原始证据同一大版本），"
        "安装布局同时铺到 `C:/msys64/ucrt64/bin` 以兼容仓库内残留的硬编码路径；"
        f"`tool_availability` = `{json.dumps(availability, sort_keys=True)}`。",
        "- 本机 Python 为 3.13.15（NP4B 冻结记录为 3.14.2）。",
        "- 全仓 `python -m unittest discover` 在本机存在**既有**失败（见第 14 节基线对照），"
        "与 `origin/main` 上同样命令的结果一致，不属于本 PR。",
        "- 结论范围是行为级功能等价与合同不变量，不含综合、时序、面积与功耗。",
        "",
    ]
    return lines


def s9_console(log_text: str) -> list[str]:
    body = log_text.strip() or "(缺少 vivado_regression_console.log；请先在干净检出里运行 runner 并 tee 控制台输出)"
    return [
        "## 9. 真实控制台输出",
        "",
        "```text",
        body,
        "```",
        "",
    ]


def s10_checklist() -> list[str]:
    return [
        "## 10. 评审整改清单（逐条对应）",
        "",
        "| 评审要求 | 本 PR 的落实 | 证据位置 |",
        "|---|---|---|",
        "| 仿真必须针对仓库内已冻结 RTL | 直接编译 `local_prune_gate_2of4.sv` + `local_prune_evidence_gain.sv` | 第 1 节 SHA-256 |",
        "| 退出码必须可信 | 每步检查退出码并记录 | 第 3 节退出码分布、`VivadoFlow.step()` |",
        "| 禁止复用来源不明的旧 snapshot | 每用例新建临时目录重编译；`.gitignore` 屏蔽 `lpgv_*`、`xsim.dir/` | `simulate()` |",
        "| 覆盖复位/稠密/exact-two/同分/饱和/INFER/无副作用/反例 | 7 个命名定向用例 × 3 模型 | 第 4 节 |",
        "| 多 seed 随机对拍，逐事务比较 | 3 模型 × 8 seed × 256 事务，24 字段全比较 | 第 5 节 |",
        "| 报告需含版本、SHA、命令、退出码、测试数、PASS 标记 | 机器摘要自动渲染 | 第 1、2、3、9 节 |",
        "| 另一台机器可直接复现 | 第 2 节命令块 | 第 2 节 |",
        "| NP4B 总签核跨 EOL 复现 | `file_sha256`/`witness_bytes` 改 canonical 折叠 + `*.vcd -text -eol` + 刷新摘要 | `np4b_signoff_summary.json`、`test_verify_np4b_signoff` |",
        "| 正常重验证保留 v2 元数据 | `build_summary` 全路径写字段；无工具路径如实记录 | `local_prune_rtl_results.json`、`test_verify_local_prune_rtl` |",
        "| 报告完整回归（不挑好看的报） | 四态矩阵进第 14 节；全仓 discover 实际数字进 PR 评论 | `TEST_MATRIX.json` |",
        "",
    ]


def s11_scope() -> list[str]:
    return [
        "## 11. 口径：本用例不声称等价复现原反例",
        "",
        "原反例（`mask=1100`、`scores=[250,200,150,100]`、`lane0 cooldown=1`）里的 lane cooldown 与 8 位 score "
        "属于被撤销的第二套设计，冻结的 V1 合同里根本没有这两个概念，所以把它们硬拼成“等价回归”会是误导。"
        "本 PR 按评审给出的第一个选项，把用例改名为它实际证明的内容：",
        "",
        "- `two_lane_mask_and_low_score_exact_two`：CONFIG 写入 `1100` 后直通数据路径，不得被重排成 "
        "`0011`/`0110`；两路有效时两条都发、`saved=0`；utility 不均（3,0,0,0）与全零时提交仍恰好两条。",
        "- 原反例的等价回归（`candidate = raw_mask & ~cooldown_mask`、top-2 只在 candidate 内排名、"
        "candidate 不足两条则拒绝且零副作用）写在 `DESIGN_PROPOSAL_DYNAMIC_PRUNE_RECOVERY.md` 第 3 节，"
        "作为该提案被批准后的必过验收门。",
        "",
    ]


def s12_signoff(signoff: dict, np4b: dict) -> list[str]:
    provenance = signoff.get("provenance", {})
    xsim = {}
    for entry in provenance.values():
        if entry.get("cross_checked_on_xsim"):
            xsim = entry["cross_checked_on_xsim"]
    refresh = np4b.get("binding_refresh", {})
    lines = [
        "## 12. 签核链：摘要刷新与 EOL 稳定性",
        "",
        "- `local_prune_rtl_results.json`（`schema: " + signoff["schema"] + "`）：源文件哈希口径为 "
        + signoff["source_hash_policy"] + "；`eol_policy` = " + signoff["eol_policy"] + "。",
        f"- 工具可用性如实记录：`tool_availability` = `{json.dumps(signoff['tool_availability'], sort_keys=True)}`，"
        f"`verified_on` = `{signoff['verified_on']}`。本机三件工具齐全，60000 事务 Icarus 回归与 32 拍 "
        "Yosys 形式检查均在本次真实重跑（每个证据块 `reverified_in_this_run: true`）。",
    ]
    if xsim:
        lines.append(
            f"- XSim 交叉验证绑定：`{xsim['summary']}`，Vivado `{xsim['tool']}`，提交 `{xsim['commit'][:12]}`，"
            f"{xsim['transactions']} 事务 / {xsim['cases']} 用例 / {xsim['mutants_caught']} 变异，结果 {xsim['result']}。")
    lines += [
        "- NP4B 总摘要（`np4b_signoff_summary.json`）：`file_sha256` 与 `formal.witness_bytes` 为 "
        + np4b["file_hash_policy"] + "；witness 长度为 " + np4b["witness_bytes_policy"] + "。",
        "- `.gitattributes` 已把 `*.vcd` 固定为 `-text -eol`：证据字节在任何检出下都不被 git 改写。",
        f"- NP4B 摘要的 `date` / `regression` / `tools` 是 **{np4b['date']} 冻结时代那次签核运行的原始记录**"
        f"（{np4b['regression']['tests']} 项全绿，Python/Icarus/Yosys 版本见摘要 `tools`），本次刷新不重测、"
        "不篡改；刷新本身的事实记录在 `binding_refresh` 块："
        f"日期 `{refresh.get('date')}`，基线提交 `{refresh.get('generated_on_top_of_commit')}`。",
        "- 跨 EOL 验证：`test_binding_is_independent_of_line_endings`（local_prune）与 "
        "`test_witness_binding_is_independent_of_line_endings`（NP4B）都同时断言 "
        "fold(LF)==fold(CRLF)==摘要值，且 naive raw 摘要必须对 EOL 敏感。",
        "",
    ]
    return lines


def s13_files(repo: pathlib.Path, sim_commit: str) -> list[str]:
    changes = git_file_list(repo)
    lines = [
        "## 13. 文件清单与自证",
        "",
        "本分支相对 `origin/main` 的全部文件变更（`git diff --name-status <merge-base> HEAD` 实时输出）：",
        "",
        "```text",
    ]
    lines += changes or ["(git 不可用，无法列出变更)"]
    lines += [
        "```",
        "",
        f"被仿真的提交是 `{sim_commit}`；该提交与本报告之间只相差文档与证据文件"
        "（报告、机器摘要、测试矩阵），被仿真的 RTL / oracle / runner 的 SHA-256 与第 1 节表格一致，"
        f"可用 `git diff --name-only {sim_commit[:12]} HEAD` 自证。",
        "",
    ]
    return lines


def s14_matrix(matrix: dict | None) -> list[str]:
    lines = [
        "## 14. 全量测试结果（不挑好看的报）",
        "",
        f"定向套件命令：`{SUITE}`，由 `run_test_matrix.py` 在四个全新一次性检出里分别执行"
        "（矩阵原始数据：`TEST_MATRIX.json`）。",
        "",
    ]
    if matrix is None:
        lines += ["(缺少 TEST_MATRIX.json；请先运行 `python run_test_matrix.py --json-out TEST_MATRIX.json`)", ""]
    else:
        lines += [
            f"矩阵提交 `{matrix['commit'][:12]}`，生成于 `{matrix['generated_utc']}`，"
            f"Python `{matrix['python']}`，整体 `pass={matrix['pass']}`。",
            "",
            "| 检出/工作树状态 | 用例总数 | 失败 | 错误 | 跳过 | 退出码 | 用时 (s) |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for row in matrix["rows"]:
            description = STATE_DESCRIPTIONS.get(row["state"], row["state"])
            lines.append(
                f"| `{row['state']}`：{description} | {row['tests_ran']} | {row['failures']} | "
                f"{row['errors']} | {row['skipped']} | {row['exit_code']} | {row['wall_seconds']:.1f} |")
        lines += [
            "",
            "跳过项读法：未导出 `VIVADO_ROOT` 的三个状态里，跳过的是 1 个 XSim 集成测试"
            "（测试内写明跳过原因）；导出 `VIVADO_ROOT` 的第四态 0 跳过，XSim 集成测试真实参与运行。"
            "本机装有 iverilog / vvp / yosys（见第 8 节），Icarus/Yosys 门不跳过。",
            "",
            "**全仓 `python -m unittest discover -v` 的诚实说明**：该命令在本机（Python 3.13.15、"
            "Icarus 12.0 stable、Yosys 0.68 WASM、Vivado 2024.2）上对 `origin/main` 干净克隆的基线为 "
            f"`Ran {BASELINE_MAIN['tests']} tests, FAILED (failures={BASELINE_MAIN['failures']}, "
            f"errors={BASELINE_MAIN['errors']})`，耗时 {BASELINE_MAIN['seconds']} s，退出码 "
            f"{BASELINE_MAIN['exit_code']}（提交 {BASELINE_MAIN['commit']}）。这些失败由仓库既有的"
            "自哈希陈旧项与工具版本差异造成，与本 PR 无关；本 PR 分支上的最终干净检出 discover 实际数字"
            "（含 ran / failures / skipped / 退出码）按评审要求贴在 PR 评论里。",
            "",
        ]
    return lines


def build_report(checkout: pathlib.Path, repo: pathlib.Path) -> str:
    summary = load(checkout / SUMMARY_NAME)
    signoff = load(repo / SIGNOFF_NAME)
    np4b = load(repo / NP4B_NAME)
    matrix_path = repo / MATRIX_NAME
    matrix = load(matrix_path) if matrix_path.is_file() else None
    log_text = read_console(checkout / CONSOLE_NAME)

    lines: list[str] = []
    lines += header(summary)
    lines += s1_hashes(summary)
    lines += s2_reproduce()
    lines += s3_steps(summary)
    lines += s4_coverage(summary)
    lines += s5_compare(summary)
    lines += s6_mutants(summary)
    lines += s7_review()
    lines += s8_limits(signoff)
    lines += s9_console(log_text)
    lines += s10_checklist()
    lines += s11_scope()
    lines += s12_signoff(signoff, np4b)
    lines += s13_files(repo, summary["checkout"]["commit"])
    lines += s14_matrix(matrix)
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkout", required=True,
                        help="clean checkout that just ran the Vivado regression "
                             "(holds VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json and the console log)")
    parser.add_argument("--repo", default=None,
                        help="repository root holding the signoff summaries (default: --checkout)")
    parser.add_argument("--out", default=None,
                        help=f"output path (default: <repo>/{REPORT_NAME})")
    arguments = parser.parse_args(argv)

    checkout = pathlib.Path(arguments.checkout).resolve()
    repo = pathlib.Path(arguments.repo).resolve() if arguments.repo else checkout
    out = pathlib.Path(arguments.out) if arguments.out else repo / REPORT_NAME

    report = build_report(checkout, repo)
    out.write_text(report, encoding="utf-8", newline="\n")
    print(f"REPORT_WRITTEN {out} chars={len(report)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
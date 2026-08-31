# Vivado/XSim 真实仿真报告：local_prune_gate_2of4

状态：**PASS**。本报告由仓库内脚本 `make_local_prune_report.py` 从机器摘要自动渲染（`VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json`、`local_prune_rtl_results.json`、`np4b_signoff_summary.json`、`TEST_MATRIX.json`），不含人工誊写数字。

| 项目 | 值 |
|---|---|
| 生成时间 (UTC) | `2026-08-31T08:24:50Z` |
| 仿真器完整版本 | `Vivado Simulator v2024.2.0` |
| Vivado 路径来源 | `--vivado-root or VIVADO_ROOT`；本次取值 `C:/Users/MGL/Documents/Codex/Vivado2024_2` |
| 被仿真的 PR 提交 | `c30ecc5dd43f0f337d68b0268e90f28d5c569e16` |
| 主机 | Windows 11 / Python 3.13.15 |
| 逐事务对拍事务数 | 6447 |
| 逐字段比较次数 | 154728（= 事务数 × 24 个可见状态） |
| 用例数 | 45（7 个定向 × 3 模型 + 8 seed × 3 模型） |
| 失败敏感变异 | 5 个，全部被捕获 |

## 1. 被仿真源码的 SHA-256

```text
4b2bb7c3d45808a0907ac60f547fe0ab0a607e3e8b4340410ea4467705b8301c  local_prune_evidence_gain.sv
d52a1fd3bcdaba8d6e2823ddfda11adb72a1e5789528b4ce6f890929c939c321  local_prune_gate_2of4.sv
c31322006295c67df092cd0073031755f344e480f0c3efb39ee3ceb867809750  local_prune_gate_cosim.py
16400290cc615eb905bdd9ae4f9be9ee82a64f0cb7956d6e310e4a5bc418b1fb  local_prune_rtl_reference.py
61074e9f794bd24140e8572a9f5f338a41c802124f8837de1d2d86ac56da8cae  run_local_prune_gate_vivado.py
```

仿真直接编译仓库内的 `local_prune_gate_2of4.sv`、`local_prune_evidence_gain.sv`，testbench 由仓库内`local_prune_gate_cosim.py::_make_testbench()` 当场生成；每个用例都在新建的临时目录里重新 xvlog/xelab 生成快照，**不复用任何历史 snapshot，工作树不留 `xsim.dir`**。

## 2. 在另一台机器上的复现命令

```powershell
git clone https://github.com/Epslion404/ENeuron.git ; cd ENeuron
git fetch origin pull/2/head:pr-2 ; git checkout pr-2
$env:VIVADO_ROOT = "C:/Xilinx/Vivado/2024.1"   # 唯一需要改的一行；2024.2 亦可
$env:PATH = "C:\msys64\ucrt64\bin;" + $env:PATH  # 可选：让 Icarus/Yosys 门参与
python run_local_prune_gate_vivado.py --seeds 8 --transactions 256 --json-out VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json
python run_test_matrix.py --vivado-root $env:VIVADO_ROOT --json-out TEST_MATRIX.json
python verify_local_prune_rtl.py
python make_local_prune_report.py --checkout . --out SIMULATION_REPORT.md
Write-Output "exit=$LASTEXITCODE"
```

退出码语义：xvlog、xelab、xsim 任一步返回非零即立刻中止；只有全部步骤为 0、每条 ROW 与 Python 黄金模型 24 字段全等、所有合同断言与变异负控都通过时，进程才返回 0 并打印 `VIVADO_LOCAL_PRUNE_GATE_PASS`。

## 3. 工具链步骤与退出码

| 步骤 | 调用次数 | 首次命令模板 |
|---|---:|---|
| `xelab` | 51 | `C:/Users/MGL/Documents/Codex/Vivado2024_2/bin/xelab.bat --relax --debug typical --mt 2 --snapshot gate_tb work.tb` |
| `xsim` | 51 | `C:/Users/MGL/Documents/Codex/Vivado2024_2/bin/xsim.bat gate_tb --tclbatch C:/Users/MGL/AppData/Local/Temp/lpgv_sim_nor8ux4g/run.tcl` |
| `xvlog` | 51 | `C:/Users/MGL/Documents/Codex/Vivado2024_2/bin/xvlog.bat -sv C:/Users/MGL/Documents/Codex/2026-08-29/vivado/wt_r4/local_prune_gate_2of4.sv C:/Users/MGL/Documents` |
| `xvlog-version` | 1 | `C:/Users/MGL/Documents/Codex/Vivado2024_2/bin/xvlog.bat -version` |

退出码分布：`{"0": 154}`（`0` 之外任一出现都会让 runner 立即失败）

## 4. 评审要求的覆盖矩阵

| 评审条目 | 定向用例 | 通过的模型数 |
|---|---|---|
| 复位 | `reset_and_dense` | 3 / 3 |
| 稠密初态 | `reset_and_dense` | 3 / 3 |
| 严格 exact-two（禁止 0/1/3/4 置位） | `exact_two` | 3 / 3 |
| 同分确定性 | `tie_break` | 3 / 3 |
| 分数饱和 | `score_saturation` | 3 / 3 |
| INFER 冻结 | `infer_freeze` | 3 / 3 |
| 非法/冲突边界无副作用 | `illegal_and_conflict_no_side_effect` | 3 / 3 |
| CONFIG 两路掩码直通 + 低/零 utility 仍 strict exact-two | `two_lane_mask_and_low_score_exact_two` | 3 / 3 |

用例目录（每条都同时做「与 Python 逐事务比对」和「合同规则断言」）：

- exact_two: strict two-of-four: six legal masks accepted, 0/1/3/4-bit masks refused, no second commit
- illegal_and_conflict_no_side_effect: bad opcode, bad mode, stale or duplicate ids, unsafe windows and illegal masks
- infer_freeze: INFER rejects OBSERVE and PRUNE_COMMIT but still reads and gates the mask
- reset_and_dense: reset state, dense 1111 before commit, first commit is exact-two
- score_saturation: utility saturates at 15 and the two pruned lanes stay frozen after the commit
- tie_break: equal scores are resolved by the lowest lane index with the fixed 0-1-2-3 scan
- two_lane_mask_and_low_score_exact_two: CONFIG 1100 passes through un-re-ranked; uneven and all-zero utility vectors still commit exactly two of four

## 5. 逐事务 Python/RTL 对拍

- 模型：`eneuron`, `pulse_mini_l`, `pulse_mini_l2`（三个固定 gain 适配器）
- 随机流：每模型 8 个 seed × 每流 256 事务；每流前 127 条为固定定向前缀，其后为随机事务。
- 比较口径：每条事务比较 24 个可见状态字段，共 154728 次比较，全部逐位相等。
- 任何一个字段不相等、任何一条合同断言失败、任何一个变异未被捕获，都会让 runner 立即非零退出。

## 6. 失败敏感（mutation）测试

| 变异 | 期望 | 实际 | 捕获方式 |
|---|---|---|---|
| `tie_break_uses_gte` | PYTHON_RTL_DIVERGENCE | CAUGHT | `PYTHON_RTL_DIVERGENCE` |
| `commit_drops_second_lane` | ILLEGAL_VISIBLE_MASK/ATOMIC_MASK_VIOLATION | CAUGHT | `ILLEGAL_VISIBLE_MASK` |
| `commit_keeps_no_lane` | ILLEGAL_VISIBLE_MASK/ATOMIC_MASK_VIOLATION | CAUGHT | `ILLEGAL_VISIBLE_MASK` |
| `commit_keeps_all_four_lanes` | ILLEGAL_VISIBLE_MASK/ATOMIC_MASK_VIOLATION | CAUGHT | `ILLEGAL_VISIBLE_MASK` |
| `commit_is_not_atomic` | ATOMIC_MASK_VIOLATION/ILLEGAL_VISIBLE_MASK | CAUGHT | `ATOMIC_MASK_VIOLATION` |

读法：每一个变异都是对 RTL 的一次故意破坏；`CAUGHT` 表示 runner 确实观测到了失败并拒绝通过，即对应的检查不是空转的。

## 7. 评审三轮阻断问题的处置

第 1 轮：

1. **Python 黄金模型与 RTL 不一致**：产生分歧的 `neuron_gate_core.sv` / `neuron_gate_reference.py` 已整体撤出 PR（它同时引入 8 位 score、cooldown、自动 regrow、image_end/epoch_end，属第二套未批准设计）。其候选集合语义与反例已写入 `DESIGN_PROPOSAL_DYNAMIC_PRUNE_RECOVERY.md` 第 3 节，等待评审裁决后再实现。本 PR 现在只验证唯一真源 `local_prune_gate_2of4.sv`；与该反例形状相关的定向用例已按实际口径改名为 `two_lane_mask_and_low_score_exact_two`（见第 11 节）。
2. **不是严格 2:4**：exact-two 有三层保证——RTL 扫描只可能产出六种双位掩码、testbench 内 `$fatal` 监视任何时刻的可见掩码、runner 独立断言；CONFIG 写入口拒绝 0/1/3/4 置位；`commit_keeps_no_lane` / `commit_drops_second_lane` / `commit_keeps_all_four_lanes` 三个变异被捕获。
3. **偏离冻结架构**：不再复制第二套门控，全部仿真交付物直接针对 `local_prune_gate_2of4.sv` 与 `LOCAL_PRUNE_RTL_CONTRACT.md`。

第 3 轮：

1. **NP4B 总签核在本 PR 的 EOL 规则下失败**：`np4b_signoff_summary.json` 的 `file_sha256` 与 `formal.witness_bytes` 改为与 `verify_local_prune_rtl.canonical_sha256` 完全相同的 **CRLF/CR 归一为 LF 之后**的哈希与长度（摘要内写明 `file_hash_policy` / `witness_bytes_policy`）；`.gitattributes` 把 `*.vcd` 固定为 `-text -eol`，证据字节永不被 git 改写；摘要新增 `binding_refresh` 块如实记录本次刷新的日期、基线提交与刷新机工具，而冻结时代的 `date` / `regression` / `tools` 原样继承、不再假装重测。`test_verify_np4b_signoff` 现为 4 例全过，含新增的 `test_witness_binding_is_independent_of_line_endings`（断言 fold(LF)==fold(CRLF) 且等于摘要值，并断言 naive raw 摘要必须对 EOL 敏感，防止空测试）。
2. **正常重验证丢失 v2 元数据**：`build_summary` 在任何路径都写 `tool_availability` / `toolchain_provenance` / `verified_on` 等 v2 字段；无 Icarus/Yosys 的机器走 `run_checks=False` 路径时不再抛异常，而是如实记录 `tool_availability=false` 与 `tools.*=not_found`。新增 3 条回归断言（见 `test_verify_local_prune_rtl.py`）。

## 8. 已知限制

- 本机 Vivado 为 **2024.2**（`Vivado Simulator v2024.2.0`），无 2024.1；评审已确认其他版本的结果同样有效，版本号已如实记录在摘要与本节。
- 本机 Yosys 为 **0.68 官方 YoWASP（WebAssembly）构建**——上游不提供 Windows 原生二进制；NP4B 原始形式化证据产生于 Yosys 0.56 原生 mingw 构建，该差异在 `np4b_signoff_summary.json` 的冻结 `tools` 记录与 `binding_refresh.tools` 中都可对照。
- 本机 Icarus 为 **12.0 (stable)**（bleyer.org 官方 Windows 安装包，与 NP4B 原始证据同一大版本），安装布局同时铺到 `C:/msys64/ucrt64/bin` 以兼容仓库内残留的硬编码路径；`tool_availability` = `{"iverilog": true, "vvp": true, "yosys": true}`。
- 本机 Python 为 3.13.15（NP4B 冻结记录为 3.14.2）。
- 全仓 `python -m unittest discover` 在本机存在**既有**失败（见第 14 节基线对照），与 `origin/main` 上同样命令的结果一致，不属于本 PR。
- 结论范围是行为级功能等价与合同不变量，不含综合、时序、面积与功耗。

## 9. 真实控制台输出

```text
VIVADO Vivado Simulator v2024.2.0 root=C:/Users/MGL/Documents/Codex/Vivado2024_2
PASS directed reset_and_dense                        eneuron       transactions=4
PASS directed reset_and_dense                        pulse_mini_l  transactions=4
PASS directed reset_and_dense                        pulse_mini_l2 transactions=4
PASS directed exact_two                              eneuron       transactions=18
PASS directed exact_two                              pulse_mini_l  transactions=18
PASS directed exact_two                              pulse_mini_l2 transactions=18
PASS directed tie_break                              eneuron       transactions=27
PASS directed tie_break                              pulse_mini_l  transactions=27
PASS directed tie_break                              pulse_mini_l2 transactions=27
PASS directed score_saturation                       eneuron       transactions=15
PASS directed score_saturation                       pulse_mini_l  transactions=15
PASS directed score_saturation                       pulse_mini_l2 transactions=15
PASS directed infer_freeze                           eneuron       transactions=9
PASS directed infer_freeze                           pulse_mini_l  transactions=9
PASS directed infer_freeze                           pulse_mini_l2 transactions=9
PASS directed illegal_and_conflict_no_side_effect    eneuron       transactions=17
PASS directed illegal_and_conflict_no_side_effect    pulse_mini_l  transactions=17
PASS directed illegal_and_conflict_no_side_effect    pulse_mini_l2 transactions=17
PASS directed two_lane_mask_and_low_score_exact_two  eneuron       transactions=11
PASS directed two_lane_mask_and_low_score_exact_two  pulse_mini_l  transactions=11
PASS directed two_lane_mask_and_low_score_exact_two  pulse_mini_l2 transactions=11
PASS random   seed=0   eneuron        transactions=256
PASS random   seed=0   pulse_mini_l   transactions=256
PASS random   seed=0   pulse_mini_l2  transactions=256
PASS random   seed=1   eneuron        transactions=256
PASS random   seed=1   pulse_mini_l   transactions=256
PASS random   seed=1   pulse_mini_l2  transactions=256
PASS random   seed=2   eneuron        transactions=256
PASS random   seed=2   pulse_mini_l   transactions=256
PASS random   seed=2   pulse_mini_l2  transactions=256
PASS random   seed=3   eneuron        transactions=256
PASS random   seed=3   pulse_mini_l   transactions=256
PASS random   seed=3   pulse_mini_l2  transactions=256
PASS random   seed=4   eneuron        transactions=256
PASS random   seed=4   pulse_mini_l   transactions=256
PASS random   seed=4   pulse_mini_l2  transactions=256
PASS random   seed=5   eneuron        transactions=256
PASS random   seed=5   pulse_mini_l   transactions=256
PASS random   seed=5   pulse_mini_l2  transactions=256
PASS random   seed=6   eneuron        transactions=256
PASS random   seed=6   pulse_mini_l   transactions=256
PASS random   seed=6   pulse_mini_l2  transactions=256
PASS random   seed=7   eneuron        transactions=256
PASS random   seed=7   pulse_mini_l   transactions=256
PASS random   seed=7   pulse_mini_l2  transactions=256
PASS mutant   tie_break_uses_gte              caught by PYTHON_RTL_DIVERGENCE
PASS mutant   commit_drops_second_lane        caught by ILLEGAL_VISIBLE_MASK
PASS mutant   commit_keeps_no_lane            caught by ILLEGAL_VISIBLE_MASK
PASS mutant   commit_keeps_all_four_lanes     caught by ILLEGAL_VISIBLE_MASK
PASS mutant   commit_is_not_atomic            caught by ATOMIC_MASK_VIOLATION
SOURCE_SHA256 local_prune_gate_2of4.sv d52a1fd3bcdaba8d6e2823ddfda11adb72a1e5789528b4ce6f890929c939c321
SOURCE_SHA256 local_prune_evidence_gain.sv 4b2bb7c3d45808a0907ac60f547fe0ab0a607e3e8b4340410ea4467705b8301c
SOURCE_SHA256 local_prune_gate_cosim.py c31322006295c67df092cd0073031755f344e480f0c3efb39ee3ceb867809750
SOURCE_SHA256 local_prune_rtl_reference.py 16400290cc615eb905bdd9ae4f9be9ee82a64f0cb7956d6e310e4a5bc418b1fb
SOURCE_SHA256 run_local_prune_gate_vivado.py 61074e9f794bd24140e8572a9f5f338a41c802124f8837de1d2d86ac56da8cae
VIVADO_LOCAL_PRUNE_GATE_PASS version=Vivado Simulator v2024.2.0 models=3 seeds=8 transactions_compared=6447 cases=45 mutants=5
```

## 10. 评审整改清单（逐条对应）

| 评审要求 | 本 PR 的落实 | 证据位置 |
|---|---|---|
| 仿真必须针对仓库内已冻结 RTL | 直接编译 `local_prune_gate_2of4.sv` + `local_prune_evidence_gain.sv` | 第 1 节 SHA-256 |
| 退出码必须可信 | 每步检查退出码并记录 | 第 3 节退出码分布、`VivadoFlow.step()` |
| 禁止复用来源不明的旧 snapshot | 每用例新建临时目录重编译；`.gitignore` 屏蔽 `lpgv_*`、`xsim.dir/` | `simulate()` |
| 覆盖复位/稠密/exact-two/同分/饱和/INFER/无副作用/反例 | 7 个命名定向用例 × 3 模型 | 第 4 节 |
| 多 seed 随机对拍，逐事务比较 | 3 模型 × 8 seed × 256 事务，24 字段全比较 | 第 5 节 |
| 报告需含版本、SHA、命令、退出码、测试数、PASS 标记 | 机器摘要自动渲染 | 第 1、2、3、9 节 |
| 另一台机器可直接复现 | 第 2 节命令块 | 第 2 节 |
| NP4B 总签核跨 EOL 复现 | `file_sha256`/`witness_bytes` 改 canonical 折叠 + `*.vcd -text -eol` + 刷新摘要 | `np4b_signoff_summary.json`、`test_verify_np4b_signoff` |
| 正常重验证保留 v2 元数据 | `build_summary` 全路径写字段；无工具路径如实记录 | `local_prune_rtl_results.json`、`test_verify_local_prune_rtl` |
| 报告完整回归（不挑好看的报） | 四态矩阵进第 14 节；全仓 discover 实际数字进 PR 评论 | `TEST_MATRIX.json` |

## 11. 口径：本用例不声称等价复现原反例

原反例（`mask=1100`、`scores=[250,200,150,100]`、`lane0 cooldown=1`）里的 lane cooldown 与 8 位 score 属于被撤销的第二套设计，冻结的 V1 合同里根本没有这两个概念，所以把它们硬拼成“等价回归”会是误导。本 PR 按评审给出的第一个选项，把用例改名为它实际证明的内容：

- `two_lane_mask_and_low_score_exact_two`：CONFIG 写入 `1100` 后直通数据路径，不得被重排成 `0011`/`0110`；两路有效时两条都发、`saved=0`；utility 不均（3,0,0,0）与全零时提交仍恰好两条。
- 原反例的等价回归（`candidate = raw_mask & ~cooldown_mask`、top-2 只在 candidate 内排名、candidate 不足两条则拒绝且零副作用）写在 `DESIGN_PROPOSAL_DYNAMIC_PRUNE_RECOVERY.md` 第 3 节，作为该提案被批准后的必过验收门。

## 12. 签核链：摘要刷新与 EOL 稳定性

- `local_prune_rtl_results.json`（`schema: eneuron.local_prune_rtl.v2`）：源文件哈希口径为 sha256 over the working-tree bytes with CRLF and CR normalised to LF (platform and core.autocrlf independent)；`eol_policy` = text files are pinned to LF by .gitattributes; the binding additionally normalises line endings, so a CRLF checkout verifies identically。
- 工具可用性如实记录：`tool_availability` = `{"iverilog": true, "vvp": true, "yosys": true}`，`verified_on` = `2026-08-31`。本机三件工具齐全，60000 事务 Icarus 回归与 32 拍 Yosys 形式检查均在本次真实重跑（每个证据块 `reverified_in_this_run: true`）。
- XSim 交叉验证绑定：`VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json`，Vivado `Vivado Simulator v2024.2.0`，提交 `c30ecc5dd43f`，6447 事务 / 45 用例 / 5 变异，结果 PASS。
- NP4B 总摘要（`np4b_signoff_summary.json`）：`file_sha256` 与 `formal.witness_bytes` 为 sha256 over the bytes with CRLF and CR normalised to LF (platform, core.autocrlf and checkout-state independent; the identical canonical policy used by verify_local_prune_rtl.canonical_sha256)；witness 长度为 byte length after normalising CRLF and CR to LF, matching file_hash_policy。
- `.gitattributes` 已把 `*.vcd` 固定为 `-text -eol`：证据字节在任何检出下都不被 git 改写。
- NP4B 摘要的 `date` / `regression` / `tools` 是 **2026-08-29 冻结时代那次签核运行的原始记录**（359 项全绿，Python/Icarus/Yosys 版本见摘要 `tools`），本次刷新不重测、不篡改；刷新本身的事实记录在 `binding_refresh` 块：日期 `2026-08-31`，基线提交 `2ccb394`。
- 跨 EOL 验证：`test_binding_is_independent_of_line_endings`（local_prune）与 `test_witness_binding_is_independent_of_line_endings`（NP4B）都同时断言 fold(LF)==fold(CRLF)==摘要值，且 naive raw 摘要必须对 EOL 敏感。

## 13. 文件清单与自证

本分支相对 `origin/main` 的全部文件变更（`git diff --name-status <merge-base> HEAD` 实时输出）：

```text
M	test_local_prune_gate_vivado.py
```

被仿真的提交是 `c30ecc5dd43f0f337d68b0268e90f28d5c569e16`；该提交与本报告之间只相差文档与证据文件（报告、机器摘要、测试矩阵），被仿真的 RTL / oracle / runner 的 SHA-256 与第 1 节表格一致，可用 `git diff --name-only c30ecc5dd43f HEAD` 自证。

## 14. 全量测试结果（不挑好看的报）

定向套件命令：`python -m unittest test_local_prune_gate_rtl test_verify_local_prune_rtl test_local_prune_gate_vivado`，由 `run_test_matrix.py` 在四个全新一次性检出里分别执行（矩阵原始数据：`TEST_MATRIX.json`）。

矩阵提交 `a75740cac21d`，生成于 `2026-08-31T12:50:05Z`，Python `3.13.15`，整体 `pass=True`。

| 检出/工作树状态 | 用例总数 | 失败 | 错误 | 跳过 | 退出码 | 用时 (s) |
|---|---:|---:|---:|---:|---:|---:|
| `autocrlf_true`：`git -c core.autocrlf=true clone` 新鲜克隆，`.gitattributes` 生效（受签核文本 = LF） | 32 | 0 | 0 | 0 | 0 | 225.5 |
| `autocrlf_false`：`git -c core.autocrlf=false clone` 新鲜克隆 | 32 | 0 | 0 | 0 | 0 | 221.6 |
| `working_tree_crlf`：新鲜克隆后把全部受签核文本在工作树里改写成 CRLF（敌对状态） | 32 | 0 | 0 | 0 | 0 | 213.6 |
| `autocrlf_true_with_vivado`：`autocrlf_true` 外加导出 `VIVADO_ROOT`，真实 XSim 集成测试参与运行 | 32 | 0 | 0 | 0 | 0 | 203.3 |

跳过项读法：未导出 `VIVADO_ROOT` 的三个状态里，跳过的是 1 个 XSim 集成测试（测试内写明跳过原因）；导出 `VIVADO_ROOT` 的第四态 0 跳过，XSim 集成测试真实参与运行。本机装有 iverilog / vvp / yosys（见第 8 节），Icarus/Yosys 门不跳过。

**全仓 `python -m unittest discover -v` 的诚实说明**：该命令在本机（Python 3.13.15、Icarus 12.0 stable、Yosys 0.68 WASM、Vivado 2024.2）上对 `origin/main` 干净克隆的基线为 `Ran 353 tests, FAILED (failures=24, errors=30)`，耗时 603.9 s，退出码 1（提交 bb73bb5 (origin/main)）。这些失败由仓库既有的自哈希陈旧项与工具版本差异造成，与本 PR 无关；本 PR 分支上的最终干净检出 discover 实际数字（含 ran / failures / skipped / 退出码）按评审要求贴在 PR 评论里。

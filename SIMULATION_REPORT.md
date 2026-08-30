# Vivado/XSim 真实仿真报告：local_prune_gate_2of4

状态：**PASS**。本报告由 `run_local_prune_gate_vivado.py` 生成的机器摘要(`VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json`) 自动渲染，不含人工誊写数字。

| 项目 | 值 |
|---|---|
| 生成时间 (UTC) | `2026-08-30T13:35:57Z` |
| 仿真器完整版本 | `Vivado Simulator v2024.2.0` |
| Vivado 路径来源 | `--vivado-root or VIVADO_ROOT`；本次取值 `C:/Users/MGL/Documents/Codex/Vivado2024_2` |
| 被仿真的 PR 提交 | `ee4b9ff67c08adb538f81cc5a5b48c49d13f34ca` |
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
git fetch origin pull/1/head:pr-1 ; git checkout pr-1
$env:VIVADO_ROOT = "C:/Xilinx/Vivado/2024.1"   # 唯一需要改的一行；也支持 --vivado-root / XILINX_VIVADO / PATH
python run_local_prune_gate_vivado.py --seeds 8 --transactions 256 --json-out VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json
Write-Output "exit=$LASTEXITCODE"
python -m unittest test_local_prune_gate_vivado -v
```

退出码语义：xvlog、xelab、xsim 任一步返回非零即立刻中止；只有全部步骤为 0、每条 ROW 与 Python 黄金模型 24 字段全等、所有合同断言与变异负控都通过时，进程才返回 0 并打印 `VIVADO_LOCAL_PRUNE_GATE_PASS`。

## 3. 工具链步骤与退出码

| 步骤 | 调用次数 | 首次命令模板 |
|---|---:|---|
| `xelab` | 51 | `C:/Users/MGL/Documents/Codex/Vivado2024_2/bin/xelab.bat --relax --debug typical --mt 2 --snapshot gate_tb work.tb` |
| `xsim` | 51 | `C:/Users/MGL/Documents/Codex/Vivado2024_2/bin/xsim.bat gate_tb --tclbatch C:/Users/MGL/AppData/Local/Temp/lpgv_sim_wb3751j8/run.tcl` |
| `xvlog` | 51 | `C:/Users/MGL/Documents/Codex/Vivado2024_2/bin/xvlog.bat -sv C:/Users/MGL/Documents/Codex/2026-08-29/vivado/wt_ac_true/local_prune_gate_2of4.sv C:/Users/MGL/Docu` |
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
- 随机流：每模型 8 个 seed × 每流 256 事务；每流前 127 条为固定定向前缀，其后为随机的命令 / CONFIG 写 / issue 混合流。
- 逐事务比较的 24 个可见状态：命令种类、响应状态、响应 ID、响应掩码、CONFIG 错误、四路 utility、结构掩码、mask-valid、last observation/commit ID 与 valid、提交数、非法命令数、hidden/output 的 dense/issued/ops/saved 计数、inactive/skipped 计数。
- V1 合同里没有 cooldown 与 candidate 状态（8 位 score / lane cooldown / 自动 regrow 属被撤销的第二套设计，见提案文档），因此对拍字段以 V1 可见协议状态为准。
- RTL 输出行数与提交事务数严格相等，并要求 testbench 末尾的 `TB_COMPLETE transactions=N` 哨兵出现，任何提前 `$fatal` 都会被判失败。

## 6. 失败敏感（mutation）测试

| 变异 | 检测手段 | 结果 |
|---|---|---|
| `tie_break_uses_gte` | `PYTHON_RTL_DIVERGENCE` | CAUGHT |
| `commit_drops_second_lane` | `ILLEGAL_VISIBLE_MASK` | CAUGHT |
| `commit_keeps_no_lane` | `ILLEGAL_VISIBLE_MASK` | CAUGHT |
| `commit_keeps_all_four_lanes` | `ILLEGAL_VISIBLE_MASK` | CAUGHT |
| `commit_is_not_atomic` | `ATOMIC_MASK_VIOLATION` | CAUGHT |

若某个变异没有被捕获，runner 以 `MUTANT_SURVIVED` 立即失败，保证这些检查不会退化成空测试。

## 7. 评审三条阻断问题的处置

1. **Python 黄金模型与 RTL 不一致**：产生分歧的 `neuron_gate_core.sv` / `neuron_gate_reference.py` 已整体撤出 PR（它同时引入 8 位 score、cooldown、自动 regrow、image_end/epoch_end，属第二套未批准设计）。其候选集合语义与反例已写入 `DESIGN_PROPOSAL_DYNAMIC_PRUNE_RECOVERY.md` 第 3 节，等待评审裁决后再实现。本 PR 现在只验证唯一真源 `local_prune_gate_2of4.sv`；与该反例形状相关的定向用例已按实际口径改名为 `two_lane_mask_and_low_score_exact_two`（见第 11 节），原反例的等价回归定义在提案文档里，待批准后作为验收门。
2. **不是严格 2:4**：exact-two 有三层保证——RTL 扫描只可能产出六种双位掩码、testbench 内 `$fatal` 监视任何时刻的可见掩码、runner 独立断言；CONFIG 写入口拒绝 0/1/3/4 置位；`commit_keeps_no_lane` / `commit_drops_second_lane` / `commit_keeps_all_four_lanes` 三个变异被捕获，证明该检查是失败敏感的。
3. **偏离冻结架构**：不再复制第二套门控，全部仿真交付物直接针对 `local_prune_gate_2of4.sv` 与 `LOCAL_PRUNE_RTL_CONTRACT.md`。

## 8. 已知限制

- 本机 Vivado 为 **2024.2**（`Vivado Simulator v2024.2.0`）。runner 与用例里没有版本或路径硬编码，把 `VIVADO_ROOT` 指向 2024.1 即可原样复现；若评审要求 2024.1 的逐字节证据，请在装有 2024.1 的机器上执行第 2 节命令并回填本报告与 JSON。
- 本机未安装 Icarus Verilog，`test_local_prune_gate_rtl.py`（Python/Icarus 门）在本机跳过；本报告只提供 XSim 证据。
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

| 评审要求 | 处置 | 证据 |
|---|---|---|
| runner 不得硬编码 `C:\Users\MGL\...` | 路径来自 `--vivado-root` / `VIVADO_ROOT` / `XILINX_VIVADO` / `PATH` | `resolve_vivado_root()`、`test_local_prune_gate_vivado.RunnerPlumbingTest` |
| xvlog → xelab → xsim，任一步失败立即非零 | 每步检查退出码并记录 | 第 3 节退出码分布、`VivadoFlow.step()` |
| 禁止复用来源不明的旧 snapshot | 每用例新建临时目录重编译；`.gitignore` 屏蔽 `lpgv_*`、`xsim.dir/` | `simulate()` |
| 覆盖复位/稠密/exact-two/同分/饱和/INFER/无副作用/反例 | 7 个命名定向用例 × 3 模型 | 第 4 节 |
| 多 seed 随机对拍，逐事务比较 | 3 模型 × 8 seed × 256 事务，24 字段全比较 | 第 5 节 |
| 报告需含版本、SHA、命令、退出码、测试数、PASS 标记 | 机器摘要自动渲染 | 第 1、2、3、9 节 |
| 另一台机器可直接复现 | 第 2 节命令块 | 第 2 节 |
| 删除生成物与机器文件 | 见第 11 节删除清单 | 提交 `git rm` 记录 |
| 修复 `git diff --check` 行尾空格 | 新增/修改文件统一 LF、无行尾空白、无 BOM；提交前 `git diff --check origin/main...HEAD` 通过 | 本提交 |
| known_hosts 畸形文件（`UsersMGL...known_hosts`） | 根因是 Vivado 把参数交给 Tcl 时吞掉反斜杠（同类问题也会让 `xsim --tclbatch C:\...` 失败）；runner 一律使用正斜杠路径，删除该文件并在 `.gitignore` 加防护 | `.gitignore`、`RunnerPlumbingTest.test_every_tool_argument_uses_forward_slashes` |

## 11. 口径：本用例不声称等价复现原反例

原反例（`mask=1100`、`scores=[250,200,150,100]`、`lane0 cooldown=1`）里的 lane cooldown 与 8 位 score
属于被撤销的第二套设计，冻结的 V1 合同里根本没有这两个概念，所以把它们硬拼成“等价回归”会是误导。
本 PR 按评审给出的第一个选项，把用例改名为它实际证明的内容：

- `two_lane_mask_and_low_score_exact_two`：CONFIG 写入 `1100` 后直通数据路径，不得被重排成
  `0011`/`0110`；两路有效时两条都发、`saved=0`；utility 不均（3,0,0,0）与全零时提交仍恰好两条。
- 原反例的等价回归（`candidate = raw_mask & ~cooldown_mask`、top-2 只在 candidate 内排名、
  candidate 不足两条则拒绝且零副作用）写在 `DESIGN_PROPOSAL_DYNAMIC_PRUNE_RECOVERY.md` 第 3 节，
  作为该提案被批准后的必过验收门。

## 12. 签核链：摘要刷新与 EOL 稳定性

- `local_prune_rtl_results.json` 升级到 `schema: eneuron.local_prune_rtl.v2`：源文件哈希改为
  **先把 CRLF/CR 归一为 LF 再取 sha256**（见 `source_hash_policy`），因此与 `core.autocrlf`
  和平台无关；同时新增 `.gitattributes` 把受签核文本固定为 LF。
- 摘要保留 `previous_signature`（2026-08-29 v1 哈希）与 `source_changes_since_previous_signature`，
  并用 `provenance` 逐个证据块声明：哪些输入变了、本机有没有重跑、重跑命令是什么。
  未重跑必须给出 `reason` + `reverify_command`，否则 `test_moved_sources_cannot_silently_rebind_evidence` 失败。
- **Yosys 形式化证据的全部输入文件哈希未变**（逐文件可比），因此形式化结论属合法继承而非陈旧；
  变化的只有 `local_prune_gate_cosim.py` 与本轮修复的 verify/test 入口。
- 本机没有 iverilog/vvp 与 yosys（`tool_availability` 如实记录），所以 60000 事务 Icarus 回归在
  本机**未**重跑；作为交叉验证，同一个 testbench 生成器产生的流在 XSim 上逐事务全部复现。
- 一键刷新绑定：`python verify_local_prune_rtl.py --refresh-signature`；
  在装有 iverilog + yosys 的机器上用 `python verify_local_prune_rtl.py` 重新生成全部证据。

## 13. 文件清单与自证

- 新增：`run_local_prune_gate_vivado.py`、`test_local_prune_gate_vivado.py`、`DESIGN_PROPOSAL_DYNAMIC_PRUNE_RECOVERY.md`、`VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json`
- 修改：`local_prune_gate_cosim.py`（testbench 缺省命令文件 + `TB_COMPLETE` 哨兵，Icarus 与 XSim 共用同一份生成器）、`.gitignore`、`SIMULATION_REPORT.md`
- 删除：`neuron_gate_core.sv`、`neuron_gate_reference.py`、`tb_neuron_gate.sv`、`test_neuron_gate.py`、`run_sim.bat`、`run_xsim.tcl`、`glbl.v`、`tb_neuron_gate_vlog.prj`、`xvlog.log`、`elaborate.log`、`simulate.log`、`tb_neuron_gate_behav.wdb`

本报告与被仿真的提交 `ee4b9ff67c08adb538f81cc5a5b48c49d13f34ca` 之间只相差本报告与 `VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json` 两个文档文件；被仿真的 RTL / oracle / runner 的 SHA-256 与第 1 节表格一致，可用 `git diff --name-only ee4b9ff67c08adb538f81cc5a5b48c49d13f34ca HEAD` 自证。

## 14. 全量测试结果（不挑好看的报）

命令：`python -m unittest test_local_prune_gate_rtl test_verify_local_prune_rtl test_local_prune_gate_vivado`

| 检出/工作树状态 | 用例总数 | 失败 | 跳过 | 退出码 |
|---|---:|---:|---:|---:|
| `wt_ac_true`：`git -c core.autocrlf=true clone`，`.gitattributes` 生效（LF） | 28 | 0 | 4（3 个 Icarus + 1 个未设 VIVADO_ROOT 的 XSim 集成） | 0 |
| `wt_ac_false`：`git -c core.autocrlf=false clone` | 28 | 0 | 4 | 0 |
| `wt_crlf_forced`：把 14 个受签核文本在工作树里全部改成 CRLF | 28 | 0 | 4 | 0 |
| `wt_ac_true` + `VIVADO_ROOT` 已设（真实 XSim 集成测试参与运行，91.649 s） | 28 | 0 | 3（仅 Icarus 三个） | 0 |
| 修复前（评审在 `1690036` 的新鲜 worktree 上） | 24 | 1 | 0 | 非 0 |

runner 自身在 `wt_ac_true` 上的完整回归：`RUNNER_RC=0`，最后一行
`VIVADO_LOCAL_PRUNE_GATE_PASS version=Vivado Simulator v2024.2.0 models=3 seeds=8
transactions_compared=6447 cases=45 mutants=5`；154 次工具调用退出码全部为 0。

跳过项的原因写在测试里（`TOOL_SKIP`）：本机没有 `iverilog`/`vvp`/`yosys`（`find_tool` 已搜索 PATH 与
`C:/msys64`），并且这一事实同时被记录进 `local_prune_rtl_results.json` 的 `tool_availability` 与
`provenance.*.reason`，不会被误读成“门已通过”。在装有这些工具的机器上，`python verify_local_prune_rtl.py`
会重新执行 60000 事务 Icarus 回归与 32 拍 Yosys 形式检查并覆盖相应证据块。

评审若在 2024.1 上复核，只需 `python -m unittest test_local_prune_gate_rtl test_verify_local_prune_rtl test_local_prune_gate_vivado`
与 `python run_local_prune_gate_vivado.py --seeds 8 --transactions 256 --json-out ...`，本报告与摘要会由脚本自动更新。

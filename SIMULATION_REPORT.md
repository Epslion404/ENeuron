# Vivado/XSim 真实仿真报告：local_prune_gate_2of4

状态：**PASS**。本报告由 `run_local_prune_gate_vivado.py` 生成的机器摘要(`VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json`) 自动渲染，不含人工誊写数字。

| 项目 | 值 |
|---|---|
| 生成时间 (UTC) | `2026-08-30T09:23:55Z` |
| 仿真器完整版本 | `Vivado Simulator v2024.2.0` |
| Vivado 路径来源 | `--vivado-root or VIVADO_ROOT`；本次取值 `C:/Users/MGL/Documents/Codex/Vivado2024_2` |
| 被仿真的 PR 提交 | `7266e2be15424bd26abe33a7fc265f454f6be368` |
| 主机 | Windows 11 / Python 3.13.15 |
| 逐事务对拍事务数 | 6447 |
| 逐字段比较次数 | 154728（= 事务数 × 24 个可见状态） |
| 用例数 | 45（7 个定向 × 3 模型 + 8 seed × 3 模型） |
| 失败敏感变异 | 5 个，全部被捕获 |

## 1. 被仿真源码的 SHA-256

```text
ba0ce8f56193bb8aa9ab607530d35f4dd76c72c3db6ca780202ca29fff281d6e  local_prune_evidence_gain.sv
01fda4fa848074a01aacb0a73f2da2ebc4a9154b210b6b45489ed8e1c7c323fd  local_prune_gate_2of4.sv
1a739a8d43e2c048c5266878c74220ebd8fbad4792d65f738e0f7e9e78114f5b  local_prune_gate_cosim.py
d5c287cf188dba1a51f1844cdb5a62c0571782a0a1783b49698448e7358522b1  local_prune_rtl_reference.py
69374024c5504e15f2cd910a604e1ec66da451c3fcc9b51f2547d94231376227  run_local_prune_gate_vivado.py
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
| `xsim` | 51 | `C:/Users/MGL/Documents/Codex/Vivado2024_2/bin/xsim.bat gate_tb --tclbatch C:/Users/MGL/AppData/Local/Temp/lpgv_sim_hkg1uyd4/run.tcl` |
| `xvlog` | 51 | `C:/Users/MGL/Documents/Codex/Vivado2024_2/bin/xvlog.bat -sv C:/Users/MGL/Documents/Codex/2026-08-29/vivado/clean_pr_checkout/local_prune_gate_2of4.sv C:/Users/M` |
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
| Python/RTL 分歧反例 | `reviewer_counterexample` | 3 / 3 |

用例目录（每条都同时做「与 Python 逐事务比对」和「合同规则断言」）：

- exact_two: strict two-of-four: six legal masks accepted, 0/1/3/4-bit masks refused, no second commit
- illegal_and_conflict_no_side_effect: bad opcode, bad mode, stale or duplicate ids, unsafe windows and illegal masks
- infer_freeze: INFER rejects OBSERVE and PRUNE_COMMIT but still reads and gates the mask
- reset_and_dense: reset state, dense 1111 before commit, first commit is exact-two
- reviewer_counterexample: mask=1100 with descending scores and a zero-utility commit stay bit-exact
- score_saturation: utility saturates at 15 and the two pruned lanes stay frozen after the commit
- tie_break: equal scores are resolved by the lowest lane index with the fixed 0-1-2-3 scan

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

1. **Python 黄金模型与 RTL 不一致**：产生分歧的 `neuron_gate_core.sv` / `neuron_gate_reference.py` 已整体撤出 PR（它同时引入 8 位 score、cooldown、自动 regrow、image_end/epoch_end，属第二套未批准设计）。其候选集合语义与反例已写入 `DESIGN_PROPOSAL_DYNAMIC_PRUNE_RECOVERY.md` 第 3 节，等待评审裁决后再实现。本 PR 现在只验证唯一真源 `local_prune_gate_2of4.sv`，并用 `reviewer_counterexample` 用例保证两路候选集不被重排、低分提交仍是 exact-two。
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
PASS directed reviewer_counterexample                eneuron       transactions=11
PASS directed reviewer_counterexample                pulse_mini_l  transactions=11
PASS directed reviewer_counterexample                pulse_mini_l2 transactions=11
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
SOURCE_SHA256 local_prune_gate_2of4.sv 01fda4fa848074a01aacb0a73f2da2ebc4a9154b210b6b45489ed8e1c7c323fd
SOURCE_SHA256 local_prune_evidence_gain.sv ba0ce8f56193bb8aa9ab607530d35f4dd76c72c3db6ca780202ca29fff281d6e
SOURCE_SHA256 local_prune_gate_cosim.py 1a739a8d43e2c048c5266878c74220ebd8fbad4792d65f738e0f7e9e78114f5b
SOURCE_SHA256 local_prune_rtl_reference.py d5c287cf188dba1a51f1844cdb5a62c0571782a0a1783b49698448e7358522b1
SOURCE_SHA256 run_local_prune_gate_vivado.py 69374024c5504e15f2cd910a604e1ec66da451c3fcc9b51f2547d94231376227
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

## 11. 文件清单与自证

- 新增：`run_local_prune_gate_vivado.py`、`test_local_prune_gate_vivado.py`、`DESIGN_PROPOSAL_DYNAMIC_PRUNE_RECOVERY.md`、`VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json`
- 修改：`local_prune_gate_cosim.py`（testbench 缺省命令文件 + `TB_COMPLETE` 哨兵，Icarus 与 XSim 共用同一份生成器）、`.gitignore`、`SIMULATION_REPORT.md`
- 删除：`neuron_gate_core.sv`、`neuron_gate_reference.py`、`tb_neuron_gate.sv`、`test_neuron_gate.py`、`run_sim.bat`、`run_xsim.tcl`、`glbl.v`、`tb_neuron_gate_vlog.prj`、`xvlog.log`、`elaborate.log`、`simulate.log`、`tb_neuron_gate_behav.wdb`

本报告与被仿真的提交 `7266e2be15424bd26abe33a7fc265f454f6be368` 之间只相差本报告与 `VIVADO_LOCAL_PRUNE_GATE_SUMMARY.json` 两个文档文件；被仿真的 RTL / oracle / runner 的 SHA-256 与第 1 节表格一致，可用 `git diff --name-only 7266e2be15424bd26abe33a7fc265f454f6be368 HEAD` 自证。

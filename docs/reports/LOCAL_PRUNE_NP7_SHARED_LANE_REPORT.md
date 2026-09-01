# NPU 局部剪枝 NP7 共享 BRAM 与共享 lane 软件签核报告（NP7.1–NP7.6，round 3 / B-V1+V2）

日期：2026-09-02。分支 `feature/np7-shared-lanes-20260901`（基线 `main @ 8853f7b`）。
周期合同来源：**PR #6 仓库管理员评论 `5498372499`**（决定 5 修订为 **B-V1+V2**，A/C/D 均不采用）；
仓库内规范副本 `docs/planning/NPU_PRUNING_NP7_DECISION_B_V1_V2.md`（含 §3 逐拍账本口径与 §4 重跑范围）。
本报告取代 round 1/2 的同名报告：那两轮的 G3 数字（22.33/21.78/21.00/21.00%）属于**已作废的旧周期合同**，
只保留作历史对照。

## 0. 结论

状态：`NP7_SOFTWARE_SIGNED_OFF` —— NP7.0–NP7.6 全部通过，G3 达标，NP7.7 的停止条件解除。

| 硬门 | 阈值 | 本轮实测（B-V1+V2，从新 HEAD 的原始逐拍账本重算） | 结论 |
|---|---|---|---|
| G1 实际权重槽读取下降 | >=45% | **72.22%**（3 模型 × L=1/2/4/8 全部同值） | PASS 12/12 |
| G2 共享 lane 操作数下降 | >=45% | **50.00%**（全部） | PASS 12/12 |
| G3 每逻辑 tick 周期下降 | >=25% | **L1 29.6875% / L2 29.0323% / L4 27.8689% / L8 27.8689%** | PASS 12/12 |
| G4 stall 单列且不抵消吞吐 | delta<=0 | dense 与 sparse 的 `stall_cycles` 相等（delta=0） | PASS |
| G5 膜状态/突触和 bit-exact | 逐拍全等 | NP7.3 160,000 事务逐拍比对 0 失败；三模型 20 样本膜状态摘要 0 不一致 | PASS |
| G6 三模型精度 | 不低于冻结 B2.1 | BAcc/coverage/`output_masks`/`hidden_masks`/`channel_enable` 与冻结产物逐字段相等 | PASS |

L1 的账本对照（每逻辑 tick 周期，同一 80 tick 流水）：dense 基线 **16.000** → sparse **11.250**；
L4：**15.250 → 11.000**。三模型（ENeuron / Pulse-Mini-L / Pulse-Mini-L2）计数同值，因为
共享 lane 只替换突触读取/累加，权重幅度不改变事务计数。

## 1. 逐步证据（命令、退出码、产物）

| 步骤 | 命令（cwd=仓库根） | rc | 产物与实测 |
|---|---|---|---|
| NP7.0 冻结 | 文档 | - | `docs/planning/NPU_PRUNING_NP7_DECISION_B_V1_V2.md`（裁定副本 + §3 逐拍账本 + §4 重跑范围）、`NPU_PRUNING_NP7_FREEZE_DECISIONS.md`（决策 5 标注作废并指向新文档） |
| NP7.1 oracle | `python -X utf8 -m unittest test_np7_shared_lane_oracle -v` | 0 | 16 tests OK；新增/改写的用例覆盖 V1 单拍零路径（ready/背压两种）、最后一批与结果退出同拍、连续无气泡请求、冷启动、尾部排空、`lane_stall` 不提前完成 |
| NP7.3 逐拍协同仿真 | `python -X utf8 np7_shared_lane_cosim.py` | 0 | `artifacts/results/np7_cosim_ledgers.json`（schema `np7-cosim-ledgers-v2`）+ `artifacts/logs/np73_cosim.txt`：**160 配置**（dense+sparse × L=1/2/4/8 × 20 seed）、**160,000 事务**、逐拍 oracle 失败 **0**、自报账本不可重建配置 **0** |
| NP7.4 三模型接入 | `python -X utf8 np7_three_model_integration_cosim.py` | 0 | `np7_three_model_integration.json`（schema `np7-three-model-integration-v2`）+ `np74_three_model.txt`：模型数=3 **问题数=0**；每模型 `v2_evidence`：`overlap_cycles=270`、`folded_cycles_saved=700`、`solo_segment_cycles=1600 > stream_cycles=900`、`zero_single_cycles=330` |
| NP7.5 形式与负向 | `python -X utf8 np7_formal_and_mutations.py` | 0 | `np7_formal_and_mutations.json` + `np75_formal_mutations.txt`：**形式检查 87/87 PASS、问题数 0**；3 个 proof（sparse/dense 协议、CONFIG 拒绝，均 `sat -seq 14 -verify`）+ 3 个 witness（`zero_path_reach` seq 10、`sparse_reach`/`dense_reach` seq 16）；**9 个 RTL mutation 全部 counterexample**；8 个负向实现运行全部被拒；3 个泄漏 mutation 全部被状态等价抓到 |
| NP7.6 软件签核 | `python -X utf8 generate_np7_manifest.py` → `python -X utf8 verify_np7_software_cost.py 3c0f06f0bc8fde8cc917f55bd7e6c0fdb1382d04` | 0 / 0 | 清单 `np7_software_cost_manifest.json`：`frozen_git_head=4ed72d6`、绑定 **27 输入 + 3 工具 + 26 证据**、`overall=PASS`、`integrity=[]`；验证器日志 `np76_verify.txt`：**rejects=0 / blocking=- / overall=PASS** |
| NP7.6 变异 | `python -X utf8 test_np7_verifier_mutations.py`；同命令在 `chcp 936` 默认代码页下再跑一遍 | 0 / 0 | `np76_mutations.txt`、`np76_mutations_defaultcp.txt`：**MUTATION_SUITE PASS checks=19**（两轮一致） |
| Vivado 行为仿真 | `python -X utf8 run_np7_vivado_xsim.py --vivado-root C:/Users/MGL/Documents/Codex/Vivado2024_2 --transactions 120` | 0 | `np7_vivado_xsim_summary.json`（schema `np7-vivado-xsim-v2`）+ `vivado_np7_xsim_reports/`：**16 用例 PASS、problems=0**、xsim 与 Icarus 观测流逐字节相同 **16/16**（见 §5） |
| NP7.7 物理门 | 未在本报告范围内 | - | 停止条件已解除；OOC 综合另出 `NP7.7` 证据与清单，不在本报告主张任何资源/时序结论 |

随机流量（NP7.3，非冻结任务）下同一份 RTL 的逐拍观测下降（20 seed 合计）：
读取 60.01 / 59.99 / 60.25 / 60.13%，操作 49.93 / 49.95 / 50.50 / 50.18%，
周期 **42.68 / 37.93 / 32.40 / 32.49%**（L=1/2/4/8）。这组数字由 NP7.6 从原始账本重算并写入
清单的 `rtl_observed_reductions`，但**不作为任何硬门的判据**（裁定决定 6）。

## 2. 裁定要求 -> 本轮落点

| 裁定条目（评论 5498372499 §二/§三） | 实现与证据落点 |
|---|---|
| V1 零路径单拍（accept 与 result 同边沿，只计 1 拍） | `np7_shared_lane_oracle.py` 的 run_stream 与 `np7_exec_unit_{sparse,dense}.sv`：`v1_single_done` 判定 + 不再置 outstanding；formal `P5`（零路径静默：无 RAM、无 lane、当拍给出 0 结果）；witness `saw_zero_single`/`saw_zero_hold`（`formal_np7_exec_unit_zero.ys` seq 10 要求 `zero_fast_paths_state=2`）；NP7.3 观测 `zero_single_cycles` dense=5 / sparse=18 |
| V1 背压时必须锁存并保持结果 | formal `P8`（`result_valid && !result_ready` 时 sum/zero_path 原样保持）+ `saw_zero_hold`；RTL 影子块在 `!outstanding` 分支断言 `result_sum==0 && result_zero_path` |
| V2 结果退出与下一事务 accept 同拍、元数据严格分离 | RTL 同拍 `retire_prev` 允许 `issue_ready`；hold 寄存器在 accept 分支不写入；formal `P1`/`P2`（单槽、每 accept 恰好一个 result）+ `P9`（同拍不覆盖元数据）；mutation `sparse/dense_same_edge_metadata_overwrite` 给出反例 |
| V2 背压下停止接受、仅旧结果退出同拍可接受 | formal `P1` `assert(!(raw_bp && accept_pulse))` + `P10`（背压期间不得 accept）；mutation `sparse/dense_accept_under_backpressure` 给出反例 |
| `lane_stall=1` 不得提前完成/接受 | formal `P6`（batch 期 `lane_stall` 时 `done_now=0`、`issue_ready=0`）+ witness `saw_lane_stall`；NP7.3 观测 `lane_stall_cycles=42,157` |
| 上层仍推进泄放/阈值/时间状态 | NP7.4 逐样本比较膜状态摘要（`state_digest_mismatch_samples=0`）与未共享实现；3 个泄漏 mutation（漏推进）全部被状态等价抓到 |
| 旧账本恒等式作废 | 验证器 `ledger_identity()` 只对**新**互斥类别求和；若账本只在旧口径 `total = busy + stall + 3*(completed-zero) + 2*zero` 下闭合，直接以 `ledger identity legacy-only: ... 旧恒等式 ...` 拒绝。变异 `legacy_identity_only_evidence` 专门证明这条拒绝路径有效 |
| 逐拍记录 accept/result/同拍/零路径/背压/RAM/lane/stall/启动/排空 | `np7_ledger_reconstruction.observe()` 从 CYC 行重建 20 个字段；NP7.3 每配置存 `observed`+`claimed` 两视角；NP7.6 只信 `observed` |
| 覆盖零路径 ready/背压、最后一批、连续请求、同拍 retire/accept、冷启动、尾部排空 | 见 §4 的 8 类覆盖度计数（全部非零）与 oracle 单测清单 |
| >=160,000 事务、无气泡 + 随机背压、dense/sparse × 1/2/4/8 | NP7.3：160 配置 / 160,000 事务；背压位图逐拍注入（`np7_bp.hex`），dense/sparse 同流同口径 |
| 三模型证明上游确实能利用 V2 | NP7.4 每模型每 lane 的 `v2_evidence` 四项判据由验证器逐条检查（`overlap>0`、`folded>0`、`solo>stream`、`zero_single>0`） |
| formal 证明四项新性质 | `formal_np7_exec_unit.sv` 的 P1–P10 + 5 个可达性见证寄存器；两个顶层（sparse/dense）同一 `sat -seq 14 -prove-asserts -verify` |
| mutation 新增两类反例 | `RTL_MUTATIONS` 从 5 条增至 **9 条**：新增 `*_same_edge_metadata_overwrite`、`*_accept_under_backpressure`（sparse 与 dense 各一份），验证器强制要求这 4 个标签存在且 verdict=counterexample |
| verifier/manifest 从原始逐拍账本重算、拒绝只改摘要 | 见 §6；新增变异 `tamper_ledger_coverage` 覆盖"改摘要不改账本" |
| 新增 `docs/planning/NPU_PRUNING_NP7_DECISION_B_V1_V2.md` | 已新增并被 NP7.6 清单绑定（`input_files`） |
| G3<25% 必须停止、不改选 A/D、不退回 V1-only | 实测 G3 最低 27.8689% >=25%，未触发停止条件；实现保留完整 V1+V2（`issue_ready`/hold/单拍零路径三项都在 RTL 与 oracle 同时生效） |

## 3. 上一轮 review 五项阻断的现状

| # | 阻断 | 修复提交 | 本轮回归证据 |
|---|---|---|---|
| 1 | testbench 中 `run_phase` 先使用后声明，Vivado 2024.1 xvlog 报 VRFC 10-3380 | `6b9701f` | `tb_np7_exec_unit.sv`/`tb_np7_negative.sv` 顶部 `logic run_phase = 1'b0;`；Vivado 2024.2 `xvlog -> xelab -> xsim` 16 用例全部编译并运行通过（`vivado_np7_xsim_reports/commands.log` 每步退出码 0） |
| 2 | 非法 sparse 索引 / dense 保留位仍被写入 RAM | `6b9701f`（`cfg_wr_ok` 门控写使能，丢弃并锁存 `cfg_error`） | formal `formal_np7_config_reject.ys`（seq 14，proof）；`tb_np7_config_negative.sv` 四相位 xsim+Icarus 双跑 PASS；旁路 mutation `config_rejection_bypass` 使测试台报 3 项 FAIL；NP7.5 mutation 集含该旁路并被拒 |
| 3 | sparse `checked_lat` 未复位/未逐事务初始化 | `6b9701f` | 复位块与 accept 分支同时清零；NP7.3 全量 160,000 事务逐拍比对 0 失败 |
| 4 | Windows 默认代码页下变异套件崩溃 | `17bc816`（子进程 `-X utf8`、父进程 decode+reconfigure）+ `33f206e`（清单按原始字节比对） | `artifacts/logs/np76_mutations_defaultcp.txt`：`chcp 936` 且清空 `PYTHONUTF8/PYTHONIOENCODING` 下 **PASS checks=19** |
| 5 | 冻结决策表第 2/3 项格式损坏 | `6b9701f`（拆分表格行） | `NPU_PRUNING_NP7_FREEZE_DECISIONS.md` §1 的 8 行表格每行恰好 4 个竖线，三列结构完整 |

## 4. 逐拍路径覆盖度（NP7.3，160 配置 / 160,000 事务）

| 观测类别（互斥） | 合计 | dense | sparse |
|---|---|---|---|
| `startup_cycles`（冷启动纯 accept 拍） | 138 | 75 | 63 |
| `drain_cycles`（尾部排空） | 60 | 19 | 41 |
| `overlap_cycles`（同拍 retire/accept） | 159,817 | 79,915 | 79,902 |
| `backpressure_cycles`（结果已就绪但 ready=0） | 8,072 | 2,940 | 5,132 |
| `lane_stall_cycles` | 42,157 | 25,831 | 16,326 |
| `hold_retire_cycles`（锁存结果退出） | 45,647 | 16,434 | 29,213 |
| `retire_latch_cycles`（发射当拍结果不可退） | 20,389 | 11,363 | 9,026 |
| `zero_single_cycles`（V1 单拍零路径） | 23 | **5** | 18 |

这 8 类计数由 NP7.6 从 NP7.3 的**观测侧**账本求和写进清单 `ledger_coverage`，验证器把清单值与
重算值做 json 等值比较（篡改即拒，变异 `tamper_ledger_coverage`）；任一类为 0 即拒绝该证据。
dense 的 `zero_single_cycles` 只有 5：连续无气泡 + 随机背压下，稠密格式几乎不存在
"结构掩码 AND 活动掩码 = 0 且当拍可退出"的组合，这是**流量性质**而非路径缺失；该路径另有
formal witness（`formal_np7_exec_unit_zero.ys` seq 10 强制 `saw_zero_single=1 & saw_zero_hold=1`）
与 16 条 oracle 单测独立覆盖。本轮如实记录该偏斜，不放宽判据。

## 5. Vivado 行为仿真对照（2024.2，逐拍重建）

执行机 `Chan-an`（Windows 11 AMD64），Vivado Simulator **v2024.2.0**，**SW Build 5239630**，
`C:/Users/MGL/Documents/Codex/Vivado2024_2`，`code_git_head` 干净工作树。每用例 `--transactions 120`，
`xvlog -> xelab -> xsim` 与同一激励目录下的 Icarus 重跑**逐字节相同**（16/16）。

| 用例 | 状态 | CYC 行 | 自报 total | 自报 done | 自报 vs 逐拍重建不一致令牌 |
|---|---|---|---|---|---|
| golden_sparse_L1/L2/L4/L8 | PASS | 411 / 376 / 345 / 365 | 398 / 363 / 332 / 352 | 120 | 无（要求全等） |
| golden_dense_L1/L2/L4/L8 | PASS | 693 / 588 / 534 / 545 | 670 / 565 / 511 / 522 | 120 | 无（要求全等） |
| neg0_L1（全读后门控） | PASS | 586 | 563 | 120 | **req, val** |
| neg0_L4 | PASS | 553 | 530 | 120 | **req, val** |
| neg1_L1（MAC 后清零） | PASS | 704 | 691 | 120 | **ops** |
| neg1_L4 | PASS | 345 | 332 | 120 | **ops** |
| cfgneg_sparse_L1/L4、cfgneg_dense_L1/L4 | PASS | 0（CFGNEG 相位报告） | - | - | `RESULT=PASS FAILED=0` |

NP7.6 不再信任这些自报字符串：`check_xsim_evidence()` 要求每条 golden 的 `raw_ledger`
（20 个由逐拍 CYC 重建的字段）字段集完整、对新恒等式闭合、窗口拍数落在日志 CYC 行数内、
自报 LEDGER 与重建逐项相等；对两个负向实现要求**至少有一个令牌不一致**（否则"逐拍重建没能
揭穿伪收益"）；并用验证器**自带的分类器**从仓库内保留的逐拍日志重算首尾各 40 拍的类别指纹，
与证据里的 `visible_class`/`visible_rows` 比对，日志字节哈希与冻结提交内的源文件字节也一并核对。

## 6. 证据链与可复核性

- 清单 `artifacts/results/np7_software_cost_manifest.json` 由 `generate_np7_manifest.py` 在证据时点
  一次写入：绑定 27 个输入（oracle、4 件 RTL、3 个测试台、6 份 `.ys` 形式件、负向件、NP7.3/7.4/7.5
  脚本、`np7_ledger_reconstruction.py`、`local_prune_b21.py`、3 份 planning 文档、xsim runner）
  + 3 个工具脚本 + 26 份证据（4 个结果 JSON、3 份运行日志、xsim 汇总、signoff 摘要、命令日志、
  16 份逐用例日志）。不绑定任何 `.dcp`。
- `verify_np7_software_cost.py` **只读**：清单磁盘字节 vs `git show <head>` 字节；每个绑定文件
  "清单哈希 / 冻结提交字节 / 当前磁盘字节"三方一致；G1–G6 全部由原始账本重算并与清单逐字段比对；
  新增 `ledger_coverage`（逐拍覆盖求和）与 `environment`（执行机 host/os/python）+ 工具 banner
  必须真实存在（`missing:` 即拒）三重比对。实现自报的任何百分比都不参与判定。
- `test_np7_verifier_mutations.py` **19 个变异**全部被拒且没有一个让验证器退出码变 0：
  删日志、翻转门槛结论/伪造 G3 数值（双向）、改 RTL 观测账本、伪造周期收益、下调验证器阈值、
  放行负向控制、削弱形式结论、放行泄漏 mutation、篡改冻结精度产物、冻结后偷改 RTL/验证器并同步
  清单哈希、伪造冻结 HEAD、伪造 integrity、伪造 xsim 汇总、伪造 xsim LEDGER 标记、删除 xsim 用例、
  **只在旧恒等式下闭合的账本**、**篡改逐拍覆盖统计**、**删掉裁定强制的 RTL mutation**。
- 干净克隆基线：`git clone` 后 `python -X utf8 verify_np7_software_cost.py <clone-head>` 输出
  `rejects=0 overall=PASS`（变异套件的第 0 步就是在验证这一点）。

## 7. 限制与不主张的内容

- **工具版本**：Vivado 证据只绑定本机 2024.2（SW Build 5239630，执行机 `Chan-an` / Windows 11），
  **不外推**到评审者使用的 2024.1；本轮 xsim 全部用例在 2024.2 编译通过，2024.1 下需复跑确认。
- **形式深度有限**：`sat -seq 14`（协议与 CONFIG 拒绝）与 `-seq 10/16`（可达性 witness）是
  Yosys 0.68 + minisat 的**有限深度**检查，不是无界模型检验；Yosys 为 YoWASP/WASM 构建。
- **仿真规模**：Vivado xsim 每用例 120 事务（受 xsim 运行时间限制），统计规模证据来自 NP7.3 的
  Icarus 全量 160,000 事务；xsim 侧主张的是"同一 RTL 在商业仿真器下的逐拍行为与开源链一致、
  且账本可被重建"，不主张统计显著性。
- dense 的 `zero_single_cycles=5`（§4）说明 V1 单拍零路径在稠密无气泡流量下稀有，本轮按实陈述。
- 周期数字来自冻结逻辑周期模型的 RTL 逐拍计数，证明的是数字执行路径；**不证明** BRAM 真实端口
  冲突、DDR/DMA、PS 软件、以太网或板级端到端吞吐；vector-less 功耗不作为 NP7 门；不做板级结论。
- NP7.3 的每组 4 连接、10 组 RAM 内容是穷举式随机结构（seed 由 `lanes*100003+seed` 决定，可复现），
  不是真实训练权重；真实权重下的活动分布只由冻结 B2.1 任务（NP7.4）代表。
- G1–G6 在 1/2/4/8 四种 lane 数下分别报告，未以任何最优 lane 数掩盖。
- 本轮未修改 `WORKFLOW_STATE.md`、`task_plan.md`、`.nexus-map/` 与任何已签核的 NP4B/NP6 产物。

## 8. 复现命令

```text
set PATH=C:\iverilog\bin;C:\msys64\ucrt64\bin;%PATH%
python -X utf8 -m unittest test_np7_shared_lane_oracle -v   # NP7.1  16 tests OK
python -X utf8 np7_shared_lane_cosim.py                     # NP7.3  160 runs / 160000 txns
python -X utf8 np7_three_model_integration_cosim.py         # NP7.4  3 models / 0 problems
python -X utf8 np7_formal_and_mutations.py                  # NP7.5  87/87 checks / 9 mutations
python -X utf8 run_np7_vivado_xsim.py --vivado-root <Vivado2024.2 根> --transactions 120
python -X utf8 generate_np7_manifest.py                     # 仅在证据时点执行一次
python -X utf8 verify_np7_software_cost.py <HEAD>           # 只读；本轮 rejects=0 overall=PASS
python -X utf8 test_np7_verifier_mutations.py               # 19 mutations 全部被拒
```

## 9. 批准链与下一步

- 八项冻结决定的批准链已在 PR #6 内闭环（评论 `5498372499` 逐项裁定），仓库内副本见
  `docs/planning/NPU_PRUNING_NP7_DECISION_B_V1_V2.md` §1；决策 5 的旧口径在
  `NPU_PRUNING_NP7_FREEZE_DECISIONS.md` 中标注为"已被管理员修订/作废"，不再作为合同使用。
- NP7.0–NP7.6 全绿且 G3>=25%，因此 TODO §5 NP7.7 的前置条件成立：下一步在
  `xc7z020clg400-1` 上对 1/2/4/8 lane × dense/sparse 共 **8 个 OOC 综合配置**跑 Vivado，
  比较 LUT/FF/BRAM/DSP、WNS/WHS 与周期/吞吐，并单独出 NP7.7 的 fail-closed 清单；
  任何 100 MHz 不满足的配置不得用软件周期收益补偿。

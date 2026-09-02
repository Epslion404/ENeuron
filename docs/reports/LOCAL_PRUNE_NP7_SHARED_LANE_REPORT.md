# NPU 局部剪枝 NP7 共享 BRAM 与共享 lane 签核报告（NP7.1–NP7.7，round 5 / B-V1+V2 + P1 lane 一拍流水 + PR gate 适配）

日期：2026-09-02。分支 `feature/np7-shared-lanes-20260901`（基线 `main @ 8853f7b`，本轮已合并 `main @ 724a5dc` 的 PR gate 与管理员裁定文档，见 §11）。
周期合同来源：**PR #6 仓库管理员评论 `5498372499`**（决定 5 修订为 **B-V1+V2**，A/C/D 均不采用）；
仓库内规范副本 `docs/planning/NPU_PRUNING_NP7_DECISION_B_V1_V2.md`（含 §3 逐拍账本口径与 §4 重跑范围）。
**P1 修订**（管理员 review `5085536010`，2026-09-02T04:21:41Z，被裁定时的 head `537eb7a`）：允许在 lane 的
饱和加法/事件计数路径插一拍流水，但 7 项证据必须同步重跑，物理验收改成 **8/8 全收敛**（不接受
『L1/L2 收敛、L4/L8 排除』）；仓库内规范副本 `docs/planning/NPU_PRUNING_NP7_DECISION_LANE_PIPELINE_P1.md`。
本报告按该裁定完成 NP7.1–NP7.7 全量重跑；round 3 的软件门数字与 4/8 物理结果按裁定 §三
**降级为历史证据**，不再作为最终签核。round 1/2 的 G3 数字（22.33/21.78/21.00/21.00%）同样只作历史对照。

## 0. 结论

状态：`NP7_SOFTWARE_SIGNED_OFF` + **`NP7_PHYSICS_SIGNED_OFF`**（P1 裁定后）——NP7.0–NP7.6 全部门通过，NP7.7 的 8 个配置（sparse/dense × L=1/2/4/8）**8/8 在 `xc7z020clg400-1`、100 MHz 下收敛**：`WNS>0 / WHS>0 / setup failing endpoints=0 / hold failing endpoints=0 / DRC=0 / route errors=0`，见 §9；round 3 的「4/8 收敛 + L4/L8 排除」按裁定 `5085536010` §三降级为历史证据（§9.1），不再作为签核口径。

| 硬门 | 阈值 | 本轮实测（P1，lane 内插一拍流水；全部由 HEAD 原始账本重算） | 结论 |
|---|---|---|---|
| G1 实体权重槽读取下降 | >=45% | **72.2222%**（3 模型 × L=1/2/4/8 全均值同值） | PASS 12/12 |
| G2 共享 lane 发射下降 | >=45% | **50.0000%**（全均值） | PASS 12/12 |
| G3 每逻辑 tick 周期下降 | >=25% | **L1 31.5068% / L2 30.9859% / L4 30.0000% / L8 30.0000%** | PASS 12/12 |
| G4 stall 不增且不出新 stall | delta<=0 | dense 与 sparse 的 `stall_cycles` 相等，delta=0 | PASS |
| G5 膜状态/突触和 bit-exact | 逐拍全比 | NP7.3 160,000 事务逐拍比对 0 失败；三模型 20 样本膜状态摘要 0 不一致 | PASS |
| G6 三模型精度 | 不劣于冻结 B2.1 | BAcc/coverage/`output_masks`/`hidden_masks`/`channel_enable` 与冻结基线逐字段相等 | PASS |

**必须如实说明的代价：P1 流水使绝对周期变长；G3 百分比上升是同一原因的比值效应，不能读成“绝对更快”。** 同一 80-tick 流水线下每逻辑 tick 周期（dense 基线 / sparse）为 L1 **18.250（旧 16.000）** / **12.500（旧 11.250）**，L4 **17.500（旧 15.250）** / **12.250（旧 11.000）**，L2 17.750 / 12.250，L8 17.500 / 12.250，见 §5。原因是闭式合同里每笔非零突触发射多 1 拍（sparse `4+batches`、dense `5+batches`），而该 trace 中 dense 基线每 tick 有 180 笔非零（2.25 笔/tick）、dense/sparse format 各 100 笔（1.25 笔/tick），于是 dense +2.25 拍、sparse +1.25 拍，比值从 29.6875%/27.8689% 升到 31.5068%/30.0000%。

物理侧代价同样如实列出（round 3 → P1，同器件同约束）：sparse LUT 115/132/181/186 → **133/143/193/193**，dense LUT 137/162/192/195 → **134/152/198/198**，FF 462 → 471/472/475、476 → 485/486/489；BRAM36=BRAM18=DSP 仍全为 0（权重是 LUTRAM/CARRY4 实现，**不声称节省 BRAM/DSP**）。最差裕量 **dense/L4 WNS=+0.138 ns**（10 ns 周期的 1.4%）、sparse/L4 WNS=+0.230 ns，属“收敛但很薄”：换器件、换 Vivado 版本或加负载不保证仍成立（见 §10 局限）。


## 1. 逐步证据（命令、退出码、产物）

| 步骤 | 命令（cwd=仓库根） | rc | 产物与实测 |
|---|---|---|---|
| NP7.0 冻结 | 文档 | - | `docs/planning/NPU_PRUNING_NP7_DECISION_B_V1_V2.md`（裁定副本 + §3 逐拍账本 + §4 重跑范围）、`NPU_PRUNING_NP7_FREEZE_DECISIONS.md`（决策 5 标注作废并指向新文档） |
| NP7.1 oracle | `python -X utf8 -m unittest test_np7_shared_lane_oracle -v` | 0 | **20 tests OK**（新增 `LanePipelineTests` 四条 P1 性质：结果恰晚最后一批发射 1 拍、零路径不进流水、DRAIN 拍受 `lane_stall` 背压、DRAIN 折叠拍遇 `result_ready=0` 锁存）；`expected_cycles()` 已改成 P1 闭式（非零事务各 +1 拍，零路径仍 1 拍），旧 B-V1+V2 闭式用例同步更新 |
| NP7.3 逐拍协同仿真 | `python -X utf8 np7_shared_lane_cosim.py` | 0 | `artifacts/results/np7_cosim_ledgers.json`（schema `np7-cosim-ledgers-v2`，日志头 `code_git_head=0dbdf59`）+ `artifacts/logs/np73_cosim.txt`：**160 配置**（dense+sparse × L=1/2/4/8 × 20 seed）、**160,000 事务**、逐拍 oracle 失败 **0**、自报账本不可重建配置 **0**（含新增 S_DRAIN 折叠拍的逐观测全等） |
| NP7.4 三模型接入 | `python -X utf8 np7_three_model_integration_cosim.py` | 0 | `np7_three_model_integration.json`（schema `np7-three-model-integration-v2`）+ `np74_three_model.txt`：模型数=3 **问题数=0**；每模型 `v2_evidence`（L1）`overlap_cycles=270`、`folded_cycles_saved=700`、`solo_segment_cycles=1700 > stream_cycles=1000`、`zero_single_cycles=330`（后两项各比 round 3 多 100 拍，正好等于 100 笔非零事务 × 1 拍 DRAIN） |
| NP7.5 形式与负向 | `python -X utf8 np7_formal_and_mutations.py` | 0 | `np7_formal_and_mutations.json`（`git_head=0dbdf59`）+ `np75_formal_mutations.txt`：**形式检查 90/90 PASS、问题数 0**（新增 P11 三组断言）；3 个 proof（sparse/dense 协议 `sat -seq 16 -verify`、CONFIG 拒绝 `-seq 14`）+ 3 个 witness（`zero_path_reach` seq 10、`sparse_reach`/`dense_reach` seq 18）；**12 个 RTL mutation 全部 counterexample**（新增 `lane_hold_ignored`、`sparse/dense_fold_last_early`）；8 个负向实现运行全部被拒；3 个泄漏 mutation 全部被状态等价抓到 |
| NP7.6 软件签核 | `python -X utf8 generate_np7_manifest.py` → `python -X utf8 verify_np7_software_cost.py <HEAD>` | 0 / 0 | 清单 `np7_software_cost_manifest.json`：`frozen_git_head=9369981`、绑定 **28 输入 + 3 工具 + 26 证据**、`overall=PASS`、`integrity=[]`；验证器日志 `np76_verify.txt`：**rejects=0 / blocking=- / overall=PASS** |
| NP7.6 变异 | `python -X utf8 test_np7_verifier_mutations.py`；同命令在 `chcp 936` 默认代码页下再跑一遍 | 0 / 0 | `np76_mutations.txt`、`np76_mutations_defaultcp.txt`：**MUTATION_SUITE PASS checks=19**（两轮一致） |
| Vivado 行为仿真 | `python -X utf8 run_np7_vivado_xsim.py --vivado-root C:/Users/MGL/Documents/Codex/Vivado2024_2 --transactions 120` | 0 | `np7_vivado_xsim_summary.json`（schema `np7-vivado-xsim-v2`，`code_git_head=9d07b99`、`worktree_dirty=[]`）+ `vivado_np7_xsim_reports/`：**16 用例 PASS、problems=0**、xsim 与 Icarus 观测流逐字节相同 **16/16**（见 §5）；在 head `9369981` 上复跑一次，逐用例 CYC 行数与首跑完全相同 |
| NP7.7 变异 | `python -X utf8 test_np7_physical_mutations.py`；同命令在默认代码页(936)下再跑一遍 | 0 / 0 | `np77_mutations.txt`、`np77_mutations_defaultcp.txt`：**NP77_MUTATION_SUITE PASS checks=13**（基线干净克隆 rejects=0；13 个变异全部被对应判据拦下，含新增 `not_met_config_forge`，见 §6） |
| NP7.7 物理门（P1 后重跑） | `python -X utf8 run_np7_vivado_ooc.py --vivado-root C:/Users/MGL/Documents/Codex/Vivado2024_2 --jobs 4` → `python -X utf8 verify_np7_physical_cost.py <HEAD>` | 0 / 0 | `np7_vivado_ooc_summary.json`（`code_git_head=9d07b99`、`worktree_dirty=[]`）+ 8 个 `vivado_np7_ooc_<fmt>_L<n>_reports/`（各 9 份报告 + OOC 封装）+ `np77_ooc.txt`、`np77_verify.txt`：**8/8 RESULT=ROUTED、DRC=0、route errors=0、hold 全收敛**，100 MHz **8/8 MET**（`NP7_PHYSICAL_GATE verdict=8/8`、`EXCLUDED none`、`rejects=0 overall=PASS`）；同 head 复跑一次，8 个配置的 LUT/WNS/WHS 逐项相同 |

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
| G3<25% 必须停止、不改选 A/D、不退回 V1-only | P1 后实测 G3 最低 30.0000% >=25%，未触发停止条件；实现保留完整 V1+V2（`issue_ready`/hold/单拍零路径三项都在 RTL 与 oracle 同时生效），并按 §一 追加 lane 一拍流水 |

### 2.1 P1 裁定 §一（7 项必须同步更新）-> 本轮落点

| P1 条目 | 实现与证据落点 |
|---|---|
| ① Python cycle oracle 与逐拍账本 | `np7_shared_lane_oracle.py`：`CYCLE_CONTRACT="P1-lane-pipeline-v1"`、`DRAIN_CYCLES_PER_NONZERO_TXN=1`，`run_stream` 新增 `inflight/issue_tree/fold_now/fold_last` 与 `DRAIN` 状态；`np7_ledger_reconstruction.py`：`STATE_DRAIN=6`、`classify_row`（DRAIN 非 stall→LAT、DRAIN stall→LANE_STALL）、`retire_latch_cycles` 改判到 DRAIN 折叠拍、`work` 序列同步 |
| ② dense/sparse RTL、testbench 与协同仿真 | `np7_shared_synapse_lane.sv` 重写为 Stage A（gate+饱和树）+ `stage2_q/valid_q` 流水寄存器 + Stage B（根节点+acc 折叠+饱和判定）；`np7_exec_unit_{sparse,dense}.sv` 新增 `S_DRAIN=3'd6`、`fold_last/fold_commit/drain_active`、`batch_last` 退化为『最后一批已发射』；两个测试台只观测不改判定口径；NP7.3 160 配置 / 160,000 事务逐拍全等、0 失败 |
| ③ B-V1+V2 的 result/retire/accept 时序证明 | `formal_np7_exec_unit.sv`（sparse/dense 两份）新增 **P11**：`result_valid` 只能来自 hold、或 DRAIN 非 stall 拍、或零路径；`prev_last_fire -> state==3'd6`（正好晚 1 拍）；`drain && !lane_stall -> result_valid && (!accept_pulse \|\| done_now)`；P1–P10 全部保留；`.ys` 深度 `sat -seq 14->16`、reach `-seq 16->18`（含 5 个 `-set-at 18`） |
| ④ 三模型逐样本状态等价 | NP7.4 三模型 × 20 样本 × 4 tick 的膜状态摘要 `state_digest_mismatch_samples=0`，3 个泄漏 mutation 仍全部被状态等价抓到；每 tick 周期与 V2 证据四项在 §0/§1 重算 |
| ⑤ formal、reachability 与 mutation | 90/90 检查、3 proof + 3 witness、RTL mutation 9 -> **12**（新增 `lane_hold_ignored`：lane 无视 `fold_hold`；`sparse/dense_fold_last_early`：发射当拍就出结果，比 Stage B 早 1 拍），12/12 全部 counterexample；`verify_np7_software_cost.py` 的 `MIN_RTL_MUTATIONS=12` 且 `REQUIRED_RTL_MUTATIONS` 强制这 3 个标签存在且被揭穿 |
| ⑥ G1–G6 与绝对周期/吞吐重算 | §0 表 + §4 覆盖度 + §7 的绝对周期代价（含随机流量下 RTL 观测周期下降从 42.68/37.93/32.40/32.49% 降到 38.64/34.11/29.81/29.62%） |
| ⑦ Vivado XSim 与 8 配置 OOC 综合 | §5：16/16 用例 xsim 与 Icarus 逐字节相同（含新增 `st=6` 拍）；§9：**8/8 MET**、`EXCLUDED none` |

同一轮还修掉两处只在 Vivado 侧暴露的问题，如实记录：`np7_negative_controls.sv` 里
`drain_active` 先用后声明，Icarus 容忍但 `xvlog` 报 `VRFC 10-3380`，XSim 首跑 4 个负向用例
`rc=1`；调整声明顺序后 16/16 通过。验证器自带的独立分类器 `tick_class()` 原本不认识
`st==6`，导致保留行里含 DRAIN 拍的 5 个用例被判『分类指纹与重算不一致』，同步更新后一致。

## 3. 上一轮 review 五项阻断的现状

| # | 阻断 | 修复提交 | 本轮回归证据 |
|---|---|---|---|
| 1 | testbench 中 `run_phase` 先使用后声明，Vivado 2024.1 xvlog 报 VRFC 10-3380 | `6b9701f` | `tb_np7_exec_unit.sv`/`tb_np7_negative.sv` 顶部 `logic run_phase = 1'b0;`；Vivado 2024.2 `xvlog -> xelab -> xsim` 16 用例全部编译并运行通过（`vivado_np7_xsim_reports/commands.log` 每步退出码 0） |
| 2 | 非法 sparse 索引 / dense 保留位仍被写入 RAM | `6b9701f`（`cfg_wr_ok` 门控写使能，丢弃并锁存 `cfg_error`） | formal `formal_np7_config_reject.ys`（seq 14，proof）；`tb_np7_config_negative.sv` 四相位 xsim+Icarus 双跑 PASS；旁路 mutation `config_rejection_bypass` 使测试台报 3 项 FAIL；NP7.5 mutation 集含该旁路并被拒 |
| 3 | sparse `checked_lat` 未复位/未逐事务初始化 | `6b9701f` | 复位块与 accept 分支同时清零；NP7.3 全量 160,000 事务逐拍比对 0 失败 |
| 4 | Windows 默认代码页下变异套件崩溃 | `17bc816`（子进程 `-X utf8`、父进程 decode+reconfigure）+ `33f206e`（清单按原始字节比对） | `artifacts/logs/np76_mutations_defaultcp.txt`：`chcp 936` 且清空 `PYTHONUTF8/PYTHONIOENCODING` 下 **PASS checks=19** |
| 5 | 冻结决策表第 2/3 项格式损坏 | `6b9701f`（拆分表格行） | `NPU_PRUNING_NP7_FREEZE_DECISIONS.md` §1 的 8 行表格每行恰好 4 个竖线，三列结构完整 |

## 4. 逐拍路径覆盖度（NP7.3，160 配置 / 160,000 事务）

| 观测类别（互斥） | 合计 | dense | sparse | round 3 合计（历史） |
|---|---|---|---|---|
| `startup_cycles` | 138 | 75 | 63 | 138 |
| `drain_cycles` | 71 | 21 | 50 | 60 |
| `overlap_cycles` | 159,817 | 79,915 | 79,902 | 159,817 |
| `backpressure_cycles` | 7,914 | 2,780 | 5,134 | 8,072 |
| `lane_stall_cycles` | 75,785 | 44,296 | 31,489 | 42,157 |
| `hold_retire_cycles` | 45,462 | 16,277 | 29,185 | 45,647 |
| `retire_latch_cycles` | 20,204 | 11,206 | 8,998 | 20,389 |
| `zero_single_cycles` | 23 | 5 | 18 | 23 |

P1 之后每一拍都被同一套互斥类别吸收，`latency_cycles` 不再单列进本表（它由恒等式的
`busy+latency+lane_stall+backpressure+hold_retire+zero_single+accept_own == total` 约束，
在 NP7.6 里逐配置重算）。相比 round 3 的三处实质变化：

- `lane_stall_cycles` 42,157 -> **75,785**：流水寄存器的折叠/发射两拍都会被 `lane_stall` 挡住，
  同一笔事务的可被挡窗口从 1 拍变 2 拍，所以随机背压下 stall 计数上升，这是**口径变化的直接后果**，
  不是新路径；
- `drain_cycles` 60 -> **71**、`retire_latch_cycles` 20,389 -> **20,204**：结果锁存与尾部排空都移到
  DRAIN 折叠拍上，量级不变；
- `overlap_cycles` **159,817** 与 `zero_single_cycles` **23**（dense 5 / sparse 18）与 round 3 完全相同：
  V2 同拍 retire/accept 与 V1 单拍零路径都没被流水化破坏（P11 与 4 条新单测各从两侧钉住）。

这 8 类计数由 NP7.6 从 NP7.3 的**观测侧**账本求和写进清单 `ledger_coverage`，验证器把清单值与
重算值做 json 等值比较（篡改即拒，变异 `tamper_ledger_coverage`）；任一类为 0 即拒绝该证据。
dense 的 `zero_single_cycles` 仍是 5：连续无气泡 + 随机背压下，稠密格式几乎不存在
『结构掩码 AND 活动掩码 = 0 且当拍可退出』的组合，这是**流量性质**而非路径缺失；该路径另有
formal witness（`formal_np7_exec_unit_zero.ys` seq 10 强制 `saw_zero_single=1 & saw_zero_hold=1`）
与 20 条 oracle 单测独立覆盖。本轮如实记录该偏斜，不放宽判据。

## 5. Vivado 行为仿真对照（2024.2，逐拍重建）

执行机 `Chan-an`（Windows 11 AMD64），Vivado Simulator **v2024.2.0**，**SW Build 5239630**，
`C:/Users/MGL/Documents/Codex/Vivado2024_2`，汇总里 `code_git_head=9d07b99` 且
`worktree_dirty=[]`（干净工作树），每用例 `--transactions 120`，
`xvlog -> xelab -> xsim` 与同一激励目录下的 Icarus 重跑**逐字节相同**（16/16）。
P1 流水化后每台仿真器的观测流都新增了 `st=6`（S_DRAIN）的拍，两侧同步变化才能全等，
因此这 16/16 同时也是『商业仿真器与开源链对新周期合同一致』的证据。

| 用例 | 状态 | CYC 行 | 自报 total | 自报 done | 逐拍窗口 | latency 拍 | lane_stall 拍 | retire_latch 拍 | 自报 vs 逐拍重建 |
|---|---|---|---|---|---|---|---|---|---|
| golden_sparse_L1 | PASS | 527 | 514 | 120 | 514 | 186 | 61 | 14 | 无（要求全等） |
| golden_sparse_L2 | PASS | 510 | 497 | 120 | 497 | 190 | 71 | 12 | 无（要求全等） |
| golden_sparse_L4 | PASS | 456 | 443 | 120 | 443 | 168 | 49 | 11 | 无（要求全等） |
| golden_sparse_L8 | PASS | 502 | 489 | 120 | 489 | 188 | 68 | 12 | 无（要求全等） |
| golden_dense_L1 | PASS | 827 | 804 | 120 | 804 | 224 | 86 | 15 | 无（要求全等） |
| golden_dense_L2 | PASS | 729 | 706 | 120 | 706 | 224 | 85 | 13 | 无（要求全等） |
| golden_dense_L4 | PASS | 677 | 654 | 120 | 654 | 226 | 58 | 18 | 无（要求全等） |
| golden_dense_L8 | PASS | 682 | 659 | 120 | 659 | 228 | 60 | 17 | 无（要求全等） |
| neg0_L1 / neg0_L4（全读后门控） | PASS | 704 / 642 | 821 / 456 | 120 | 681 / 619 | 808 / 443 | 213 / 204 | 186 / 168 | **req, val** |
| neg1_L1 / neg1_L4（MAC 后清零） | PASS | 50 / 38 | 109 / 49 | 120 | 14 / 9 | 15 / 11 | 681 / 619 | 808 / 443 | **ops** |
| cfgneg_sparse_L1/L4、cfgneg_dense_L1/L4 | PASS | 0（CFGNEG 相位报告） | - | - | - | - | - | - | `RESULT=PASS FAILED=0` |

NP7.6 不再信任这些自报字符串：`check_xsim_evidence()` 要求每条 golden 的 `raw_ledger`
（20 个由逐拍 CYC 重建的字段）字段集完整、对新恒等式闭合、窗口拍数落在日志 CYC 行数内、
自报 LEDGER 与重建逐项相等；对两个负向实现要求**至少有一个令牌不一致**（否则『逐拍重建没能
揭穿伪收益』）；并用验证器**自带的分类器**从仓库内保留的逐拍日志重算首尾各 40 拍的类别指纹，
与证据里的 `visible_class`/`visible_rows` 比对，日志字节哈希与冻结提交内的源文件字节也一并核对。
本轮为此把验证器自带的 `tick_class()` 同步到 P1（`st==6` 非 stall 归 LAT、stall 归 LANE_STALL），
否则保留行里出现 DRAIN 拍的 5 个用例会被判『指纹与重算不一致』——这条拒绝路径本轮真实触发过。

## 6. 证据链与可复核性

- 清单 `artifacts/results/np7_software_cost_manifest.json` 由 `generate_np7_manifest.py` 在证据时点
  一次写入：绑定 28 个输入（oracle、4 件 RTL、3 个测试台、6 份 `.ys` 形式件、负向件、NP7.3/7.4/7.5
  脚本、`np7_ledger_reconstruction.py`、`local_prune_b21.py`、4 份 planning 文档（含新增的
  `NPU_PRUNING_NP7_DECISION_LANE_PIPELINE_P1.md`）、xsim runner）
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
- 本报告里六份日志（`np76_verify.txt`、`np77_verify.txt`、两个变异套件各含默认代码页复跑）绑定同一个提交号（见每份日志头部的 `git_head:` 行），即它们所验证的那个提交；日志文件自身随下一个提交入库（日志无法记录自己所在的提交号，这里如实说明，不伪造"自包含"链接）。
- NP7.7 的物理侧独立绑定链（与软件链互不复用）：`artifacts/results/np7_vivado_ooc_summary.json`
  由 `run_np7_vivado_ooc.py` 在综合时点一次写入，8 个 `vivado_np7_ooc_<fmt>_L<n>_reports/` 里
  的 Vivado 原始报告全部提交；`verify_np7_physical_cost.py` **只读**，逐配置把
  `signoff_summary.txt`、汇总 JSON 自报值、以及从 `.rpt` 重算的
  LUT/FF/BRAM36/BRAM18/DSP/WNS/TNS/WHS/THS/失败端点/DRC/route-error 做三方比对，
  并重算自动生成的 OOC 顶层封装 sha256（改端口表就必然暴露）。
  不绑定任何 `.dcp/.jou/.pb/.str`（被 `.gitignore` 排除，未提交即不算证据）。
- `test_np7_physical_mutations.py` **13 个变异**全部被拒且没有一个让验证器退出码变 0：
  只改汇总数字、改 signoff 并同步 sha256、篡改某个配置的 WNS 符号、删原始报告、
  报告留在工作树但不进提交、删配置、伪造 `code_git_head`、清空执行机字段、
  冻结后偷改 RTL 并同步哈希、偷换 OOC 封装（把 `clk` 悬空以规避时序）、
  制造 L2 比 L1 还省的『自洽』面积回退、把已收敛的 dense 全标成 FAIL、
  **新增 `not_met_config_forge`**：把 `sparse/L8` 的报告+signoff+汇总三处自洽地伪造成
  100 MHz 未收敛（重算一致、只有 8/8 硬判据能挡），用来证明 P1 §二 的判据真的生效。
  面积回退那个变异本轮先失效过一次——它把 LUT 数字写死成 round 3 的 132，重新综合后
  替换静默不命中、变异变成空操作；已改成用正则从真实报告里取值，失效时直接抛
  『变异未施加』而不是伪装成通过。
  两套变异（NP7.6 的 19 项 + NP7.7 的 13 项）都在 UTF-8 与 Windows 默认代码页 936
  下各跑一遍，日志 `np76_mutations.txt` / `np76_mutations_defaultcp.txt` /
  `np77_mutations.txt` / `np77_mutations_defaultcp.txt`，四份结论一致。

## 7. 限制与不主张的内容

- **工具版本**：Vivado 证据只绑定本机 2024.2（SW Build 5239630，执行机 `Chan-an` / Windows 11），
  **不外推**到评审者使用的 2024.1；本轮 xsim 全部用例在 2024.2 编译通过，2024.1 下需复跑确认。
- **形式深度有限**：P1 后是 `sat -seq 16`（sparse/dense 协议，含新增 P11）、`-seq 14`
  （CONFIG 拒绝）与 `-seq 10/18`（可达性 witness）——仍是 Yosys 0.68 + minisat 的**有限深度**
  检查，不是无界模型检验；Yosys 为 YoWASP/WASM 构建。深度从 14/16 提到 16/18 是因为流水化
  让每笔事务多一拍，proof 时间从 39.5 s / 13.8 s 涨到 **246.8 s / 99.9 s**（本机实测）。
- **绝对周期变长**（P1 的代价，不用比例收益掩盖）：每笔非零事务 +1 个 S_DRAIN 折叠拍，
  单事务闭式周期 sparse `3+batches -> 4+batches`、dense `4+batches -> 5+batches`；
  V1 零路径仍 1 拍、lane 吞吐仍 1 batch/拍。三模型每逻辑 tick 周期因此从
  dense 基线 16.000/15.250 涨到 **18.250/17.500**（L1/L4），sparse 从 11.250/11.000 涨到
  **12.500/12.250**。G3 比例反而变好是因为两格式的非零事务数不同（同一 trace 里
  dense 基线 180 笔非零、sparse 100 笔，差值恰为每 tick 1 拍），这一点在 §0 已明说。
  随机流量下 RTL 观测的周期下降从 42.68/37.93/32.40/32.49% 降到
  **38.64/34.11/29.81/29.62%**（L=1/2/4/8，20 seed 合计；非门，仅登记）。
- **仿真规模**：Vivado xsim 每用例 120 事务（受 xsim 运行时间限制），统计规模证据来自 NP7.3 的
  Icarus 全量 160,000 事务；xsim 侧主张的是"同一 RTL 在商业仿真器下的逐拍行为与开源链一致、
  且账本可被重建"，不主张统计显著性。
- dense 的 `zero_single_cycles=5`（§4）说明 V1 单拍零路径在稠密无气泡流量下稀有，本轮按实陈述。
- 8/8 收敛的裕量不均：L1/L2 有 +3.0~+3.7 ns，L4/L8 只有 +0.138~+0.353 ns（§9）。本轮只主张
  『在 2024.2 / xc7z020clg400-1 / 默认策略下 8/8 满足 §二 的 6 条判据』，不主张跨版本、
  跨速度等级或加真实系统约束后仍然收敛；`dense/L4` 的 +0.138 ns 在任何环境波动下都可能翻负。
- 周期数字来自冻结逻辑周期模型的 RTL 逐拍计数，证明的是数字执行路径；**不证明** BRAM 真实端口
  冲突、DDR/DMA、PS 软件、以太网或板级端到端吞吐；vector-less 功耗不作为 NP7 门；不做板级结论。
- NP7.3 的每组 4 连接、10 组 RAM 内容是穷举式随机结构（seed 由 `lanes*100003+seed` 决定，可复现），
  不是真实训练权重；真实权重下的活动分布只由冻结 B2.1 任务（NP7.4）代表。
- **NP7.7 只覆盖综合/实现层**：OOC（out-of-context）单模块综合，不含真实 BRAM/DDR 端口竞争、时钟树、布局收敛后的系统级时序；`BRAM36=0/DSP=0` 是 32x20 同步 RAM 被映射成 LUTRAM、8-bit 饱和加被映射进 CARRY4 的结果，**不主张“省 BRAM/省 DSP”**，只如实报告占用为 0。
- G1–G6 在 1/2/4/8 四种 lane 数下分别报告，未以任何最优 lane 数掩盖。
- 本轮未修改 `WORKFLOW_STATE.md`、`task_plan.md`、`.nexus-map/` 与任何已签核的 NP4B/NP6 产物。

## 8. 复现命令

```text
set PATH=C:\iverilog\bin;C:\msys64\ucrt64\bin;%PATH%
python -X utf8 -m unittest test_np7_shared_lane_oracle -v   # NP7.1  20 tests OK (含 LanePipelineTests)
python -X utf8 np7_shared_lane_cosim.py                     # NP7.3  160 runs / 160000 txns
python -X utf8 np7_three_model_integration_cosim.py         # NP7.4  3 models / 0 problems
python -X utf8 np7_formal_and_mutations.py                  # NP7.5  90/90 checks / 12 mutations
python -X utf8 run_np7_vivado_xsim.py --vivado-root <Vivado2024.2 根> --transactions 120
python -X utf8 generate_np7_manifest.py                     # 仅在证据时点执行一次
python -X utf8 verify_np7_software_cost.py <HEAD>           # 只读；本轮 rejects=0 overall=PASS
python -X utf8 test_np7_verifier_mutations.py               # 19 mutations 全部被拒
python -X utf8 run_np7_vivado_ooc.py --vivado-root <Vivado2024.2 根> --jobs 4
python -X utf8 verify_np7_physical_cost.py <HEAD>           # 只读；NP7.7 rejects=0 overall=PASS
python -X utf8 test_np7_physical_mutations.py              # NP7.7 13 mutations 全部被拒
python test_np7_physical_mutations.py                      # 默认代码页(936)再跑一遍，结论一致
```

## 9. NP7.7 八配置 OOC 综合（Vivado 2024.2，P1 一拍流水后 8/8 收敛）

前置条件（NP7.0–NP7.6 全绿 + G3>=25%）成立后，按 P1 裁定 §二在 `xc7z020clg400-1` 上对
`sparse/dense x 1/2/4/8 lane` 共 8 个 out-of-context 配置**重新**执行 synth+place+route，
`create_clock -period 10.000`（100 MHz），默认策略。表里每个数字都由
`verify_np7_physical_cost.py` 从原始 `.rpt` **重算**后才写入；
`artifacts/logs/np77_ooc.txt` 头部记录本次运行 `code_git_head=9d07b99`、`worktree_dirty=[]`。

| 配置 | LUT | FF | BRAM36 | BRAM18 | DSP | WNS (ns) | TNS (ns) | WHS (ns) | THS (ns) | setup 失败端点 | hold 失败端点 | DRC | route err | RESULT | 100 MHz |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sparse/L1 | 133 | 471 | 0 | 0 | 0 | +3.727 | 0.000 | 0.159 | 0.000 | 0 | 0 | 0 | - | ROUTED | **MET** |
| sparse/L2 | 143 | 472 | 0 | 0 | 0 | +3.445 | 0.000 | 0.176 | 0.000 | 0 | 0 | 0 | - | ROUTED | **MET** |
| sparse/L4 | 193 | 475 | 0 | 0 | 0 | +0.230 | 0.000 | 0.184 | 0.000 | 0 | 0 | 0 | - | ROUTED | **MET** |
| sparse/L8 | 193 | 475 | 0 | 0 | 0 | +0.353 | 0.000 | 0.174 | 0.000 | 0 | 0 | 0 | - | ROUTED | **MET** |
| dense/L1 | 134 | 485 | 0 | 0 | 0 | +3.041 | 0.000 | 0.177 | 0.000 | 0 | 0 | 0 | - | ROUTED | **MET** |
| dense/L2 | 152 | 486 | 0 | 0 | 0 | +3.512 | 0.000 | 0.194 | 0.000 | 0 | 0 | 0 | - | ROUTED | **MET** |
| dense/L4 | 198 | 489 | 0 | 0 | 0 | +0.138 | 0.000 | 0.205 | 0.000 | 0 | 0 | 0 | - | ROUTED | **MET** |
| dense/L8 | 198 | 489 | 0 | 0 | 0 | +0.155 | 0.000 | 0.192 | 0.000 | 0 | 0 | 0 | - | ROUTED | **MET** |

验证器在同一提交上的判据输出（`artifacts/logs/np77_verify.txt`）：

```text
NP7_PHYSICAL_EXCLUDED none
NP7_PHYSICAL_GATE required=8 met=8 verdict=8/8
NP7_PHYSICAL_SUMMARY rejects=0 configs=8 timing_clean=8(sparse/L1,sparse/L2,sparse/L4,sparse/L8,dense/L1,dense/L2,dense/L4,dense/L8) excluded=0(-) overall=PASS
```

- **§二 的 6 条判据 8/8 成立**：WNS>0、WHS>0、setup 失败端点=0、hold 失败端点=0、
  DRC errors=0、routing errors=0，且 `RESULT=ROUTED`。`verify_np7_physical_cost.py` 已从
  round 3 的『未收敛列入 excluded』改成 **8/8 硬判据**：任一配置 not-MET 或原始报告缺失即
  reject；配套变异 `not_met_config_forge`（把 `sparse/L8` 的 `timing_impl.rpt`+signoff+汇总
  三处自洽地伪造成未收敛，让『重算一致』挑不出毛病）专门证明这条判据是载荷性的。
- **关键路径换了方向**（裁定的目的就是切断长链）：现在最差 setup 路径是
  `dut/pending_mask_reg[3]/C -> dut/lanes/stage2_q_reg[0][k]/D`，即 **Stage A**
  （gate + 2:4 选择 + 饱和加法树写流水寄存器）——`dense/L4` 13 级（CARRY4=10）、
  `sparse/L4` 14 级（CARRY4=7）。round 3 那条
  `dut/word0_reg[*]/C -> dut/saturation_events_state_reg[*]/CE`（14.338 ns、20 级、
  12 个 CARRY4）被寄存器切断。**Stage B**（`stage2_q -> acc + 饱和判定 + 事件计数`）
  最差 slack 是 `sparse/L4` 的 +1.293 ns（9 级、CARRY4=6），已不进最差路径。
- **裕量薄，如实说**：最差 +0.138 ns（`dense/L4`，10 ns 周期的 1.4%）、`dense/L8` +0.155、
  `sparse/L4` +0.230、`sparse/L8` +0.353。这些是本机、OOC、默认策略、布局布线后的数字；
  换 Vivado 版本、换速度等级或收紧约束都可能翻负。同 head 复跑一次 8 个配置的
  LUT/WNS/WHS 逐项相同（本机可复现），但**不等于跨环境可复现**。
- **面积代价**：LUT sparse 115/132/181/186 -> **133/143/193/193**、
  dense 137/162/192/195 -> **134/152/198/198**；FF 462 -> 471/472/475、476 -> 485/486/489
  （每 lane 多一组部分和寄存器 + 1 bit valid）。`sparse/L4` 与 `sparse/L8` 的 LUT 同为 193，
  验证器的单调性判据只拒绝『lane 增多而 LUT 减少』，等值不算回退。
- `BRAM36=0`、`BRAM18=0`、`DSP=0`：32x20 同步 RAM 被综合进 LUTRAM，8-bit 饱和加未被推断成
  DSP48。**因此不主张『节省 BRAM/DSP 资源』**，只报告实测占用为 0、面积代价全在 LUT/FF。
- 版本绑定（决定 8）：`vivado v2024.2 (64-bit) / SW Build 5239630`，执行机 `Chan-an`
  （Windows 11 AMD64，python 3.14.7）。评审者若用 2024.1 需自行复跑，**不跨版本外推**。
- 证据：8 个 `vivado_np7_ooc_<fmt>_L<n>_reports/`（各 9 份 `.rpt`/`.txt` + 自动生成的 OOC 顶层
  封装 `.sv`）+ `artifacts/results/np7_vivado_ooc_summary.json` + `np77_ooc.txt` +
  `np77_verify.txt`。`.dcp/.jou/.pb/.str` 被 `.gitignore` 排除，不作为证据。

### 9.1 历史证据：round 3 的 4/8 结果（`code_git_head=116d79c`，按裁定 §三 已降级）

| 配置 | LUT | FF | WNS (ns) | TNS (ns) | WHS (ns) | setup 失败端点 | 100 MHz |
|---|---|---|---|---|---|---|---|
| sparse/L1 | 115 | 462 | +1.281 | 0.000 | 0.179 | 0 | MET |
| sparse/L2 | 132 | 462 | +0.477 | 0.000 | 0.224 | 0 | MET |
| sparse/L4 | 181 | 462 | -4.627 | -246.636 | 0.192 | 56 | MISS |
| sparse/L8 | 186 | 462 | -5.709 | -295.570 | 0.186 | 56 | MISS |
| dense/L1 | 137 | 476 | +2.024 | 0.000 | 0.183 | 0 | MET |
| dense/L2 | 162 | 476 | +0.405 | 0.000 | 0.163 | 0 | MET |
| dense/L4 | 192 | 476 | -3.541 | -179.684 | 0.198 | 56 | MISS |
| dense/L8 | 195 | 476 | -4.695 | -243.964 | 0.197 | 56 | MISS |

该表**不参与本轮任何签核结论**，只保留作对照：同一批配置在未插流水时的 100 MHz 结果，
根因（单周期内串完 gate+饱和树+acc+饱和判定+事件计数）与 §二 的 8/8 要求共同构成了
P1 裁定的内容。软件侧同理：round 3 的 G1–G6 与每 tick 绝对周期已随 §三 降级，
本轮的 G1–G6 见 §0、覆盖度见 §4。

## 10. 批准链与下一步

- 八项冻结决定的批准链已在 PR #6 内闭环（评论 `5498372499` 逐项裁定），仓库内副本见
  `docs/planning/NPU_PRUNING_NP7_DECISION_B_V1_V2.md` §1；决策 5 的旧口径在
  `NPU_PRUNING_NP7_FREEZE_DECISIONS.md` 中标注为『已被管理员修订/作废』，不再作为合同使用。
- 本轮的 P1 修订同样只在 PR 内裁定（review `5085536010`：§一 允许 lane 内插一拍流水并列出
  7 项必须同步的重跑、§二 8/8 硬判据、§三 旧证据降级为历史证据），仓库内副本
  `docs/planning/NPU_PRUNING_NP7_DECISION_LANE_PIPELINE_P1.md` 只做逐字引用与落点映射，
  不自加授权。上一轮 §10 等待裁定的两问（可否插一拍、可否部分通过）正是该 review 的两条结论。
- 现状：NP7.0–NP7.6 全绿（`NP7_VERIFY_SUMMARY rejects=0 overall=PASS`），NP7.7 按 §二
  达成 **8/8 收敛**（`NP7_PHYSICAL_GATE verdict=8/8`、`EXCLUDED none`、`rejects=0`），
  Vivado XSim 16/16 与 Icarus 逐字节相同。
- 仓库内 TODO 的复选框由维护者勾选：本轮**未勾选任何一项**，也未改动 `WORKFLOW_STATE.md`、
  `task_plan.md`、`.nexus-map/` 与任何已签核的 NP4B/NP6 产物。
- 下一步（等复审）：(1) 按 §一 7 项 + §二 6 判据复核本轮全量重跑证据；(2) 若接受，NP7 才进入
  签核收口，是否合并由维护者决定；(3) 2024.1 跨版本复跑仍待有该版本的环境时执行，本轮不外推；
  (4) 真实权重活动分布、BRAM 端口竞争、系统级时序仍属 NP8+ 范围，本轮不主张。

## 11. PR gate（main `724a5dc`）适配与本地复刻结果

本轮 push 前 main 前进到 `724a5dc`：新增 `.github/workflows/pr-gate.yml` + `docs/CI_PR_GATE.md`，
并把 DP-NP7-001 决策文档与 TODO §8 的管理员裁定版本落库。PR #6 因此变成 `mergeable_state=dirty`，
唯一重叠文件是 `docs/planning/NPU_PRUNING_NP7_DECISION_B_V1_V2.md`——**取 main 版原文**（管理员自己写的
DP-NP7-001），撤掉我们此前的“仓库内副本”，P1 修订单独记在 `NPU_PRUNING_NP7_DECISION_LANE_PIPELINE_P1.md`。
合并提交 `27bd388`。`task_plan.md` / `findings.md` / `progress.md` / `docs/README.md` 只是随合并带入
main 的内容，本方未自行编辑这些文件。

gate 的 `NP7 functional` 作业顺序是“先重跑 NP7.3/NP7.5，再用 PR HEAD 校验 NP7.6 清单绑定”，
所以本轮做了三处适配（提交 `a0987e1`）：

1. `np7_formal_and_mutations.py` 的 yosys/iverilog/vvp 由写死的 `C:\...` 改为
   “环境变量 `NP7_YOSYS/NP7_IVEROLOG/NP7_VVP` > PATH > 已知 Windows 安装路径 > 裸名”
   （与仓库既有 `rtl_tile_cosim.find_tool()` 同一口径）。本机解析结果与旧绝对路径一致
   （yosys 0.68 / Icarus 12.0，`C:\iverilog\bin`），所以证据语义不变；ubuntu runner 上用 apt 版本。
2. 同脚本新增 `keep_or_freeze_evidence()`：**默认不改写已冻结证据字节**，只有显式
   `NP7_FREEZE_EVIDENCE=1` 才重绑；若语义字段（formal / mutation / negative / ledger）与冻结证据
   不一致则不改写、直接返回失败。旧实现无条件写入 `git_head`/`tool_versions`，在 CI 顺序下必然触发
   `evidence_files 磁盘字节偏离清单 artifacts/results/np7_formal_and_mutations.json`——
   这是复现门的假失败（本地按 CI 顺序复刻时已实测复现，见下方矩阵）。
3. 结论行打印去掉行尾空白，`formal_np7_exec_unit.sv` 第 570 行的行尾空白一并清掉
   （gate 的 `git diff --check` 会因日志尾随空格整体失败）。

`.gitattributes` 只给**工具生成的原始报告**加 `-whitespace`（`*.rpt`、`vivado_np7_ooc_*_reports/**`、
`vivado_np7_xsim_reports/**`、`artifacts/logs/np7_vivado_xsim.txt`）：Vivado/xsim 的行尾空格是其表格排版
的一部分，为满足 lint 去改写工具输出等于伪造证据。豁免只关闭空白 lint，不改行尾策略、不影响哈希与清单绑定。
实测 `git diff --check main...HEAD` 由 **4930 处（51 文件）降到 0 处**（其中 27 处 NP7.5 日志随生成器修复重跑消除，
1 处是我们手写 SV 的真实缺陷已修，其余全是 Vivado/xsim 原样输出）。

`test_artifact_layout.py` 的归档清单与 `artifacts/README.md` 索引补登 PR #5/#6 新增的 7 个
`artifacts/results/*.json`（`np6_physical_cost_manifest` + 6 个 `np7_*`）。该测试在 main tip `724a5dc`
的干净工作树上**本来也 FAIL**（缺 `np6_physical_cost_manifest.json` 登记），本轮一并修好。

### 11.1 本地按 `docs/CI_PR_GATE.md` 逐条复刻（隔离工作树，HEAD `27bd388` = 适配前）

| gate 步骤 | 命令 | rc | 结论 |
|---|---|---|---|
| Python and syntax | `python -X utf8 -m compileall -q .` | 0 | PASS |
| Python and syntax | `python -X utf8 -m unittest discover -v` | 1 | 407 tests：**1 FAIL**（`test_artifact_layout`，本轮已修）+ **2 ERROR**（`test_host_bridge_xpm_wrapper`，见 §11.2） |
| NP7 functional | `python -X utf8 -m unittest -v test_np7_shared_lane_oracle` | 0 | PASS |
| NP7 functional | `python -X utf8 np7_shared_lane_cosim.py` | 0 | 160 配置 / 160,000 事务；输出与冻结证据逐字节相同（确定性复现，57s） |
| NP7 functional | `python -X utf8 np7_three_model_integration_cosim.py` | 0 | 输出与冻结证据逐字节相同 |
| NP7 functional | `python -X utf8 np7_formal_and_mutations.py` | 0 | 90/90、12/12 counterexample；但**改写了**证据字节 → 下一步假失败 |
| NP7 functional | `python -X utf8 verify_np7_software_cost.py <PR HEAD>` | 1 | `rejects=3`：2 条来自合并改动的 planning 文档（随后重绑清单解决），1 条正是上面那条“磁盘字节偏离清单” |
| NP7 physical evidence | `python -X utf8 verify_np7_physical_cost.py <PR HEAD>` | 0 | `rejects=0 8/8` |
| NP7 physical evidence | `python -X utf8 test_np7_physical_mutations.py` | 0 | 13/13 PASS |
| Python and syntax | `git diff --check base...head` | 2 | 4930 处尾随空白（→ 本轮 .gitattributes + 生成器修复后 0） |

适配后（HEAD `06d7f38`）的本地复跑：`verify_np7_software_cost.py` **rejects=0 / overall=PASS**，
`verify_np7_physical_cost.py` **rejects=0 / configs=8 / timing_clean=8**，
两套变异 `19/19` 与 `13/13` PASS（UTF-8 与默认代码页 936 各一轮），NP7.5 重跑 `90/90`、
`12/12 mutation counterexample`、`problems=0`，且除新增一行 FREEZE 提示外与上一轮输出逐行相同。

### 11.2 仍未解决、且不属于 NP7 范围的 gate 失败（请管理员裁定）

`test_host_bridge_xpm_wrapper` 写死 `C:/msys64/ucrt64/bin/iverilog.exe`：在 ubuntu runner 上必然
`RuntimeError: 需要 C:/msys64/ucrt64/bin 下的 iverilog 和 vvp`；在本机该 iverilog 构建编译
`xpm_fifo_async_sim.sv` 时以退出码 `3221225477`（`0xC0000409`）崩溃、无 stdout/stderr，而仓库其余
NP7 步骤用的是 `C:\iverilog\bin` 的 Icarus 12.0（同一份 RTL 手工编译 rc=0 通过）。
在 `724a5dc` 干净工作树上单独运行该模块同样 2 ERROR（`Ran 3 tests ... FAILED (errors=2)`），
**与 PR #6 的改动无关**。可选处置：(a) 把该测试改用仓库既有 `find_tool()` 并在工具缺失时 `skipUnless`；
(b) 让 gate 的 discover 步骤只跑与改动相关的测试；(c) 维持现状，把它记为已知红。按
`docs/CI_PR_GATE.md` 的“出现门槛或范围选择必须回到 PR 请求裁定”，本方**不擅自修改他人的测试与工作流**。

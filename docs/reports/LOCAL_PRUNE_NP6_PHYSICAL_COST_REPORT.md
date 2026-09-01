# NPU 局部剪枝 NP6 物理成本阶段报告（NP6.2–NP6.7）

日期：2026-09-01。冻结分支 `feature/np6-runner-audit-20260901`，冻结 HEAD `67a70f342d46e358742b98242e3b14a5238445b0`（短 `67a70f3`）。

## 1. 冻结基线

- 批准：用户 2026-09-01 明确批准进入 NP6 并调用 Vivado；九项冻结决策记录于 `docs/planning/NPU_PRUNING_NP6_FREEZE_DECISIONS.md`。
- 器件：`xc7z020clg400-1`；时钟：单时钟对象 100 MHz（10 ns）；配对 4 两侧统一采用 CLK_SRC + I/O false paths（测量范围为 register-to-register）。
- 策略：Vivado 默认综合 + 默认实现，`out_of_context`；不做策略扫描。
- 执行机与版本：MGL 笔记本，Vivado 2024.2（SW Build 5239630）。与 TODO §2 所写评审机 2024.1 不同，全部结论仅对本机版本成立，跨版本不外推。
- 范围：未修改任何已冻结 RTL/约束；新增 5 个测量用 runner 与 2 个既有 runner 的证据字段补丁（均不在 NP4B 签核文件清单内）。

## 2. 逐次运行结果

7 次运行全部综合/实现退出码 0、route error 0、DRC error 0。vector-less 功耗仅为估算（置信度 Medium），不是真实活动功耗。
| 配对/侧 | TOP | LUT | FF | BRAM36 | DSP | WNS ns | TNS ns | WHS ns | THS ns | setup失败端点 | hold失败端点 | 功耗估算 W |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1-gate/gate | `local_prune_gate_2of4` | 200 | 499 | 0 | 0 | 3.073 | 0.000 | 0.182 | 0.000 | 0 | 0 | 0.108 |
| 2-eneuron/unpruned | `digital_lif_core` | 2320 | 214 | 0 | 0 | -21.587 | -3108.765 | 0.241 | 0.000 | 204 | 0 | 0.143 |
| 2-eneuron/pruned | `eneuron_local_prune_wrapper` | 1166 | 834 | 0 | 0 | 0.063 | 0.000 | 0.133 | 0.000 | 0 | 0 | 0.121 |
| 3-pulse-mini-l/unpruned | `pulse_mini_core` | 299 | 79 | 0 | 0 | -2.775 | -61.844 | 0.212 | 0.000 | 27 | 0 | 0.105 |
| 3-pulse-mini-l/pruned | `pulse_mini_l_prune_wrapper` | 596 | 435 | 0 | 0 | -5.094 | -119.900 | 0.098 | 0.000 | 26 | 0 | 0.108 |
| 4-pulse-mini-l2/unpruned | `pulse_mini_l2_core` | 347 | 93 | 0 | 0 | -2.866 | -75.777 | 0.191 | 0.000 | 33 | 0 | 0.105 |
| 4-pulse-mini-l2/pruned | `pulse_mini_l2_prune_wrapper` | 696 | 453 | 0 | 0 | -5.160 | -155.235 | 0.165 | 0.000 | 33 | 0 | 0.109 |

## 3. 配对增量（剪枝侧 − 未剪枝侧）

| 配对 | 未剪枝 LUT/FF | 剪枝 LUT/FF | dLUT | dFF |
|---|---|---|---|---|
| 2-eneuron | NOT_COMPARABLE | NOT_COMPARABLE | NOT_COMPARABLE | NOT_COMPARABLE |
| 3-pulse-mini-l | 299 / 79 | 596 / 435 | +297 | +356 |
| 4-pulse-mini-l2 | 347 / 93 | 696 / 453 | +349 | +360 |

说明：配对 2 的增量按冻结决策 10 标 `NOT_COMPARABLE`（排除单周期核与多周期引擎的微架构差异；见 §5/§6）。配对 3/4 的剪枝侧开销为 bridge + gate + evidence 逻辑，裸核关键路径未变，故两侧时序门状态一致。

## 5. NOT_COMPARABLE 配对与增量

- 配对 2（ENeuron 对）增量：按冻结决策 10（评审 review 5077084799 第 2 条）标 `NOT_COMPARABLE`——未剪枝侧为单周期 `digital_lif_core`，剪枝封装内含多周期 `digital_lif_engine`，资源/时序差值混入微架构变化；仅保留两侧绝对实现结果，不计算剪枝增量。
- 配对 5（`4→8→2` 网络对）：仓库中不存在未剪枝 `4→8→2` 顶层；按冻结决策 7 标 `NOT_COMPARABLE`，不新建仅测量用顶层。
- 配对 6（Host Bridge + Tile 系统对）：不存在接入剪枝 sideband 的系统版本；按冻结决策 8 标 `NOT_COMPARABLE`，不新建系统 RTL。
## 6. 注意事项与限制

- 配对 2 口径：−21.587 ns 与 +0.063 ns 的差异主要由微架构（单周期对多周期）导致；资源差值同样含架构差异，故按决策 10 不计增量。独立成立的结论是：剪枝封装实现本身满足 100 MHz。
- `pulse_mini_core` 旧证据（提交 `a04a1a0`，Vivado 2024.1，WNS +0.463 ns，182 LUT）对应 `b53ac95` 加入 leak timer 之前的 RTL，已过期不可比；本报告以冻结 HEAD 上的重测（299 LUT，WNS −2.775 ns）为准。
- vector-less 功耗：静态功耗 0.103 W 占绝对主导，各配置动态功耗差异在毫瓦级；不将功耗数值解释为剪枝收益。
- OOC 测量不含 I/O 延迟；配对 3 用纯时钟约束、配对 4 用 CLK_SRC + I/O false paths，口径差异已在配对内保持一致。
- 时序门部分未通过是测量结果而非执行错误；本报告未为通过时序而修改任何冻结 RTL。

## 7. 证据链与可复核性（按评审 5077084799 修订）

- 每个报告目录含固定 9 件套：synth/impl 的 utilization、timing、drc 报告，impl 的 power 与 route_status 报告，以及 `signoff_summary.txt`（含 PART/TOP/CLOCK_MHZ/GIT_HEAD/RUNNER/PAIR/SIDE/资源/时序/失败端点数）。
- 验证器 `verify_np6_physical_cost.py` 为**只读**：从已提交清单（`git show` 字节级比对）出发，逐文件核对 SHA-256，并**直接从 utilization/timing/DRC/route 报告重算**关键结论、与摘要交叉核对；清单由 `generate_np6_manifest.py` 在证据时点一次性生成，不绑定 `.dcp`；绑定对象含全部 runner、验证器自身与被测 RTL。
- 变异负向测试 `test_np6_verifier_mutations.py`：删时序报告、改摘要、改报告、改 runner、删摘要、改清单六类 mutation 均必须非零退出；并断言正向通过后清单字节不变、工作树干净。
- 运行前结构预检：Icarus elaboration 7 配置 `NP6_STATIC_ELAB PASS`。

## 8. 结论与后续

- 剪枝门 `local_prune_gate_2of4`：200 LUT / 499 FF / 0 BRAM / 0 DSP，100 MHz 时序通过。
- 剪枝封装相对裸核开销（同微架构可比对）：Pulse-Mini-L +297 LUT / +356 FF；Pulse-Mini-L2 +349 LUT / +360 FF（含 bridge + gate + evidence 逻辑）。
- 建议状态记为 `NP6_PHYSICAL_COST_PARTIAL`（时序门部分未通过）；`WORKFLOW_STATE.md` 由评审管理，协作侧不修改，状态推进请评审核查后执行。
- 授权链：批准来源与待确认状态见 `docs/planning/NPU_PRUNING_NP6_FREEZE_DECISIONS.md` 与 PR #5 评论 5492861157。
- 后续选项（均需另行裁定）：降低时钟目标重测；流水线/重定时（涉及 RTL 修改，另立项）；补测配对 2 同引擎未剪枝侧；维持 100 MHz 结论不变。
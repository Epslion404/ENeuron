# NPU 局部剪枝 NP6 冻结决策记录（NP6.0）

- 日期：2026-09-01
- 批准来源：仓库外用户指令（2026-09-01，原文"我批准，现在跑vivado仿真，跑完pr"）。按评审意见（review 5077084799 第 3 条），批准链溯源记录于 PR #5 评论 5492861157，并提请仓库所有者在 PR 内逐项确认；确认前本轮证据视为"已执行、授权待确认"。协作者自述不作为自身执行授权的唯一证据。
- 冻结分支：`feature/np6-runner-audit-20260901`；执行 HEAD 以各运行摘要的 GIT_HEAD 字段为准
- 执行机：MGL 笔记本（本机）；Vivado 2024.2（SW Build 5239630），路径 C:/Users/MGL/Documents/Codex/Vivado2024_2
- 状态：九项裁定完成，允许按 NP6.2 及后续任务执行

## 1. 九项冻结决策

| # | 决策 | 裁定 |
|---|------|------|
| 1 | 是否批准进入 NP6 并允许调用 Vivado | 批准（限本文件记载的执行机、版本与范围） |
| 2 | 器件 | `xc7z020clg400-1` |
| 3 | 时钟 | 单时钟对象 100 MHz（10 ns）；Host/Tile 50/100 MHz 双时钟合同冻结但本轮不使用（配对 6 为 NOT_COMPARABLE） |
| 4 | 比较矩阵 | 接受六类配对对象；不可比对象必须标记 `NOT_COMPARABLE` |
| 5 | vector-less 功耗 | 仅作附带估算，不作硬门或性能收益声明 |
| 6 | 既有 5 个 xc7a35 代理 runner | 不修改；NP6 新建 xc7z020 平行 runner，既有代理证据保留原 part 上下文 |
| 7 | 配对 5 未剪枝 4→8→2 基线 | 标 `NOT_COMPARABLE`（不新建仅测量用未剪枝顶层；用户后续如要求重建可重开本决策） |
| 8 | 配对 6 系统对 | 确认 `NOT_COMPARABLE`（剪枝系统版本不存在，不新建系统 RTL） |
| 9 | Vivado 版本与执行机 | 本机 Vivado 2024.2；与 TODO §2 所写评审机 2024.1 的偏差如实记录，证据仅绑定 2024.2 |

说明：决策 7/8/9 为用户概括批准下的默认裁定，并已在 PR 评论中提请评审知悉；如有异议，任一停止条件触发即停并回退到静态审计状态。
## 2. 冻结执行矩阵（本轮实际运行范围）

| 配对 | 对象 | 未剪枝侧 | 剪枝侧 | 本轮动作 |
|------|------|----------|--------|----------|
| 1 | `local_prune_gate_2of4` 独立 OOC | 不适用 | `local_prune_gate_2of4` | 新建 runner 并运行（剪枝侧） |
| 2 | ENeuron wrapper 对 | `digital_lif_core` | `eneuron_local_prune_wrapper` | 新建两侧 xc7z020 runner 并运行 |
| 3 | Pulse-Mini-L wrapper 对 | `pulse_mini_core` | `pulse_mini_l_prune_wrapper` | 未剪枝侧复用既有 `vivado_pulse_mini_synth.tcl`；剪枝侧新建 runner 并运行 |
| 4 | Pulse-Mini-L2 wrapper 对 | `pulse_mini_l2_core` | `pulse_mini_l2_prune_wrapper` | 未剪枝侧复用既有 `vivado_pulse_mini_l2_synth.tcl`；剪枝侧新建 runner 并运行 |
| 5 | `4→8→2` 网络对 | 未剪枝顶层不存在 | 存在 | 标 `NOT_COMPARABLE`，不运行 |
| 6 | Host Bridge + Tile 系统对 | 存在 | 无剪枝系统版本 | 标 `NOT_COMPARABLE`，不运行 |

冻结参数：器件 `xc7z020clg400-1`；单时钟 100 MHz（period 10.000 ns）；Vivado 默认综合/默认实现策略；`out_of_context`；不做策略扫描。

## 3. 证据合同（对应 TODO §2/§5）

- 每次运行记录：Git HEAD、Vivado 版本、Tcl 脚本名、退出码、运行时长、报告目录；`signoff_summary.txt` 含 PART/TOP/CLOCK/资源/WNS/WHS/TNS/THS/GIT_HEAD/RUNNER。
- 新鲜度门：报告由本轮在冻结 HEAD 上实际运行产生，不早于被测对象最后修改时间；由独立校验器核对。
- 绑定门：报告目录内关键文件做 SHA-256 清单，随提交入库。
- vector-less 功耗：仅记录为估算值与置信度说明，不解释为真实活动功耗或收益。

## 4. 边界与限制

- 本轮不修改任何已冻结 RTL/约束；仅新增静态审计、冻结记录、新 runner 与运行证据。
- 本机为 Vivado 2024.2，与 TODO 所写评审机 2024.1 不同；所有结论仅对 2024.2 + 本机 + 上述冻结参数成立，跨版本不外推。
- 逻辑资源计数不得解释为物理加速、BRAM 跳读或真实功耗收益。

## 5. 评审修订（review 5077084799，2026-09-01）

| # | 决策 | 裁定 |
|---|------|------|
| 10 | 配对 2 的资源/时序增量 | 标 `NOT_COMPARABLE`：未剪枝侧 `digital_lif_core` 为单周期微架构，剪枝封装内含多周期 `digital_lif_engine`，差值混入微架构变化，不能解释为剪枝收益或开销；仅保留剪枝封装绝对实现结果，本阶段不补测 |

- 验证器改为只读 fail-closed：清单生成（`generate_np6_manifest.py`）与验证（`verify_np6_physical_cost.py`）分离；验证器从 utilization/timing/DRC/route 报告直接重算关键结论并与摘要交叉核对；清单不绑定 `.dcp`；新增变异负向测试套件 `test_np6_verifier_mutations.py`（删时序报告/改摘要/改报告/改 runner/删摘要/改清单均必须非零退出）。
- 修复后从新冻结 HEAD 全量重跑并重新生成证据。
- 根目录孤立诊断片段 `tight_setup_hold_pins.txt` 已删除（并加入 `.gitignore`）。

# NPU 局部剪枝 NP7 冻结决策记录（NP7.0）

- 日期：2026-09-01
- 批准来源：仓库外用户指令（2026-09-01，原文"拉取并按todo执行下一步的vivado仿真"）。该指令为概括批准：既授权按 TODO 顺序推进功能门，也授权执行 NP7.7 的 Vivado 仿真。据此对 TODO 第 8 节八项决定按默认条款逐项裁定，并在 PR 中提请仓库所有者逐项确认（NP6 先例：PR #5 评论 5492928792 闭环批准链）。
- 冻结分支：`feature/np7-shared-lanes-20260901`，基线 `main @ 8853f7b`
- 执行机：MGL 笔记本；Vivado 2024.2（SW Build 5239630），路径 C:/Users/MGL/Documents/Codex/Vivado2024_2
- 状态：八项裁定完成；NP7.1-NP7.6 功能门允许实施；NP7.7 Vivado 仅在 NP7.0-NP7.6 全绿后执行

## 1. 八项冻结决策

| # | 决策 | 裁定 |
|---|------|------|
| 1 | 两阶段边界：先做单个共享突触执行单元，再接入三神经元网络 | 批准。阶段一边界为"共享 RAM+lane 执行单元"与"网络"，网络只替换突触读取/累加 |
| 2 | 稀疏记录使用两权重 + 两个 2-bit 位置索引，掩码由索引重建 | 批准。追加裁定：索引必须互异且严格升序（`idx0 < idx1`）；等值、降序或越界均为非规范编码，在 CONFIG 写入时拒绝，执行路径不再重复检查；不存第二份掩码真值 || 3 | 底板 RAM 为 CONFIG 写入、运行时只读，不做训练权重写回 | 批准。权重与剪枝结构经 CONFIG 装载口预写入；运行时无权重写端口、无双写仲裁、无一致性回写 |
| 4 | 固定扫描 1/2/4/8 lane，并与同 lane 数 dense 基线比较周期 | 批准。lane 数 = 每周期可发射的"命中活动的带符号权重饱和加"操作数；dense 与 sparse 顶层共用同一 lane 阵列与同一饱和加法模块 |
| 5 | 单槽 ready/valid 与 issue_mask=0 零突触快速路径 | 批准。零路径不产生 RAM 请求与 lane 发射，仍在同一协议下产生恰好一个 done；同一逻辑 tick 内上层照常推进泄放、阈值与时间状态 |
| 6 | 三模型全部接入冻结 4->8->2 B2.1 任务，禁止跨模型替换 | 批准。ENeuron、Pulse-Mini-L、Pulse-Mini-L2 各自独立接入并独立签核 |
| 7 | 硬门：读取/操作相对 dense 减少 >=45%，同 lane 周期相对 dense 减少 >=25% | 批准。拥塞抵消必须单列（stall 与结构跳过、输入为零分账），不得用 busy 掩盖；不达标即 NP7.6 失败并停在功能阶段 |
| 8 | NP7.0-NP7.6 全通过后才使用 Vivado 2024.1 | 批准执行门；版本偏差如实记录：本机仅有 Vivado 2024.2，NP7.7 证据只绑定 2024.2，不外推到 2024.1，与 NP6 决策 9 处理方式一致，待所有者在 PR 内确认 |

## 2. 冻结数据格式、位宽与周期合同

| 项目 | 冻结值 |
|------|--------|
| 权重位宽 | signed 8-bit，与既有 host_weight_wdata 一致 |
| 突触输入语义 | 1-bit 活动（spike）；lane 操作 = 对"结构保留 AND 活动命中"的权重做饱和加 |
| 组宽度 | 每组固定 4 条连接（与既有 2:4 gate 合同一致） |
| dense 记录 | 4 个权重 = 40 bit 有效负载（每 2 权重一字 + 4 bit 保留必须为 0），每组 2 字 |
| sparse 记录 | 2 权重 + idx0 + idx1 = 20 bit 有效负载，每组 1 字 |
| RAM 字宽 | 20 bit（16 bit 权重对 + 4 bit 索引/保留）；深度 32 字；地址 5 bit |
| 累加域 | signed 12-bit 饱和加法，组突触和输出 signed 12-bit |
| 活动/结构掩码 | 各 4 bit；issue_mask = 结构掩码 AND 活动掩码，仅在 CONFIG 由索引重建 |
| lane 数 | 1 / 2 / 4 / 8（同一测试向量分别扫描） |

### 2.1 周期模型（oracle 与 RTL 共用，逐拍一致）

单槽执行协议，非流水状态机。记 n_words = dense 2 字 / sparse 1 字，k = 本组实际发射的 lane 操作数：

1. ACCEPT 拍：issue_valid 且 issue_ready，状态机离开 IDLE；该拍不发 RAM 请求、不发 lane 操作。
2. READ 拍：n_words 拍，每拍一次同步 RAM 读请求（ram_ce=1，地址递增）。issue_mask=0 时整段跳过。
3. LATENCY 拍：1 拍，等待同步 RAM 输出有效（BRAM 原语读延迟）。零快速路径整段跳过。
4. BATCH 拍：ceil(k / L) 拍，L 为 lane 数；lane_ready=0 时该拍不推进并记 stall。
5. DONE 拍：done_valid 至 done_ready，至少 1 拍；每个已接受事务恰好一个 done。

因此 k>0 的组周期 = 1 + n_words + 1 + ceil(k/L) + 1；issue_mask=0 的零路径组周期 = 1 + 1 = 2（仍完成事务，无 RAM/lane 请求）。

### 2.2 账本分账（禁止重复记功）

- weight_values_fetched：dense 每组 4 个权重槽，sparse 每组 2 个；这是"实际权重槽读取"硬门口径。
- lane_ops_issued：等于 k = popcount(结构掩码 AND 活动掩码)；dense 基线的 k = popcount(活动掩码)。
- 结构跳过（被 2:4 去掉）、输入为零（活动掩码为 0）、背压等待（lane_ready=0）三者分列计数；同一条连接只计入其中一类。
- busy_cycles：状态机非 IDLE 且当拍发出 RAM 请求或 lane 操作的拍；stall_cycles：非 IDLE 且因下游 ready=0 未推进的拍；二者不重叠。

## 3. 硬门与测量口径

| 门 | 口径 | 阈值 |
|----|------|------|
| G1 读取减少 | 冻结 B2.1 全网络实际权重槽读取（含 CONFIG 后运行期），结构 2:4 + 活动门控 vs dense 基线 | >=45% 下降 |
| G2 操作减少 | 全网络 lane 操作数，同上比较 | >=45% 下降 |
| G3 周期减少 | 每逻辑 tick 周期，共享 lane vs 同 lane 数 dense 基线 | >=25% 下降 |
| G4 无拥塞抵消 | busy/stall 分账，持续吞吐不得被 stall 增长抵消 | stall 增幅须单列并可解释 |
| G5 等价性 | 膜状态/spike/输出/剪枝账本 bit-exact；dense 与 sparse 相同有效连接突触和 bit-exact | 逐拍全等 |
| G6 精度 | 三模型 BAcc/coverage 维持既有门槛，INFER 状态冻结 | 不低于 B2.1 冻结值 |

G1-G6 在 1/2/4/8 四种 lane 数下分别报告；总体结论取"是否存在同时满足全部硬门的最小配置"，与 NP7.7 "选择同时满足时序与工程信道的最小实现"一致。任一 lane 数不达标必须如实标 FAIL 并列出，不得以最优 lane 数掩盖。

## 4. 停止条件与证据边界

- NP7.0-NP7.6 任一硬门失败：停在功能阶段，不开 NP7.7 Vivado，PR 内如实标注状态。
- 稀疏格式要求额外读取才能还原结构、或实际权重槽读取超过 dense：立即停止。
- 共享 lane 改动神经元泄放、阈值、学习或响应协议：停止。
- 需要违反 2:4 结构、双写一致性、跨 lane 写回或引入 AXI/DMA 才能通过：停止，不扩展范围。
- NP6 的源码与资源结果不能替代 NP7 的 RAM/lane 实现证据；本轮只证明逻辑周期模型与器件综合，不证明 DDR/DMA/PS 软核端到端；vector-less 功耗不作为 NP7 门；不做板级或以太网结论。

## 5. 任务-产物映射

| 任务 | 产物 |
|------|------|
| NP7.1 | np7_shared_lane_oracle.py、test_np7_shared_lane_oracle.py |
| NP7.2 | np7_weight_ram.sv、np7_shared_synapse_lane.sv、np7_exec_unit_dense.sv、np7_exec_unit_sparse.sv、tb_np7_exec_unit.sv |
| NP7.3 | np7_shared_lane_cosim.py |
| NP7.4 | np7_three_model_integration_cosim.py |
| NP7.5 | np7_negative_controls.sv（两个负向实现）、np7_formal_and_mutations.py、formal_np7_exec_unit.ys |
| NP7.6 | verify_np7_software_cost.py、generate_np7_manifest.py、test_np7_verifier_mutations.py、docs/reports/LOCAL_PRUNE_NP7_SHARED_LANE_REPORT.md |
| NP7.7 | vivado_np7_*_synth.tcl、vivado_np7_*_reports/、verify_np7_physical_cost.py（功能门全绿后才执行） |

# 核心领域概念

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-07
provenance: NP4B/NP6/NP7 TODO、工作流状态与 RTL 文件；集成边界来自审核材料包

- `TICK`：推进一个样本或网络时刻。
- `OBSERVE`/`evidence`：读取已提交学习证据，不读取 live 工作副本。
- `2:4`：每四个连接恰保留两个，提交必须原子完成。
- `issue_mask`：在读取/发射前形成的门控掩码。
- `STATE_CLEAR`：清动态历史但保留剪枝状态。
- `PRUNE_CLEAR`：配置阶段恢复稠密掩码并清 utility。
- `fail-closed`：证据缺失、陈旧或哈希不符时拒绝签核。
- `NP6_PHYSICAL_COST_PARTIAL`：物理成本阶段的正式状态；不是整体时序通过，也不是板级性能结论。
- `NP7`：已合并并签核的共享 BRAM 与共享 lane 阶段；其逻辑/物理证据不能外推为传统 NPU + ENeuron 的集成收益。
- `RTL_DESIGN_REVIEW_WITH_ACTIONS`（历史阶段）：OF4g 修正模型端口冻结边界，`loading/complete` 阻止冻结而 `committed` 允许冻结和推理；OF5 冻结 hard reset 的破坏性清理，丢弃模型/mask/runtime staging、结果与冻结状态并恢复 `epoch=0`、全开 mask、`model_valid=0`。OF6 汇总 OF1-OF5，相关 Python oracle 回归 48/48、CI-Fast 8/8，曾签核合并于 `main@0982ac5`。该阶段的“单时钟 RTL、完整流接口与 Vivado 尚未完成”仅描述当时快照，不覆盖当前 PR #55/OOC 归档状态。
- `VIVADO_OOC_100MHZ_PASS`：当前单时钟 NPU + ENeuron 集成的 OOC 物理状态。V2 绑定 `f744bff`，资源 `2126 LUT / 1916 FF / 0 BRAM / 4 DSP48E1`，100 MHz `WNS=+0.060 ns / TNS=0 / WHS=+0.040 ns`，setup/hold/route/DRC 零失败；不等价于板级签核。
- `DSP_GATE_PASS`：Vivado utilization 为 `DSP=4`，实现网表 `DSP48E1_COUNT=4`，四个 cell 对应 `lane_product_0..3`；只表示强制 DSP 结构合同成立，不代替 setup 签核。
- `TIMING_REPAIR_V1_FUNCTIONAL_GREEN`：TR1-TR6 已实现，共享四 DSP lane、FETCH/EXECUTE/COMMIT、C1-C4、固定 `20×100` 和完整回归均通过；因 setup 失败，该状态不等于物理通过。
- `TIMING_REPAIR_V2_FUNCTIONAL_GREEN`：TR7-TR12 已实施，V2 独立 RED、定向门、固定 `20×100`、完整回归和逐组 WRITEBACK/激活锁存合同均通过；C1-C4 为 `1902/1898/718/1900` 拍。
- `P15_T0_APPROVED / T1_RTL_AUTHORIZED`：方案 A 与 A1-A7 已批准，允许实现纯 RTL wrapper、四条异步 FIFO 和 FIFO 外 AXI-Stream shim；这是实施授权，不是完成证据。当前 T1/T2/T3 均未签核。
- `T1_PROTOCOL_SLICE_PROVEN / T1_FULL_PENDING`：T1 wrapper、testbench、XPM 仿真模型、manifest 和统一复现入口已进入仓库；隔离快照中的 G0/G1 与 Icarus 协议切片通过。该状态只覆盖当前协议场景，不等于 T1-01～T1-12 全量、T2 双时钟、T3 XC7Z020 OOC 或板级完成。
- `RESOURCE_CUT_DEFERRED_UNTIL_FIRST_END_TO_END_RUN`：资源裁剪候选已完成风险审查，但第一次完整端到端运行成功前不得实施；当前优先保持功能、CDC、原子性和诊断基线完成 T1/T2/T3。
- `B-V1+V2`：NP7 已批准的单槽弹性流水合同，允许零路径同拍完成及非零结果退出与下一事务接受重叠；其收益只由逐拍账本证明。
- `CI-Fast V1`：按变更路径选择验证范围的 Action 编排；Action 基线已从 `actions/checkout@v4`、`actions/setup-python@v5` 升级为二者 `@v7`（Node 24）。已完成 workflow 全量、文档轻量与 NPU-only 定向路径验证；任何 workflow 变更必须运行全量门，未知代码触发全仓回归，手动运行触发全部专项门。
- `PR Gate`：始终执行的汇总状态；只允许被选专项门 `success` 或 `skipped`，任何失败均拒绝合并。分支保护应只要求该状态。
- `SINGLE_CLOCK_RTL_DECISION_V2`：OF6 后的单时钟 RTL 裁定修订稿。V1 审计暴露了统一命令流中的双 commit 假竞争、未定义 `model_epoch`、样本 framing/首拍 mask 回滚边界、idle 槽位遗漏及过弱随机门槛；V2 固定 8/10 beat 内部计数、删除 `model_epoch`、按单命令流串行化配置、补全 idle 槽位，并恢复 20 个固定 seed × 100 样本门槛。管理员已批准，状态为 `RTL_DESIGN_CONTRACT_V2_APPROVED`；“仅允许 RED/端口骨架，先过 Python/Icarus 逐拍验证，再申请 Vivado”是当时的历史准入规则，当前已推进到 OOC setup 失败与时序修复审核阶段。
- `RTL_SKELETON_IN_PROGRESS`（历史实现阶段）：V2 协议的渐进 RTL 阶段。模型/流、mask epoch、控制三条切片已通过 Icarus；控制切片加入 abort、clear 和严格 idle freeze，冻结仍允许推理但拒绝配置/clear。该状态不代表真实 mask 已控制 MAC，也不包含完整随机逐拍或 Vivado 证据；当前已由 PR #54 的真实计算/随机门和 PR #55 归档的 `VIVADO_OOC_SETUP_FAIL` 证据覆盖。

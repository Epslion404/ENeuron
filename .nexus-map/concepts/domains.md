# 核心领域概念

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-05
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
- `VIVADO_OOC_SETUP_FAIL`：当前单时钟 NPU + ENeuron 集成的物理签核状态。Vivado 2024.1、`xc7z020clg400-1`、100 MHz OOC 已完成综合/实现、资源、setup/hold、route 和 DRC 报告；route/DRC error=0、hold 通过，但 setup `WNS=-5.087 ns`、244 个端点失败，因此必须先修复关键路径并在同一器件/频率范围重跑，不能宣称 100 MHz 收敛或板级性能。
- `TIMING_REPAIR_REQUIRED`：功能、协议和固定 `20×100` 随机门已绿，但 100 MHz setup 未收敛。修复不得弱化 INT32 累加、`64→32→10` 拓扑、四权重整组 mask、mask epoch 原子切换、结果单槽背压、freeze/clear、8-beat 输入、10-beat 输出及配置错误处理；完成后必须在同器件、同频率约束下重跑 OOC。
- `TIMING_REPAIR_V1_REVIEW_REQUIRED`：`docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V1.md` 提出的 TR1-TR6 尚待管理员批准。当前只允许文档审计和测试合同检查，不代表分拍 RTL 已实现，也不代表 100 MHz 已收敛。
- `TIMING_REPAIR_TEST_CONTRACT_PREPARED`：`docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_TEST_CONTRACT_V1.md` 已把三拍设计转换为 C1-C4 状态次数、延迟、最后组和关闭组检查，状态为 `PREPARED / BLOCKED_BY_TR1_TR6_APPROVAL`。C1/C2/C3/C4 分别为 `592/590/0/591` 个启用组与 `1860/1856/676/1858` 拍；五个 watchdog 无需放宽。该状态不表示 RED 已创建、RTL 已修改或 100 MHz 已通过。
- `B-V1+V2`：NP7 已批准的单槽弹性流水合同，允许零路径同拍完成及非零结果退出与下一事务接受重叠；其收益只由逐拍账本证明。
- `CI-Fast V1`：按变更路径选择验证范围的 Action 编排；Action 基线已从 `actions/checkout@v4`、`actions/setup-python@v5` 升级为二者 `@v7`（Node 24）。已完成 workflow 全量、文档轻量与 NPU-only 定向路径验证；任何 workflow 变更必须运行全量门，未知代码触发全仓回归，手动运行触发全部专项门。
- `PR Gate`：始终执行的汇总状态；只允许被选专项门 `success` 或 `skipped`，任何失败均拒绝合并。分支保护应只要求该状态。
- `SINGLE_CLOCK_RTL_DECISION_V2`：OF6 后的单时钟 RTL 裁定修订稿。V1 审计暴露了统一命令流中的双 commit 假竞争、未定义 `model_epoch`、样本 framing/首拍 mask 回滚边界、idle 槽位遗漏及过弱随机门槛；V2 固定 8/10 beat 内部计数、删除 `model_epoch`、按单命令流串行化配置、补全 idle 槽位，并恢复 20 个固定 seed × 100 样本门槛。管理员已批准，状态为 `RTL_DESIGN_CONTRACT_V2_APPROVED`；“仅允许 RED/端口骨架，先过 Python/Icarus 逐拍验证，再申请 Vivado”是当时的历史准入规则，当前已推进到 OOC setup 失败与时序修复审核阶段。
- `RTL_SKELETON_IN_PROGRESS`（历史实现阶段）：V2 协议的渐进 RTL 阶段。模型/流、mask epoch、控制三条切片已通过 Icarus；控制切片加入 abort、clear 和严格 idle freeze，冻结仍允许推理但拒绝配置/clear。该状态不代表真实 mask 已控制 MAC，也不包含完整随机逐拍或 Vivado 证据；当前已由 PR #54 的真实计算/随机门和 PR #55 归档的 `VIVADO_OOC_SETUP_FAIL` 证据覆盖。

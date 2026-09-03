# 核心领域概念

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-03
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
- `OF1-OF6_REVIEW_REQUIRED`：当前 Python oracle 冻结门；分别约束 INT32 数值、V1 固定参数域、mask 位序/整组含义、单时钟流与配置边界、epoch/freeze/clear/reset 状态组合，以及不可变结果与冻结验收。批准并完成前不创建集成 RTL、不运行 Vivado。
- `B-V1+V2`：NP7 已批准的单槽弹性流水合同，允许零路径同拍完成及非零结果退出与下一事务接受重叠；其收益只由逐拍账本证明。
- `CI-Fast V1`：按变更路径选择验证范围的 Action 编排；已完成 workflow 全量、文档轻量与 NPU-only 定向路径验证，未知代码触发全仓回归，手动运行触发全部专项门。
- `PR Gate`：始终执行的汇总状态；只允许被选专项门 `success` 或 `skipped`，任何失败均拒绝合并。分支保护应只要求该状态。

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
- `NP7`：已合并的共享 BRAM 与共享 lane 阶段；PR #14 HEAD `78062a7`、merge commit `b754498a`、CI run `33749767954` 已由 GitHub 与仓库外 Webhook 确认成功，后续转入传统 NPU + 神经元集成审核；I1-I6 仍为 `REVIEW_REQUIRED`，集成尚未实现。
- `NPU_NEURON_INTEGRATION_REVIEW_REQUIRED`：当前工作流状态；传统 INT8 NPU 与 ENeuron 仍停在材料审查，尚无集成业务 RTL、Vivado 或板级证据。
- `B-V1+V2`：NP7 已批准的单槽弹性流水合同，允许零路径同拍完成及非零结果退出与下一事务接受重叠；其收益只由逐拍账本证明。

# 核心领域概念

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-02
provenance: NP4B/NP6 TODO、工作流状态与 RTL 文件

- `TICK`：推进一个样本或网络时刻。
- `OBSERVE`/`evidence`：读取已提交学习证据，不读取 live 工作副本。
- `2:4`：每四个连接恰保留两个，提交必须原子完成。
- `issue_mask`：在读取/发射前形成的门控掩码。
- `STATE_CLEAR`：清动态历史但保留剪枝状态。
- `PRUNE_CLEAR`：配置阶段恢复稠密掩码并清 utility。
- `fail-closed`：证据缺失、陈旧或哈希不符时拒绝签核。
- `NP6_PHYSICAL_COST_PARTIAL`：物理成本阶段的正式状态；不是整体时序通过，也不是板级性能结论。
- `NP7`：已合并的共享 BRAM 与共享 lane 阶段；PR #10 清单绑定与 CI 已通过，后续转入传统 NPU + 神经元集成审核。

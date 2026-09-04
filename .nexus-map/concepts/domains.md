# 核心领域概念

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
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
- `OF4B1_MASK_WORD_MAP_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS`：OF4b1 在 OF4a 基础上冻结严格 19-word uint32 掩码镜像：word0..15 按 LSB-first 映射到 `mask0[0..511]`（512 bit），word16..18 按 LSB-first 映射到 `mask1[0..79]`（80 bit）；`word18[31:16]` 为保留位且必须为零。输入长度、整数类型与 uint32 范围均严格校验，解码结果为两个独立不可变 tuple，不保留源列表引用。oracle 27/27 通过。四态命令机、逐拍 `ready/valid`、错误响应、`MODEL_COMMIT`、状态协议、RTL 与 Vivado 尚未完成。
- `B-V1+V2`：NP7 已批准的单槽弹性流水合同，允许零路径同拍完成及非零结果退出与下一事务接受重叠；其收益只由逐拍账本证明。
- `CI-Fast V1`：按变更路径选择验证范围的 Action 编排；Action 基线已从 `actions/checkout@v4`、`actions/setup-python@v5` 升级为二者 `@v7`（Node 24）。已完成 workflow 全量、文档轻量与 NPU-only 定向路径验证；任何 workflow 变更必须运行全量门，未知代码触发全仓回归，手动运行触发全部专项门。
- `PR Gate`：始终执行的汇总状态；只允许被选专项门 `success` 或 `skipped`，任何失败均拒绝合并。分支保护应只要求该状态。

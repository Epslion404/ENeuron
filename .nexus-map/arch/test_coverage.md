# 测试面与缺口

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: repository test names, signoff summaries, workflow state, latest GitHub/Webhook evidence

已覆盖：Python/RTL 协同仿真、有限形式安全与可达性、负向 mutation、Tile/System Vivado OOC、XPM 仿真、NP4B 三模型 60000 事务签核；CI-Fast V1 已完成 workflow 全量、文档轻量和 NPU-only 定向路径验证。CI Action 已升级到 `actions/checkout@v7` 与 `actions/setup-python@v7` 的 Node 24 基线，分类合同要求任何 workflow 变更运行全量门。NPU oracle 新增并通过 `test_zero_activity_with_closed_gate_emits_no_reads_or_macs`、`test_frequent_epoch_switches_never_mix_masks`、`test_pending_slot_backpressure_rejects_overwrite` 三项最坏情况测试。

NP6 已增加 7 组 Vivado 物理成本证据与 12 项 verifier mutation，结论为部分通过。NP7 已具备软件 oracle、共享 lane 协同仿真、形式/负向控制、Vivado XSim 及物理证据完整性门。OF1-OF6 Python oracle 保持 `48/48`、CI-Fast `8/8`。当前状态为 `RTL_DESIGN_CONTRACT_V2_APPROVED / RTL_SKELETON_IN_PROGRESS`：基础、mask epoch、控制三条 Icarus 测试各 1/1。第三条覆盖 abort、clear、freeze idle 边界、冻结推理和拒绝副作用。证据仍是 Icarus 协议切片；真实 MAC、mask 门控计算、20×100 随机逐拍门、Vivado 与板级性能均未完成。

## V2 审核门

- V2 八项裁定已获管理员批准，状态为 `RTL_DESIGN_CONTRACT_V2_APPROVED / RTL_SKELETON_IN_PROGRESS`；当前三条切片仍是端口/状态骨架，不得描述为已实现计算 RTL。
- 先完成 Python/Icarus 逐拍与负向验证，再运行 Vivado；未通过前禁止 Vivado。
- 后续逐拍证据必须覆盖 OF6 确定性边界、统一响应路由、配置/样本背压、freeze/clear/reset、epoch 回绕和负向 mutation；Python 函数级 48/48 不替代这些证据。
# OF6 证据更新

当前状态覆盖为 `RTL_DESIGN_REVIEW_WITH_ACTIONS`。OF4g 修正 `committed` 模型冻结边界，OF5 验证模型/mask/runtime hard reset 丢弃 staging、结果和冻结状态并恢复 `epoch=0`、全开 mask、`model_valid=0`；OF6 对 OF1-OF5 做最终汇总，`test_npu_eneuron_reference.py` 为 48/48、CI-Fast 为 8/8，已合并至 `main@0982ac5`。静态审计列出 8 项逐拍规格缺口；这些仍是 Python oracle/协议证据，单时钟 RTL、完整流接口与 Vivado 仍无冻结证据。

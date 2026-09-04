# 测试面与缺口

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: repository test names, signoff summaries, workflow state, latest GitHub/Webhook evidence

已覆盖：Python/RTL 协同仿真、有限形式安全与可达性、负向 mutation、Tile/System Vivado OOC、XPM 仿真、NP4B 三模型 60000 事务签核；CI-Fast V1 已完成 workflow 全量、文档轻量和 NPU-only 定向路径验证。CI Action 已升级到 `actions/checkout@v7` 与 `actions/setup-python@v7` 的 Node 24 基线，分类合同要求任何 workflow 变更运行全量门。NPU oracle 新增并通过 `test_zero_activity_with_closed_gate_emits_no_reads_or_macs`、`test_frequent_epoch_switches_never_mix_masks`、`test_pending_slot_backpressure_rejects_overwrite` 三项最坏情况测试。

NP6 已增加 7 组 Vivado 物理成本证据与 12 项 verifier mutation，结论为部分通过。NP7 已具备软件 oracle、共享 lane 协同仿真、形式/负向控制、Vivado XSim 及物理证据完整性门。OF1a/OF1b/OF3/OF4a/OF4b1 证据继续成立；OF4b2 已通过严格四态命令端口、19-word 顺序装载、next-epoch、错误响应背压、同索引重试、abort 和样本边界激活测试（34/34）。OF4b2b 在既有实现上补充完整非法状态矩阵回归 9/9，并通过 `NpuEpochRuntime.bind_mask_port()` 验证运行中/结果背压/pending/staging 的全局 idle/freeze 拒绝、完全 idle 双端同步以及 frozen 仍可推理；runtime 组合 5/5。OF4d/OF4e/OF4f 继续冻结 634-word 模型装载、模型端口组合冻结与同拍仲裁；OF4g 修正 `committed` 模型被误判为 staging 的边界，OF5 增加模型、mask、runtime hard reset 后旧状态不可见，OF6 完成最终签核。相关 Python oracle 回归为 `48/48`，CI-Fast 为 `8/8`；上述均为 Python/协议证据，不伪称新的 RED。当前状态为 `RTL_DESIGN_CONTRACT_V2_APPROVED`，已允许 RED/端口状态骨架；`npu_eneuron_single_clock_skeleton.sv`、`tb_npu_eneuron_single_clock_skeleton.sv`、`test_npu_single_clock_skeleton.py` 的 Icarus 冒烟为 `1/1 OK`，但完整计算 RTL、逐拍协同仿真与 Vivado 尚未开始。更远证据缺口包括完整板级 bitstream、真实活动功耗、规模化 RAM、通用 AI 自训练能力及集成 RTL/端到端证明。Vivado 必须等待 Python/Icarus 逐拍门通过；`np75_tmp_sparse_protocol.ys` 仍排除在提交、Nexus 文件树和原始探针之外。

## V2 审核门

- V2 八项裁定已获管理员批准，状态为 `RTL_DESIGN_CONTRACT_V2_APPROVED`；当前仅允许 RED/端口状态骨架，不得将骨架描述为已实现计算 RTL。
- 先完成 Python/Icarus 逐拍与负向验证，再运行 Vivado；未通过前禁止 Vivado。
- 后续逐拍证据必须覆盖 OF6 确定性边界、统一响应路由、配置/样本背压、freeze/clear/reset、epoch 回绕和负向 mutation；Python 函数级 48/48 不替代这些证据。
# OF6 证据更新

当前状态覆盖为 `RTL_DESIGN_REVIEW_WITH_ACTIONS`。OF4g 修正 `committed` 模型冻结边界，OF5 验证模型/mask/runtime hard reset 丢弃 staging、结果和冻结状态并恢复 `epoch=0`、全开 mask、`model_valid=0`；OF6 对 OF1-OF5 做最终汇总，`test_npu_eneuron_reference.py` 为 48/48、CI-Fast 为 8/8，已合并至 `main@0982ac5`。静态审计列出 8 项逐拍规格缺口；这些仍是 Python oracle/协议证据，单时钟 RTL、完整流接口与 Vivado 仍无冻结证据。

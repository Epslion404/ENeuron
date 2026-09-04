# 测试面与缺口

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: repository test names, signoff summaries, workflow state, latest GitHub/Webhook evidence

已覆盖：Python/RTL 协同仿真、有限形式安全与可达性、负向 mutation、Tile/System Vivado OOC、XPM 仿真、NP4B 三模型 60000 事务签核；CI-Fast V1 已完成 workflow 全量、文档轻量和 NPU-only 定向路径验证。CI Action 已升级到 `actions/checkout@v7` 与 `actions/setup-python@v7` 的 Node 24 基线，分类合同要求任何 workflow 变更运行全量门。NPU oracle 新增并通过 `test_zero_activity_with_closed_gate_emits_no_reads_or_macs`、`test_frequent_epoch_switches_never_mix_masks`、`test_pending_slot_backpressure_rejects_overwrite` 三项最坏情况测试。

NP6 已增加 7 组 Vivado 物理成本证据与 12 项 verifier mutation，结论为部分通过。NP7 已具备软件 oracle、共享 lane 协同仿真、形式/负向控制、Vivado XSim 及物理证据完整性门。OF1a/OF1b/OF3/OF4a/OF4b1 证据继续成立；OF4b2 已通过严格四态命令端口、19-word 顺序装载、next-epoch、错误响应背压、同索引重试、abort 和样本边界激活测试（34/34）。OF4b2b 在既有实现上补充完整非法状态矩阵回归 9/9，并通过 `NpuEpochRuntime.bind_mask_port()` 验证运行中/结果背压/pending/staging 的全局 idle/freeze 拒绝、完全 idle 双端同步以及 frozen 仍可推理；runtime 组合 5/5，完整 oracle 41/41。该状态矩阵是回归补强而非新的 RED。当前状态为 `OF4B2B_RUNTIME_COMBINATION_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS`；`MODEL_COMMIT`、单时钟 RTL、完整流接口与 Vivado 尚未开始。更远证据缺口包括完整板级 bitstream、真实活动功耗、规模化 RAM、通用 AI 自训练能力及集成 RTL/端到端证明。CI-Fast 专项 job 被跳过不代表对应硬件证据成立；统一状态为唯一 `PR Gate`，但当前私有仓库套餐不能服务端强制 required check。
# OF4b2 证据更新

当前状态覆盖为 `OF4B2B_RUNTIME_COMBINATION_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS`。OF4b2 的四态命令端口证据为 34/34；OF4b2b 新增完整非法状态矩阵回归 9/9、runtime 组合 5/5，并使完整 oracle 达到 41/41。`NpuEpochRuntime.bind_mask_port()` 在运行中、结果背压、pending mask 或端口 staging 非空时拒绝 freeze，完全 idle 时同步两端；frozen 仍允许推理，但配置和动态清除被拒绝。状态矩阵是既有实现上的回归补强，不伪称 RED。`MODEL_COMMIT`、单时钟 RTL、完整流接口与 Vivado 仍无冻结证据。

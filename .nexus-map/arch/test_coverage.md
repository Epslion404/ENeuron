# 测试面与缺口

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-03
provenance: repository test names, signoff summaries, workflow state, latest GitHub/Webhook evidence

已覆盖：Python/RTL 协同仿真、有限形式安全与可达性、负向 mutation、Tile/System Vivado OOC、XPM 仿真、NP4B 三模型 60000 事务签核；CI-Fast V1 已完成 workflow 全量、文档轻量和 NPU-only 定向路径验证。NPU oracle 新增并通过 `test_zero_activity_with_closed_gate_emits_no_reads_or_macs`、`test_frequent_epoch_switches_never_mix_masks`、`test_pending_slot_backpressure_rejects_overwrite` 三项最坏情况测试。

NP6 已增加 7 组 Vivado 物理成本证据与 12 项 verifier mutation，结论为部分通过。NP7 已具备软件 oracle、共享 lane 协同仿真、形式/负向控制、Vivado XSim 及物理证据完整性门。NPU oracle 仍受 `OF1-OF6_REVIEW_REQUIRED` 阻断：INT32、固定参数域、mask 位序、单时钟逐拍协议、epoch/freeze/clear/reset 组合和不可变结果尚未冻结。更远证据缺口包括完整板级 bitstream、真实活动功耗、规模化 RAM、通用 AI 自训练能力及集成 RTL/端到端证明。CI-Fast 专项 job 被跳过不代表对应硬件证据成立；统一状态为唯一 `PR Gate`，但当前私有仓库套餐不能服务端强制 required check。

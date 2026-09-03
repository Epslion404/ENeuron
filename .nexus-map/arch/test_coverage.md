# 测试面与缺口

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-03
provenance: repository test names, signoff summaries, workflow state, latest GitHub/Webhook evidence

已覆盖：Python/RTL 协同仿真、有限形式安全与可达性、负向 mutation、Tile/System Vivado OOC、XPM 仿真、NP4B 三模型 60000 事务签核。

NP6 已增加 7 组 Vivado 物理成本证据与 12 项 verifier mutation，结论为部分通过。NP7 已具备软件 oracle、共享 lane 协同仿真、形式/负向控制、Vivado XSim 及物理证据完整性门；PR #15 HEAD `fc633259` 对应 run `33752156575` 四道门成功，且 Webhook 已收到同一 SHA 的 `workflow_run completed/success`。证据缺口仍包括完整板级 bitstream、真实活动功耗、规模化 RAM、通用 AI 自训练能力，以及传统 NPU + 神经元集成的端到端证明；集成审核 I1-I6 尚未批准。

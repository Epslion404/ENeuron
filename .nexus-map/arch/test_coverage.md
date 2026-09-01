# 测试面与缺口

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-01
provenance: repository test names, signoff summaries, workflow state

已覆盖：Python/RTL 协同仿真、有限形式安全与可达性、负向 mutation、Tile/System Vivado OOC、XPM 仿真、NP4B 三模型 60000 事务签核。

NP6 已增加 7 组 Vivado 物理成本证据与 12 项 verifier mutation；结论仍为部分通过。证据缺口：无限时域等价、任意 RAM 规模、完整板级 bitstream、真实活动功耗、BRAM 真跳读、共享 lane 周期收益和通用 AI 自训练能力。NP7 尚无功能或 Vivado 证据。

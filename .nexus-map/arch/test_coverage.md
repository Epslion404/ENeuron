# 测试面与缺口

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: repository test names, signoff summaries, workflow state, latest GitHub/Webhook evidence

已覆盖：Python/RTL 协同仿真、有限形式安全与可达性、负向 mutation、Tile/System Vivado OOC、XPM 仿真、NP4B 三模型 60000 事务签核；CI-Fast V1 已完成 workflow 全量、文档轻量和 NPU-only 定向路径验证。CI Action 已升级到 `actions/checkout@v7` 与 `actions/setup-python@v7` 的 Node 24 基线，分类合同要求任何 workflow 变更运行全量门。NPU oracle 新增并通过 `test_zero_activity_with_closed_gate_emits_no_reads_or_macs`、`test_frequent_epoch_switches_never_mix_masks`、`test_pending_slot_backpressure_rejects_overwrite` 三项最坏情况测试。

NP6 已增加 7 组 Vivado 物理成本证据与 12 项 verifier mutation，结论为部分通过。NP7 已具备软件 oracle、共享 lane 协同仿真、形式/负向控制、Vivado XSim 及物理证据完整性门。OF1a/OF1b/OF3/OF4a 证据继续成立；OF4b1 新增并通过严格 19-word uint32 掩码镜像、512+80 bit LSB-first 映射、word18 保留位和不可变快照测试，`test_npu_eneuron_reference.py` 为 27/27，状态为 `OF4B1_MASK_WORD_MAP_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS`。逐拍 ready/valid、四态命令机、错误响应、MODEL_COMMIT、完全 idle freeze 和 epoch/clear/reset 组合仍缺冻结证据；RTL 与 Vivado 尚未开始。更远证据缺口包括完整板级 bitstream、真实活动功耗、规模化 RAM、通用 AI 自训练能力及集成 RTL/端到端证明。CI-Fast 专项 job 被跳过不代表对应硬件证据成立；统一状态为唯一 `PR Gate`，但当前私有仓库套餐不能服务端强制 required check。
# OF4b1 证据更新

当前状态覆盖为 `OF4B1_MASK_WORD_MAP_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS`。OF4b1 已通过 19-word uint32 掩码镜像定向测试：512+80 bit、LSB-first，且 `word18[31:16]` 保留位严格为零；`test_npu_eneuron_reference.py` 共 27/27。四态命令机、逐拍 ready/valid、错误响应、MODEL_COMMIT、完全 idle freeze、epoch/clear/reset 组合、RTL 与 Vivado 仍无冻结证据。

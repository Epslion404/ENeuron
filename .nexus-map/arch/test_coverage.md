# 测试面与缺口

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-05
provenance: repository test names, signoff summaries, workflow state, latest GitHub/Webhook evidence

已覆盖：Python/RTL 协同仿真、有限形式安全与可达性、负向 mutation、Tile/System Vivado OOC、XPM 仿真、NP4B 三模型 60000 事务签核；CI-Fast V1 已完成 workflow 全量、文档轻量和 NPU-only 定向路径验证。CI Action 已升级到 `actions/checkout@v7` 与 `actions/setup-python@v7` 的 Node 24 基线，分类合同要求任何 workflow 变更运行全量门。NPU oracle 新增并通过 `test_zero_activity_with_closed_gate_emits_no_reads_or_macs`、`test_frequent_epoch_switches_never_mix_masks`、`test_pending_slot_backpressure_rejects_overwrite` 三项最坏情况测试。

NP6 结论为部分通过，NP7 已签核。OF1-OF6 Python oracle 保持 48/48。DSP V1 已通过单时钟专项 8/8、固定 `20×100` 和完整仓库 473 项；PR #58 run `33907986001` 在 CI 环境为 473 项通过、3 项跳过，最终 `PR Gate` 成功。Vivado 已确认 4 个 DSP48E1、hold/route/DRC 通过，但 setup 未通过，板级性能仍未完成。

## 当前签核门（DSP V1 OOC 后）

- 实现与 report head=`5055073`；C1-C4 的启用组/周期为 `592/1860`、`590/1856`、`0/676`、`591/1858`，逐组 bitmap、模型地址和关闭组旁路均通过。
- Vivado 2024.1、`xc7z020clg400-1`、100 MHz 结果为 `2192 LUT / 1904 FF / 0 BRAM / 4 DSP48E1`；setup `WNS=-0.673 ns / TNS=-6.462 ns / 22` 个失败端点，hold `WHS=+0.090 ns / 0` 个失败端点，route/DRC error 为 0。
- 扩展 50-path 报告中的 22 条 `Slack (VIOLATED)` 已全部核对：14 条经过动态激活选择、DSP48E1 和四乘积求和到 `lane_sum_latched`，8 条从 `compute_group_index` 到 `logit_values` 写使能，不再存在未分类失败端点。外部报告 `eneuron_timing_expand_50.rpt` 的 SHA-256 为 `BE8F1BF268553E9BDAEB31FF7DB348D6F4573011DF6CBDB699D840A71D91F04D`。
- V2 已获 TR7-TR12 批准并进入实施；当前先建立独立 V2 RED，再修改业务 RTL。实施地图为 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V2_IMPLEMENTATION_MAP.md`，KISS 方案复用 signed 32-bit `mac_accumulator`，不新增 `writeback_value_latched`，仅预计新增四个 signed 8-bit 激活锁存器（约 32 FF）。

## V2 审核门（历史/协议背景）

- V2 八项裁定已获管理员批准，曾记录为 `RTL_DESIGN_CONTRACT_V2_APPROVED / RTL_SKELETON_IN_PROGRESS`；该状态属于实现过程历史，当前 RTL 已通过真实计算切片与随机门。
- Python/Icarus、随机逐 beat 和历史 PR 合并门已通过；该条只保留协议背景。当前 TR1-TR6 已实现，新的活动门是 V2 RED、RTL 和功能回归。
- 后续逐拍证据必须覆盖 OF6 确定性边界、统一响应路由、配置/样本背压、freeze/clear/reset、epoch 回绕和负向 mutation；Python 函数级 48/48 不替代这些证据。
# OF6 证据更新（历史记录）

OF4g 修正 `committed` 模型冻结边界，OF5 验证模型/mask/runtime hard reset 丢弃 staging、结果和冻结状态并恢复 `epoch=0`、全开 mask、`model_valid=0`；OF6 对 OF1-OF5 做最终汇总，`test_npu_eneuron_reference.py` 为 48/48、CI-Fast 为 8/8，曾合并至 `main@0982ac5`。该段保留作为协议签核历史；当前权威状态以上方“当前签核门”和 DSP V1 manifest 为准。

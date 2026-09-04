# 测试面与缺口

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: repository test names, signoff summaries, workflow state, latest GitHub/Webhook evidence

已覆盖：Python/RTL 协同仿真、有限形式安全与可达性、负向 mutation、Tile/System Vivado OOC、XPM 仿真、NP4B 三模型 60000 事务签核；CI-Fast V1 已完成 workflow 全量、文档轻量和 NPU-only 定向路径验证。CI Action 已升级到 `actions/checkout@v7` 与 `actions/setup-python@v7` 的 Node 24 基线，分类合同要求任何 workflow 变更运行全量门。NPU oracle 新增并通过 `test_zero_activity_with_closed_gate_emits_no_reads_or_macs`、`test_frequent_epoch_switches_never_mix_masks`、`test_pending_slot_backpressure_rejects_overwrite` 三项最坏情况测试。

NP6 已增加 7 组 Vivado 物理成本证据与 12 项 verifier mutation，结论为部分通过。NP7 已具备软件 oracle、共享 lane 协同仿真、形式/负向控制、Vivado XSim 及物理证据完整性门。OF1-OF6 Python oracle 保持 `48/48`、CI-Fast `8/8`。当前状态为 `RTL_RANDOM_GATE_GREEN / PR55_MERGED / VIVADO_OOC_SETUP_FAIL / TIMING_REPAIR_REQUIRED / TIMING_REPAIR_V1_REVIEW_REQUIRED`：基础、mask epoch、控制和真实计算四条 Icarus 门通过；固定 `20×100` 随机逐 beat 门、PR #54 CI 与完整回归 `469/469（1 skipped）` 已在 `main@2a33f12` 收口，PR #55 已将 OOC 证据合入 `main@dc2452b`。Vivado 2024.1 OOC 已完成，route/DRC 无错误且 hold 通过，但 setup 未通过；板级性能仍未完成。

## 当前签核门（PR55 合并后）

- RTL merge=`2a33f12`：PR #54 包含四条 Icarus 切片、固定 `20 seeds × 100 samples = 2000` 随机逐 beat 门、完整回归 `469/469（1 skipped）` 和同一 HEAD 的 CI，均已通过；evidence merge=`dc2452b`：PR #55 已归档 OOC manifest、报告和 runner，当前权威仓库基线为 `origin/main@dc2452b`。
- OOC report head=`39e41d4`，对应 `origin/main@2a33f12` 的 RTL，manifest 以 SHA-256 绑定 RTL、runner、Tcl 与报告。Vivado 2024.1、`xc7z020clg400-1`、100 MHz 结果为 `2672 LUT / 1879 FF / 0 BRAM / 0 DSP`，setup `WNS=-5.087 ns / TNS=-421.539 ns / 244` 个失败端点，hold `WHS=+0.098 ns / 0` 个失败端点，route/DRC error 为 0。
- `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V1.md` 当前为 `REVIEW_REQUIRED`，TR1-TR6 待批准。批准后验收门仍为四项定向、固定 `20×100`、完整回归和同范围 OOC 重跑，不能用历史 OOC 或软件仿真替代。

## V2 审核门（历史/协议背景）

- V2 八项裁定已获管理员批准，曾记录为 `RTL_DESIGN_CONTRACT_V2_APPROVED / RTL_SKELETON_IN_PROGRESS`；该状态属于实现过程历史，当前 RTL 已通过真实计算切片与随机门。
- Python/Icarus、随机逐 beat 和 PR 合并门已通过；OOC 报告已由 manifest 绑定并经 PR #55 归档，但 setup 未收敛，下一门是 TR1-TR6 获批后的关键路径修复与同范围 OOC 重跑；板级与网络验证仍后置。
- 后续逐拍证据必须覆盖 OF6 确定性边界、统一响应路由、配置/样本背压、freeze/clear/reset、epoch 回绕和负向 mutation；Python 函数级 48/48 不替代这些证据。
# OF6 证据更新（历史记录）

OF4g 修正 `committed` 模型冻结边界，OF5 验证模型/mask/runtime hard reset 丢弃 staging、结果和冻结状态并恢复 `epoch=0`、全开 mask、`model_valid=0`；OF6 对 OF1-OF5 做最终汇总，`test_npu_eneuron_reference.py` 为 48/48、CI-Fast 为 8/8，曾合并至 `main@0982ac5`。该段保留作为协议签核历史；当前权威状态以 PR #55 合并后的 `origin/main@dc2452b` 及上方“当前签核门”为准。

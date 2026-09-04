# ENeuron 知识库入口

generated_by: nexus-mapper v2 / manual synthesis from raw probe
verified_at: 2026-09-04
provenance: `.nexus-map/raw/ast_nodes.json`, `git_stats.json`, `file_tree.txt`（文件树按版本化基线排除工作区未跟踪文件）；SystemVerilog边界由文件树与文档人工核对

ENeuron 是以 Python 黄金模型、SystemVerilog RTL、Icarus/Yosys/Vivado 验证组成的数字脉冲神经元与 NPU 局部剪枝研究仓库。

## 主要系统

- 神经元与参考模型：`digital_lif_engine.sv`、`neuron_sim.py`、`pulse_mini_reference.py`
- 网络/Tile/Host：`digital_snn_tile_4x2x2.sv`、`digital_snn_host_bridge_controller.sv`、`network_sim.py`
- 单时钟 NPU 骨架：`npu_eneuron_single_clock_skeleton.sv`；基础、mask epoch、控制入口分别为 `test_npu_single_clock_skeleton.py`、`test_npu_single_clock_mask.py`、`test_npu_single_clock_control.py`
- 局部剪枝：`local_prune_gate_2of4.sv`、`local_prune_reference.py`、`verify_np4b_signoff.py`
- NP7 共享执行器：`np7_shared_synapse_lane.sv`、`np7_weight_ram.sv`、`np7_shared_lane_oracle.py`、`np7_shared_lane_cosim.py`
- 验证入口：`verify_goal.py`、`verify_np4b_signoff.py`、`test_*.py`、formal `.ys/.sv`
- 规划与状态：`WORKFLOW_STATE.md`、`docs/planning/NPU_NEURON_INTEGRATION_REVIEW.md`、`docs/planning/NPU_PRUNING_NP6_TODO.md`、`docs/planning/NPU_PRUNING_NP7_TODO.md`
- 集成材料包：`docs/planning/NPU_NEURON_INTEGRATION_MATERIALS.md`、`docs/planning/NPU_ORACLE_FREEZE_REVIEW.md`、`docs/planning/NPU_ORACLE_SINGLE_CLOCK_CONTRACT_V3.md`、`docs/planning/NPU_MODEL_COMMIT_CONTRACT_V3.md`、`docs/planning/NPU_SINGLE_CLOCK_RTL_DESIGN_REVIEW_V1.md`、`docs/planning/NPU_SINGLE_CLOCK_RTL_DESIGN_AUDIT_V1.md`、`docs/planning/NPU_SINGLE_CLOCK_RTL_DECISION_SHEET_V2.md`、`docs/planning/npu_single_clock_contract_provisional_v2.json`（I1-I6、OF1-OF6 V3 与 V2 RTL 裁定已批准；Python oracle 与当前单时钟 RTL 随机门均已签核）
- CI 编排：`.github/workflows/pr-gate.yml`、`tools/ci/classify_changes.py`、`test_ci_fast_v1.py`（路径分类、条件专项门和唯一 `PR Gate` 汇总）

## 当前状态

NP4B 已签核；NP6 已收口为 `NP6_PHYSICAL_COST_PARTIAL`。NP7 共享 BRAM/lane 已实现并签核。I1-I6 与 OF1-OF6 V3 已批准，OF1-OF6 Python oracle 已签核（48/48、CI-Fast 8/8）。管理员已批准 V2 八项单时钟 RTL 裁定；PR #54 已合并为 `main@2a33f12`，当前状态为 `RTL_RANDOM_GATE_GREEN / PR54_MERGED / VIVADO_OOC_SETUP_FAIL / TIMING_REPAIR_REQUIRED`。模型/流、mask epoch、控制和真实计算四条 Icarus 切片均通过，固定 `20×100` 随机逐 beat 门及完整回归 `469/469（1 skipped）` 已完成；Vivado 2024.1 OOC 已完成但 setup 未通过。

## 单时钟 RTL 审核摘要

- **V1 审计问题**：统一单命令流却定义 `MODEL_COMMIT` 与 `MASK_COMMIT` 同拍竞争；结果 sideband 引入未冻结的 `model_epoch` 且硬件槽位账本不足；首 beat mask 切换未说明 framing 错误的零副作用/回滚；`runtime_idle` 漏待消费错误、部分结果和同拍握手占用；验证门低于 I5 的 20 个固定 seed × 100 样本要求。
- **V2 修正**：固定 8/10 beat 并取消外部 `last`；明确 nibble 位序和内部 beat 计数；删除 `model_epoch`，结果 metadata 仅为 sample ID 与 mask epoch；统一命令流按握手顺序串行，配置命令优先样本首 beat；idle 纳入错误响应、部分输出、统一槽位及同拍仲裁；验证门恢复至少 20×100 样本并保留 OF6 定向/负向覆盖。
- **当前门槛**：V2 八项裁定已批准并冻结为 `RTL_DESIGN_CONTRACT_V2_APPROVED`；固定 `20×100` 逐 beat 门、完整回归和 PR #54 同一 HEAD CI 已通过并合并为 `2a33f12`。当前 HEAD 的 Vivado OOC 已完成并得到 `2672 LUT / 1879 FF`、setup `WNS=-5.087 ns`、hold `WHS=+0.098 ns`、route/DRC error=0；因 setup 失败，下一门是关键路径修复后的同范围 OOC 重跑，仍不声明板级或网络性能。
- **第二条 RTL 切片**：`test_npu_single_clock_mask.py` 驱动公开接口验证完整 19-word 顺序装载；非法 word18 高 16 位产生 128-bit 单槽错误响应且隐式索引保持 18，响应消费后可重试；`MASK_COMMIT` 只发布，后续样本首 beat 才令 epoch 1 active 并置 `mask_valid`，两个连续样本结果均携带 epoch 1。
- **第三条 RTL 切片**：`test_npu_single_clock_control.py` 验证部分 mask 可由 `MASK_ABORT` 丢弃；`STATE_CLEAR` 保留模型/mask；freeze 只在严格 idle 边界切换，冻结时样本仍可完成，而模型/mask 配置与动态清除返回稳定错误且不改变状态。
- **真实计算状态**：`test_npu_single_clock_compute.py`/`tb_npu_eneuron_single_clock_compute.sv` 已锁定 uint4×INT8、隐藏饱和、INT32 logit 与 L0 mask 门控；四 lane FETCH/ACCUM 引擎通过首组 137/-117、两层最后组 59、L1 bit79 关闭后 -1，以及忙态阻塞检查。
- **随机门 GREEN**：固定 `20 seeds × 100 samples = 2000` 个样本逐 beat 比对 logits、sample ID、mask epoch、背压和 mask 轮换；同一证据已进入 PR #54 并合并。Vivado OOC 已完成但 setup 失败，下一步是关键路径修复，不能用软件周期或历史报告代偿。
- **配置合同补强**：模型写入已执行两层 signed bias 安全窗；mask 四态命令可与部分输入、计算和结果流并行准备 published bank，但只在下一样本首 beat 切换 active，模型/冻结/清除命令仍要求严格运行空闲。

## 状态校正与下一门

- **当前权威基线**：`origin/main@2a33f12`，对应 PR #54 已合并；不要再使用合并前的 `PR54_WAITING_RANDOM_COMMIT_CI` 或“RTL 骨架尚未完成”作为当前状态。
- **已完成证据**：四条 Icarus 切片、固定 `20 seeds × 100 samples = 2000` 个样本逐 beat 随机门、完整回归 `469/469（1 skipped）`，以及 PR #54 同一 HEAD 的 CI 均已通过。
- **已完成物理阶段**：使用 Vivado 2024.1 对当前 RTL、器件 `xc7z020clg400-1`、100 MHz 约束执行了 OOC 综合/实现、资源、setup/hold 和 DRC；setup 失败证据已归档。在关键路径修复通过前，不宣称当前设计的板级、功耗或网络吞吐性能。
- **历史保留**：下方审计条目保留设计演进背景；其中标注为 V1/OF6 历史阶段的缺口不覆盖上述当前签核结果。

## 必读路由

- `.nexus-map/arch/systems.md`
- `.nexus-map/arch/dependencies.md`
- `.nexus-map/arch/test_coverage.md`
- `.nexus-map/hotspots/git_forensics.md`
- `.nexus-map/concepts/domains.md`

## [操作指南] 强制执行步骤

> 本节是对所有读取本文件的 AI 发出的硬性操作指令，不是建议。

### 步骤1 — 必须先读完以下所有文件（顺序不限）

读完本文件后，在执行任何任务之前，必须依次读取以下文件完整内容：

- `.nexus-map/arch/systems.md` — 系统边界与代码位置
- `.nexus-map/arch/dependencies.md` — 系统间依赖关系与 Mermaid 图
- `.nexus-map/arch/test_coverage.md` — 测试面与证据缺口
- `.nexus-map/hotspots/git_forensics.md` — Git 热点与耦合风险
- `.nexus-map/concepts/domains.md` — 核心领域概念

这些文件均为高密度摘要，不得以任务简单或只改一个文件为由跳过。

### 步骤2 — 按任务类型追加操作（步骤1 完成后执行）

- 若任务涉及接口修改、新增跨模块调用、删除或重命名公共函数：运行 `query_graph.py --impact <目标文件>` 确认影响半径后再写代码。
- 若任务需要判断某文件被谁引用：运行 `query_graph.py --who-imports <模块名>`。
- 若仓库结构发生重大变化：任务完成后重新评估并更新 Nexus 知识库。

# ENeuron 知识库入口

generated_by: nexus-mapper v2 / manual synthesis from raw probe
verified_at: 2026-09-03
provenance: `.nexus-map/raw/ast_nodes.json`, `git_stats.json`, `file_tree.txt`（文件树按版本化基线排除工作区未跟踪文件）；SystemVerilog边界由文件树与文档人工核对

ENeuron 是以 Python 黄金模型、SystemVerilog RTL、Icarus/Yosys/Vivado 验证组成的数字脉冲神经元与 NPU 局部剪枝研究仓库。

## 主要系统

- 神经元与参考模型：`digital_lif_engine.sv`、`neuron_sim.py`、`pulse_mini_reference.py`
- 网络/Tile/Host：`digital_snn_tile_4x2x2.sv`、`digital_snn_host_bridge_controller.sv`、`network_sim.py`
- 局部剪枝：`local_prune_gate_2of4.sv`、`local_prune_reference.py`、`verify_np4b_signoff.py`
- NP7 共享执行器：`np7_shared_synapse_lane.sv`、`np7_weight_ram.sv`、`np7_shared_lane_oracle.py`、`np7_shared_lane_cosim.py`
- 验证入口：`verify_goal.py`、`verify_np4b_signoff.py`、`test_*.py`、formal `.ys/.sv`
- 规划与状态：`WORKFLOW_STATE.md`、`docs/planning/NPU_NEURON_INTEGRATION_REVIEW.md`、`docs/planning/NPU_PRUNING_NP6_TODO.md`、`docs/planning/NPU_PRUNING_NP7_TODO.md`
- 集成材料包：`docs/planning/NPU_NEURON_INTEGRATION_MATERIALS.md`、`docs/planning/NPU_ORACLE_FREEZE_REVIEW.md`（I1-I6 已批准；OF1-OF6 待批准）
- CI 编排：`.github/workflows/pr-gate.yml`、`tools/ci/classify_changes.py`、`test_ci_fast_v1.py`（路径分类、条件专项门和唯一 `PR Gate` 汇总）

## 当前状态

NP4B 已签核；NP6 已收口为 `NP6_PHYSICAL_COST_PARTIAL`。NP7 共享 BRAM/lane 已实现并签核。I1-I6 已批准，`64→32→10` INT8 NPU + ENeuron Python oracle 已覆盖零活动关闭、逐样本频繁 epoch 切换和 pending 单槽背压三项最坏情况；当前进入 `OF1-OF6_REVIEW_REQUIRED`，批准并完成冻结测试前不得创建集成 RTL 或运行 Vivado。CI-Fast V1 已完成 workflow 全量、文档轻量和 NPU-only 定向路径验证，所有路径由唯一 `PR Gate` 汇总。`np75_tmp_sparse_protocol.ys` 是用户临时文件，不得修改、提交或纳入 Nexus 文件树/原始探针。

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

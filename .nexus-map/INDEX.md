> generated_by: nexus-mapper v2
> verified_at: 2026-09-02
> provenance: Python AST-backed; SystemVerilog/Tcl and report semantics verified by file-tree/manual inspection

# ENeuron Nexus Map

ENeuron 是面向 FPGA 的可塑脉冲神经元与局部剪枝研究仓库。当前工作流已从 NP4B 集成推进到 NP6 物理成本评估，并包含 NP7 共享 lane 的阶段性结果。NP6/NP7 的硬件报告来自协作者 Vivado 2024.2，不能外推为本机 Vivado 2024.1 结果。

## 主要系统

- **神经元与网络 RTL**：`digital_lif_core.sv`、`digital_lif_engine.sv`、`digital_snn_tile_4x2x2.sv`、`digital_snn_host_bridge_system.sv`。
- **Python 黄金模型与协同仿真**：`neuron_sim.py`、`rtl_reference.py`、`rtl_tile_cosim.py`、`network_sim.py`。
- **局部剪枝**：`local_prune_reference.py`、`local_prune_gate_2of4.sv`、三种神经元 wrapper 及 `*_pruned_network_4x8x2`。
- **验证与签核**：`verify_goal.py`、`verify_np4b_signoff.py`、各 `test_*.py`、`formal_*.sv`/`.ys`。
- **工作流与证据**：`WORKFLOW.md`、`WORKFLOW_STATE.md`、`task_plan.md`、`findings.md`、`progress.md`、`docs/`、`artifacts/`。

## 当前路由

先读 `WORKFLOW_STATE.md` 与 `docs/planning/NPU_PRUNING_NP6_TODO.md`，再读下方架构、依赖、测试、热点和领域摘要。NP6 当前状态以工作流文件为准；不得仅凭本索引宣称硬件性能。

## [操作指南] 强制执行步骤

### 步骤1 — 必须先读完以下所有文件（顺序不限）

- `.nexus-map/arch/systems.md`
- `.nexus-map/arch/dependencies.md`
- `.nexus-map/arch/test_coverage.md`
- `.nexus-map/hotspots/git_forensics.md`
- `.nexus-map/concepts/domains.md`

### 步骤2 — 按任务类型追加操作

- 接口或跨模块修改前运行 `query_graph.py --impact <目标文件>`。
- 查询引用关系运行 `query_graph.py --who-imports <模块名>`。
- 系统边界变化后重新评估并更新 `.nexus-map/`。

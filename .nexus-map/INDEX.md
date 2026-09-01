# ENeuron 知识库入口

generated_by: nexus-mapper / manual synthesis from raw probe
verified_at: 2026-09-01
provenance: `.nexus-map/raw/ast_nodes.json`, `git_stats.json`, `file_tree.txt`

ENeuron 是以 Python 黄金模型、SystemVerilog RTL、Icarus/Yosys/Vivado 验证组成的数字脉冲神经元与 NPU 局部剪枝研究仓库。

## 主要系统

- 神经元与参考模型：`digital_lif_engine.sv`、`neuron_sim.py`、`pulse_mini_reference.py`
- 网络/Tile/Host：`digital_snn_tile_4x2x2.sv`、`digital_snn_host_bridge_controller.sv`、`network_sim.py`
- 局部剪枝：`local_prune_gate_2of4.sv`、`local_prune_reference.py`、`verify_np4b_signoff.py`
- 验证入口：`verify_goal.py`、`verify_np4b_signoff.py`、`test_*.py`、formal `.ys/.sv`
- 规划与状态：`WORKFLOW_STATE.md`、`docs/planning/NPU_PRUNING_NP6_TODO.md`

## 当前状态

NP4B 已签核；NP6 仍为 `REVIEW_REQUIRED`，未经用户批准不得运行 Vivado。NP6 只测量指定器件下的资源、时序和 DRC，不证明真实 BRAM 跳读或板级加速。

## 必读路由

- `.nexus-map/arch/systems.md`
- `.nexus-map/arch/dependencies.md`
- `.nexus-map/arch/test_coverage.md`
- `.nexus-map/hotspots/git_forensics.md`
- `.nexus-map/concepts/domains.md`

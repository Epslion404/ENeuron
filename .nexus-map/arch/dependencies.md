# 依赖关系

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: `.nexus-map/raw/ast_nodes.json` hub analysis and Python imports；SystemVerilog依赖由文件树/手工检查推断

```mermaid
graph TD
  ref[Python reference models] --> cosim[RTL co-simulation]
  rtl[SystemVerilog neuron/tile] --> wrap[pruning wrappers]
  wrap --> net[network and host bridge]
  net --> np7[NP7 shared BRAM/lane]
  np7 --> verify[signoff verifiers]
  cosim --> verify[signoff verifiers]
  vivado[Vivado runners] --> reports[physical reports]
  reports --> verify
  np7 -. planned integration boundary .-> npu[traditional INT8 NPU + ENeuron]
  changes[changed paths] --> classify[tools/ci/classify_changes.py]
  classify --> fast[fast-check]
  classify --> specialized[conditional specialized gates]
  fast --> gate[PR Gate]
  specialized --> gate
```

```text
Python oracle → cosim runners → unittest/verifier
神经元 RTL → wrapper → Tile/network → Host bridge
local_prune_reference → local_prune wrappers/network → NP4B signoff
NP7 shared lane oracle → dense/sparse RTL → XSim/OOC runners → physical/evidence gates
Vivado Tcl/runner → reports → verify_goal
传统 NPU + ENeuron 集成材料包 → OF1a/OF1b/OF3 已绿 → OF4a 634-word 模型镜像 → OF4b1 19-word mask 映射 → `OF4B2_COMMAND_PORT_GREEN`（四态、错误响应背压、next-epoch、同索引重试、样本边界激活、oracle 34/34）→ `OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS` → 完整状态矩阵与 runtime idle/freeze → RTL 设计审核 → Vivado 证据
变更路径 → `classify-changes` → fast/全仓/XPM/NP7 专项门 → 唯一 `PR Gate`
```

高扇入模块包括 `pulse_mini_reference.py`、`rtl_tile_cosim.py`、`pulse_mini_l2_reference.py`、`neuron_sim.py`、`local_prune_reference.py`、`network_sim.py` 和 `host_bridge_oracle.py`。AST 仅覆盖 Python；RTL→wrapper→network 方向是人工核对的结构依赖。

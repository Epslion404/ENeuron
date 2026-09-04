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
  reports -. V1 setup fail .-> timing[Timing repair V2 review]
  timing -. TR7-TR12 approval required .-> npu
  np7 -. shared execution boundary .-> npu[traditional INT8 NPU + ENeuron]
  npu --> vivado
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
传统 NPU + ENeuron 集成材料包 → Python oracle 签核 → 单时钟 RTL 与随机门 → 旧 OOC setup 失败 → TR1-TR6 批准 → 四 DSP 三拍 RTL → 单时钟 8/8 + 固定 `20×100` + 完整 473 项 → DSP V1 OOC（DSP/hold/route/DRC 通过，setup 失败）→ `NPU_SINGLE_CLOCK_TIMING_REPAIR_V2` 审核 → TR7-TR12 批准后才允许下一轮 RED/RTL/OOC
变更路径 → `classify-changes` → fast/全仓/XPM/NP7 专项门 → 唯一 `PR Gate`
```

高扇入模块包括 `pulse_mini_reference.py`、`rtl_tile_cosim.py`、`pulse_mini_l2_reference.py`、`neuron_sim.py`、`local_prune_reference.py`、`network_sim.py` 和 `host_bridge_oracle.py`。AST 仅覆盖 Python；RTL→wrapper→network 方向是人工核对的结构依赖。

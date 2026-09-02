> generated_by: nexus-mapper v2
> verified_at: 2026-09-02
> provenance: Python AST-backed; RTL boundaries inferred from SystemVerilog module declarations and project reports

# 系统边界

1. **神经元/网络 RTL**：多周期 LIF 核、4→2→2 tile、Host Bridge 与双时钟 FIFO；实现路径见根目录 `.sv` 文件。
2. **参考模型与仿真**：定义神经元状态、事务语义、网络路由并生成 Icarus/Vivado 测试台；核心模块为 `neuron_sim.py`、`rtl_reference.py`、`rtl_tile_cosim.py`。
3. **局部剪枝**：2-of-4 gate、证据/提交屏障、ENeuron/Pulse-Mini wrapper 与网络模型；核心路径为 `local_prune_*`、`eneuron_*`、`pulse_mini_*`。
4. **验证签核**：单元测试、形式脚本、报告解析和 fail-closed verifier；入口为 `verify_goal.py` 与 `verify_np4b_signoff.py`。
5. **工作流与证据归档**：TODO、阶段报告、Vivado 目录和 artifacts；状态入口为 `WORKFLOW_STATE.md`。
6. **NP6/NP7 后续能力**：物理成本与共享 lane 已有规划/阶段报告，但不能视为通用 AI 或板级闭环实现。

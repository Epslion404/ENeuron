# 系统边界

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-03
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为五个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、验证与签核工具。传统 NPU + 神经元集成仍是规划边界，不是已实现系统。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并，代码位置包括 `np7_weight_ram.sv`、`np7_exec_unit_dense.sv`、`np7_exec_unit_sparse.sv`、`np7_shared_synapse_lane.sv` 及其 Python oracle/cosim/runner。PR #15 merge commit 为 `feec6bcb`，HEAD `fc633259` 的 CI run `33752156575` 已由 GitHub 与仓库外 Webhook 双重确认 `completed/success`。当前边界进入传统 NPU + 神经元集成审核，I1-I6 仍为 `REVIEW_REQUIRED`；`WORKFLOW_STATE.md` 是状态权威来源，该阶段尚未形成集成业务 RTL 或新的 Vivado 集成证据。

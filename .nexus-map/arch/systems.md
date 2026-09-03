# 系统边界

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-03
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。PR #24 已合并为 `3b53a7e`；用户未跟踪文件 `np75_tmp_sparse_protocol.ys` 被明确排除在提交和 Nexus 文件树之外。当前边界进入传统 NPU + ENeuron 集成 Python oracle；I1-I6 已批准，尚未形成集成业务 RTL 或新的 Vivado 集成证据。CI 编排由 `.github/workflows/pr-gate.yml` 实现，未知路径 fail-safe 进入全仓回归。

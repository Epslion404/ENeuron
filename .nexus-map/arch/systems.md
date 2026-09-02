# 系统边界

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-01
provenance: AST/file-tree probe and repository documents

仓库分为四个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、验证与签核工具。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估已经合并；NP7 是下一阶段的共享 BRAM 与共享 lane 方案审核，证据和实现尚未开始。`WORKFLOW_STATE.md` 是当前状态权威来源。

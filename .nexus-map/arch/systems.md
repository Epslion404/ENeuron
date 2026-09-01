# 系统边界

generated_by: nexus-mapper / manual synthesis
verified_at: 2026-09-01
provenance: AST/file-tree probe and repository documents

仓库分为四个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、验证与签核工具。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 是规划中的物理评估阶段，当前没有新的 RTL 实施。

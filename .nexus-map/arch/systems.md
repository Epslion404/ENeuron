# 系统边界

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-03
provenance: AST/file-tree probe and repository documents

仓库分为四个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、验证与签核工具。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估已部分通过；NP7 共享 BRAM 与共享 lane 已实现并合并。PR #10 当前 HEAD 为 `cadc3a8`，CI run `33729657078` 已由 GitHub 与仓库外 Webhook 双重确认 `completed/success`。当前边界进入传统 NPU + 神经元集成审核，I1-I6 仍为 `REVIEW_REQUIRED`；`WORKFLOW_STATE.md` 是状态权威来源，该阶段尚未形成集成 RTL 或 Vivado 新证据。

# 系统边界

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-03
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。传统 NPU + ENeuron 当前状态为 `OF1A_UINT4_CORE_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS`，OF1-OF6 V3 已于 2026-09-04 获管理员批准。OF1a 在 `npu_eneuron_reference.py` 实现严格 uint4 核心输入，非法像素在状态提交前拒绝，不消费 pending epoch；oracle 15/15、OF1a 定向 2/2 通过。V3 其余安全 bias、634-word 精确映射与错误重试、19-word mask 四态配置、完全 idle freeze、固定 read/MAC 账本和不可变结果仍待实现与冻结，因此没有集成业务 RTL 或新 Vivado 证据。CI-Fast V1 已完成全量/文档/NPU 定向路径验证，未知路径仍 fail-safe 进入全仓回归。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

# 系统边界

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-03
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。传统 NPU + ENeuron 边界由 `npu_eneuron_reference.py`、`npu_eneuron_protocol.py` 和定向测试表达；三项新增最坏情况证明零活动关闭不发读/MAC、逐样本 epoch 切换不混用 mask、pending 单槽满时拒绝覆盖。当前门为 `OF1-OF6_V2_REVIEW_REQUIRED`：核心数据口只接收 uint4，Host 负责外部灰度裁剪；第一层 bias 为 `[-2147360768, 2147361727]`、第二层为 `[-2146963456, 2146967519]`；模型按 `512 权重 + 32 bias + 80 权重 + 10 bias = 634` 个 32-bit word 顺序装载，mask 按 19 个 32-bit word 顺序装载。数值、顺序流、状态组合和不可变结果尚未完成冻结测试，因此没有集成业务 RTL 或新 Vivado 证据。CI-Fast V1 已完成全量/文档/NPU 定向路径验证，未知路径仍 fail-safe 进入全仓回归。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

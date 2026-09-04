# 系统边界

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-03
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。传统 NPU + ENeuron 当前状态为 `OF1B_FIXED_MODEL_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS`，OF1-OF6 V3 已于 2026-09-04 获管理员批准。OF1a 严格 uint4 与非法像素零副作用继续成立；OF1b 在 `npu_eneuron_reference.py` 实现严格 INT8 权重、两层安全 bias、固定 `64→32→10/group=4` 参数、配置完整预检后原子 reload 以及 tuple logits，oracle 19/19 通过。V3 其余 634-word 精确映射与错误重试、19-word mask 四态配置、完全 idle freeze 和固定 read/MAC 账本仍待实现与冻结，因此没有集成业务 RTL 或新 Vivado 证据。CI-Fast V1 已完成全量/文档/NPU 定向路径验证，未知路径仍 fail-safe 进入全仓回归。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

# 系统边界

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-03
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。传统 NPU + ENeuron 当前状态为 `OF4A_MODEL_WORD_MAP_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS`。OF1a/OF1b/OF3 合同继续成立；OF4a 在 Python 协议边界实现严格 634-word uint32 镜像，固定映射为 512 个第一层权重 word、32 个第一层 bias、80 个第二层权重 word和 10 个第二层 bias。每个权重 word 按 little-endian signed INT8 解码四个字节，bias 按完整 little-endian signed INT32 解码；全部检查通过后才原子 load，oracle 25/25 通过。逐拍 ready/valid、错误响应、MODEL_COMMIT、19-word mask、状态协议、集成 RTL 与 Vivado 证据仍待完成。CI-Fast V1 已完成全量/文档/NPU 定向路径验证，未知路径仍 fail-safe 进入全仓回归。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

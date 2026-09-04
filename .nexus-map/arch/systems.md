# 系统边界

OF4b2 更新：传统 NPU + ENeuron 集成状态为 `OF4B2_COMMAND_PORT_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS`。已冻结严格 19-word uint32 掩码镜像及 `MaskConfigPort` 四态命令端口：顺序装载、next-epoch、单槽错误响应背压、同索引重试和样本边界激活；oracle 34/34 通过。完整状态矩阵、全局 idle/freeze runtime 组合、RTL 与 Vivado 证据仍未完成。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。传统 NPU + ENeuron 当前状态为 `OF4B2_COMMAND_PORT_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS`。OF1a/OF1b/OF3 合同继续成立；OF4a/OF4b1 冻结模型与掩码镜像，OF4b2 增加四态命令端口、错误背压、next-epoch 和样本边界激活，oracle 34/34 通过。完整状态矩阵、全局 idle/freeze runtime 组合、集成 RTL 与 Vivado 证据仍待完成。CI-Fast V1 已完成全量/文档/NPU 定向路径验证，未知路径仍 fail-safe 进入全仓回归。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

状态覆盖（OF4b2）：以上 OF4a/OF4b1 描述属于历史阶段；当前以 `OF4B2_COMMAND_PORT_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS` 为准。OF4b2 已冻结四态命令端口、错误响应背压、next-epoch 和样本边界激活及 34/34 oracle 证据，但不代表完整状态矩阵、全局 runtime idle/freeze、RTL 或 Vivado 已完成。

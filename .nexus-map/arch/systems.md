# 系统边界

OF4b2b 更新：传统 NPU + ENeuron 集成状态为 `OF4B2B_RUNTIME_COMBINATION_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS`。在严格 19-word uint32 掩码镜像和 `MaskConfigPort` 四态命令端口基础上，已完成完整非法状态矩阵回归（9/9）与 `NpuEpochRuntime.bind_mask_port()` 组合合同（5/5）：运行中、结果背压、runtime pending 或端口 staging 非空时拒绝 freeze，完全 idle 时双端同步；frozen 仍允许样本推理但拒绝配置和动态清除；完整 oracle 41/41 通过。状态矩阵为既有实现的回归补强，不是新的 RED。单时钟 RTL、完整流接口与 Vivado 证据仍未完成。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。传统 NPU + ENeuron 当前状态为 `OF4B2B_RUNTIME_COMBINATION_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS`。OF1a/OF1b/OF3 合同继续成立；OF4a/OF4b1 冻结模型与掩码镜像，OF4b2 冻结四态命令端口，OF4b2b 补齐非法状态矩阵回归 9/9、runtime 组合 5/5 和完整 oracle 41/41，并证明全局 idle/freeze 双端同步与 frozen 推理不被阻断。状态矩阵是既有实现上的回归补强；`MODEL_COMMIT`、集成 RTL、完整流接口与 Vivado 证据仍待完成。CI-Fast V1 已完成全量/文档/NPU 定向路径验证，未知路径仍 fail-safe 进入全仓回归。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

状态覆盖（OF4b2b）：以上 OF4a/OF4b1/OF4b2 描述属于历史阶段；当前以 `OF4B2B_RUNTIME_COMBINATION_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS` 为准。OF4b2b 已冻结完整非法状态矩阵回归与 runtime 全局 idle/freeze 组合：状态矩阵 9/9、runtime 组合 5/5、完整 oracle 41/41；frozen 仍可推理。该证据只覆盖 Python 组合层，`MODEL_COMMIT`、单时钟 RTL、完整流接口和 Vivado 仍未完成。

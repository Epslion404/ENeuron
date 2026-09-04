# 系统边界

OF6 更新：传统 NPU + ENeuron 集成已进入 `RTL_DESIGN_CONTRACT_V2_APPROVED / RTL_SKELETON_IN_PROGRESS`。模型/流、mask epoch、控制三条 Icarus 切片已通过；第三条加入 `MASK_ABORT`、`STATE_CLEAR` 与严格 idle freeze 切换，并证明冻结仍可推理、配置与 clear 零副作用拒绝。真实 MAC、mask 门控计算与 Vivado 证据仍未完成。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。传统 NPU + ENeuron 当前状态为 `RTL_DESIGN_CONTRACT_V2_APPROVED / RTL_SKELETON_IN_PROGRESS`。OF1-OF6 Python 合同继续成立；V2 三条 RTL 切片只证明公开协议状态路径。除模型/样本与 mask epoch 外，第三条证明 abort 清 staging、clear 保留 committed 状态、freeze 严格 idle 切换、冻结推理与配置拒绝。尚无真实 INT8 MAC、active mask 对组读/MAC 的门控、完整随机逐拍门或 Vivado 物理证据，不得外推性能。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

状态覆盖：OF4a 至 OF6 属于已签核 Python oracle 历史阶段；当前以 `RTL_DESIGN_CONTRACT_V2_APPROVED / RTL_SKELETON_IN_PROGRESS` 为准。三条 Icarus 切片已覆盖部分逐拍协议，但完整计算、随机逐拍签核和 Vivado 仍未完成。

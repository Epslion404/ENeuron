# 系统边界

OF6 更新：传统 NPU + ENeuron 集成已进入 `RTL_DESIGN_CONTRACT_V2_APPROVED / RTL_SKELETON_IN_PROGRESS`。第一条骨架冻结模型顺序装载与固定样本/结果流；第二条 mask epoch 切片加入 19-word staging、published→样本首拍激活、`mask_valid`、结果 epoch、word18 保留位同索引重试、连续两样本与完整 128-bit response。两条 Icarus 入口各 1/1 通过；真实 MAC、mask 门控计算、freeze/clear 与 Vivado 证据仍未完成。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。传统 NPU + ENeuron 当前状态为 `RTL_DESIGN_CONTRACT_V2_APPROVED / RTL_SKELETON_IN_PROGRESS`。OF1-OF6 Python 合同继续成立；V2 的第一、第二条 RTL 切片只证明公开握手、模型/样本骨架和 mask epoch 状态路径。第二条具体证明 19-word loading→complete→published、样本首拍激活、`mask_valid`、结果 epoch、word18[31:16] 错误零推进/同索引重试、连续两个固定 8-beat 样本，以及 128-bit response 字段未被截断。尚无真实 INT8 MAC、active mask 对组读/MAC 的门控、freeze/clear、完整随机逐拍门或 Vivado 物理证据，不得外推性能。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

状态覆盖（OF6）：以上 OF4a 至 OF5 描述属于历史阶段；当前以 `RTL_DESIGN_REVIEW_WITH_ACTIONS` 为准。OF4g 已修正 `committed` 模型的冻结判定，OF5 已验证 hard reset 清理模型/mask/runtime 动态状态，OF6 相关 Python oracle 回归 48/48 且 CI-Fast 8/8；`loading/complete` 仍阻止 freeze，`committed` 允许 freeze 与推理，冻结后配置/动态清除仍拒绝。静态审计列出 8 项待补逐拍规格。该证据只覆盖 Python 组合层，单时钟 RTL、完整流接口和 Vivado 仍未完成。

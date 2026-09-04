# 系统边界

OF6 更新：传统 NPU + ENeuron 集成已进入 `RTL_DESIGN_CONTRACT_V2_APPROVED / RTL_SKELETON_IN_PROGRESS`。模型/流、mask epoch、控制三条 Icarus 切片已通过；第三条加入 `MASK_ABORT`、`STATE_CLEAR` 与严格 idle freeze 切换，并证明冻结仍可推理、配置与 clear 零副作用拒绝。真实 MAC、mask 门控计算与 Vivado 证据仍未完成。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。传统 NPU + ENeuron 当前状态为 `RTL_DESIGN_CONTRACT_V2_APPROVED / RTL_SKELETON_IN_PROGRESS`。OF1-OF6 Python 合同继续成立；当前 RTL 已包含四 lane 顺序 INT8 MAC、hidden 饱和、logit 槽和 active-mask 门控，并通过单时钟定向门。PR #54 的合并门暂缓：随机测试台首 beat 采样竞态已定位为消费者握手顺序错误，样本 0 已通过且样本 1 的失败值正好重复 output0；修复需在 result_ready 拉高后先完成首 beat posedge，再检查 beat1..9。GitHub CI 仅覆盖已提交 HEAD。尚无完整随机逐拍门或 Vivado 物理证据，不得外推性能。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

状态覆盖：OF4a 至 OF6 属于已签核 Python oracle 历史阶段；当前以 `RTL_DESIGN_CONTRACT_V2_APPROVED / RTL_SKELETON_IN_PROGRESS` 为准。三条 Icarus 切片已覆盖部分逐拍协议，但完整计算、随机逐拍签核和 Vivado 仍未完成。

# 系统边界

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-03
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。传统 NPU + ENeuron 边界由 `npu_eneuron_reference.py`、`npu_eneuron_protocol.py` 和定向测试表达；三项新增最坏情况证明零活动关闭不发读/MAC、逐样本 epoch 切换不混用 mask、pending 单槽满时拒绝覆盖。当前门为 `OF1-OF6_V3_REVIEW_REQUIRED`：保留 uint4 核心、Host 裁剪、安全 bias 与 634/19-word 顺序流。模型映射固定为 `16*h+g → w0[h][4*g+j]`、`512+h → bias0[h]`、`544+8*o+g → w1[o][4*g+j]`、`624+o → bias1[o]`，权重 word 均低字节优先。非法配置 beat 完成握手后返回一次错误且零副作用，允许同一隐式索引重试。mask staging 的 empty 只接受 begin，loading 只接受 data/abort，complete 只接受 commit/abort，published 拒绝全部 staging 命令。freeze 只在无部分输入、无运行样本、无待消费结果且 staging empty 的完全 idle 状态切换。open group 即使四个激活全零也计一次读取和四次 MAC。Python 输入与权重要求 `type(value) is int`，拒绝 bool、浮点、字符串及隐式转换。获批后的首个实现停止点仅为 OF1a uint4 fail-closed、非法样本零副作用且第 15 项 oracle 测试全绿。其余数值、配置流、状态组合和不可变结果尚未完成冻结测试，因此没有集成业务 RTL 或新 Vivado 证据。CI-Fast V1 已完成全量/文档/NPU 定向路径验证，未知路径仍 fail-safe 进入全仓回归。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

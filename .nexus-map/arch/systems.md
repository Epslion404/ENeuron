# 系统边界

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-03
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。传统 NPU + ENeuron 当前状态为 `OF3_MASK_ORDER_COST_GREEN / OF1-OF6_V3_IMPLEMENTATION_IN_PROGRESS`。OF1a/OF1b 数值模型合同继续成立；OF3 新增三项证据冻结 `mask0[h*16+g]`、`mask1[o*8+g]` 的行主序、内部单 bit 与两层首尾 mixed mask，并证明 open group 即使四个激活全零也固定计 1 次读取和 4 次 MAC。Oracle 22/22、OF3 3/3 通过，`npu_eneuron_reference.py` 无需修改。V3 其余 634-word 精确映射、19-word 配置、状态协议、集成 RTL 与 Vivado 证据仍待完成。CI-Fast V1 已完成全量/文档/NPU 定向路径验证，未知路径仍 fail-safe 进入全仓回归。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

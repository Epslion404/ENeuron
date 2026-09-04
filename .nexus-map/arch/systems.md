# 系统边界

OF6 更新：传统 NPU + ENeuron 集成状态为 `RTL_DESIGN_REVIEW_WITH_ACTIONS`。OF4g 修正模型冻结边界：只有 `loading/complete` 属于 staging 占用，`committed` 可进入冻结；OF5 又冻结 hard reset 的破坏性清理，恢复全开 mask、epoch=0 和 model_valid=0；冻结后仍允许推理，配置与动态清除仍拒绝。OF1-OF5 相关 Python oracle 最终回归 48/48、CI-Fast 8/8，签核已合并至 `main@0982ac5`。单时钟 RTL、完整流接口与 Vivado 证据仍未完成；静态审计列出 8 项待补逐拍规格。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。传统 NPU + ENeuron 当前状态为 `RTL_DESIGN_REVIEW_WITH_ACTIONS`。OF1a/OF1b/OF3 合同继续成立；OF4a/OF4b1 冻结模型与掩码镜像，OF4b2 冻结四态命令端口，OF4b2b 补齐非法状态矩阵回归 9/9、runtime 组合 5/5，OF4d/OF4e/OF4f 冻结模型提交、组合冻结和同拍仲裁，OF4g 修正 `committed` 模型边界，OF5 验证 hard reset 后旧状态不可见，OF6 汇总为 48/48 且 CI-Fast 8/8。静态审计另列 8 项逐拍规格缺口；上述证据仍只覆盖 Python oracle/组合层，集成 RTL、完整流接口与 Vivado 证据仍待完成。CI-Fast V1 已完成全量/文档/NPU 定向路径验证，未知路径仍 fail-safe 进入全仓回归。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

状态覆盖（OF6）：以上 OF4a 至 OF5 描述属于历史阶段；当前以 `RTL_DESIGN_REVIEW_WITH_ACTIONS` 为准。OF4g 已修正 `committed` 模型的冻结判定，OF5 已验证 hard reset 清理模型/mask/runtime 动态状态，OF6 相关 Python oracle 回归 48/48 且 CI-Fast 8/8；`loading/complete` 仍阻止 freeze，`committed` 允许 freeze 与推理，冻结后配置/动态清除仍拒绝。静态审计列出 8 项待补逐拍规格。该证据只覆盖 Python 组合层，单时钟 RTL、完整流接口和 Vivado 仍未完成。

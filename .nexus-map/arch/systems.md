# 系统边界

OF6 更新：传统 NPU + ENeuron 集成已进入 `RTL_RANDOM_GATE_GREEN / PR54_MERGED / VIVADO_OOC_NEXT`。模型/流、mask epoch、控制和真实计算四条 Icarus 切片已通过；固定 `20×100` 随机逐 beat 门、完整回归与 PR #54 CI 已在 `main@2a33f12` 收口。Vivado 2024.1 OOC 资源、时序、DRC 仍未完成。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。传统 NPU + ENeuron 当前状态为 `RTL_RANDOM_GATE_GREEN / PR54_MERGED / VIVADO_OOC_NEXT`。OF1-OF6 Python 合同继续成立；当前 RTL 已包含四 lane 顺序 INT8 MAC、hidden 饱和、logit 槽和 active-mask 门控，并通过定向与固定 `20×100` 随机逐 beat 门。尚无当前 HEAD 的 Vivado 物理证据，不得外推资源、时序、功耗或板级性能。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

状态覆盖：OF4a 至 OF6 属于已签核 Python oracle 历史阶段；当前以 `RTL_RANDOM_GATE_GREEN / PR54_MERGED / VIVADO_OOC_NEXT` 为准。四条 Icarus 切片、固定 `20×100` 随机逐拍签核和完整回归已完成；Vivado 2024.1 OOC 仍待执行。

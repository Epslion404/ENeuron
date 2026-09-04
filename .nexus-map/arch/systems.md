# 系统边界

状态更新（2026-09-04）：TR1-TR6 已实现并完成 C1-C4、单时钟专项 8/8、固定 `20×100` 和完整仓库 473/473（1 skipped）。DSP V1 OOC 已确认恰好 4 个 DSP48E1，hold/route/DRC 通过，但 setup `WNS=-0.673 ns`、22 个端点失败。当前进入 `TIMING_REPAIR_V2_REVIEW_REQUIRED`，TR7-TR12 未批准前不继续修改 RTL。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 已签核。传统 NPU + ENeuron 的 DSP V1 实现为 report head=`5055073`：`2192 LUT / 1904 FF / 4 DSP48E1`，setup 失败，故不得外推 100 MHz 收敛、板级吞吐、动态功耗或部署性能。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

状态覆盖：OF4a 至 OF6 属于已签核 Python oracle 历史阶段；当前以 `TR1_TR6_APPROVED / TIMING_REPAIR_V1_FUNCTIONAL_GREEN / DSP_GATE_PASS / VIVADO_OOC_SETUP_FAIL / TIMING_REPAIR_V2_REVIEW_REQUIRED` 为准。三拍 RTL 已实现，但 100 MHz 仍未收敛。

# 系统边界

历史基线（2026-09-05）：PR #64 已合并为 `main@a53a040`；PR #65 已合并为 `main@618c1e4`；PR #66 已合并为 `main@a1457bb`。V2 OOC 100 MHz 通过，资源为 `2126 LUT / 1916 FF / 4 DSP48E1`。首段旧快照中的 V1 失败数据仅作历史记录。

状态更新（2026-09-07）：TR7-TR12 已实现并完成 C1-C4、单时钟专项、固定 `20×100` 和完整仓库回归。V2 OOC 已确认 `2126 LUT / 1916 FF / 4 DSP48E1`，100 MHz `WNS=+0.060 ns / TNS=0 / WHS=+0.040 ns`，setup/hold/route/DRC 全部通过。V1 失败端点审计仍保留为历史证据；P15-T0 方案 A 与 A1-A7 已批准，T1-12 边界闭环、T1-06 fence testbench、T1-09 N/A 文档及复现扩展已在 `e4d48dd` 纳入提交基线；T2 参数化可变时钟及并发 epoch 切片已在 `872fa90` 通过 `(7,2)/(9,1)/(4,3)`：epoch=2 在旧样本计算期间发布，旧结果和下一 fence 仍回显 active epoch=1，下一样本才回显 epoch=2。完整 T1-01～T1-12、T2 全矩阵、T3 仍待验收，GitHub Actions 暂停期间不以远端 checks 作为证据。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-07
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为七个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、XC7Z020 顶层适配规划、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 已签核。传统 NPU + ENeuron 的 V2 实现为 report head=`f744bff`：`2126 LUT / 1916 FF / 4 DSP48E1`，100 MHz OOC 通过；仍不得外推板级吞吐、动态功耗或部署性能。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

状态覆盖：OF4a 至 OF6 属于已签核 Python oracle 历史阶段；当前以 `TR1_TR6_APPROVED / TR7_TR12_APPROVED / TIMING_REPAIR_V2_FUNCTIONAL_GREEN / VIVADO_OOC_100MHZ_PASS / P15_T0_APPROVED / T1_RTL_AUTHORIZED / T1_PROTOCOL_SLICE_PROVEN / T1_FULL_PENDING / T2_VARIABLE_CLOCK_SLICE_GREEN / T2_CONCURRENT_EPOCH_SLICE_GREEN / T2_FULL_MATRIX_PENDING / RESOURCE_CUT_DEFERRED_UNTIL_FIRST_END_TO_END_RUN` 为准。P15-T0 方案 A 及 A1-A7 已获批准；T1-02 主要路径、T1-06 fence 独立切片与 T1-12 四 FIFO 边界已在本机 `e4d48dd` 通过，T1-09 已记录为当前 wrapper 的 `NA_FOR_T1_WRAPPER / OUTER_SHIM_PENDING`，T2 三组可变时钟及并发 epoch 切片已在 `872fa90` 通过；T1/T2 全矩阵、T3 仍需独立验收。资源裁剪审查已完成，但所有裁剪实施推迟到第一次完整端到端运行成功之后。旧 Host Bridge OOC 的 `xc7a35tcpg236-1` 不得替代 P15 目标 `xc7z020clg400-1`。V2 已复用 signed 32-bit `mac_accumulator` 作为最终写回值，不新增 `writeback_value_latched`，并完成激活锁存、WRITEBACK、功能和 OOC 证明。

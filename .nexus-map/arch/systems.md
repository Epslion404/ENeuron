# 系统边界

历史基线（2026-09-05）：PR #64 已合并为 `main@a53a040`；PR #65 已合并为 `main@618c1e4`；PR #66 已合并为 `main@a1457bb`。V2 OOC 100 MHz 通过，资源为 `2126 LUT / 1916 FF / 4 DSP48E1`。首段旧快照中的 V1 失败数据仅作历史记录。

状态更新（2026-09-07）：当前 HEAD=`fd12afd`。T1/T2 切片已提交并通过本机复现：基础可变时钟绑定 `a616d60`，六组扩展绑定 `f54e762`，并发 epoch 绑定 `872fa90`，FIFO 矩阵绑定 `ee3a351`，wrapper 交错/复位绑定 `8457a20`。这些是 Icarus/等价模型证据，不是 AMD XPM/xsim 或物理证据。下一阶段 T3 必须使用真实 AMD XPM 库在 xsim 重放协同场景，再对“核心 + 适配器 + 四 FIFO”执行 `xc7z020clg400-1` OOC，分别记录 LUT/FF/BRAM/DSP、CDC、WNS/TNS/WHS/THS、route 和 DRC。GitHub Actions 已暂停，远端 checks 不作通过或失败证据。

T2 FIFO 矩阵切片已提交于 `ee3a351`：`tb_xpm_fifo_async_matrix.sv` 对四条 FIFO 通道执行 8 组时钟/相位×3 seed 的 24 次固定 scoreboard，入口输出 `REPRO_G2_T2_FIFO_MATRIX_PASS`。它只覆盖 Icarus 等价模型的顺序、满空、回绕/背压和复位压力，不代表 AMD XPM/xsim、XC7Z020 T3 或板级证据；该切片已通过并归档；它仍不等于真实 AMD XPM/xsim 或 T3 物理证据。

T2 wrapper 交错/复位切片已提交于 `8457a20`：`tb_npu_zynq7020_t2_interleave_reset.sv` 在 `(2,0)/(3,1)/(7,2)/(11,4)` 四组配置下验证命令/样本交错和多个复位位置，4/4 输出 `REPRO_G2_T2_INTERLEAVE_RESET_PASS`。它只覆盖 Icarus wrapper 切片，不代表 T2 全矩阵、AMD XPM/xsim、XC7Z020 T3 或 Actions 结果；该切片已通过并归档；它仍不等于真实 AMD XPM/xsim 或 T3 物理证据。

T2 归档校正：FIFO 矩阵已提交于 `ee3a351`，wrapper 交错/复位切片已提交于 `8457a20`；原有“工作树候选”文字只作提交前快照。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-07
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为七个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、XC7Z020 顶层适配规划、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 已签核。传统 NPU + ENeuron 的 V2 实现为 report head=`f744bff`：`2126 LUT / 1916 FF / 4 DSP48E1`，100 MHz OOC 通过；仍不得外推板级吞吐、动态功耗或部署性能。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

状态覆盖：OF4a 至 OF6 属于已签核 Python oracle 历史阶段；当前以 `TR1_TR6_APPROVED / TR7_TR12_APPROVED / TIMING_REPAIR_V2_FUNCTIONAL_GREEN / VIVADO_OOC_100MHZ_PASS / P15_T0_APPROVED / T1_RTL_AUTHORIZED / T1_PROTOCOL_SLICE_PROVEN / T1_FULL_PENDING / T2_VARIABLE_CLOCK_SLICE_GREEN / T2_CONCURRENT_EPOCH_SLICE_GREEN / T2_EXTENDED_CLOCK_SLICE_GREEN / T2_FIFO_MATRIX_SLICE_GREEN / T2_INTERLEAVE_RESET_SLICE_GREEN / T2_FULL_MATRIX_PENDING / T3_XPM_XSIM_OOC_PENDING / RESOURCE_CUT_DEFERRED_UNTIL_FIRST_END_TO_END_RUN` 为准。P15-T0 方案 A 及 A1-A7 已获批准；T1-02 主要路径、T1-06 fence 独立切片与 T1-12 四 FIFO 边界已在本机 `e4d48dd` 通过，T1-09 已记录为当前 wrapper 的 `NA_FOR_T1_WRAPPER / OUTER_SHIM_PENDING`，T2 六组可变时钟、FIFO 矩阵及交错/复位切片已提交并通过；T1/T2 随机频率/相位全矩阵、T3 仍需独立验收。资源裁剪审查已完成，但所有裁剪实施推迟到第一次完整端到端运行成功之后。旧 Host Bridge OOC 的 `xc7a35tcpg236-1` 不得替代 P15 目标 `xc7z020clg400-1`。V2 已复用 signed 32-bit `mac_accumulator` 作为最终写回值，不新增 `writeback_value_latched`，并完成激活锁存、WRITEBACK、功能和 OOC 证明。

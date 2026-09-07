# 系统边界

当前校正（2026-09-07）：T3 真实 XPM/xsim 与 XC7Z020 OOC 证据绑定 `c2bc03f`；顶层 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`，host/npu WNS/WHS 为 `+3.639/+0.105 ns`、`+0.214/+0.042 ns`。下方 `822cf93` 为历史快照。

历史基线（2026-09-05）：PR #64 已合并为 `main@a53a040`；PR #65 已合并为 `main@618c1e4`；PR #66 已合并为 `main@a1457bb`。V2 OOC 100 MHz 通过，资源为 `2126 LUT / 1916 FF / 4 DSP48E1`。首段旧快照中的 V1 失败数据仅作历史记录。

状态更新（2026-09-07，T3 复核）：当前提交 HEAD=`c2bc03f`。真实 AMD XPM/xsim 协同仿真 `RESULT=PASS`；XC7Z020 OOC `PHYSICAL_GATE=PASS`，绑定 Vivado 2024.1、`xc7z020clg400-1`、host/npu 100 MHz 双时钟。顶层资源为 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`；外部 CDC critical/warning 均为 0；setup/hold、route、DRC error 均为 0。XPM 内部 CDC 仍有 8 个工具 warning，DRC 保留建议性 warning（不构成 error gate）。这项证据不覆盖 AXI、DMA、PS7、Ethernet、bitstream、板级 I/O/吞吐、功耗或首次端到端运行。GitHub Actions 已暂停，远端 checks 不作通过或失败证据。

T3 证据文件：`vivado_npu_zynq7020_t3_xsim/xsim_signoff_summary.txt` 与 `vivado_npu_zynq7020_t3_ooc_reports/signoff_summary.txt`。两份报告均绑定 `GIT_HEAD=c2bc03f`；xsim 使用真实 `XPM_LIBRARIES=XPM_FIFO`，OOC 报告 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / DSP48E1_COUNT=4`、`EXTERNAL_CDC_CRITICAL=0`、`EXTERNAL_CDC_WARNING=0`、host `WNS=3.639 ns / WHS=0.105 ns`、npu `WNS=0.214 ns / WHS=0.042 ns`，route/DRC errors 均为 0。

T2 FIFO 矩阵切片已提交于 `ee3a351`：`tb_xpm_fifo_async_matrix.sv` 对四条 FIFO 通道执行 8 组时钟/相位×3 seed 的 24 次固定 scoreboard，入口输出 `REPRO_G2_T2_FIFO_MATRIX_PASS`。它只覆盖 Icarus 等价模型的顺序、满空、回绕/背压和复位压力，不代表 AMD XPM/xsim、XC7Z020 T3 或板级证据；该切片已通过并归档；它仍不等于真实 AMD XPM/xsim 或 T3 物理证据。

T2 wrapper 交错/复位切片已提交于 `8457a20`：`tb_npu_zynq7020_t2_interleave_reset.sv` 在 `(2,0)/(3,1)/(7,2)/(11,4)` 四组配置下验证命令/样本交错和多个复位位置，4/4 输出 `REPRO_G2_T2_INTERLEAVE_RESET_PASS`。它只覆盖 Icarus wrapper 切片，不代表 T2 全矩阵、AMD XPM/xsim、XC7Z020 T3 或 Actions 结果；该切片已通过并归档；它仍不等于真实 AMD XPM/xsim 或 T3 物理证据。

T2 归档校正：FIFO 矩阵已提交于 `ee3a351`，wrapper 交错/复位切片已提交于 `8457a20`；原有“工作树候选”文字只作提交前快照。

T2 wrapper 固定种子随机矩阵状态为 `T2_RANDOM_CLOCK_MATRIX_GREEN`：`--t2-random-matrix` 使用种子 `20260907` 生成 24 个唯一时钟/相位组合，并以 `2000 + 400 × NPU_HALF` 个 Host 周期作为随慢时钟增长的观察预算，最终输出 `REPRO_G2_T2_RANDOM_MATRIX_PASS`。该证据扩展了有限确定性矩阵，但仍不是数学穷举。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-07
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为七个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、XC7Z020 顶层适配规划、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 已签核。传统 NPU + ENeuron 的 V2 实现为 report head=`f744bff`：`2126 LUT / 1916 FF / 4 DSP48E1`，100 MHz OOC 通过；仍不得外推板级吞吐、动态功耗或部署性能。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

状态覆盖：OF4a 至 OF6 属于已签核 Python oracle 历史阶段；当前以 `TR1_TR6_APPROVED / TR7_TR12_APPROVED / TIMING_REPAIR_V2_FUNCTIONAL_GREEN / VIVADO_OOC_100MHZ_PASS / P15_T0_APPROVED / T1_RTL_AUTHORIZED / T1_PROTOCOL_SLICE_PROVEN / T1_FULL_PENDING / T2_VARIABLE_CLOCK_SLICE_GREEN / T2_CONCURRENT_EPOCH_SLICE_GREEN / T2_EXTENDED_CLOCK_SLICE_GREEN / T2_FIFO_MATRIX_SLICE_GREEN / T2_INTERLEAVE_RESET_SLICE_GREEN / T2_FINITE_CLOCK_MATRIX_GREEN / T2_RANDOM_CLOCK_MATRIX_GREEN / T2_FULL_MATRIX_PENDING / T3_XPM_XSIM_PASS / T3_XC7Z020_OOC_PASS / T3_SIGNOFF_PASS / RESOURCE_CUT_DEFERRED_UNTIL_FIRST_END_TO_END_RUN` 为准。P15-T0 方案 A 及 A1-A7 已获批准；T1-02 主要路径、T1-06 fence 独立切片与 T1-12 四 FIFO 边界已在本机 `e4d48dd` 通过，T1-09 已记录为当前 wrapper 的 `NA_FOR_T1_WRAPPER / OUTER_SHIM_PENDING`，T2 六组可变时钟、FIFO、交错/复位、16 组有限矩阵和 24 组固定种子随机矩阵已提交并通过；T1 全量、T2 更广泛并发交错、外层 shim、首次端到端运行仍待独立验收。T3 真实 AMD XPM/xsim 与 XC7Z020 OOC 已通过，详见上方报告路径。资源裁剪审查已完成，但所有裁剪实施推迟到第一次完整端到端运行成功之后。旧 Host Bridge OOC 的 `xc7a35tcpg236-1` 不得替代 P15 目标 `xc7z020clg400-1`。V2 已复用 signed 32-bit `mac_accumulator` 作为最终写回值，不新增 `writeback_value_latched`，并完成激活锁存、WRITEBACK、功能和 OOC 证明。

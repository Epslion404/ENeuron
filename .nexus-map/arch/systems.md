# 系统边界

## 当前边界校正（中等精简）

部署主线固定为 `xc7z020clg484-2` 的 NPU + ENeuron 动态剪枝。`xc7z020clg400-1` 上的 T3/NP7 OOC 与资源/时序报告仅作历史结构参考，不能替代 `clg484-2` 最终 routed 证据；`archive/legacy/` 内容不进入日常 CI/PR 门。B1 高地址 DDR、PHY 和 UDP 是板卡资格支线，仍决定完整 `B1-GATE`，但不阻塞低地址容量满足条件下的 NPU MVP。CH340 设备按 `VID_1A86:PID_7523` 识别，COM 编号仅作现场观测。

合同层级（2026-09-09）：当前阶段合同为 `docs/planning/NPU_ZYNQ7020_BOARD_VALIDATION_PHASE2_V1.md`；P16 TODO 段、`NPU_PRUNING_TODO.md` 和 `NPU_PRUNING_NP7_TODO.md` 是关联合同。P16 当前活动未完成项为 `63`。当前活动分支为 `codex/b1b-high-ddr-board-repro`，仓库 HEAD=`6f3d40e6f0470bbb57a9a10fb107ffc892add25c`（父级审计基线 `d7e1035`）；主线执行链为 B2-03 低地址实板回环 → B2-04 边界帧 → B2-05 背压/压力，B1-06B6 UART 基准 → B1-06B7 OCM 高地址最小复现保留为资格支线，尚未进行高地址 DDR 访问。

B1B状态（2026-09-08）：当前B1A硬件身份为`29edf6a...`，B1B软件身份为`97ddd1a...`，bitstream/XSA/ELF为`1f98e949...bc5f6`、`ed4a2ff...d417b`、`4992d26c...128560`。正式UART为Bank 33的V14 RX/V15 TX，外置CH340按 VID/PID 自动发现（现场枚举 COM10）并在三次完整断电冷启动后收到完整协议；低地址1 MiB DDR九阶段与OCM记录也三次通过。`0x10000000`异常未关闭且高地址尚未访问，B1B与`B1-GATE`仍未完成。`hsi::open_hw_design`只能对临时XSA副本运行，正式build目录保持只读。

B1A-HW状态（2026-09-08）：`boards/hellozynq/b1a_hw/`已在干净提交`29edf6a...`完成正式UART方向的Vivado 2024.1实现。最终I/O确认V14为Bank 33固定INPUT、V15为固定OUTPUT，均为LVCMOS33；资源与旧版本相同，WHS=`+0.138 ns`，其余实现硬门通过。状态保持`B1A_HW_DEFINITION_COMPLETE / B1_GATE_PASS=false`。

阶段2实板状态（2026-09-09）：实际板卡目标固定为`xc7z020clg484-2`。B0双运行与完整断电证据已通过PR #69合并为`main@102dee2...`；B1-D1已批准，B1A完成，B1B的UART与低地址1 MiB DDR三次冷启动通过，高地址DDR边界仍阻塞完整 B1-GATE。B2-00、B2-D1、B2-01 已冻结；正式同源 bit/XSA/ELF manifest 为 HEAD `6f3d40e…`、bit `44163a…`、XSA `b80e3f…`、ELF `6bf1e9…`，`run_b2_board.ps1` 已加入烧写前 fail-closed SHA-256 身份检查。`20260909T045710Z` 已完成 program/download/run，并读取 MM2S/S2MM 各 16 beats、64 bytes、TLAST=1、TKEEP=0xF、stall=0；UART 仍 `NO_TERMINAL_MARKER`，受控背压与错误恢复仍待收口，B2-03/B2-GATE 未关闭。

B2 观测器边界（2026-09-09）：双 `axi_stream_monitor:1.1` routed setup 为 `WNS=-0.325 ns/TNS=-11.113 ns/127` 个失败端点，单 monitor 为 `WNS=-0.284 ns/TNS=-22.272 ns/256` 个失败端点；两者均仅为历史实验。自有轻量 `axis_stream_probe` 双向 sampler 已进入正式同源拓扑并在 `20260909T045710Z` 实板读取成功，MM2S/S2MM 均为 `16 beats/64 bytes/TLAST=1/TKEEP=0xF/stall=0`、`probe_exit_code=0`；合同测试合计 `21/21`（DMA app 12/12、monitor 5/5、probe 4/4）。该单端点读数不覆盖受控背压、连续回绕或错误恢复，B2-03/B2-GATE 仍未完成。

P16最终硬门仍按B0→B1→B2→B3→B4串行，但代码按Fastlane V1小步合并。B1A/B1B/B1C中间切片可进入main但不改变阶段通过状态；B2–B4仍不得提前声明实现或签核。

B3/B4 包含两条不同证据链：Host 静态 `2:4` mask 是由 Host 重放冻结 mask，只证明 NPU 门控执行、位序、epoch 和跳过计数；live-ENeuron 是由实板神经元证据生成严格 `2:4` 决策，经 pending bank 和 fence 原子生效。只有后者可证明神经元参与自动剪枝，两类数据不得混合。

当前校正（2026-09-07）：T3 真实 XPM/xsim 与 XC7Z020 OOC 证据绑定 `c2bc03f`；顶层 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`，host/npu WNS/WHS 为 `+3.639/+0.105 ns`、`+0.214/+0.042 ns`。下方 `822cf93` 为历史快照。

历史基线（2026-09-05）：PR #64 已合并为 `main@a53a040`；PR #65 已合并为 `main@618c1e4`；PR #66 已合并为 `main@a1457bb`。V2 OOC 100 MHz 通过，资源为 `2126 LUT / 1916 FF / 4 DSP48E1`。首段旧快照中的 V1 失败数据仅作历史记录。

状态更新（2026-09-07，T3 复核）：当前提交 HEAD=`c2bc03f`。真实 AMD XPM/xsim 协同仿真 `RESULT=PASS`；XC7Z020 OOC `PHYSICAL_GATE=PASS`，绑定 Vivado 2024.1、`xc7z020clg400-1`、host/npu 100 MHz 双时钟。顶层资源为 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`；外部 CDC critical/warning 均为 0；setup/hold、route、DRC error 均为 0。XPM 内部 CDC 仍有 8 个工具 warning，DRC 保留建议性 warning（不构成 error gate）。这项证据不覆盖 AXI、DMA、PS7、Ethernet、bitstream、板级 I/O/吞吐、功耗或首次端到端运行。GitHub Actions 已暂停，远端 checks 不作通过或失败证据。

T3 证据文件：`vivado_npu_zynq7020_t3_xsim/xsim_signoff_summary.txt` 与 `vivado_npu_zynq7020_t3_ooc_reports/signoff_summary.txt`。两份报告均绑定 `GIT_HEAD=c2bc03f`；xsim 使用真实 `XPM_LIBRARIES=XPM_FIFO`，OOC 报告 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / DSP48E1_COUNT=4`、`EXTERNAL_CDC_CRITICAL=0`、`EXTERNAL_CDC_WARNING=0`、host `WNS=3.639 ns / WHS=0.105 ns`、npu `WNS=0.214 ns / WHS=0.042 ns`，route/DRC errors 均为 0。

T2 FIFO 矩阵切片已提交于 `ee3a351`：`tb_xpm_fifo_async_matrix.sv` 对四条 FIFO 通道执行 8 组时钟/相位×3 seed 的 24 次固定 scoreboard，入口输出 `REPRO_G2_T2_FIFO_MATRIX_PASS`。它只覆盖 Icarus 等价模型的顺序、满空、回绕/背压和复位压力，不代表 AMD XPM/xsim、XC7Z020 T3 或板级证据；该切片已通过并归档；它仍不等于真实 AMD XPM/xsim 或 T3 物理证据。

T2 wrapper 交错/复位切片已提交于 `8457a20`：`tb_npu_zynq7020_t2_interleave_reset.sv` 在 `(2,0)/(3,1)/(7,2)/(11,4)` 四组配置下验证命令/样本交错和多个复位位置，4/4 输出 `REPRO_G2_T2_INTERLEAVE_RESET_PASS`。它只覆盖 Icarus wrapper 切片，不代表 T2 全矩阵、AMD XPM/xsim、XC7Z020 T3 或 Actions 结果；该切片已通过并归档；它仍不等于真实 AMD XPM/xsim 或 T3 物理证据。

T2 归档校正：FIFO 矩阵已提交于 `ee3a351`，wrapper 交错/复位切片已提交于 `8457a20`；原有“工作树候选”文字只作提交前快照。

T2 wrapper 固定种子随机矩阵状态为 `T2_RANDOM_CLOCK_MATRIX_GREEN`：`--t2-random-matrix` 使用种子 `20260907` 生成 24 个唯一时钟/相位组合，并以 `2000 + 400 × NPU_HALF` 个 Host 周期作为随慢时钟增长的观察预算，最终输出 `REPRO_G2_T2_RANDOM_MATRIX_PASS`。该证据扩展了有限确定性矩阵，但仍不是数学穷举。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-09
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为八个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、XC7Z020 顶层适配、HelloZynq 阶段 2 实板验证、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 已签核。传统 NPU + ENeuron 的 V2 实现为 report head=`f744bff`：`2126 LUT / 1916 FF / 4 DSP48E1`，100 MHz OOC 通过；仍不得外推板级吞吐、动态功耗或部署性能。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

状态覆盖：OF4a 至 OF6 属于已签核 Python oracle 历史阶段；当前以 `TR1_TR6_APPROVED / TR7_TR12_APPROVED / TIMING_REPAIR_V2_FUNCTIONAL_GREEN / VIVADO_OOC_100MHZ_PASS / P15_T0_APPROVED / T1_RTL_AUTHORIZED / T1_PROTOCOL_SLICE_PROVEN / T1_FULL_PENDING / T2_VARIABLE_CLOCK_SLICE_GREEN / T2_CONCURRENT_EPOCH_SLICE_GREEN / T2_EXTENDED_CLOCK_SLICE_GREEN / T2_FIFO_MATRIX_SLICE_GREEN / T2_INTERLEAVE_RESET_SLICE_GREEN / T2_FINITE_CLOCK_MATRIX_GREEN / T2_RANDOM_CLOCK_MATRIX_GREEN / T2_FULL_MATRIX_PENDING / T3_XPM_XSIM_PASS / T3_XC7Z020_OOC_PASS / T3_SIGNOFF_PASS / RESOURCE_CUT_DEFERRED_UNTIL_FIRST_END_TO_END_RUN` 为准。P15-T0 方案 A 及 A1-A7 已获批准；T1-02 主要路径、T1-06 fence 独立切片与 T1-12 四 FIFO 边界已在本机 `e4d48dd` 通过，T1-09 已记录为当前 wrapper 的 `NA_FOR_T1_WRAPPER / OUTER_SHIM_PENDING`，T2 六组可变时钟、FIFO、交错/复位、16 组有限矩阵和 24 组固定种子随机矩阵已提交并通过；T1 全量、T2 更广泛并发交错、外层 shim、首次端到端运行仍待独立验收。T3 真实 AMD XPM/xsim 与 XC7Z020 OOC 已通过，详见上方报告路径。资源裁剪审查已完成，但所有裁剪实施推迟到第一次完整端到端运行成功之后。旧 Host Bridge OOC 的 `xc7a35tcpg236-1` 不得替代 P15 目标 `xc7z020clg400-1`。V2 已复用 signed 32-bit `mac_accumulator` 作为最终写回值，不新增 `writeback_value_latched`，并完成激活锁存、WRITEBACK、功能和 OOC 证明。

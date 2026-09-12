# 系统边界

> generated_by: nexus-mapper v2 / manual synthesis
> verified_at: 2026-09-13
> provenance: live tree=`D:/Documents/Code/ENeuron-board-b0`，分支 `codex/b1b-high-ddr-board-repro` / PR #88。bitstream RTL 身份 `be84596`。`D:/Documents/Code/ENeuron` 不是当前 live tree。SPEED 证据 `artifacts/logs/b3_speed_20260912_be84596/b3_speed_comparison.json`。

## 当前权威快照（2026-09-13，日常主线 B3-POWER）

器件 `xc7z020clg484-2`。日常主线是 `B3-POWER`（外部功耗），不是 B3-08b。主线仍是板上 packet-NPU + ENeuron 组级动态剪枝。live tree 是本工作树 / PR #88，不是 `D:/Documents/Code/ENeuron`。

B3-MVP-GATE 已关。同一份集中 Vivado 2024.1 bitstream：RTL 身份 `be84596`，200 MHz FCLK0，WNS=+0.045 ns，TNS=0，WHS=+0.036 ns，THS=0，route/DRC hard errors=0，DSP48E1=4。bit SHA-256=`0ecbe76274c39418f2a60a88358d3ff6f09f5a2ed73a44a3a419c34eb91d3a11`，XSA SHA-256=`135d979d61c629922ee5419e51dd97ef045d9bab79930432816d09f109291d1a`。

冻结 AXI-Lite 状态块 `0x40430000`（`b2_npu_status_probe.v`）：0x00-0x4C 不变；0x50 runtime_status；0x54/0x58 active/pending mask epoch；0x5C last NPU compute cycles；0x60 protocol errors。pending epoch 来自 core `mask_state==MASK_PUBLISHED`，不是 `mask_valid`。COM15 CH340 `VID_1A86:PID_7523`。B3-11 hold：MASK_COMMIT 后、下一样本前 `active=0 pending=1`；样本后 `active=1 pending=0`。

四模式 A/B 两轮一致：dense/full-open 592/0 组、2494 cycles、logits 165,-18,14,0,0,0,0,0,0,153；static mixed 296/296、1606 cycles、logits 74,-18,...,114、`decision_source=host_replay_static_mixed`；live-ENeuron 296/296、1606 cycles、dense logits、`decision_source=live_eneuron_s2`。同源 bit `be84596` / SHA `0ecbe762…3a11`、COM15 系统路径：dense/full-open PS 7 µs、DMA ~60 µs、UART ~66–77 ms；static DMA 56 µs、UART 63 ms；live PS 996 µs、DMA 56 µs。只可声称 `group_4way` 动态剪枝正确性 + 局部 NPU 周期差值 888 cycles。禁止：888 当端到端加速、Vivado 功耗当板上功耗、19-word 当连接级 `2:4`。

`B3-SPEED` 已关。`claim=local_npu_cycle_delta_only`，`end_to_end_accelerated=false`。888 cycle ≈ 4.4 µs 被系统路径掩盖。证据：`artifacts/logs/b3_speed_20260912_be84596/b3_speed_comparison.json`。当前门：`B3-POWER`（外部功耗）。`B3-STRICT-GATE`（lane 2:4、10k 样本）是结构实验，不是加速硬门。后文旧 HEAD（`fe25a70`/`88bec9e`/`c3a50eb`/`f070577`）只描述当时证据身份。

## 当前边界校正（中等精简）

当前摘要校正（2026-09-12）：packet-NPU 在 `xc7z020clg484-2`、200 MHz 通过 routed timing。B3-00/02/04/06/07/08a/09/11/13/14 已关闭；B3-MVP-GATE 已关。B3-09 组级 live 与 B3-11 epoch 读回、B3-13/14 四模式周期 A/B 均在 `be84596` 同一 bitstream 上完成。后文若仍写 B3-09 实板 pending 或当前门为 `B3-MVP-GATE`，以本条为准。

部署主线固定为 `xc7z020clg484-2` 的 NPU + ENeuron 组级动态剪枝。`xc7z020clg400-1` 上的 T3/NP7 OOC 与资源/时序报告仅作历史结构参考，不能替代 `clg484-2` 最终 routed 证据；`archive/legacy/` 内容不进入日常 CI/PR 门。B1 高地址 DDR、PHY 和 UDP 是板卡资格支线，仍决定完整 `B1-GATE`，但不回写已关闭的 B3-MVP。CH340 设备按 `VID_1A86:PID_7523` 识别，COM 编号仅作现场观测；双设备时必须显式 COM15。

合同层级（2026-09-12）：当前阶段合同为 `docs/planning/NPU_ZYNQ7020_BOARD_VALIDATION_PHASE2_V1.md`；P16 TODO 段、`NPU_PRUNING_TODO.md` 和 `NPU_PRUNING_NP7_TODO.md` 是关联合同。当前执行链为 `B3-STRICT-GATE → B4-RELEASE-GATE`。B2-GATE 仍是完整 packet 发布门，未关闭。严格 `2:4`、10000 样本、完整恢复属于 STRICT；网口和外部功耗属于 B4。

B1B状态（2026-09-08）：当前B1A硬件身份为`29edf6a...`，B1B软件身份为`97ddd1a...`，bitstream/XSA/ELF为`1f98e949...bc5f6`、`ed4a2ff...d417b`、`4992d26c...128560`。正式UART为Bank 33的V14 RX/V15 TX，外置CH340按 VID/PID 自动发现（现场枚举 COM10）并在三次完整断电冷启动后收到完整协议；低地址1 MiB DDR九阶段与OCM记录也三次通过。`0x10000000`异常未关闭且高地址尚未访问，B1B与`B1-GATE`仍未完成。`hsi::open_hw_design`只能对临时XSA副本运行，正式build目录保持只读。

B1A-HW状态（2026-09-08）：`boards/hellozynq/b1a_hw/`已在干净提交`29edf6a...`完成正式UART方向的Vivado 2024.1实现。最终I/O确认V14为Bank 33固定INPUT、V15为固定OUTPUT，均为LVCMOS33；资源与旧版本相同，WHS=`+0.138 ns`，其余实现硬门通过。状态保持`B1A_HW_DEFINITION_COMPLETE / B1_GATE_PASS=false`。

阶段2实板状态（2026-09-09）：实际板卡目标固定为`xc7z020clg484-2`。B0双运行与完整断电证据已通过PR #69合并；B1-D1已批准，B1A完成，B1B的UART与低地址1 MiB DDR三次冷启动通过，高地址DDR边界仍阻塞完整 B1-GATE。正式 run `20260909T105109Z`（HEAD `f7f01b0`）在交换 USB-TTL TX/RX 后取得 UART/JTAG PASS，边界 `7 PASS + 1 zero-length reject + 0 fail`，pressure `10000/10000`，backpressure `64/64`，连续回绕 `256/256`、rollovers=`3`，首末地址 `TX 0x01006000→0x01006FC0`、`RX 0x01007000→0x01007FC0`。recovery run `20260909T110436Z` 进一步取得 UART/JTAG/XSCT PASS，timeout/reset/passed/failed=`1/1/1/0`、sequence=`10329`、CRC32=`0xD3E3C978`，recovery ELF=`f2706099…e0363`。B2-03/B2-04/B2-05/B2-GATE 仍因更完整逐帧 PL 观测、间歇/ready 恢复和错误注入未关闭。

B2 观测器边界（2026-09-09）：双/单 `axi_stream_monitor:1.1` routed setup 均为历史失败（`WNS=-0.325/-0.284 ns`），不计入物理通过。当前轻量 probe 修复将软件配置设为 `0x04030201`、零 stall 直接失败，RTL 从首个输入启动 phase，并在已公开 VALID 等待 READY 时冻结 phase；六个 B2 合同文件 `51/51` 通过。正式 run `20260909T105109Z`（HEAD `f7f01b0`）已证明 UART/JTAG PASS、受控背压 `64/64`、连续回绕 `256/256` 帧、`rollovers=3`；首末地址为 TX `0x01006000→0x01006FC0`、RX `0x01007000→0x01007FC0`。连续回绕切片为 BOARD_PASS，但多长度逐帧 PL、错误/复位恢复及 B2-03/B2-04/B2-05/B2-GATE 整体关闭仍未完成。

P16 最终发布仍要求 B1/B2 完整门、`B3-STRICT-GATE` 与 `B4-RELEASE-GATE`，但开发实验按 Fastlane V1 小步合并。`B3-MVP-GATE` 已关；不因发布链未全部关闭而回写 MVP。

B3 数值功能入口：固定 `64→32→10` 模型与共享黄金 manifest。B3-02 已由 Python loader 与 Host PowerShell 生成 C 头文件合同测试关闭。B3-01 的完整 clean-worktree 发布身份冻结属于 `B3-STRICT-GATE`；B3-MVP 每次实板 run 绑定当次 bit/XSA/ELF/manifest 即可。当前 19 个 mask word 表达 592 个 `group_4way` 门，先用于 live-ENeuron MVP，不得称为严格连接级 `2:4`。

B3 计数器物理边界（2026-09-12）：第三次 `route_design -directive Explore` 加 post-route `AggressiveExplore` 已在 HEAD `c3a50eb`、`xc7z020clg484-2`、200 MHz 上通过物理硬门（`WNS/TNS=+0.008/0 ns`、`WHS/THS=+0.036/0 ns`、route/DRC hard errors=0、DSP48E1=4）。后续 dense/full-open/bypass 实板已读回 execute/skip=`592/0`，B3-00/B3-06/B3-07 已关闭。该物理身份不是当前提交 HEAD `fe25a70`，未提交 RTL 也不是该身份。

B3 包含两条必须分开的证据链：Host 静态 mask 只证明 NPU 门控执行、位序、epoch 和跳过计数；live-ENeuron 由当前样本证据生成 mask，经 pending bank 和 fence 原子生效。MVP 两者均使用现有 `group_4way` 粒度，且均已在 `be84596` bitstream 上关闭；STRICT 再分别扩展为严格连接级 `2:4`，两级数据不得混合或互相代证。

B3-08a 组级静态 mixed mask 已在 COM15 实板通过：`b3_static_mixed`、同一物理通过 bit/XSA、logits=`74,-18,14,0,0,0,0,0,0,114`、execute/skip=`296/296`、fence valid=`1`。其 `group_4way` 粒度不构成严格连接级 `2:4` 或 ENeuron 自动决策；B3-08b 延后到 STRICT。

B3-09 Host/板级边界（2026-09-12）：提交 `fe25a70` 增加 `eneuron_group4way_live.py` 与 `packet_main.c` 的 `B3_LIVE_ENEURON`。S2 gain=1，148 次 meta 提交各保留 2/4 组，打包 19-word mask。板级 live 已在 `be84596` bitstream、COM15 上关闭：logits=`165,-18,14,0,0,0,0,0,0,153`，execute/skip=`296/296`，`decision_source=live_eneuron_s2`。mask word1=`0x33393335`，不等于 static mixed 全 `0x33333333`。禁止生成 `B3_LIVE_ENEURON_MASK_WORDS` 常量。不是严格 `2:4`。

当前校正（2026-09-07）：T3 真实 XPM/xsim 与 XC7Z020 OOC 证据绑定 `c2bc03f`；顶层 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`，host/npu WNS/WHS 为 `+3.639/+0.105 ns`、`+0.214/+0.042 ns`。下方 `822cf93` 为历史快照。

历史基线（2026-09-05）：PR #64 已合并为 `main@a53a040`；PR #65 已合并为 `main@618c1e4`；PR #66 已合并为 `main@a1457bb`。V2 OOC 100 MHz 通过，资源为 `2126 LUT / 1916 FF / 4 DSP48E1`。首段旧快照中的 V1 失败数据仅作历史记录。

状态更新（2026-09-07，T3 复核）：当前提交 HEAD=`c2bc03f`。真实 AMD XPM/xsim 协同仿真 `RESULT=PASS`；XC7Z020 OOC `PHYSICAL_GATE=PASS`，绑定 Vivado 2024.1、`xc7z020clg400-1`、host/npu 100 MHz 双时钟。顶层资源为 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`；外部 CDC critical/warning 均为 0；setup/hold、route、DRC error 均为 0。XPM 内部 CDC 仍有 8 个工具 warning，DRC 保留建议性 warning（不构成 error gate）。这项证据不覆盖 AXI、DMA、PS7、Ethernet、bitstream、板级 I/O/吞吐、功耗或首次端到端运行。GitHub Actions 已暂停，远端 checks 不作通过或失败证据。

T3 证据文件：`vivado_npu_zynq7020_t3_xsim/xsim_signoff_summary.txt` 与 `vivado_npu_zynq7020_t3_ooc_reports/signoff_summary.txt`。两份报告均绑定 `GIT_HEAD=c2bc03f`；xsim 使用真实 `XPM_LIBRARIES=XPM_FIFO`，OOC 报告 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / DSP48E1_COUNT=4`、`EXTERNAL_CDC_CRITICAL=0`、`EXTERNAL_CDC_WARNING=0`、host `WNS=3.639 ns / WHS=0.105 ns`、npu `WNS=0.214 ns / WHS=0.042 ns`，route/DRC errors 均为 0。

T2 FIFO 矩阵切片已提交于 `ee3a351`：`tb_xpm_fifo_async_matrix.sv` 对四条 FIFO 通道执行 8 组时钟/相位×3 seed 的 24 次固定 scoreboard，入口输出 `REPRO_G2_T2_FIFO_MATRIX_PASS`。它只覆盖 Icarus 等价模型的顺序、满空、回绕/背压和复位压力，不代表 AMD XPM/xsim、XC7Z020 T3 或板级证据；该切片已通过并归档；它仍不等于真实 AMD XPM/xsim 或 T3 物理证据。

T2 wrapper 交错/复位切片已提交于 `8457a20`：`tb_npu_zynq7020_t2_interleave_reset.sv` 在 `(2,0)/(3,1)/(7,2)/(11,4)` 四组配置下验证命令/样本交错和多个复位位置，4/4 输出 `REPRO_G2_T2_INTERLEAVE_RESET_PASS`。它只覆盖 Icarus wrapper 切片，不代表 T2 全矩阵、AMD XPM/xsim、XC7Z020 T3 或 Actions 结果；该切片已通过并归档；它仍不等于真实 AMD XPM/xsim 或 T3 物理证据。

T2 归档校正：FIFO 矩阵已提交于 `ee3a351`，wrapper 交错/复位切片已提交于 `8457a20`；原有“工作树候选”文字只作提交前快照。

T2 wrapper 固定种子随机矩阵状态为 `T2_RANDOM_CLOCK_MATRIX_GREEN`：`--t2-random-matrix` 使用种子 `20260907` 生成 24 个唯一时钟/相位组合，并以 `2000 + 400 × NPU_HALF` 个 Host 周期作为随慢时钟增长的观察预算，最终输出 `REPRO_G2_T2_RANDOM_MATRIX_PASS`。该证据扩展了有限确定性矩阵，但仍不是数学穷举。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-12
provenance: Git HEAD `fe25a70`、已提交 Host/manifest 与文件树人工核对；未提交 status probe / 计数器 RTL 排除在签核源码身份之外

仓库分为八个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、XC7Z020 顶层适配、HelloZynq 阶段 2 实板验证、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 已签核。传统 NPU + ENeuron 的 V2 实现为 report head=`f744bff`：`2126 LUT / 1916 FF / 4 DSP48E1`，100 MHz OOC 通过；仍不得外推板级吞吐、动态功耗或部署性能。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

B2 物理状态最新校正（2026-09-10）：提交 `074ed56` 的 egress BRAM 预取构建已完成 route、bit/XSA 和 DRC，但 200 MHz setup 仍未达标（`WNS=-0.052 ns`、`TNS=-0.134 ns`、6 个失败端点，`WHS=+0.073 ns`、`THS=0`）；最差路径迁移到 `compute_unit_mask_latched_reg[3] -> compute_group_index_reg[1]`。bit/XSA 仅分析用途，B2-06 仍停在时序修复，B2-GATE 与 ENeuron A/B 均未开始。

B2 提交态物理基线（2026-09-11）：上述条目为历史失败记录。`97398bf` 构建在 `xc7z020clg484-2`、200 MHz 下通过 routed timing gate：`WNS=+0.012 ns`、`TNS=0`、`WHS=+0.036 ns`、`THS=0`，setup/hold 失败端点为 0，route/DRC hard error=0；post-route phys-opt 已执行，并已完成合法 packet smoke。当前工作树下载资格由下方 B2-08 状态块结果覆盖。

B2-08 状态块当前值（2026-09-11）：工作树 `88bec9e` 的 adapter 计数器、E2E testbench和 `b2_npu_status_probe.v` 已通过功能合同；状态块位于 `0x40430000`。错误响应候选统一锁存已移除 `cmd_hold_data -> rsp_payload_reg/CE` 和 `/R` 失败族；当前最差路径为 egress `mask_epoch_reg[1] -> payload_word_count_reg[7]/R`，另有 result 计数和 AXI DMA 内部轻微违例。200 MHz setup 仍未通过，尚未进入板级 runner；B2-GATE、B3、ENeuron A/B 保持未完成。

状态覆盖：OF4a 至 OF6 属于已签核 Python oracle 历史阶段；当前以 `TR1_TR6_APPROVED / TR7_TR12_APPROVED / TIMING_REPAIR_V2_FUNCTIONAL_GREEN / VIVADO_OOC_100MHZ_PASS / P15_T0_APPROVED / T1_RTL_AUTHORIZED / T1_PROTOCOL_SLICE_PROVEN / T1_FULL_PENDING / T2_VARIABLE_CLOCK_SLICE_GREEN / T2_CONCURRENT_EPOCH_SLICE_GREEN / T2_EXTENDED_CLOCK_SLICE_GREEN / T2_FIFO_MATRIX_SLICE_GREEN / T2_INTERLEAVE_RESET_SLICE_GREEN / T2_FINITE_CLOCK_MATRIX_GREEN / T2_RANDOM_CLOCK_MATRIX_GREEN / T2_FULL_MATRIX_PENDING / T3_XPM_XSIM_PASS / T3_XC7Z020_OOC_PASS / T3_SIGNOFF_PASS / RESOURCE_CUT_DEFERRED_UNTIL_FIRST_END_TO_END_RUN` 为准。P15-T0 方案 A 及 A1-A7 已获批准；T1-02 主要路径、T1-06 fence 独立切片与 T1-12 四 FIFO 边界已在本机 `e4d48dd` 通过，T1-09 已记录为当前 wrapper 的 `NA_FOR_T1_WRAPPER / OUTER_SHIM_PENDING`，T2 六组可变时钟、FIFO、交错/复位、16 组有限矩阵和 24 组固定种子随机矩阵已提交并通过；T1 全量、T2 更广泛并发交错、外层 shim、首次端到端运行仍待独立验收。T3 真实 AMD XPM/xsim 与 XC7Z020 OOC 已通过，详见上方报告路径。资源裁剪审查已完成，但所有裁剪实施推迟到第一次完整端到端运行成功之后。旧 Host Bridge OOC 的 `xc7a35tcpg236-1` 不得替代 P15 目标 `xc7z020clg400-1`。V2 已复用 signed 32-bit `mac_accumulator` 作为最终写回值，不新增 `writeback_value_latched`，并完成激活锁存、WRITEBACK、功能和 OOC 证明。

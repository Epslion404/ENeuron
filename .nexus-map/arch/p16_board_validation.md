# P16 项目阶段 2：实板验证路线

> generated_by: nexus-mapper v2 / manual synthesis
> verified_at: 2026-09-13
> provenance: Git checkout 身份以命令实时输出为准；板级签核仍绑定 RTL `be84596` 与对应 bit/XSA/ELF/manifest。旧 t0-state 工作区不是现状。

当前边界（中等精简）：实板部署目标为 `xc7z020clg484-2`，主线是板上 packet-NPU + ENeuron 动态剪枝。B3-MVP-GATE 已关闭；当前按 `B3-SPEED-GATE + B3-POWER-GATE → B3-GOAL-GATE` 收口。高地址 DDR、PHY、UDP 与完整 B2-GATE 保留为网口发布依赖；严格连接级 `2:4` 仍是独立 B3-08b/STRICT 实验，不前置到速度或功耗目标。

authoritative_sources: `docs/planning/TODO.md`、`task_plan.md`、`findings.md`、`progress.md`

当前工作流上下文（2026-09-13）：packet-NPU 在 `xc7z020clg484-2`、200 MHz 通过 routed timing 与实板数值检查，B3-MVP-GATE 已关闭。提交 `82b079e` 的 Host 缓存候选消除 512 次重复 L0 `group_mac`，新 ELF 三次实板保持正确并得到 `ps_us=827/829/828`；历史单次为 996。端到端加速仍未证明，外部功耗尚未测量；严格 `2:4` 继续作为独立结构实验。

计数器物理与实板状态（2026-09-12）：构建绑定 HEAD `c3a50eb`，最终 `WNS/TNS=+0.008/0 ns`、`WHS/THS=+0.036/0 ns`，route/DRC hard errors=0、DSP48E1=4；bit/XSA SHA-256 为 `5c6ebc07…c910a88`/`86288374…177a614`。后续 dense/full-open/bypass 实板均读回 execute/skip=`592/0`，static mixed 为 `296/296`，因此基础数值与组级静态门已关闭。

监听观察：2026-09-08 按 VID/PID 监听 COM10 10 秒（115200 8N1）读取 0 字节，未见 `ENEURON_B1B_BEGIN`/`ALIVE`/`PASS`；未下载 bitstream/ELF、未发送 GO，DDR access=0。该观察不改变 `B1-06B6_UART_BASELINE_PENDING`，也不是 DDR 失败证据。

B1-06B6 实板复测（2026-09-08）：运行目录为 `artifacts/logs/hellozynq_b1b/20260908T202605Z_df56180_b1-06b6_uart_no_marker`，构建 HEAD=`df561803fd44f791a38bda3be3422fe1f6411b77`。COM10（`VID_1A86:PID_7523`）监听 20 秒期间 FPGA program、ELF download、CPU run 均 PASS，但 UART terminal marker=`NO_TERMINAL_MARKER`，DDR accesses=0；状态仍为 `B1-06B6_UART_BASELINE_PENDING`，不构成 DDR 失败证据。两个 runner 的 PowerShell `$PID` 参数冲突已修复为 `$ProductId`：`boards/hellozynq/b1b_sw/run_b1b_board.ps1`、`boards/hellozynq/b1b_sw/run_b1b_high_diag_board.ps1`。

## 目标与当前入口

P16 的目标是在 HelloZynq `xc7z020clg484-2` 上依次打通 PL、PS/DDR/网口、DMA、`64→32→10` 传统 NPU、ENeuron 局部门控和网口端到端 A/B。阶段门只由同一身份链上的实板证据关闭；仿真和 OOC 可用于定位，但不能代替 bitstream、JTAG、UART、Host/网口日志与现场观察。

当前 B3 入口：基础 dense/bypass、full-open、Host 静态 `group_4way` 和 B3-09 live-ENeuron 实板均已关闭，B3-MVP-GATE 已通过。Host live L0 contribution 缓存候选也已完成三次同源实板诊断；下一步是冻结不含 UART 的重复端到端速度窗口，而不是继续把单样本 `ps_us` 外推为目标通过。严格连接级 `2:4` 仍是 B3-08b。

B3-08a 已完成（2026-09-12）：同一物理通过 bit/XSA、COM15、`b3_static_mixed` 实板 run `20260912T102046Z` 通过，logits=`74,-18,14,0,0,0,0,0,0,114`，fence valid=`1`，execute/skip=`296/296`。mask 粒度是 `group_4way`；B3-08b 属于后续 STRICT。

B3-09 实板已关闭（2026-09-12）：提交 `fe25a70`/`ab163fe`。COM15 UART `B3_LIVE_ENEURON_PASS` logits=`165,-18,14,0,0,0,0,0,0,153`；JTAG execute/skip=`296/296`、fence valid。证据 `artifacts/logs/b3_live_eneuron_pass_20260912_fe25a70/`。不是严格连接级 `2:4`。

P16-B0 已完成。当前源码 `f3b8174e8ca30d427e9de3eea2d36feb6a5e6a06`、bitstream `df16ed6ccd9124f2dc4391d96e868ebd7846aebf3df335099b742cc7cd318971` 在同一target/device上完成两次正式program和现场观察；10个完整周期分别实测 `13.42 s`、`13.4 s`，均通过理论 `13.4217728 s` 与冻结窗口 `12.6–14.2 s`。

用户随后确认板卡完全断电。`2026-09-07T15:02:49Z` 的正式只读探针精确匹配 target `localhost:3121/xilinx_tcf/Digilent/210251A08870` 1 个，但 `target_opened=0`、`accessible_device_count=0`，Vivado transcript 明确报告 `No devices detected`。证据位于 `artifacts/logs/hellozynq_b0/20260907T150221Z_df16ed6c_power_off/`，结果 SHA-256 为 `fe594c87...3776e`，transcript SHA-256 为 `3a953999...1f634`，完整断电确认 PASS。

重新上电后只读探针确认同一Digilent target上的唯一`xc7z020_1`恢复且下载前未配置；run-2于`2026-09-07T15:26:56Z`下载同一bitstream，三项DONE=`1/1/1`、错误位为0，现场10周期`13.4 s`。PR #69已合并为`main@102dee2...`，Fastlane V1已进入`main@308bdec...`，PR #72已合并为`main@065a68ce...`；当前正式UART硬件身份为`29edf6a...`，B1B软件身份为`97ddd1a...`。当前状态为`B0_COMPLETE / B1A_HW_DEFINITION_COMPLETE / B1B_UART_LOW_DDR_THREE_COLD_RUNS_PASS / B1B_HIGH_DDR_PENDING / FASTLANE_V1`。

B1A来源审计固定在板厂`73d529d8...`，其中L17/M17只描述板厂原始CH340布线。当前硬件定义按管理员批准和实板诊断将UART0冻结为V14 RX/V15 TX；干净提交`29edf6a...`的完整实现通过，因此B1A切片仍完成。DDR、PHY和RGMII既有边界不变；B1-GATE仍需B1B高地址边界与B1C实板证据。

B1B使用外置3.3V CH340，连接V14←TTL TX、V15→TTL RX并共地；V14/V15同时与板载HDMI并行RGB低位共网，B1B不得启用HDMI。`bare-metal + lwIP`路线已批准，裸机UART与低地址1 MiB DDR三次冷启动通过；`0x10000000`高地址异常尚未关闭，lwIP仍留到B1C。

高地址诊断状态：B1-06A合同已冻结，独立诊断ELF必须从低位OCM运行，代码、页表、堆和栈不得进入DDR，并预留OCM结果区。`dae5473` 干净构建已通过 `readelf -lW`/`nm -n` 门，生成与 manifest 绑定的 OCM 诊断 ELF，SHA-256=`3e0469265a1482081ce93188d905753b2fa998673a17e575776e115abfb76f01`，应用限制在`0x00000000–0x0002EFFF`，入口`0x00000000`、`runtime_end=0x0000D840`；该新 ELF 尚未上板。旧 `43ff54d`/ELF `706ceb09...a5698` 和 `main@436d1b2`/ELF `619ab70c...1b82` 仅作历史构建参考。先完成 B1-06B6 UART 基准，再在 B1-06B7 运行 `0x10000000` 附近稀疏地址探针与 4 KiB 单一固定模式读写；每次危险访问前预写 OCM 记录，UART、READY 或 GO 成功、失败或超时后都先保存 OCM 和 PC/SP/CPSR。当前仍为`B1B_HIGH_DDR_PENDING`，不得宣称整片DDR、B1B或B1-GATE通过。

run-1 机器归档由 `boards/hellozynq/b0_smoke/archive_b0_program_run.ps1` 生成。归档 manifest 绑定当前 bitstream `df16ed6c...8971`、program log SHA-256 `0152fe32...a49e`。`field_observation.json` 已更新为稳定闪烁、10周期 `13.42 s` 与 `status=PASS`，当前 SHA-256 为 `d93bcc25...ab083`。run-1已形成机器与现场闭环。

run-2归档位于 `artifacts/logs/hellozynq_b0/20260907T152656Z_df16ed6c_run2_machine/`，program log与现场观察SHA-256分别为 `1d4fada3...3613b`、`73c81d86...a25f8`，`observation_status=PASS`。双运行和完整断电证据已进入最终B0摘要。

## MVP、严格门与发布门

最终网口发布仍需完整 B1/B2 与 B4-RELEASE；B3-STRICT 是独立结构/长稳实验，不作为发布前置。相同 RTL/XDC/BD/Tcl/IP 身份不重复跑 Vivado；文档和纯 Host 改动不重建 PL。

- **B1：PS7、DDR、UART、PHY、最小 UDP。** 入口只接受主线上的 `B0-GATE=PASS`。先冻结 PS7/DDR/引脚和启动合同，再以 UART 冷启动、DDR 零错误、PHY/千兆链路、三档 UDP 和拔插恢复关闭本门；B1 不表示 NPU 已接入。
  - **B2：AXI DMA 与固定帧协议。** 低地址 packet-NPU 物理通过与合法路径 smoke 已足以支撑 B3-MVP。B2-GATE 继续覆盖完整错误、复位与发布账本，但不阻塞组级 live-ENeuron 开发实验，也不能用 MVP 结果反向宣称 B2-GATE 已通过。
  - **B2 观测器与背压收敛（2026-09-09）。** 官方双/单 `axi_stream_monitor:1.1` routed setup 实验均为历史失败（`WNS=-0.325 ns`、`WNS=-0.284 ns`），不进入正式物理基线。当前轻量 probe 配置为 `0x04030201`，首个输入后启动 phase，且在 `TVALID=1/TREADY=0` 时冻结 phase 以保持 VALID/payload；六个 B2 合同测试文件已扩展为 `51/51` 通过。最新正式 run `20260909T094406Z` 已取得 UART/JTAG PASS，pressure=10000/10000、backpressure=64/64、stall_cycles=83082、S2MM STALL=3；UART 恢复不等于 B2-GATE 关闭，连续回绕、错误/复位恢复和更完整逐帧 PL 观测仍待完成。
  - **B2 连续回绕切片（2026-09-09）。** 提交 `69ed289` 已实现并由正式 run `20260909T105109Z`（HEAD `f7f01b0`）在目标板验证：`256/256` 帧、`64/64` 个 64-byte slot、`rollovers=3`，首末地址 `TX 0x01006000→0x01006FC0`、`RX 0x01007000→0x01007FC0`；bit/XSA/ELF 已绑定 `ef974000…5175a`/`8419e00e…4185`/`dfe8088a…9082d0`。该切片为 `BOARD_PASS`，但 B2-03/B2-04/B2-05/B2-GATE 尚未整体关闭。
  - **B2 连续回绕切片（2026-09-09）。** 提交 `69ed289` 已实现并由正式 run `20260909T105109Z`（HEAD `f7f01b0`）在目标板验证：`256/256` 帧、`64/64` 个 64-byte slot、`rollovers=3`，首末地址 `TX 0x01006000→0x01006FC0`、`RX 0x01007000→0x01007FC0`；bit/XSA/ELF 已绑定 `ef974000…5175a`/`8419e00e…4185`/`dfe8088a…9082d0`。该切片为 `BOARD_PASS`，但 B2-03/B2-04/B2-05/B2-GATE 尚未整体关闭。
  - **B2 recovery 切片（2026-09-09）。** recovery run `20260909T110436Z`（HEAD `f7f01b0`）在目标板验证 `PASS_UART_JTAG_XSCT`：`jtag_recovery_status=2`，timeout/reset/passed/failed=`1/1/1/0`，sequence=`10329`、CRC32=`0xD3E3C978`；pressure=`10000/10000`、backpressure=`64/64`、stall=`83082`、连续回绕=`256/256`、mask lo/hi 均为 `0xFFFFFFFF`、rollovers=`3`。manifest SHA-256=`46833A…0922C`，recovery ELF SHA-256=`f2706099…e0363`。该切片为 `BOARD_PASS`，但 B2-GATE 仍未关闭；剩余缺口为更完整逐帧 PL 观测、间歇/ready 恢复覆盖和错误注入。
  - **B2 persistent DMA frame ledger 子门（2026-09-09）。** 提交 `5ff9088` 修复持久 ledger；实现前一 HEAD `76e06b6` 的正式 run `20260909T125200Z` 在 `xc7z020clg484-2`、COM10 实板取得 UART/JTAG/XSCT PASS，`ledger_pass=true`，8/8 边界记录完整并按 `64-byte` stride 读取。pressure=`10000/10000`、backpressure=`64/64`、stall=`83082`、wrap=`256/256`、recovery ready=`1→0→1`、gap=`2/2`；新 ELF SHA-256=`7fbcc85aa964a02e30d61f2e47e53e3f70e0e8421275852ba2e36963831d9f3e`，bit/XSA 沿用当时有效身份。该历史子门当时未覆盖 `packetizer/fence`；后续 packet-NPU smoke 与 B2-08 状态块功能集成已完成，但状态块 setup、板级读回、B2-GATE 和 ENeuron A/B 仍未完成。
- **B3-MVP-GATE：** 在现有 `group_4way` 上完成 live-ENeuron 决策、pending/fence epoch 原子性、最小状态和 dense/full-open/static/live 小集合周期 A/B。通过只允许声称组级动态剪枝正确性与局部周期差值。
- **B3-STRICT-GATE：** MVP 通过后，再补正式身份、严格连接级 `2:4`、非法 mask、完整错误/复位恢复和每模式至少 10000 样本。历史 `B3-GATE` 名称均指此严格门。
- **B4-RELEASE-GATE：** 完整 B2-GATE 通过后执行网口端到端重复 A/B，并补充网络负载差异；B3-STRICT 不前置。板级速度/功耗目标由 B3-SPEED/B3-POWER 关闭，B4 只在需要时复用仪器合同补测网口负载。历史 `B4-GATE` 名称均指此发布门。

只有 B4 的同一完整证据包证明“网口输入 → PS/DDR → DMA → 传统 NPU + ENeuron → 网口输出”并完成正确性和可重复 A/B，阶段 2 才能标记完成。

## 静态 mask 与 live-ENeuron 的事实边界

- `Host static mask`：Host 重放预先冻结的 mask，用于隔离验证 NPU 门控执行器、位序、epoch 和跳过计数。MVP 使用 `group_4way`，STRICT 才使用严格连接级 `2:4`；它始终不是神经元自动决策。
- `live-ENeuron`：实板运行中由 ENeuron 证据形成 mask，经 pending bank 与 fence 原子提交，并绑定决策证据、gain、epoch 和生效样本。MVP 先使用 `group_4way`，STRICT 再扩展为严格 `2:4`。
- B3、B4 的正确性、周期、执行/跳过组和性能统计必须将两种模式分开，不得合并或互相代证。

## 发布状态

PR #69最终HEAD `02514b5...` 已于 `2026-09-07T16:17:15Z` 合并，merge commit为 `102dee2...`。Actions已关闭，空 `statusCheckRollup`只表示未运行；B0合并依据是本机定向验证、Vivado/JTAG/现场证据及PR CLEAN/MERGEABLE。B1从该main提交启动。
  - **B2 missing-TLAST 切片（2026-09-09）。** run `20260909T133721Z`（HEAD `b2332a0`）在目标板验证 `B2_MISSING_TLAST_PASS / PASS_UART_JTAG_XSCT`：missing_tlast observed=`1`，dma_error/reset/recovered/failed=`1/1/1/0`，注入/恢复 sequence=`10332/10333`，MM2S/S2MM TLAST=`0/0`、beats=`16/16`，recovery sequence=`10329` 保持不变。manifest SHA-256=`F4D559…FE9B7`，ELF=`0abb11b0…e1ee3`，bit/XSA=`922b9cd6…0c64d`/`5b78919b…c2a9f`。该切片为 `B2_MISSING_TLAST_PASS`，但 B2-06/B2-08/B2-GATE 仍未完成。
- **B2-08 四流状态块子门（2026-09-11）。** 工作树 `88bec9e` 已把八个计数器和 256-bit fence 快照接入 `b2_npu_axis_top` 与 `0x40430000` 只读 AXI-Lite 状态块；状态块仿真、E2E/reset 和统一合同回归 `117 passed`。错误响应候选统一锁存后，`cmd_hold_data -> rsp_payload_reg/CE` 和 `/R` 均退出失败端点；setup 仍为 `WNS=-0.030 ns/TNS=-0.203 ns`，最差路径迁到 egress `mask_epoch -> payload_word_count/R`。因此尚无合法实板读回，不关闭 B2-08 总门、B2-GATE、B3 或 ENeuron A/B。
  - **B2 packet-NPU 适配器切片（2026-09-09）。** `cb9eb66` 的 `b2_npu_packet_adapter.sv` 与 `62f2d8b` 的 packetized sample/result 场景分别通过 `B2_NPU_PACKET_ADAPTER_PASS`（4/4）和 `B2_NPU_PACKET_ADAPTER_E2E_PASS`（3/3）；`ea35d74`/`1d0e3ba` 新增并固定 `boards/hellozynq/b2_hw/b2_npu_axis_top.v` 及 BD Verilog reference。当前仍为 RTL 合同证据；现有 Vivado build 产物绑定旧 `b2332a0`，新顶层尚未完成 `xc7z020clg484-2` 重建、routed timing/DRC 或实板验证。
  - **B2 packet-NPU 物理收敛（2026-09-10）。** 提交 `2f2ce03` 的 Vivado 2024.1 完整构建在 `xc7z020clg484-2` 上完成 route 并生成 bit/XSA，route errors=`0`、DRC hard errors=`0`；200 MHz setup 仍失败但已收敛至 `WNS=-0.279 ns`、`TNS=-8.283 ns`、`141` 个失败端点，hold=`WHS=+0.036 ns`、`THS=0`。最差路径为 `output_index_reg[3]/C -> response_mem/ENARDEN`。证据归档于 `artifacts/logs/b2_packet_npu_route_timing_fail_20260910_2f2ce03/`；bit/XSA 为 `analysis_only_no_download`，不得上板或宣称 packet-NPU 物理门通过。
  - **B2 packet-NPU egress 预取重建（2026-09-10）。** 提交 `074ed56` 的 Vivado 2024.1 完整构建已完成 route 并生成 bit/XSA，route errors=`0`、DRC hard errors=`0`；200 MHz setup 为 `WNS=-0.052 ns`、`TNS=-0.134 ns`、6 个失败端点，hold=`WHS=+0.073 ns`、`THS=0`。最差路径为 `compute_unit_mask_latched_reg[3]/C -> compute_group_index_reg[1]/D`。证据归档于 `artifacts/logs/b2_packet_npu_route_timing_fail_20260910_074ed56/`；bit/XSA 为 `analysis_only_no_download`，不得上板或宣称 packet-NPU 物理门通过。

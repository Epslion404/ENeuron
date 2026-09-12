# P16 项目阶段 2：实板验证路线


verified_at: 2026-09-12

当前边界（中等精简）：实板部署目标为 `xc7z020clg484-2`，NPU + ENeuron 动态剪枝是活动主线。高地址 DDR、PHY、UDP 只属于板卡资格支线，仍用于关闭完整 `B1-GATE`，不阻塞低地址容量满足条件下的 NPU MVP。外置 CH340 由 `VID_1A86:PID_7523` 识别，COM 编号不是稳定契约；旧 `clg400-1` NP7/T3 物理结果和 `archive/legacy/` 材料均不参与日常门。

authoritative_sources: `docs/planning/TODO.md`、`task_plan.md`、`findings.md`、`progress.md`

当前工作流上下文（2026-09-12）：活动分支为 `codex/b1b-high-ddr-board-repro`，当前仓库 HEAD=`f070577`。packet-NPU 在 `xc7z020clg484-2`、200 MHz routed timing 通过（`WNS=+0.005 ns/TNS=0/WHS=+0.034 ns/THS=0`，route/DRC hard errors=0、`B2_SIGNOFF_PASS=1`）。实板 run `20260912T040206Z`（COM15）完成合法 packet smoke，随后 `0x40430000` 状态块读回 command/sample/response/result=`658/658`、`8/8`、`1/1`、`10 beats/1 packet`，fence snapshot valid；dense `20260912T050553Z`、bypass `20260912T053341Z`、full-open `20260912T053426Z` 三次固定向量输出均一致。B2 状态为 `BOARD_STATUS_PARTIAL`；执行/跳过组计数器物理核对、B3-06/B3-07 整项、静态 `2:4`、live-ENeuron、恢复矩阵及 B2-06～B2-10/B2-GATE 仍未完成。

计数器物理重建状态（2026-09-12）：第三次 `route_design -directive Explore` 加 post-route `AggressiveExplore` 的构建绑定 HEAD `c3a50eb`，最终 `WNS/TNS=+0.008/0 ns`、`WHS/THS=+0.036/0 ns`，setup/hold 失败端点为 0，route/DRC hard errors=0，DSP48E1=4；bit/XSA SHA-256 为 `5c6ebc07…c910a88`/`86288374…177a614`，具备下载资格。尚未完成实板 execute/skip 读回，dense 期望 `592/0`，所以 B3-06/B3-07 仍保持未完成。

监听观察：2026-09-08 按 VID/PID 监听 COM10 10 秒（115200 8N1）读取 0 字节，未见 `ENEURON_B1B_BEGIN`/`ALIVE`/`PASS`；未下载 bitstream/ELF、未发送 GO，DDR access=0。该观察不改变 `B1-06B6_UART_BASELINE_PENDING`，也不是 DDR 失败证据。

B1-06B6 实板复测（2026-09-08）：运行目录为 `artifacts/logs/hellozynq_b1b/20260908T202605Z_df56180_b1-06b6_uart_no_marker`，构建 HEAD=`df561803fd44f791a38bda3be3422fe1f6411b77`。COM10（`VID_1A86:PID_7523`）监听 20 秒期间 FPGA program、ELF download、CPU run 均 PASS，但 UART terminal marker=`NO_TERMINAL_MARKER`，DDR accesses=0；状态仍为 `B1-06B6_UART_BASELINE_PENDING`，不构成 DDR 失败证据。两个 runner 的 PowerShell `$PID` 参数冲突已修复为 `$ProductId`：`boards/hellozynq/b1b_sw/run_b1b_board.ps1`、`boards/hellozynq/b1b_sw/run_b1b_high_diag_board.ps1`。

## 目标与当前入口

P16 的目标是在 HelloZynq `xc7z020clg484-2` 上依次打通 PL、PS/DDR/网口、DMA、`64→32→10` 传统 NPU、ENeuron 局部门控和网口端到端 A/B。阶段门只由同一身份链上的实板证据关闭；仿真和 OOC 可用于定位，但不能代替 bitstream、JTAG、UART、Host/网口日志与现场观察。

当前 B3 入口：使用已通过物理门的 packet-NPU 身份冻结 Python/Host 共用黄金 manifest，先做 dense/bypass 逐样本 10-logit bit-exact 对比，再做 full-open mask 透明性对比；只有这两个基础门通过后，才进入静态 2:4 与 live-ENeuron 动态 mask A/B。packet smoke 只证明协议与状态路径，不证明 NPU 数值正确。

P16-B0 已完成。当前源码 `f3b8174e8ca30d427e9de3eea2d36feb6a5e6a06`、bitstream `df16ed6ccd9124f2dc4391d96e868ebd7846aebf3df335099b742cc7cd318971` 在同一target/device上完成两次正式program和现场观察；10个完整周期分别实测 `13.42 s`、`13.4 s`，均通过理论 `13.4217728 s` 与冻结窗口 `12.6–14.2 s`。

用户随后确认板卡完全断电。`2026-09-07T15:02:49Z` 的正式只读探针精确匹配 target `localhost:3121/xilinx_tcf/Digilent/210251A08870` 1 个，但 `target_opened=0`、`accessible_device_count=0`，Vivado transcript 明确报告 `No devices detected`。证据位于 `artifacts/logs/hellozynq_b0/20260907T150221Z_df16ed6c_power_off/`，结果 SHA-256 为 `fe594c87...3776e`，transcript SHA-256 为 `3a953999...1f634`，完整断电确认 PASS。

重新上电后只读探针确认同一Digilent target上的唯一`xc7z020_1`恢复且下载前未配置；run-2于`2026-09-07T15:26:56Z`下载同一bitstream，三项DONE=`1/1/1`、错误位为0，现场10周期`13.4 s`。PR #69已合并为`main@102dee2...`，Fastlane V1已进入`main@308bdec...`，PR #72已合并为`main@065a68ce...`；当前正式UART硬件身份为`29edf6a...`，B1B软件身份为`97ddd1a...`。当前状态为`B0_COMPLETE / B1A_HW_DEFINITION_COMPLETE / B1B_UART_LOW_DDR_THREE_COLD_RUNS_PASS / B1B_HIGH_DDR_PENDING / FASTLANE_V1`。

B1A来源审计固定在板厂`73d529d8...`，其中L17/M17只描述板厂原始CH340布线。当前硬件定义按管理员批准和实板诊断将UART0冻结为V14 RX/V15 TX；干净提交`29edf6a...`的完整实现通过，因此B1A切片仍完成。DDR、PHY和RGMII既有边界不变；B1-GATE仍需B1B高地址边界与B1C实板证据。

B1B使用外置3.3V CH340，连接V14←TTL TX、V15→TTL RX并共地；V14/V15同时与板载HDMI并行RGB低位共网，B1B不得启用HDMI。`bare-metal + lwIP`路线已批准，裸机UART与低地址1 MiB DDR三次冷启动通过；`0x10000000`高地址异常尚未关闭，lwIP仍留到B1C。

高地址诊断状态：B1-06A合同已冻结，独立诊断ELF必须从低位OCM运行，代码、页表、堆和栈不得进入DDR，并预留OCM结果区。`dae5473` 干净构建已通过 `readelf -lW`/`nm -n` 门，生成与 manifest 绑定的 OCM 诊断 ELF，SHA-256=`3e0469265a1482081ce93188d905753b2fa998673a17e575776e115abfb76f01`，应用限制在`0x00000000–0x0002EFFF`，入口`0x00000000`、`runtime_end=0x0000D840`；该新 ELF 尚未上板。旧 `43ff54d`/ELF `706ceb09...a5698` 和 `main@436d1b2`/ELF `619ab70c...1b82` 仅作历史构建参考。先完成 B1-06B6 UART 基准，再在 B1-06B7 运行 `0x10000000` 附近稀疏地址探针与 4 KiB 单一固定模式读写；每次危险访问前预写 OCM 记录，UART、READY 或 GO 成功、失败或超时后都先保存 OCM 和 PC/SP/CPSR。当前仍为`B1B_HIGH_DDR_PENDING`，不得宣称整片DDR、B1B或B1-GATE通过。

run-1 机器归档由 `boards/hellozynq/b0_smoke/archive_b0_program_run.ps1` 生成。归档 manifest 绑定当前 bitstream `df16ed6c...8971`、program log SHA-256 `0152fe32...a49e`。`field_observation.json` 已更新为稳定闪烁、10周期 `13.42 s` 与 `status=PASS`，当前 SHA-256 为 `d93bcc25...ab083`。run-1已形成机器与现场闭环。

run-2归档位于 `artifacts/logs/hellozynq_b0/20260907T152656Z_df16ed6c_run2_machine/`，program log与现场观察SHA-256分别为 `1d4fada3...3613b`、`73c81d86...a25f8`，`observation_status=PASS`。双运行和完整断电证据已进入最终B0摘要。

## B1–B4 串行门

最终阶段门仍按B1→B2→B3→B4串行；实现进入主线采用Fastlane V1。B1拆为B1A板级事实/可重建硬件定义、B1B PS7/UART/DDR、B1C PHY/UDP，每段定向验证后即可合并，但只有B1C最终摘要满足全部条件才标记B1-GATE通过。相同RTL/XDC/BD/Tcl/IP身份不重复跑Vivado，软件和文档修改只跑受影响门。

- **B1：PS7、DDR、UART、PHY、最小 UDP。** 入口只接受主线上的 `B0-GATE=PASS`。先冻结 PS7/DDR/引脚和启动合同，再以 UART 冷启动、DDR 零错误、PHY/千兆链路、三档 UDP 和拔插恢复关闭本门；B1 不表示 NPU 已接入。
  - **B2：AXI DMA 与固定帧协议。** 低地址 B2-MVP 可在 `B1A=PASS + B1B低地址1 MiB三次冷启动=PASS` 且布局合同冻结后先行；完整网络化 B2 仍受 `B1-GATE=PASS` 约束。正式 run `20260909T094406Z` 绑定 HEAD `55822ae`、bit/XSA=`ef974000…5175a`/`8419e00e…4185`、ELF=`f6fe12ea…e421f`，UART/JTAG/XSCT/probe 均 PASS；pressure=10000/10000、backpressure=64/64、stall_cycles=83082、S2MM probe STALL=3，边界为 `7 PASS + 1 zero-length reject + 0 fail`。B2-03/B2-05/B2-GATE 仍未关闭，通过前不接入 B3 或报告剪枝加速。
  - **B2 观测器与背压收敛（2026-09-09）。** 官方双/单 `axi_stream_monitor:1.1` routed setup 实验均为历史失败（`WNS=-0.325 ns`、`WNS=-0.284 ns`），不进入正式物理基线。当前轻量 probe 配置为 `0x04030201`，首个输入后启动 phase，且在 `TVALID=1/TREADY=0` 时冻结 phase 以保持 VALID/payload；六个 B2 合同测试文件已扩展为 `51/51` 通过。最新正式 run `20260909T094406Z` 已取得 UART/JTAG PASS，pressure=10000/10000、backpressure=64/64、stall_cycles=83082、S2MM STALL=3；UART 恢复不等于 B2-GATE 关闭，连续回绕、错误/复位恢复和更完整逐帧 PL 观测仍待完成。
  - **B2 连续回绕切片（2026-09-09）。** 提交 `69ed289` 已实现并由正式 run `20260909T105109Z`（HEAD `f7f01b0`）在目标板验证：`256/256` 帧、`64/64` 个 64-byte slot、`rollovers=3`，首末地址 `TX 0x01006000→0x01006FC0`、`RX 0x01007000→0x01007FC0`；bit/XSA/ELF 已绑定 `ef974000…5175a`/`8419e00e…4185`/`dfe8088a…9082d0`。该切片为 `BOARD_PASS`，但 B2-03/B2-04/B2-05/B2-GATE 尚未整体关闭。
  - **B2 连续回绕切片（2026-09-09）。** 提交 `69ed289` 已实现并由正式 run `20260909T105109Z`（HEAD `f7f01b0`）在目标板验证：`256/256` 帧、`64/64` 个 64-byte slot、`rollovers=3`，首末地址 `TX 0x01006000→0x01006FC0`、`RX 0x01007000→0x01007FC0`；bit/XSA/ELF 已绑定 `ef974000…5175a`/`8419e00e…4185`/`dfe8088a…9082d0`。该切片为 `BOARD_PASS`，但 B2-03/B2-04/B2-05/B2-GATE 尚未整体关闭。
  - **B2 recovery 切片（2026-09-09）。** recovery run `20260909T110436Z`（HEAD `f7f01b0`）在目标板验证 `PASS_UART_JTAG_XSCT`：`jtag_recovery_status=2`，timeout/reset/passed/failed=`1/1/1/0`，sequence=`10329`、CRC32=`0xD3E3C978`；pressure=`10000/10000`、backpressure=`64/64`、stall=`83082`、连续回绕=`256/256`、mask lo/hi 均为 `0xFFFFFFFF`、rollovers=`3`。manifest SHA-256=`46833A…0922C`，recovery ELF SHA-256=`f2706099…e0363`。该切片为 `BOARD_PASS`，但 B2-GATE 仍未关闭；剩余缺口为更完整逐帧 PL 观测、间歇/ready 恢复覆盖和错误注入。
  - **B2 persistent DMA frame ledger 子门（2026-09-09）。** 提交 `5ff9088` 修复持久 ledger；实现前一 HEAD `76e06b6` 的正式 run `20260909T125200Z` 在 `xc7z020clg484-2`、COM10 实板取得 UART/JTAG/XSCT PASS，`ledger_pass=true`，8/8 边界记录完整并按 `64-byte` stride 读取。pressure=`10000/10000`、backpressure=`64/64`、stall=`83082`、wrap=`256/256`、recovery ready=`1→0→1`、gap=`2/2`；新 ELF SHA-256=`7fbcc85aa964a02e30d61f2e47e53e3f70e0e8421275852ba2e36963831d9f3e`，bit/XSA 沿用当时有效身份。该历史子门当时未覆盖 `packetizer/fence`；后续 packet-NPU smoke 与 B2-08 状态块功能集成已完成，但状态块 setup、板级读回、B2-GATE 和 ENeuron A/B 仍未完成。
- **B3：传统 NPU + ENeuron 固定向量。** 入口只接受 `B2-GATE=PASS`。保持 `64→32→10`、634 model words、8-beat sample、10-beat result 和四 DSP 合同，依次验证 dense、full-open、Host 静态 `2:4`、live-ENeuron，并覆盖 epoch 原子性、背压与复位恢复。
- **B4：网口端到端 A/B。** 入口只接受 `B3-GATE=PASS`。固定同一 bitstream、ELF、模型、样本、时钟和网络条件，对四种模式执行可重复 A/B；正确性先于性能，端到端结果必须拆分网口、软件、DMA、排队和 NPU 计算开销。没有合格外部测量链时写 `POWER_NOT_MEASURED`。

只有 B4 的同一完整证据包证明“网口输入 → PS/DDR → DMA → 传统 NPU + ENeuron → 网口输出”并完成正确性和可重复 A/B，阶段 2 才能标记完成。

## 静态 mask 与 live-ENeuron 的事实边界

- `Host static 2:4 mask`：Host 重放预先冻结的合法 mask，用于隔离验证 NPU 门控执行器、位序、epoch 和跳过计数。它不是神经元自动决策。
- `live-ENeuron`：实板运行中由 ENeuron 证据形成组内候选和严格 `2:4` mask，经 pending bank 与 fence 原子提交，并能绑定决策证据、gain、epoch 和生效样本。只有该路径通过，才可声称“神经元参与局部自动剪枝”。
- B3、B4 的正确性、周期、执行/跳过组和性能统计必须将两种模式分开，不得合并或互相代证。

## 发布状态

PR #69最终HEAD `02514b5...` 已于 `2026-09-07T16:17:15Z` 合并，merge commit为 `102dee2...`。Actions已关闭，空 `statusCheckRollup`只表示未运行；B0合并依据是本机定向验证、Vivado/JTAG/现场证据及PR CLEAN/MERGEABLE。B1从该main提交启动。
  - **B2 missing-TLAST 切片（2026-09-09）。** run `20260909T133721Z`（HEAD `b2332a0`）在目标板验证 `B2_MISSING_TLAST_PASS / PASS_UART_JTAG_XSCT`：missing_tlast observed=`1`，dma_error/reset/recovered/failed=`1/1/1/0`，注入/恢复 sequence=`10332/10333`，MM2S/S2MM TLAST=`0/0`、beats=`16/16`，recovery sequence=`10329` 保持不变。manifest SHA-256=`F4D559…FE9B7`，ELF=`0abb11b0…e1ee3`，bit/XSA=`922b9cd6…0c64d`/`5b78919b…c2a9f`。该切片为 `B2_MISSING_TLAST_PASS`，但 B2-06/B2-08/B2-GATE 仍未完成。
- **B2-08 四流状态块子门（2026-09-11）。** 工作树 `88bec9e` 已把八个计数器和 256-bit fence 快照接入 `b2_npu_axis_top` 与 `0x40430000` 只读 AXI-Lite 状态块；状态块仿真、E2E/reset 和统一合同回归 `117 passed`。错误响应候选统一锁存后，`cmd_hold_data -> rsp_payload_reg/CE` 和 `/R` 均退出失败端点；setup 仍为 `WNS=-0.030 ns/TNS=-0.203 ns`，最差路径迁到 egress `mask_epoch -> payload_word_count/R`。因此尚无合法实板读回，不关闭 B2-08 总门、B2-GATE、B3 或 ENeuron A/B。
  - **B2 packet-NPU 适配器切片（2026-09-09）。** `cb9eb66` 的 `b2_npu_packet_adapter.sv` 与 `62f2d8b` 的 packetized sample/result 场景分别通过 `B2_NPU_PACKET_ADAPTER_PASS`（4/4）和 `B2_NPU_PACKET_ADAPTER_E2E_PASS`（3/3）；`ea35d74`/`1d0e3ba` 新增并固定 `boards/hellozynq/b2_hw/b2_npu_axis_top.v` 及 BD Verilog reference。当前仍为 RTL 合同证据；现有 Vivado build 产物绑定旧 `b2332a0`，新顶层尚未完成 `xc7z020clg484-2` 重建、routed timing/DRC 或实板验证。
  - **B2 packet-NPU 物理收敛（2026-09-10）。** 提交 `2f2ce03` 的 Vivado 2024.1 完整构建在 `xc7z020clg484-2` 上完成 route 并生成 bit/XSA，route errors=`0`、DRC hard errors=`0`；200 MHz setup 仍失败但已收敛至 `WNS=-0.279 ns`、`TNS=-8.283 ns`、`141` 个失败端点，hold=`WHS=+0.036 ns`、`THS=0`。最差路径为 `output_index_reg[3]/C -> response_mem/ENARDEN`。证据归档于 `artifacts/logs/b2_packet_npu_route_timing_fail_20260910_2f2ce03/`；bit/XSA 为 `analysis_only_no_download`，不得上板或宣称 packet-NPU 物理门通过。
  - **B2 packet-NPU egress 预取重建（2026-09-10）。** 提交 `074ed56` 的 Vivado 2024.1 完整构建已完成 route 并生成 bit/XSA，route errors=`0`、DRC hard errors=`0`；200 MHz setup 为 `WNS=-0.052 ns`、`TNS=-0.134 ns`、6 个失败端点，hold=`WHS=+0.073 ns`、`THS=0`。最差路径为 `compute_unit_mask_latched_reg[3]/C -> compute_group_index_reg[1]/D`。证据归档于 `artifacts/logs/b2_packet_npu_route_timing_fail_20260910_074ed56/`；bit/XSA 为 `analysis_only_no_download`，不得上板或宣称 packet-NPU 物理门通过。

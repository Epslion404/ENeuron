# ENeuron 知识库入口

> generated_by: nexus-mapper v2 / manual synthesis
> verified_at: 2026-09-13
> provenance: live tree=`D:/Documents/Code/ENeuron-board-b0`；Git checkout 身份以 `git branch --show-current` 与 `git rev-parse HEAD` 的实时输出为准，历史分支/PR 名称仅作来源。bitstream RTL 身份 `be84596`。`D:/Documents/Code/ENeuron` 不是当前 live tree。raw 探针仍绑定历史 `c46320e`。SPEED 证据 `artifacts/logs/b3_speed_20260912_be84596/b3_speed_comparison.json`。

## 当前权威快照（2026-09-13，日常主线 B3-SPEED-GATE / B3-POWER-GATE）

器件 `xc7z020clg484-2`。日常主线是 `B3-SPEED-GATE`（端到端速度）与 `B3-POWER-GATE`（外部功耗目标），不是 B3-08b，也不是 `B3-STRICT`。主线仍是板上 packet-NPU + ENeuron 组级动态剪枝。live tree 是本工作树，不是 `D:/Documents/Code/ENeuron`。

B3-MVP-GATE 已在同一份集中 Vivado 2024.1 bitstream 上关闭：RTL 身份 `be84596`，200 MHz FCLK0。WNS=+0.045 ns，TNS=0，WHS=+0.036 ns，THS=0，route/DRC hard errors=0，DSP48E1=4。
- bit SHA-256=`0ecbe76274c39418f2a60a88358d3ff6f09f5a2ed73a44a3a419c34eb91d3a11`
- XSA SHA-256=`135d979d61c629922ee5419e51dd97ef045d9bab79930432816d09f109291d1a`

冻结 AXI-Lite 状态块 `0x40430000`：0x00-0x4C 不变；0x50 runtime_status；0x54/0x58 active/pending mask epoch；0x5C last NPU compute cycles；0x60 protocol errors。pending epoch 来自 `mask_state==MASK_PUBLISHED`，不是 `mask_valid`。

板卡 COM15 CH340 `VID_1A86:PID_7523`。B3-11 hold：MASK_COMMIT 后、下一样本前 `active=0 pending=1`；样本后 `active=1 pending=0`。

四模式 A/B 两轮一致：dense/full-open 592/0 组、2494 cycles、logits 165,-18,14,0,0,0,0,0,0,153；static mixed 296/296、1606 cycles、logits 74,-18,...,114、`decision_source=host_replay_static_mixed`；live-ENeuron 296/296、1606 cycles、logits 与 dense 相同、`decision_source=live_eneuron_s2`。

`B3-SPEED-MEASURED` 已完成单样本诊断。同源 bit `be84596` / SHA `0ecbe762…3a11`、COM15：dense/full-open 2494 cycles、PS 7 µs、DMA ~60 µs、UART ~66–77 ms；static 1606 cycles、DMA 56 µs、UART 63 ms；live 1606 cycles、PS 996 µs、DMA 56 µs。DMA 包含 NPU，UART 又包住整个流程，字段不可相加；当前为 `B3-SPEED-GATE=OPEN / END_TO_END_ACCELERATION_NOT_PROVEN`。证据：`artifacts/logs/b3_speed_20260912_be84596/b3_speed_comparison.json`。

只可声称：`group_4way` 动态剪枝正确性 + 局部 NPU 周期差值 888 cycles。禁止：把 888 当端到端加速、把 Vivado 功耗当板上功耗、把 19-word 当连接级 `2:4`。不可声称网口加速、测得功耗、B2-GATE。MVP 证据：`artifacts/logs/b3_mvp_20260912_be84596/`。

当前门：`B3-SPEED-GATE=OPEN`、`B3-POWER-MEASURED=OPEN`、`B3-POWER-GATE=OPEN`、`B3-GOAL-GATE=OPEN`。历史 Host live 决策约 996 µs；当前候选以 16 项局部缓存消除 512 次重复 L0 `group_mac`，但仍保留 mask 所需 dense L0 扫描，新 ELF/实板 `ps_us` 尚待复测。POWER 为 `POWER_NOT_MEASURED`（本机无外部功耗仪；合同 `tools/repro/b3_power_instrument_contract.json`）；完成测量也不能在未冻结并满足改善门限时自动关闭目标门。严格 2:4 是结构实验。

## 当前活动范围

主线固定 `xc7z020clg484-2`：NPU 单时钟、ENeuron 组级动态剪枝、NP7 共享 lane，以及 B1/B2/B3/B4 集成。活动入口：`npu_eneuron_*`、`npu_zynq7020_t1_wrapper.sv`、`local_prune_*`、`eneuron_group4way_live.py`、`np7_*`、`b2_npu_status_probe.v`。CH340 按 VID/PID 识别；双设备时必须显式 COM15。合同：`docs/planning/NPU_ZYNQ7020_BOARD_VALIDATION_PHASE2_V1.md`。状态串：`FUNCTIONAL_PASS / PHYSICAL_PASS / B3_MVP_GATE_PASS / B3_SPEED_MEASURED / B3_SPEED_GATE_OPEN / B3_POWER_NOT_MEASURED / B3_POWER_GATE_OPEN / B3_GOAL_GATE_OPEN / B3_STRICT_DEFERRED_STRUCTURAL / B2_GATE_PENDING`。

pytest 日常主线收集边界由根目录 `pytest.ini` 冻结：递归排除 `archive/`、`.planning/`、Git/Xilinx/pytest 缓存目录，并忽略仍依赖归档前相对路径的根级 legacy 测试；历史文件保留，但不参与当前 ZYNQ7020 日常门。边界合同由 `test_pytest_scope_contract.py` 检查；完整 B2 编排入口为 `run_b2_checks.ps1 -Full`。

## 主要系统

- live-ENeuron Host：`eneuron_group4way_live.py`、`packet_main.c`（`B3_LIVE_ENEURON`）
- 单时钟 NPU：`npu_eneuron_single_clock_skeleton.sv`、`npu_zynq7020_t1_wrapper.sv`
- packet 与状态块：`b2_npu_packet_adapter.sv`、`b2_npu_status_probe.v`（`0x40430000`）
- 剪枝 / NP7：`local_prune_gate_2of4.sv`、`np7_shared_synapse_lane.sv`
- 实板：`boards/hellozynq/`；规划：`WORKFLOW_STATE.md`、`docs/CURRENT_STATUS.md`

## 必读路由

- `.nexus-map/arch/systems.md`
- `.nexus-map/arch/dependencies.md`
- `.nexus-map/arch/test_coverage.md`
- `.nexus-map/hotspots/git_forensics.md`
- `.nexus-map/concepts/domains.md`

## [操作指南] 强制执行步骤

> 本节是对所有读取本文件的 AI 发出的硬性操作指令，不是建议。

### 步骤1 — 必须先读完以下所有文件（顺序不限）

- `.nexus-map/arch/systems.md`
- `.nexus-map/arch/dependencies.md`
- `.nexus-map/arch/test_coverage.md`
- `.nexus-map/hotspots/git_forensics.md`
- `.nexus-map/concepts/domains.md`

### 步骤2 — 按任务类型追加操作

- 接口修改、新增跨模块调用、删除或重命名公共函数：运行 `query_graph.py --impact <目标文件>`。
- 判断某文件被谁引用：运行 `query_graph.py --who-imports <模块名>`。
- 仓库结构发生重大变化：任务完成后更新 Nexus 知识库。本轮仅外科更新，不做全仓 remap。

## 当前活动范围（中等精简）

主线固定为 `xc7z020clg484-2`：NPU 单时钟计算、ENeuron 动态剪枝、NP7 共享 lane，以及 B1/B2/B3/B4 集成。活动入口见 `npu_eneuron_*`、`npu_zynq7020_t1_wrapper.sv`、`local_prune_*`、`eneuron_local_prune_wrapper.sv`、`digital_lif_engine.sv`、`eneuron_group4way_live.py` 和 `np7_*`。绑定旧 `xc7z020clg400-1` 的 OOC 只能作结构参考，不能替代目标器件最终 routed 证据。

`archive/legacy/` 下的 Pulse-Mini、digit8x8、G4、旧 Tile/Host Bridge、NP6/NP7 旧物理报告和普通历史结果不参与当前日常门。高地址 DDR 与 B1C UDP 保留为板卡资格支线；低地址窗口满足模型/DMA 容量后即可推进 NPU MVP。MVP 已关闭；当前并行推进 `B3-SPEED-GATE` 与 `B3-POWER-MEASURED/B3-POWER-GATE`，两者都通过后才关闭 `B3-GOAL-GATE`。严格连接级 `2:4`、10000 样本和完整恢复属于独立的 STRUCTURAL/STRICT 实验；网口发布属于 B4，不前置到 B3 速度/功耗目标门。

证据边界：当前部署和最终板级物理签核目标是 `xc7z020clg484-2`。`xc7z020clg400-1` 上的 T3/NP7 OOC、时序和资源报告只作为历史结构参考，不得写成 `clg484-2` 已签核；`archive/legacy/` 中的材料不进入日常 CI/PR 门。B1 高地址 DDR、PHY 和 UDP 属于板卡资格支线，仍阻塞完整 `B1-GATE`，但在已验证低地址窗口足以容纳模型与 DMA 缓冲区时，不阻塞 NPU MVP 的 RTL/软件推进。CH340 运行脚本按 `VID_1A86:PID_7523` 识别设备，COM 号只是现场枚举结果，不是固定合同。

合同与恢复口径（2026-09-13）：`WORKFLOW_STATE.md` 指定 `docs/planning/NPU_ZYNQ7020_BOARD_VALIDATION_PHASE2_V1.md` 为当前阶段合同；中等精简后的主线 TODO 仅统计 `docs/planning/TODO.md` 的 P16，当前活动计数以脚本实时输出为准。`P16-E` 公共证据合同与 `P16-S` 统一停止条件是持续适用的常驻合同，不计入一次性计数；`NP8` 为 `DEFERRED_OPTIONAL`，`NP9` 已并入 P16 的 B2/B3/B4。B3-MVP-GATE 已关闭；当前门是 `B3-SPEED-GATE` 与 `B3-POWER-MEASURED/B3-POWER-GATE`，最终汇入 `B3-GOAL-GATE`。B2-GATE 仍是网口发布门；B3-STRICT 是独立结构实验，不阻塞当前速度/功耗目标。

状态更正（2026-09-10）：上方为当前权威状态；本文件后续 2026-09-09 历史段落中若仍写“B2-03/B2-04/B2-05 未关闭”，均由后续正式边界、压力、背压、回绕、恢复、间歇和 missing-TLAST 证据 supersede。当前待关闭项仅为 B2-06/B2-07/B2-08/B2-09/B2-10 与 B2-GATE；BRAM 探针已由 `f4827e2` 提交，命令 FIFO 保持槽时序切片已由 `195e6e7` 提交，但尚未以该 RTL 重跑完整 Vivado。

TODO 计数更正：`workflow_resume.ps1 -Mode Check` 于 2026-09-11 在 HEAD `97398bf` 上报告 `TODO.md:P16=59`；本文其余 `63` 计数均为历史快照。

B2 packet-NPU 提交态物理基线（2026-09-11）：完整 Vivado 2024.1 构建绑定源 HEAD=`97398bf`，目标器件为 `xc7z020clg484-2`；200 MHz routed timing 全绿（`WNS=+0.012 ns`、`TNS=0`、`WHS=+0.036 ns`、`THS=0`），setup/hold 失败端点为 0，route errors=`0`、DRC hard errors=`0`。post-route `phys_opt_design -directive AggressiveExplore` 已在日志确认执行；该身份已完成合法 packet smoke。当前下载资格由下方 B2-08 工作树覆盖决定。

B2-08 与 packet-NPU 当前实板状态（2026-09-12）：HEAD `88bec9e` 在 `xc7z020clg484-2`、200 MHz 通过 routed timing（`WNS=+0.005 ns`、`TNS=0`、`WHS=+0.034 ns`、`THS=0`，route/DRC hard errors=0），bit SHA-256=`782a977c…d93b6e`、XSA SHA-256=`5e6a31bd…15ef7`。`20260912T040206Z` 在 COM15 完成 FPGA/ELF/UART/JTAG/XSCT PASS，验证 634 model words、19 mask words、fence、8-beat sample 和 10-beat result；随后 `0x40430000` 读回 command/sample/response/result=`658/658`、`8/8`、`1/1`、`10 beats/1 packet`，fence snapshot valid。该结果是合法 packet path 和状态可见性的部分实板证据，不等价于数值 logit 正确、完整错误矩阵、B2-GATE 或剪枝收益。

B3 入口（2026-09-12）：dense/bypass/full-open 与 execute/skip 实板核对已经关闭 B3-00、B3-06、B3-07；Host 重放 `group_4way` mixed mask 已关闭 B3-08a。B3-09 Host 已接通 `ENeuron evidence → 592-bit group_4way mask → pending bank → fence`，但实板 ELF/JTAG 尚未关闭。下一步是用现有 bit/XSA 上板 live ELF，再补 B3-03/B3-11 与同一 bitstream 上的 dense、full-open、static-group_4way、live-ENeuron-group_4way 小集合周期 A/B。不得把 Host 合同写成板级通过。

B3-08a（2026-09-12）：提交 `73b12c3` 的 `b3_static_mixed` 在同一物理通过 bit/XSA、COM15 实板通过，run `20260912T102046Z`，manifest 位于 `boards/hellozynq/b2_sw/build/73b12c30baf1507876c6bff01059a2c28c919a8d/direct/runs/20260912T102046Z/run_manifest.json`；logits=`74,-18,14,0,0,0,0,0,0,114`，`fence_snapshot_valid=1`，execute/skip=`296/296`。粒度为 `group_4way`，不是严格连接级 `2:4`，也不是 ENeuron 自动决策；B3-08b 延后到 `B3-STRICT-GATE`。

B3-09 实板（2026-09-12）：提交 `fe25a70`/`ab163fe`。COM15 UART `B3_LIVE_ENEURON_PASS` logits=`165,-18,14,0,0,0,0,0,0,153`；JTAG execute/skip=`296/296`、fence valid。证据 `artifacts/logs/b3_live_eneuron_pass_20260912_fe25a70/`。B3-09 已关闭；不是严格 `2:4`。

B3-02 共享固定向量 manifest（2026-09-12）：`tools/repro/b3_fixed_vector_manifest.json` 作为 Python 参考模型与 Host PowerShell 构建的唯一输入；`b3_fixed_vector_manifest.py` 可重建 634 个模型 word、8 个输入 beat、19 个 group-level mask word，并校验 packed model SHA-256；`run_b2_packet_sw_build.ps1` 从同一 manifest 生成 `b3_fixed_vector_generated.h`。`test_b3_fixed_vector_manifest_contract.py` 与 `test_b3_fixed_vector_manifest_loader.py` 共 `6 passed`，Host 生成 C 头文件的合同也通过。B3-02 已关闭；B3-01 的完整发布身份冻结仍开放，但每次 MVP run 保存当次身份即可继续开发实验。该 manifest 不扩展严格连接级 `2:4`，也不构成 live-ENeuron 证据。

B3 execute/skip 计数器物理重建（2026-09-12）：第三次使用 `route_design -directive Explore` 加既有 post-route `AggressiveExplore`，绑定 HEAD `c3a50eb`，在 `xc7z020clg484-2`、200 MHz 下物理硬门通过：`WNS/TNS=+0.008/0 ns`、`WHS/THS=+0.036/0 ns`、setup/hold 失败端点=0、route/DRC hard errors=0、DSP48E1=4。后续 dense/full-open/bypass 实板已读回 execute/skip=`592/0`，B3-00/B3-06/B3-07 已关闭。该物理身份不是当前提交 HEAD `fe25a70`，也不是未提交 RTL。

B2-00 已完成（2026-09-08）：低地址 DDR 窗口 `[0x01000000,0x01100000)` 内冻结 9 个 4 KiB 区域，总保留 `36 KiB`，最大 DMA frame 为 `4096` bytes；机器 manifest `tools/repro/b2_dma_address_layout.json` 与 `verify_b2_dma_address_layout.py` 验证通过，状态为 `B2_00_LOW_ADDRESS_LAYOUT_FROZEN`。B2-D1 已完成并单独记录；所有 manifest 继续保留 `B1_HIGH_DDR_PENDING`，不把 B2-00 误写成完整 B1-GATE 或高地址 DDR 通过。

B2-D1 已完成（2026-09-09）：首轮 DMA 控制合同冻结为 AXI DMA simple mode、单次 buffer、polling、S2MM 先行、1 us polling、1 s 传输超时、500 次 reset poll、错误/超时寄存器快照和一次短帧恢复；`verify_b2_dma_contract.py` 与 B2-00 布局验证合计 `12/12` 定向测试通过。状态为 `B2_D1_DMA_CONTRACT_FROZEN`；e26c7c1 的旧运行未产生受控背压，随后正式 run `20260909T094406Z` 在交换 USB-TTL TX/RX 后完成 UART/JTAG 收口；B2-03/B2-05 仍保留后续恢复与逐帧观测项；`B1_HIGH_DDR_PENDING` 保持不变。

B2 loopback 身份与背压收口（2026-09-09）：最终 VALID 保持修复 bit/XSA=`ef974000…5175a`/`8419e00e…4185`，同源正式 run 绑定 HEAD `875dd1e` 与 ELF=`37722f3c…39056`，运行目录为 `boards/hellozynq/b2_sw/build/875dd1eaf3cea28b75d7bd10762758fe9bf73d55/direct/runs/20260909T111310Z/`。`20260909T111310Z` 在交换外部 USB-TTL TX/RX 后 `run_manifest.status=PASS`、UART/JTAG/XSCT/probe 均 PASS；边界为 `7 PASS + 1 zero-length reject + 0 fail`，pressure=`10000/10000`，backpressure=`64/64`、`stall_cycles=83082`，S2MM probe STALL=3。连续回绕另已完成 `256/256`、`64/64` slot、`rollovers=3`；B2-03/B2-04/B2-05/B2-GATE 仍未关闭，缺口为更完整 PL 逐帧观测、间歇/ready 恢复和错误注入。

B2 观测器与背压收敛（2026-09-09）：官方双/单 `axi_stream_monitor:1.1` routed setup 实验分别以 `WNS=-0.325 ns`、`WNS=-0.284 ns` 失败，均不是正式 B2 物理基线。当前配置为 `0x04030201`（enable=1、stall length=2、period=3），软件在累计 stall 为 0 时 fail-closed；RTL 在首个 `input_fire` 后启动 phase，并在已公开 `TVALID` 等待 `TREADY` 时冻结 phase，避免撤回 VALID/payload。六个 B2 合同测试文件已扩展为 `51/51` 通过。最新正式 run `20260909T094406Z` 已同时取得 UART/JTAG PASS，pressure=`10000/10000`、backpressure=`64/64`、stall_cycles=83082、S2MM STALL=3。B2-03/B2-05/B2-GATE 仍未关闭，尚不得接入 NPU/ENeuron 或报告剪枝收益。
B2 连续回绕切片（2026-09-09）：提交 `69ed289` 的软件/runner/probe 合同已由正式 run `20260909T111310Z`（HEAD `875dd1e`）在 `xc7z020clg484-2` 实板验证为 `BOARD_PASS`：`256/256` 帧、`64/64` slot 覆盖、`rollovers=3`，首末地址 `TX 0x01006000→0x01006FC0`、`RX 0x01007000→0x01007FC0`；bit/XSA/ELF SHA-256=`ef974000…5175a`/`8419e00e…4185`/`37722f3c…39056`。该切片通过不等于 B2-03/B2-04/B2-05/B2-GATE 整体关闭，更完整逐帧 PL 观测、间歇/ready 恢复与错误注入仍待完成。
B2 recovery 切片（2026-09-09）：recovery run `20260909T111310Z`（HEAD `875dd1e`）在 `xc7z020clg484-2` 实板验证为 `BOARD_PASS / PASS_UART_JTAG_XSCT`，`jtag_recovery_status=2`，timeout/reset/passed/failed=`1/1/1/0`，sequence=`10329`、CRC32=`0xD3E3C978`；压力=`10000/10000`、受控背压=`64/64`、stall=`83082`、连续回绕=`256/256`、mask lo/hi 均为 `0xFFFFFFFF`、rollovers=`3`。manifest SHA-256=`044E22…A3226`，recovery ELF SHA-256=`37722f3c…39056`，bit/XSA SHA-256=`ef974000…5175a`/`8419e00e…4185`。该切片通过不等于 B2-03/B2-04/B2-05/B2-GATE 整体关闭；剩余缺口为更完整逐帧 PL 观测、间歇/ready 恢复覆盖和错误注入。
B2 inter-frame gap 切片（2026-09-09）：run `20260909T115218Z`（HEAD `da9147a`，COM10）在 `xc7z020clg484-2` 实板验证为 `B2_GAP_PASS / PASS_UART_JTAG_XSCT`；新增 gap ledger `0x01008340..0x0100836C`，软件 `usleep(1000)`，4B→64B 两帧 `gap=2/2` 通过，sequence=`10330/10331`、CRC XOR=`0x8B08CC4D`，runner/JTAG fail-closed；recovery sequence=`10329` 保持不变。manifest SHA-256=`ACD260…CF211`，ELF SHA-256=`41c6ab2d…63ca7`，bit/XSA SHA-256=`ef974000…5175a`/`8419e00e…4185`。该切片通过不等于 B2-03/B2-04/B2-05/B2-GATE 整体关闭。

B2 persistent DMA frame ledger 子门（2026-09-09）：提交 `5ff9088` 修复持久 ledger；前一实现 HEAD `76e06b6` 的正式 run `20260909T125200Z`（`xc7z020clg484-2`、COM10）取得 UART/JTAG/XSCT PASS，`ledger_pass=true`，8/8 边界记录完整并按 `64-byte` stride 读取。同期 pressure=`10000/10000`、backpressure=`64/64`、`stall_cycles=83082`、wrap=`256/256`、recovery ready=`1→0→1`、gap=`2/2`；新 ELF SHA-256=`7fbcc85aa964a02e30d61f2e47e53e3f70e0e8421275852ba2e36963831d9f3e`，bit/XSA 沿用既有有效身份。该历史子门当时未覆盖 `packetizer/fence`；后续 packet-NPU smoke 与 B2-08 状态块功能集成已完成，但状态块 setup、板级读回、B2-GATE 和 ENeuron A/B 仍未完成。

当前执行点（2026-09-08）：活动链为 `B1-06B6` UART 基准复测 → `B1-06B7` OCM 高地址最小复现。先按 VID/PID 找到 CH340 并确认既有低地址应用的 banner/alive marker；通过后才进入 `B1-06B7`。此前两次诊断均停在 READY 等待 GO，`command=0`、`completed_accesses=0`，尚未进行任何 DDR 访问；不得把高地址探针写成已执行或把 UART 阻塞写成 DDR 失败。

非侵入式监听记录（2026-09-08）：按 `VID_1A86:PID_7523` 监听 COM10，115200 8N1，持续 10 秒，读取 0 字节，未收到 `ENEURON_B1B_BEGIN`、`ALIVE` 或 `PASS`。本次未下载 bitstream/ELF、未发送 GO，DDR access 仍为 0；`B1-06B6_UART_BASELINE_PENDING` 保持不变，不能解释为 DDR 失败。

B1-06B6 实板复测（2026-09-08）：运行目录为 `artifacts/logs/hellozynq_b1b/20260908T202605Z_df56180_b1-06b6_uart_no_marker`，构建 HEAD=`df561803fd44f791a38bda3be3422fe1f6411b77`；按 `VID_1A86:PID_7523` 使用 COM10 监听 20 秒。FPGA program、ELF download、CPU run 均 PASS，但 UART terminal marker=`NO_TERMINAL_MARKER`，DDR accesses=0，因此仍为 `B1-06B6_UART_BASELINE_PENDING`，不能解释为 DDR 失败。两个 runner `boards/hellozynq/b1b_sw/run_b1b_board.ps1` 与 `run_b1b_high_diag_board.ps1` 的 PowerShell `$PID` 参数冲突已修复为 `$ProductId`。

高地址合同已冻结（2026-09-08，当前执行上下文于 2026-09-08 校正）：B1-06A要求诊断ELF独立运行于OCM；`dae5473` 干净构建已重新生成与 manifest 绑定的 OCM 诊断 ELF，SHA-256 为 `3e0469265a1482081ce93188d905753b2fa998673a17e575776e115abfb76f01`，应用范围为 `0x00000000–0x0002EFFF`、入口 `0x00000000`、`runtime_end=0x0000D840`，末尾 4 KiB 保留为结果区。旧 `main@436d1b2`/ELF `619ab70c...1b82` 仅作历史构建参考；新 ELF 尚未上板。B1-06B7 的高地址稀疏探针和 4 KiB 固定模式复现必须以后续 B1-06B6 UART 基准通过为前提。危险访问前预写 OCM 记录，UART、READY 或 GO 任意失败后仍先采集 OCM 和 CPU 状态。不得把构建通过写成整片 DDR、B1B 或 B1-GATE 通过。

B1B实板历史进度（2026-09-08）：当时活动分支为`codex/b1b-high-ddr-board-repro`，父级审计基线为 `d7e1035`；已签核硬件身份为`29edf6adc6613445f0983f2c1b8e4d037164985b`，软件身份为`97ddd1a38f00595e580168ebd59fe0b2d8e1db92`。现场诊断后的正式UART为V14 RX、V15 TX、LVCMOS33，外置CH340按`VID_1A86:PID_7523`识别，COM号仅为现场枚举，115200 8N1；bitstream/XSA/ELF为`1f98e949...bc5f6`、`ed4a2ff...d417b`、`4992d26c...128560`。同一冻结组合已在三次完整断电重启后通过UART协议和低地址1 MiB DDR九阶段；`0x10000000`高地址异常仍未关闭，且尚未执行高地址 DDR 访问，因此状态为`B1B_UART_LOW_DDR_THREE_COLD_RUNS_PASS / B1B_HIGH_DDR_PENDING / B1-GATE=false`。

B1A-HW更新（2026-09-08）：正式UART方向的可重建硬件定义已在干净提交`29edf6a...`上通过Vivado 2024.1实现；资源为`136 LUT / 257 FF / 0 BRAM / 0 DSP / 4 BUFG / 1 MMCM`，WNS/WHS为`+0.240/+0.138 ns`，setup/hold失败端点、route error、DRC error/critical warning及RGMII TX缺失output delay均为0。当前执行点为B1B高地址DDR边界；`B1-GATE`仍为false。

阶段 2 实板校正（2026-09-07）：PR #69 已合并为 `main@102dee2a004283ce4144aaf6ee0a2cee3ebd2887`，B0正式进入主线；Fastlane V1已进入 `main@308bdecd9573e71340359729fdbb2f3fcb7723c7`。B1A来源审计已完成，当前执行点是解决DDR型号、物理PHY复位、物理PHY地址和RGMII时序后生成可重建硬件定义；B1-D1软件栈裁定并行进行。来源审计完成不等于B1A或B1通过。

发布终态（2026-09-07）：PR #69最终HEAD为 `02514b5f4ffd3b5c6a033a2f2d9e6f7b6bcaef92`，于 `2026-09-07T16:17:15Z` 合并，merge commit为 `102dee2a004283ce4144aaf6ee0a2cee3ebd2887`。Actions关闭且checks为空；合并依据是本机Vivado/JTAG/实板证据、17项定向测试、37份JSON和PR CLEAN/MERGEABLE。

P16 阶段 2 总路线见 `.nexus-map/arch/p16_board_validation.md` 和 `.nexus-map/concepts/p16_board_validation.json`。B0-GATE与 B3-MVP-GATE 已关闭。当前日常目标按 `B3-SPEED-GATE + B3-POWER-GATE → B3-GOAL-GATE` 收口；B3-STRICT 是独立结构实验，B2-GATE 与板卡资格支线保留为网口发布依赖。Host 静态 mask 与 live-ENeuron 结果继续分开验收和统计。

当前校正（2026-09-07）：T3 证据已用提交 `c2bc03f` 重跑并绑定；顶层资源为 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`。下方旧快照中的 `822cf93` 仅保留历史来源，不覆盖本条。

generated_by: nexus-mapper v2 / manual synthesis from raw probe
verified_at: 2026-09-12
provenance: `.nexus-map/raw/ast_nodes.json`, `git_stats.json`, `file_tree.txt`（最后探针提交于 `c46320e`）；当前权威 HEAD=`fe25a70` 由 Git 与已提交 Host/manifest 人工核对。未提交 status probe / 计数器 RTL 排除在签核源码身份之外。

T3 最新机器可读签核覆盖见 `.nexus-map/concepts/t3_signoff.json`，人类摘要见 `.nexus-map/arch/t3_signoff.md`；它们优先于早期生成快照中的 `T3_XPM_XSIM_OOC_PENDING` 字样。

ENeuron 是以 Python 黄金模型、SystemVerilog RTL、Icarus/Yosys/Vivado 验证组成的数字脉冲神经元与 NPU 局部剪枝研究仓库。

## 主要系统

- 组级 live-ENeuron Host：`eneuron_group4way_live.py`、`test_eneuron_group4way_live.py`、`boards/hellozynq/b2_sw/src/packet_main.c`（`B3_LIVE_ENEURON`）
- 神经元与参考模型：`digital_lif_engine.sv`、`neuron_sim.py`、`pulse_mini_reference.py`
- 网络/Tile/Host：`digital_snn_tile_4x2x2.sv`、`digital_snn_host_bridge_controller.sv`、`network_sim.py`
- 单时钟 NPU + ENeuron 集成 RTL：`npu_eneuron_single_clock_skeleton.sv`；基础、mask epoch、控制、真实计算和随机逐拍入口分别为 `test_npu_single_clock_skeleton.py`、`test_npu_single_clock_mask.py`、`test_npu_single_clock_control.py`、`test_npu_single_clock_compute.py`、`test_npu_single_clock_random.py`
- 局部剪枝：`local_prune_gate_2of4.sv`、`local_prune_reference.py`、`verify_np4b_signoff.py`
- NP7 共享执行器：`np7_shared_synapse_lane.sv`、`np7_weight_ram.sv`、`np7_shared_lane_oracle.py`、`np7_shared_lane_cosim.py`
- 验证入口：`verify_goal.py`、`verify_np4b_signoff.py`、`test_*.py`、formal `.ys/.sv`
- 规划与状态：`WORKFLOW_STATE.md`、`docs/planning/NPU_NEURON_INTEGRATION_REVIEW.md`、`docs/planning/NPU_PRUNING_NP6_TODO.md`、`docs/planning/NPU_PRUNING_NP7_TODO.md`
- 集成材料包：`docs/planning/NPU_NEURON_INTEGRATION_MATERIALS.md`、`docs/planning/NPU_ORACLE_FREEZE_REVIEW.md`、`docs/planning/NPU_ORACLE_SINGLE_CLOCK_CONTRACT_V3.md`、`docs/planning/NPU_MODEL_COMMIT_CONTRACT_V3.md`、`docs/planning/NPU_SINGLE_CLOCK_RTL_DECISION_SHEET_V2.md`（I1-I6、OF1-OF6 V3 与 V2 RTL 裁定已批准）；TR1-TR6 的实现与功能合同见 `NPU_SINGLE_CLOCK_TIMING_REPAIR_V1.md` 和 `NPU_SINGLE_CLOCK_TIMING_REPAIR_TEST_CONTRACT_V1.md`，下一轮审核稿与实施地图分别为 `NPU_SINGLE_CLOCK_TIMING_REPAIR_V2.md`、`NPU_SINGLE_CLOCK_TIMING_REPAIR_V2_IMPLEMENTATION_MAP.md`。
- 单时钟 OOC 入口：`run_vivado_npu_single_clock_ooc.ps1`、`vivado_npu_single_clock_ooc.tcl`、`artifacts/results/npu_single_clock_ooc_manifest.json`、`vivado_npu_single_clock_ooc_reports/`
- CI 编排：`.github/workflows/pr-gate.yml`、`tools/ci/classify_changes.py`、`test_ci_fast_v1.py`（路径分类、条件专项门和唯一 `PR Gate` 汇总）
- 阶段 2 实板 B0：`boards/hellozynq/b0_smoke/`；两次机器/现场运行与完整断电证据均通过，状态为 `B0_COMPLETE`
- P16 阶段 2 路线：B0 PL → B1 PS/DDR/UART/UDP → B2 DMA/固定帧 → B3 NPU+ENeuron 固定向量 → B4 网口端到端 A/B

## 当前状态

状态校正（2026-09-07）：PR #64 已合并为 `main@a53a040`；PR #65 已合并为 `main@618c1e4`；PR #66 已合并为 `main@a1457bb`。下文若仍出现旧的“OPEN”或“等待合并”措辞，均属于生成快照中的历史内容，不覆盖本条和 `WORKFLOW_STATE.md` 的当前状态。

NP4B 已签核；NP6 已收口为 `NP6_PHYSICAL_COST_PARTIAL`，NP7 已签核。TR7-TR12 已批准并完成 V2 实现：单时钟专项、固定 `20×100` 和完整仓库回归均通过。实现提交 `f744bff2bdde68e138a7b2b348ce103bec1ab469` 的 OOC 为 `2126 LUT / 1916 FF / 0 BRAM / 4 DSP48E1`，100 MHz `WNS=+0.060 ns / TNS=0 / WHS=+0.040 ns`，setup/hold/route/DRC 零失败。T3 随后在 HEAD=`c2bc03f` 上完成：真实 AMD XPM/xsim `RESULT=PASS`，XC7Z020 OOC `PHYSICAL_GATE=PASS`，顶层 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`、外部 CDC 0、100 MHz setup/hold/route/DRC error 0；详见 `.nexus-map/arch/test_coverage.md` 的 T3 条目与两份 signoff 报告。PR #64 已合并为 `main@a53a040`，PR #65 已合并为 `main@618c1e4`，PR #66 已合并为 `main@a1457bb`。PR #68 的 `55ec08e`/run `33976357259` 是历史审计快照：当时为 `OPEN / MERGEABLE / UNSTABLE`，runner 因账户付款/额度限制未启动，归类为 `NOT_RUN_BILLING_BLOCKED`；不得把该快照当作当前 CI。当前状态为 `TIMING_REPAIR_V2_FUNCTIONAL_GREEN / VIVADO_OOC_100MHZ_PASS / P15_T0_APPROVED / T1_RTL_AUTHORIZED / T1_PROTOCOL_SLICE_PROVEN / T1_FULL_PENDING / T2_VARIABLE_CLOCK_SLICE_GREEN / T2_CONCURRENT_EPOCH_SLICE_GREEN / T2_EXTENDED_CLOCK_SLICE_GREEN / T2_FIFO_MATRIX_SLICE_GREEN / T2_INTERLEAVE_RESET_SLICE_GREEN / T2_FINITE_CLOCK_MATRIX_GREEN / T2_RANDOM_CLOCK_MATRIX_GREEN / T2_FULL_MATRIX_PENDING / T3_XPM_XSIM_PASS / T3_XC7Z020_OOC_PASS / T3_SIGNOFF_PASS / RESOURCE_CUT_DEFERRED_UNTIL_FIRST_END_TO_END_RUN`。T1-12 边界 testbench、manifest/runner/classify_changes 扩展和相关测试计划证据已随 `c55a8b6`/`f21c06b` 纳入当前提交基线；T1-06 fence testbench 与 T1-09 N/A 文档/静态测试已随 `e4d48dd` 提交。T1-02 主要路径、T1-12 四 FIFO 边界和 T1-06 独立 fence 均有本机通过证据（`T1_FIFO_BOUNDARY_PASS`、`T1_FENCE_ACCEPT_PASS`），本机合同 22/22 与 G0/G1/G2 复现入口全部通过；这些不是 GitHub CI 结果。T1-09 当前 DUT 已裁定为 `NA_FOR_T1_WRAPPER / OUTER_SHIM_PENDING`，外层 AXI-Stream shim 仍属后续工作，不把它写成当前 TLAST 仿真通过。T1-01～T1-12 全覆盖、T2 更广泛并发命令/样本交错、外层 shim、首次完整端到端运行和板级验证仍需按各自门验收；本次 T3 已完成，不接入 AXI-Lite、DMA、Ethernet 或 PS7。Actions 已暂停，远端 checks 缺失不作通过或失败判定。资源裁剪候选已经审查，但管理员决定等第一次完整端到端运行成功后再考虑实施。Webhook 未签名事件只作触发提示；GitHub Checks/API 仍为 CI 权威来源；板级、DMA、PS、网口和功耗仍未签核。

- T2 证据分层（当前知识库同步提交 `8eab78e`）：基础可变时钟复现入口绑定 `a616d60`，六组 `(NPU_HALF,PHASE)` 扩展绑定 `f54e762`，并发 mask epoch 场景绑定 `872fa90`；摘要文档分别由 `af520b2`、`1a3c371` 和 `8eab78e` 更新。`python -X utf8 tools/repro/verify_repository.py --t2` 的 `REPRO_G2_T2_VARIABLE_CLOCKS_PASS` 是本机 Icarus/复现证据，不是 GitHub Actions 结果。

- T2 FIFO 矩阵切片已提交于 `ee3a351`：`tb_xpm_fifo_async_matrix.sv` 对命令、响应、样本和结果四通道做固定 8 组 `(NPU_HALF,PHASE)` × 3 个 seed，共 24 次逐序列 scoreboard；入口 `python -X utf8 tools/repro/verify_repository.py --t2-fifo-matrix` 输出 `REPRO_G2_T2_FIFO_MATRIX_PASS`。该结果是本机 Icarus 等价 FIFO 模型证据，不是 AMD XPM/xsim、Vivado T3 或 GitHub Actions 结果；T2 全矩阵和真实 XPM/xsim 仍待完成。

- T2 固定种子随机时钟/相位矩阵已通过：入口 `python -X utf8 tools/repro/verify_repository.py --t2-random-matrix` 使用种子 `20260907` 生成 24 个唯一 `(NPU_HALF,NPU_PHASE)` 组合，结果为 `REPRO_G2_T2_RANDOM_MATRIX_PASS`。每组结果观察预算为 `2000 + 400 × NPU_HALF` 个 Host 周期，以覆盖慢 NPU 时钟下的完整场景；状态记为 `T2_RANDOM_CLOCK_MATRIX_GREEN`。这是可复现的有限压力集，不是所有频率和相位的数学穷举。

- T2 wrapper 交错/复位切片已提交于 `8457a20`：`tb_npu_zynq7020_t2_interleave_reset.sv` 在 `(NPU_HALF, NPU_PHASE)=(2,0),(3,1),(7,2),(11,4)` 四组配置下验证命令与样本交错、配置中途复位、结果背压复位、半帧复位和旧 payload 清除，入口 `python -X utf8 tools/repro/verify_repository.py --t2-interleave-reset` 输出 `REPRO_G2_T2_INTERLEAVE_RESET_PASS`。这是 Icarus wrapper 切片证据，不是 T2 全矩阵、AMD XPM/xsim、Vivado T3 或 GitHub Actions 结果。

## 单时钟 RTL 审核摘要

Nexus 归档校正：T2 FIFO 矩阵已提交 `ee3a351`，wrapper 交错/复位切片已提交 `8457a20`。

- **V1 审计问题**：统一单命令流却定义 `MODEL_COMMIT` 与 `MASK_COMMIT` 同拍竞争；结果 sideband 引入未冻结的 `model_epoch` 且硬件槽位账本不足；首 beat mask 切换未说明 framing 错误的零副作用/回滚；`runtime_idle` 漏待消费错误、部分结果和同拍握手占用；验证门低于 I5 的 20 个固定 seed × 100 样本要求。
- **V2 修正**：固定 8/10 beat 并取消外部 `last`；明确 nibble 位序和内部 beat 计数；删除 `model_epoch`，结果 metadata 仅为 sample ID 与 mask epoch；统一命令流按握手顺序串行，配置命令优先样本首 beat；idle 纳入错误响应、部分输出、统一槽位及同拍仲裁；验证门恢复至少 20×100 样本并保留 OF6 定向/负向覆盖。
- **当前门槛**：V2 已实现于 `f744bff`。OOC 结果为 `2126 LUT / 1916 FF / 4 DSP48E1`，DSP 双重结构门、setup/hold、route 和 DRC 全部通过；`WNS=+0.060 ns / TNS=0 / WHS=+0.040 ns`。V1 的 22 个失败端点仍保留在独立审计文档中，仅作历史路径证据；当前 OOC 结果和哈希由 `artifacts/results/npu_single_clock_ooc_manifest.json` 绑定。
- **第二条 RTL 切片**：`test_npu_single_clock_mask.py` 驱动公开接口验证完整 19-word 顺序装载；非法 word18 高 16 位产生 128-bit 单槽错误响应且隐式索引保持 18，响应消费后可重试；`MASK_COMMIT` 只发布，后续样本首 beat 才令 epoch 1 active 并置 `mask_valid`，两个连续样本结果均携带 epoch 1。
- **第三条 RTL 切片**：`test_npu_single_clock_control.py` 验证部分 mask 可由 `MASK_ABORT` 丢弃；`STATE_CLEAR` 保留模型/mask；freeze 只在严格 idle 边界切换，冻结时样本仍可完成，而模型/mask 配置与动态清除返回稳定错误且不改变状态。
- **真实计算状态**：`test_npu_single_clock_compute.py`/`tb_npu_eneuron_single_clock_compute.sv` 已锁定 uint4×INT8、隐藏饱和、INT32 logit 与 L0 mask 门控；四 lane FETCH/EXECUTE/COMMIT 引擎通过首组 137/-117、两层最后组 59、L1 bit79 关闭后 -1，以及忙态阻塞检查。
- **随机门 GREEN**：固定 `20 seeds × 100 samples = 2000` 个样本逐 beat 比对 logits、sample ID、mask epoch、背压和 mask 轮换；DSP V1 完整仓库回归为 473/473（1 skipped）。物理 setup 仍失败，下一步是审核 V2，不能用软件周期或历史报告代偿。
- **配置合同补强**：模型写入已执行两层 signed bias 安全窗；mask 四态命令可与部分输入、计算和结果流并行准备 published bank，但只在下一样本首 beat 切换 active，模型/冻结/清除命令仍要求严格运行空闲。

## P15-T0 顶层规划（当前门）

- 规划文档：`docs/planning/NPU_ZYNQ7020_TOPLEVEL_INTEGRATION_V1.md`；裁定稿：`docs/planning/NPU_ZYNQ7020_TOPLEVEL_DECISION_SHEET_V1.md`。
- 推荐方案 A：命令/响应继续使用现有 128-bit 异步 FIFO；新增独立 32-bit 样本输入和结果输出 FIFO，并在 FIFO 外侧放置 AXI-Stream shim。样本固定 8 beat，结果固定 10 beat，`sample_id`/`mask_epoch` sideband 在各自事务内保持稳定。
- 当前状态：`P15_T0_APPROVED / T1_RTL_AUTHORIZED / T1_PROTOCOL_SLICE_PROVEN / T1_FULL_PENDING / T2_VARIABLE_CLOCK_SLICE_GREEN / T2_CONCURRENT_EPOCH_SLICE_GREEN / T2_EXTENDED_CLOCK_SLICE_GREEN / T2_FIFO_MATRIX_SLICE_GREEN / T2_INTERLEAVE_RESET_SLICE_GREEN / T2_FINITE_CLOCK_MATRIX_GREEN / T2_RANDOM_CLOCK_MATRIX_GREEN / T2_FULL_MATRIX_PENDING / T3_XPM_XSIM_PASS / T3_XC7Z020_OOC_PASS / T3_SIGNOFF_PASS / RESOURCE_CUT_DEFERRED_UNTIL_FIRST_END_TO_END_RUN`。方案 A、A1-A7、四条流 sideband/固定 beat 语义以及 AXI 外置边界已获批准；T1 纯 RTL 适配器及协议切片已进入仓库并可由统一入口复现，T2 的六组可变时钟、并发 epoch、FIFO、交错/复位、16 组有限矩阵和 24 组固定种子随机矩阵已提交并通过本机复现，但 T1-01～T1-12 全覆盖、T2 更广泛并发交错、外层 AXI-Stream shim 和首次完整端到端运行仍待完成。T3 真实 AMD XPM/xsim 与 XC7Z020 OOC 已通过，不接入 AXI-Lite、DMA、Ethernet 或 PS7，直到后续阶段单独批准。资源裁剪只保留为首次端到端跑通后的候选，不进入当前实施基线。

### 下一阶段 T1 最小执行集（当前 DUT 已闭环）

T1-02、T1-06 和 T1-12 的主要路径/独立切片已通过本机 Icarus 验证；T1-09 已形成 `NA_FOR_T1_WRAPPER / OUTER_SHIM_PENDING` 裁定。当前 T1 DUT 没有剩余独立测试项，外层 AXI-Stream shim 的 TLAST 测试留待后续接口落地，不改变四条流、8/10 beat 或 A1-A7 合同。

T2 双时钟协同切片已扩展通过：`tb_npu_zynq7020_t2_variable_clocks.sv` 在 `(7,2)/(9,1)/(4,3)/(5,0)/(11,4)/(3,1)` 六组参数下均通过；每组都包含并发 epoch 场景，旧样本结果仍为 epoch=1，下一 fence 仍回显 active=1，下一样本才为 epoch=2。统一入口为 `python -X utf8 tools/repro/verify_repository.py --t2`。当前优先进入 T3：真实 AMD XPM/xsim 协同仿真和 `xc7z020clg400-1` OOC；T2 随机全矩阵保留为未完成项。外层 shim 若实现，再单独验证改变、提前或缺失 TLAST 不改变完整核心结果。严格包错误仍由外层 packetizer 负责，不能伪造 T1 核心通过。

### P15-T0 只读审计结论（2026-09-05，历史快照）

本节保留批准前的审计依据。下列阻断已由 2026-09-07 批准的 A1-A7 形成唯一合同并解除，不覆盖上方当前状态，也不能再据此推导 `NO_RTL_AUTHORIZATION`。

- **命令格式必须先选唯一权威**：当前 `npu_eneuron_single_clock_skeleton.sv` 与 `NPU_SINGLE_CLOCK_RTL_PORT_TABLE_V1.md` 使用高位 4-bit opcode（`[127:124]`）、epoch（`[119:88]`）和 word（`[31:0]`）；历史 `NPU_ORACLE_SINGLE_CLOCK_CONTRACT_V3.md` 仍描述低位 8-bit opcode/txn 格式。P15 不能只说“沿用核心协议”，T1 前必须明确采用当前 skeleton 格式，或同步修改 RTL/Oracle。
- **V1/V2 framing 不得混用**：V1 文档曾要求内部 `last` 和 `model_epoch`；V2 已删除二者，固定 8/10 beat 由内部计数器结束。P15 的 AXI `TLAST` 只能在明确早/晚/缺失时的检查或忽略语义后使用，不能把旧 `last` 接入核心。
- **四条流仅各自有序，跨流 fence 尚未冻结**：独立 command/sample FIFO 会使 `MASK_COMMIT`、`STATE_CLEAR`、`FREEZE_SET` 与样本首 beat 的相对顺序不确定；样本首 beat 的 mask 绑定发生在 NPU 域 core handshake，而非必然发生在 Host FIFO 写入沿。T1 必须定义控制完成栅栏或显式串行化策略。
- **reset-busy/状态 CDC 尚未形成可实现合同**：当前旧 Bridge 的 ready 只门控本侧 FIFO busy，不能直接证明“任一域 busy 时四流均不 ready”。Host 侧 `model_valid`、mask/epoch、错误和 FIFO domain-up 的同步方式、复位重入/半包丢弃边界都必须冻结。
- **AXI sideband 与错误路由仍缺字段**：需明确 sample `sample_id` 是否逐 beat 校验（core 当前只采样首 beat）、result sideband 在 10 beat 的保持、`TLAST`/`TKEEP`/`TSTRB`/`TID`/`TDEST` tie-off，以及样本 framing/sideband 错误如何在没有旁路错误包时报告。
- **FIFO 参数与资源归因未冻结**：新增 sample FIFO 实际为 64-bit、result FIFO 为 96-bit；depth、FWFT/latency、CDC stages、memory type 尚未定义，不能先验声称 BRAM/LUT/FF 增量。应以四个 FIFO 的实际 XPM 参数和 post-route 报告分别归因。
- **器件边界必须统一**：P15 目标是 `xc7z020clg400-1`；旧 Host Bridge OOC 使用 `xc7a35tcpg236-1`，只能作历史结构参考，不得替代 XC7Z020 资源、时序或 CDC 证据。
- 历史结论：在上述合同补齐前，状态保持 `P15_T0_REVIEW_REQUIRED / NO_RTL_AUTHORIZATION`，不得创建 T1 顶层 RTL。当前这些合同已补齐并获批准，状态已转为 `P15_T0_APPROVED / T1_RTL_AUTHORIZED`。

### P15-T0 附录二次复核（2026-09-05，历史快照）

对 `NPU_ZYNQ7020_TOPLEVEL_T0_DECISION_ADDENDUM_V1.md`、`NPU_ZYNQ7020_TOPLEVEL_T0_TEST_CONTRACT_V1.md`、`NPU_SINGLE_CLOCK_RTL_PORT_TABLE_V1.md`、V2 实施合同和当前 skeleton 的只读交叉审计仍发现以下 T1 阻断。它们不是对方案 A 的否定，而是必须在批准稿中写成唯一可实现语义：

- **A3 没有冻结 fence 的线级格式**：附录第 36–39 行只指定保留 opcode `0xA` 和“带 fence ID 的响应”，没有规定 fence ID 位段、响应成功类别、错误码、响应字段布局，也没有说明 fence 被 wrapper 接受时如何阻止它泄漏到核心。当前 PORT_TABLE 只定义了 `0xE` 错误响应；T1 无法据此实现或逐拍比对 fence 确认。
- **严格 TLAST 与流式丢弃语义存在实现矛盾**：附录第 22–28 行要求晚到/缺失 TLAST 的整帧“不送入核心”，但若样本 beat 已逐拍穿过 FIFO，直到第 8 个 beat 或下一帧才发现错误就无法撤回；要满足该保证必须明确整帧预缓冲，或改为允许已送入的 beat 被取消。结果流是 wrapper 的输出，不能与样本输入共用同一套“接收 TLAST 检查”语句。与此同时，旧裁定稿第 49–51 行仍说 TLAST 只是提示、8/10 beat 不依赖 TLAST，必须明确哪一份被废止。
- **fence 前样本准入边界未定义**：附录第 37–40 行规定一个 fence 只授权一笔样本，但没有规定 fence 前 `sample_ready` 是否必须为 0、sample FIFO 是否允许预填、已有预填 beat 在拒绝/复位时如何丢弃。由于 sample FIFO 不携带 TLAST/帧号，T1 若不先冻结该规则，不能证明一笔 fence 对应恰好 8 个 beat。
- **A3 的“命令完成”层级不清**： “此前命令已完成核心握手”没有区分命令 FIFO 出队、核心 `cmd_valid&&cmd_ready` 握手、mask published 生效和状态操作实际完成；成功配置命令又不产生普通响应。必须指定 fence 的等待条件、与 response FIFO 满的 backpressure/拒绝优先级，否则可能在配置尚未可见时放行样本。
- **A4 的 busy 门控可能破坏 ready/valid 稳定合同**：附录第 48–50 行把任一域 busy 解释为四条流的 ready/valid 都关闭；若 result FIFO 已有 `valid=1` 且下游 `ready=0`，busy 变化不能撤销 valid 或改变 payload。应冻结为“禁止新事务握手，但在非复位期间保持已呈现事务稳定”，并定义 busy 重新开放的状态机。
- **A1 保留位检查尚未落到错误优先级**：附录要求 `[123:120]` 和 `[87:32]` 为零，但 skeleton 当前按 opcode 直接解码，未定义 wrapper 对非零保留位、未知 opcode、冻结状态和 payload/地址错误的检查先后。T0 测试合同虽要求非法字段向量，仍需把错误码、被拒字段和无副作用顺序写入批准的线级合同。
- **Host 状态/epoch 不是普通逐 bit 同步问题**：A4/A6 只说同步摘要；32-bit `mask_epoch` 若逐 bit 两级同步可能产生撕裂值，Host 会把结果匹配到不存在的 epoch。必须使用稳定握手、快照+有效标志或等价原子总线 CDC，并冻结 error/IRQ 的 sticky 与清除语义；否则 A6 的结果匹配合同不可验证。
- **A5 的参数来源仍有两套**：附录第 55–64 行只明确 depth/FWFT/auto，而 T0 测试合同第 48–50 行又加了 `read_latency=0`、`CDC_SYNC_STAGES=2`、`SIM_ASSERT_CHK=1`。这些实现参数和仿真专用参数必须在批准稿中标为唯一权威，不能让 T1 自行取 XPM 默认值。

历史结论：上述问题在当时尚未改变门槛，状态为 `P15_T0_REVIEW_REQUIRED / PROPOSED / ADMIN_REVIEW_REQUIRED / NO_RTL_AUTHORIZATION`。2026-09-07 管理员批准 A1-A7 后，该结论不再是当前门；T1 已授权且协议切片已提交，但完整 T1 仍待完成。

### P15-T0 提案修订状态（2026-09-05，历史提案；2026-09-07 已批准）

- A2 已按 KISS 修订为“V2 8/10 beat 计数唯一权威，T1 不解释 TLAST”；严格 TLAST/整帧检查移到外层 packetizer，避免无预缓冲流式 wrapper 无法回滚的问题。
- A3 已补充建议线级格式：wrapper-only `0xA`、`fence_id=cmd_payload[31:0]`、成功响应类别 `0xD`、fence 前 `sample_ready=0` 且禁止预填、成功后只开放一个 8-beat 窗口。fence 成功条件不得依赖核心 `runtime_idle`（`MASK_PUBLISHED` 等待首 beat 时该摘要为假，可能自锁）；应使用核心 `sample_ready=1`、核心 `result_valid=0`、核心 `rsp_valid=0`、wrapper 无活动样本窗口，以及 model/mask staging 已闭合（允许 `MASK_PUBLISHED` 等待首 beat 激活）作为准入条件。
- A4/A6 已补充 ready/valid 稳定和状态 CDC 建议：busy 只禁止新握手，非复位期间不撤销已呈现 payload；`mask_epoch` 只通过 result/fence 原子 payload，不做逐 bit CDC。
- A1/A5 已补充保留位/未知 opcode 错误优先级，以及 `FIFO_READ_LATENCY=0`、`CDC_SYNC_STAGES=2`、`SIM_ASSERT_CHK=1` 唯一参数。该组 A1-A7 提案已于 2026-09-07 获管理员批准；T1-02 主要路径、T1-06 fence 独立切片与 T1-12 FIFO 边界已在本机 `e4d48dd` 工作树通过，当前仍为 `T1_RTL_AUTHORIZED / T1_PROTOCOL_SLICE_PROVEN / T1_FULL_PENDING`，不等于 T1 全量、T2 或 T3 完成。

## 资源裁剪门

- `docs/planning/NPU_ZYNQ7020_RESOURCE_CUT_REVIEW_V1.md` 已记录可裁、可配置裁与不可裁候选；其中收益仍是待 A/B Vivado OOC 验证的估算，不是物理实测。
- 管理员决定在第一次完整端到端运行成功前不实施任何资源裁剪，不修改当前训练/推理、FIFO、CDC、原子 sideband、fence、四 DSP 或诊断基线。
- 首次端到端跑通后，才按 telemetry、模型存储 BRAM 化、独立 `INFER_ONLY` 构建、固定拓扑特化的顺序重新评审。

## 状态校正与下一门

器件口径校正：状态串中的 `T3_XC7Z020_OOC_PASS` 仅表示旧 `xc7z020clg400-1` 核心/适配器 OOC 参考已通过；当前部署目标仍是 `xc7z020clg484-2`，其最终 routed/DRC/板级证据尚待建立。NP7 的 `clg400-1` 物理结果同样只作历史材料。

- **当前权威基线**：V2 OOC report head 与 RTL 均绑定 `f744bff2bdde68e138a7b2b348ce103bec1ab469`；其变更已随 PR #64 合并为 `main@a53a040`。P15-T0 规划随 PR #65 合并为 `main@618c1e4`，端口裁定稿随 PR #66 合并为 `main@a1457bb`。不要把旧 report head=`39e41d4` 的 0 DSP 结果或 V1 `5055073` 失败结果当作当前物理状态。
- **已完成证据**：单时钟专项 8/8、固定 `20 seeds × 100 samples = 2000` 个样本逐 beat 随机门、完整回归 `473/473（1 skipped）`，以及 4 DSP 网表证据。
- **已完成物理阶段**：使用 Vivado 2024.1 对 V2 RTL、器件 `xc7z020clg400-1`、100 MHz 约束执行了 OOC 综合/实现、资源、setup/hold 和 DRC，物理硬门通过。该结果不宣称板级、功耗或网络吞吐性能。
- **历史保留**：下方审计条目保留设计演进背景；其中标注为 V1/OF6 历史阶段的缺口不覆盖上述当前签核结果。

## 必读路由

- `.nexus-map/arch/systems.md`
- `.nexus-map/arch/dependencies.md`
- `.nexus-map/arch/test_coverage.md`
- `.nexus-map/hotspots/git_forensics.md`
- `.nexus-map/concepts/domains.md`

## [操作指南] 强制执行步骤

> 本节是对所有读取本文件的 AI 发出的硬性操作指令，不是建议。

### 步骤1 — 必须先读完以下所有文件（顺序不限）

读完本文件后，在执行任何任务之前，必须依次读取以下文件完整内容：

- `.nexus-map/arch/systems.md` — 系统边界与代码位置
- `.nexus-map/arch/dependencies.md` — 系统间依赖关系与 Mermaid 图
- `.nexus-map/arch/test_coverage.md` — 测试面与证据缺口
- `.nexus-map/hotspots/git_forensics.md` — Git 热点与耦合风险
- `.nexus-map/concepts/domains.md` — 核心领域概念

这些文件均为高密度摘要，不得以任务简单或只改一个文件为由跳过。

### 步骤2 — 按任务类型追加操作（步骤1 完成后执行）

- 若任务涉及接口修改、新增跨模块调用、删除或重命名公共函数：运行 `query_graph.py --impact <目标文件>` 确认影响半径后再写代码。
- 若任务需要判断某文件被谁引用：运行 `query_graph.py --who-imports <模块名>`。
- 若仓库结构发生重大变化：任务完成后重新评估并更新 Nexus 知识库。
B2 missing-TLAST 切片（2026-09-09）：run `20260909T133721Z`（HEAD `b2332a0`，COM10）在 `xc7z020clg484-2` 实板验证为 `B2_MISSING_TLAST_PASS / PASS_UART_JTAG_XSCT`；`missing_tlast observed=1`，`dma_error/reset/recovered/failed=1/1/1/0`，注入/恢复 sequence=`10332/10333`，MM2S/S2MM TLAST=`0/0`、beats=`16/16`，recovery sequence=`10329` 保持不变。manifest SHA-256=`F4D559…FE9B7`，ELF=`0abb11b0…e1ee3`，bit/XSA=`922b9cd6…0c64d`/`5b78919b…c2a9f`。该切片通过不等于 B2-06/B2-08/B2-GATE 整体完成。

B2 packet-NPU 适配器更新（2026-09-09）：`cb9eb66` 的 response 适配器切片与 `62f2d8b` 的 sample/result 端到端切片已分别通过 `B2_NPU_PACKET_ADAPTER_PASS`（4/4）和 `B2_NPU_PACKET_ADAPTER_E2E_PASS`（3/3）。`ea35d74` 将 `b2_npu_axis_top` 接入 B2 BD，`1d0e3ba` 固定为 `boards/hellozynq/b2_hw/b2_npu_axis_top.v` 的 Verilog BD reference；顶层合同测试 3/3。现有 Vivado bit/XSA/report 仍绑定旧 `b2332a0`，状态为 `STALE_PRE_PACKET_TOP_BUILD`，新顶层尚无目标器件 routed 或实板证据。

B2-07 ingress fail-closed 增量（2026-09-10）：提交 `c1f3c8c`、`1b35180`、`2e6734c`、`0598d53` 在 `tb_b2_packet_ingress.sv` 新增坏 magic、错误 version、未知 type、保留 flags 四个坏帧子门；每项均验证明确错误码且 `cmd_valid/sample_valid/busy` 不泄漏。`test_b2_packet_ingress_contract.py` 为 `4/4 PASS`，`python -X utf8 tools/repro/verify_repository.py --t1` 输出 `REPRO_G0_MANIFEST_PASS` 与 `REPRO_G1_T1_PROTOCOL_SLICE_PASS`。这仍是 RTL/Icarus 证据；B2-07 其余错误矩阵、packet 顶层 routed/实板证据仍待完成。

B2 packet-NPU 物理构建更新（2026-09-10）：HEAD=`1bfeb12` 的 Vivado 2024.1 构建已完成 route 并生成 bit/XSA（器件 `xc7z020clg484-2`，route errors=`0`，DRC hard errors=`0`），但 200 MHz `clk_fpga_0` setup 未通过：`WNS=-2.750 ns`、`TNS=-8221.926 ns`、`8788` 个 setup failing endpoints；hold 为 `WHS=+0.053 ns`、`THS=0`。最差路径已由此前 command FIFO→model staging 转移为 `egress/response_mem` BRAM→`crc_state`。新保持槽切片已提交，但时序仍未签核，不能进行实板下载或宣称 packet-NPU 物理通过。

B2 packet-NPU egress CRC 分拍后重建（2026-09-10）：提交 `8d57e7e` 的 Vivado 2024.1 构建完成 route、bit/XSA 和 DRC，但 200 MHz setup 仍失败：`WNS=-1.958 ns`、`TNS=-3308.760 ns`、`5902` 个失败端点；hold=`WHS=+0.055 ns`、`THS=0`，route errors=`0`、DRC hard errors=`0`。最差路径已离开 egress BRAM/CRC，转为 `core/compute_unit_index_reg[0]`→`compute_group_index_reg[2]` 控制路径，数据延迟 `6.574 ns`（布线 `5.077 ns`，8 级逻辑）。bit/XSA 仅作失败分析，不得上板。

B2 packet memory BRAM 化探针（2026-09-10，已归档）：`b2_packet_egress.sv` 已将 response/result payload 从大范围分布式缓存改为 `b2_packet_bram.sv` 的 XPM simple-dual-port block RAM；Vivado 2024.1、器件 `xc7z020clg484-2` 综合报告 `artifacts/logs/b2_packet_memory_ooc_20260910_bram/b2_packet_egress_utilization.rpt` 显示新 egress 为 `532 LUT / 251 FF / 2 RAMB36 / 1 RAMB18`，其中 `response_mem=2 RAMB36`、`result_mem=1 RAMB18`。相对旧 egress 约 `35944 LUT / 0 BRAM`，约减少 `35412 LUT`，但该差值是 OOC 综合探针，不是完整顶层 routed 结果。`b2_packet_ingress.sv` 已改为四 bank、同步读路径并加 `ram_style="block"`；当前报告仍为 `2085 LUT / 1408 LUTRAM / 488 FF / 0 BRAM`，说明 bank 化尚未被 Vivado 推断为 BRAM，不能宣称 ingress BRAM 化完成。合同测试 `test_b2_packet_memory_inference_contract.py` 仅检查结构声明；packet 语义、时序和实板验证仍待补齐。

B2 packet-NPU 最新物理重建（2026-09-10）：提交 `074ed56` 的 egress BRAM 预取已完成 route、bit/XSA 和 DRC，但 200 MHz setup 仍失败（`WNS=-0.052 ns`、`TNS=-0.134 ns`、6 个失败端点，`WHS=+0.073 ns`、`THS=0`）；最差路径为 `compute_unit_mask_latched_reg[3]/C -> compute_group_index_reg[1]/D`。证据归档于 `artifacts/logs/b2_packet_npu_route_timing_fail_20260910_074ed56/`，bit/XSA 标记为 `analysis_only_no_download`，不得上板或进入 ENeuron A/B。

B2 packet-NPU 当前状态（2026-09-11）：物理构建源 HEAD=`97398bf641b49ef2f2ab6b16edd68b6327a14488` 已通过 `xc7z020clg484-2`、200 MHz routed physical gate（WNS=+0.012 ns、TNS=0、WHS=+0.036 ns、THS=0，route/DRC hard errors=0）。随后软件/证据提交 `8c8e44c`、`591fe08`、`cbfd2b4` 完成 packet board smoke：FPGA program、ELF download、634 model words、19 mask words、fence、8-beat sample→10-beat result 以及 UART/JTAG/XSCT 均 PASS；bit/XSA/ELF SHA-256 记录在 `artifacts/logs/b2_packet_board_pass_20260911_8c8e44c/`。该切片只证明合法 packet path 的板级最小运行，不关闭 B2-06～B2-10 或 B2-GATE；B3 和 ENeuron A/B 仍未完成。

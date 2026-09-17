# 核心领域概念

当前主线（2026-09-16）：QAT CP0/CP1/CP3c/CP4 clean 已完成，严格 2:4 live/static 精度失败；无损零组跳过在 clean 完整 wrapper 上完成 397 样本正式对拍，logits 逐元素一致、任务准确率 88.665% 无下降，核心周期约 1.089x，单样本窗口约 1.008x。下一步是 CP5 连续流吞吐；功耗证据仍为 `POWER_NOT_MEASURED / NOT_PROVEN`。

> generated_by: nexus-mapper v2 / manual synthesis
> verified_at: 2026-09-16
> provenance: 当前 checkout 路径、分支与提交以 Git 命令实时查询；历史路径、分支和 PR 名称仅作来源。bitstream RTL 身份 `be84596`。证据 `artifacts/logs/b3_mvp_20260912_be84596/`。

## 当前权威概念边界（2026-09-16，CP4 clean 正式通过）

器件 `xc7z020clg484-2`，checkout 身份以 Git 实时输出为准。B3-MVP-GATE、QAT CP1 dense、lossless CP3c 和 CP4 clean 已完成；397 样本正式对拍 logits 逐元素一致，核心周期约 `1.089x`，单样本窗口约 `1.008x`。CP5b 397 样本纯 PL 连续吞吐已通过（`1.088168676x`）；无损候选的 `B3-ACCURACY-GATE` 与 `B3-PL-SPEED-GATE` 已通过，`B3-POWER-MEASURED/B3-POWER-GATE` 保持 OPEN。严格连接级 `2:4`、独立 PL auto-mask 与网口发布是后置支线。

- `B3_MVP_GATE_PASS`：同一份集中 Vivado 2024.1 bitstream（RTL `be84596`，200 MHz FCLK0）上关闭 B3-04/09/11/13/14。WNS=+0.045 ns，TNS=0，WHS=+0.036 ns，THS=0，route/DRC hard errors=0，DSP48E1=4。bit SHA-256=`0ecbe76274c39418f2a60a88358d3ff6f09f5a2ed73a44a3a419c34eb91d3a11`，XSA SHA-256=`135d979d61c629922ee5419e51dd97ef045d9bab79930432816d09f109291d1a`。只可声称 `group_4way` 动态剪枝正确性 + 局部 NPU 周期差值 888 cycles。
- 历史 `B3_SPEED_MEASURED / B3_SPEED_GATE_OPEN`（单样本诊断，现顶层为 `B3-SPEED-GATE=PASS_PURE_PL_ONLY`）：COM15 同源 bit 上 dense/full-open/static/live 已分开 NPU/PS/DMA/Host UART。888 cycle ≈ 4.4 µs，小于 Host live 决策约 996 µs；DMA 包含 NPU、UART 又包含整个流程，字段不可相加。`claim=local_npu_cycle_delta_only`。证据 `artifacts/logs/b3_speed_20260912_be84596/`。
- `PENDING_EPOCH_FROM_MASK_PUBLISHED`：公开 `pending_mask_epoch` 必须来自 `mask_state==MASK_PUBLISHED`。`mask_valid` 只表示已在样本首 beat 激活；commit 后、下一样本前它仍可为 0。B3-11 hold：MASK_COMMIT 后 `active=0 pending=1`；样本后 `active=1 pending=0`。
- `STATUS_BLOCK_0x40430000_FROZEN`：AXI-Lite 只读状态块基址 `0x40430000`。0x00-0x4C 不变；0x50 runtime_status；0x54/0x58 active/pending mask epoch；0x5C last NPU compute cycles；0x60 protocol errors。写请求完成握手并返回 `SLVERR`，不修改状态。
- `B3_LIVE_ENEURON_HOST_GREEN / B3_09_BOARD_PASS`：Host 路径由 `fe25a70` 接通；板级 live 已在 `be84596` bitstream、COM15 上关闭。`eneuron_group4way_live.py` 用 ENeuron S2、gain=1，把每四个 NPU 组当 meta-neuron，量化 0..3 后保留 2 组。live logits=`165,-18,14,0,0,0,0,0,0,153`，execute/skip=`296/296`，`decision_source=live_eneuron_s2`。不是 B3-08b。
- `CHECKOUT_IDENTITY_RUNTIME`：当前 checkout 路径、分支和 HEAD 必须由 Git 命令实时查询；知识库不固定本机工作树路径。
- `DIRTY_WORKTREE_NOT_CLEAN_RELEASE`：`be84596` hw_build_manifest 记录 `git_worktree_clean=false`。下载/签核物理身份是 `be84596`，不得把 dirty tree 回写成 clean release。

B3-02 共享固定向量合同：`tools/repro/b3_fixed_vector_manifest.json` 是 Python loader 与 Host PowerShell/C 头文件生成的单一来源；合同测试共 `6 passed`，因此 B3-02 已关闭。当前冻结 634-word 模型、8-beat 输入、19-word `group_4way` mask 与期望输出，足以进入保存当次产物身份的 `B3-MVP-GATE`；B3-01 的全量发布身份冻结与严格连接级 `2:4` 属于 `B3-STRICT-GATE`。

B3-08a 组级静态 mixed mask 实板子门（2026-09-12）：提交 `73b12c3` 的 `b3_static_mixed` 在同一物理通过 bit/XSA、COM15 上通过，run `20260912T102046Z`，manifest 为 `boards/hellozynq/b2_sw/build/73b12c30baf1507876c6bff01059a2c28c919a8d/direct/runs/20260912T102046Z/run_manifest.json`。结果 logits=`74,-18,14,0,0,0,0,0,0,114`，`fence_snapshot_valid=1`，592 个 `group_4way` 组中 execute/skip=`296/296`。该证据关闭 B3-08a；严格连接级 `2:4` 延后到 STRICT。B3-09 板级 live 已由 `be84596` 关闭。

B3 门禁分层：`B3-MVP-GATE`、QAT CP1 dense、lossless CP3c 和 CP4 已关，CP5b 纯 PL 分布吞吐已通过；当前执行 CP8 paired 功耗。`B3-ACCURACY-GATE`、`B3-PL-SPEED-GATE` 与 `B3-POWER-MEASURED/B3-POWER-GATE` 三者均通过后才关闭 `B3-GOAL-GATE`。`B3-STRICT-GATE` 独立覆盖严格连接级 `2:4`、10000 样本和完整恢复；`B4-RELEASE-GATE` 覆盖网口发布。

B3 execute/skip 计数器前置物理状态（2026-09-12）：第三次 `route_design -directive Explore` 加既有 post-route `AggressiveExplore` 的构建绑定 HEAD `c3a50eb`，在 `xc7z020clg484-2`、200 MHz 下通过物理硬门：`WNS/TNS=+0.008/0 ns`、`WHS/THS=+0.036/0 ns`、setup/hold 失败端点为 0、route errors=0、DRC hard errors=0、DSP48E1=4；bit/XSA SHA-256 分别为 `5c6ebc07…c910a88`/`86288374…177a614`。后续 `be84596` 同源实板已读回 dense/full-open/bypass=`592/0`，并关闭 B3-06/B3-07。

历史 B2-08 状态块覆盖（2026-09-12、B3-MVP 前）：packet smoke 与部分状态读回绑定 HEAD `88bec9e`，计数器前置物理身份绑定 `c3a50eb` bit/XSA；当时的未提交 status probe / 计数器 RTL 不属于签核源码。COM15 已读回 command/sample/response/result=`658/658`、`8/8`、`1/1`、`10 beats/1 packet`，fence snapshot valid。后续 B3-09 与 B3-MVP 已关闭；完整 B2-08 ledger 和 B2-GATE 仍未完成。

历史摘要校正（2026-09-12、B3-MVP 前）：当时仓库 HEAD=`fe25a70`，packet-NPU 200 MHz routed 基线、合法 packet path、dense/full-open/bypass 和 B3-08a 组级 static mixed 已有实板证据，B3-09 仅接通 Host。后续 B3-09 实板和组级 B3-MVP 已关闭；完整 B2-06～B2-10 与 B2-GATE 仍未完成。`f070577`/`88bec9e` 只作历史证据身份。

历史主线（2026-09-12、B3-MVP 前）：部署目标已是 `xc7z020clg484-2`，当时下一步是把 `b3_live_eneuron` ELF 送到已通过物理门的 bit/XSA 上关闭 B3-09；该动作与 epoch、小集合 A/B 后续均已完成。`archive/legacy/` 不参与日常门，旧 `xc7z020clg400-1` 的 NP7/T3 物理证据只作历史参考；B1 高地址 DDR 与 B2-GATE 仍是发布支线缺口。

历史状态更新（2026-09-12、B3-MVP 前）：mask-scan 优化构建绑定 `0f71f49`，packet-NPU 物理基线绑定 `97398bf`/`88bec9e` 的 bit/XSA 身份；packet board smoke、sample/result E2E、八计数器/fence 快照和 `0x40430000` 状态块已有功能/实板部分读回。当时未提交的 status probe / 计数器 RTL 不属于签核源码；后续 live-ENeuron 板级路径已关闭，但这些部分读回仍不等于完整 B2-GATE。

- `ACTIVE_CONTRACT_HIERARCHY`：当前阶段合同为 `docs/planning/NPU_ZYNQ7020_BOARD_VALIDATION_PHASE2_V1.md`；`docs/planning/TODO.md` 的 P16 段、`docs/planning/NPU_PRUNING_TODO.md` 和 `docs/planning/NPU_PRUNING_NP7_TODO.md` 为关联合同，未完成项由脚本实时统计。日常主线是 B3-SPEED/B3-POWER 汇入 B3-GOAL；B2-06～B2-10 与 B2-GATE 仍作为 B4 发布链并行补齐。
- `B1_06B6_UART_BASELINE_PENDING`：当前先按 VID/PID 恢复 CH340 UART 接收基准；此前诊断停在 READY 等待 GO，`command=0`、`completed_accesses=0`，尚未进行 DDR 访问。执行链固定为 B1-06B6 UART 基准 → B1-06B7 OCM 高地址最小复现；B1-06B7 高地址探针必须以后续 UART 基准通过为前提。
- `B1_06B6_COM10_PASSIVE_LISTEN_NO_BYTES`：2026-09-08 按 `VID_1A86:PID_7523` 对 COM10 以 115200 8N1 监听 10 秒，读取 0 字节，未见 `ENEURON_B1B_BEGIN`、`ALIVE` 或 `PASS`；未下载 bitstream/ELF、未发送 GO，DDR access=0。该观察保持 `B1-06B6_UART_BASELINE_PENDING`，不是 DDR 失败证据。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-12
provenance: Git HEAD `fe25a70`、NP4B/NP6/NP7 TODO、工作流状态与已提交 Host/RTL 文件；未提交 RTL 排除在签核源码身份之外

- `B1A_HW_DEFINITION_COMPLETE`：当前身份为`29edf6a...`，UART0使用Bank 33的V14 RX/V15 TX、LVCMOS33并已由最终I/O确认FIXED；bitstream/XSA为`1f98e949...bc5f6`/`ed4a2ff...d417b`。该状态本身不表示整个B1-GATE通过。
- `B1B_UART_LOW_DDR_THREE_COLD_RUNS_PASS / B1B_HIGH_DDR_PENDING`：`bare-metal + lwIP`路线已批准；固定SW/HW/bitstream/XSA/ELF在三次完整断电后通过外置CH340 UART协议和低地址1 MiB DDR九阶段。此前`0x10000000`异常未关闭，不得写成整片DDR、B1B或B1-GATE通过。
- `B2_BACKPRESSURE_FAIL_CLOSED_PROVEN / HISTORICAL_B2_03_B2_05_PENDING`：提交 `e26c7c1` 的旧配置 `0x04000201` 含 period=0；`20260909T063702Z` 的 64/64 PASS 伴随 stall=0，不能作为背压证据。加入零 stall 拒绝后的 `20260909T065258Z` 返回总状态/背压状态 FAIL、`backpressure_failed=1`，证明 fail-closed 生效。该条目的 B2-03/B2-05 pending 是历史时点；当前 packet-NPU 已有合法路径 smoke，但 B2-GATE 与 ENeuron A/B 未关闭，仍不得报告剪枝加速或功耗收益。
- `B2_AXI_VALID_HOLD_FIX_BUILD_BOARD_UART_JTAG_PASS`：当前工作树使用 `0x04030201`，在首个输入后启动 phase，并在已公开 VALID 等待 READY 时冻结 phase；六个 B2 合同测试文件 51/51 通过。最终 Vivado 构建 WNS/WHS=`+0.017/+0.014 ns`；正式 run `20260909T105109Z` 绑定 HEAD `f7f01b0` 与 ELF=`dfe8088a…9082d0`，UART/JTAG 均 PASS，受控背压 `64/64`、failed=0、stall_cycles=83082、S2MM STALL=3。连续回绕切片已另行 BOARD_PASS；B2-03/B2-04/B2-05/B2-GATE 仍待错误/复位恢复和更完整逐帧 PL 观测。

- `B2_CONTINUOUS_WRAP_BOARD_PASS`：提交 `69ed289` 已加入 256 帧连续回绕切片；正式 run `20260909T105109Z`（HEAD `f7f01b0`）在目标板完成 `256/256` 帧、64 个 64-byte slot、`rollovers=3` 及首末地址核对，bit/XSA/ELF 身份已绑定。该切片通过不等于 B2-03/B2-04/B2-05/B2-GATE 整体关闭，错误/复位恢复和更完整逐帧 PL 观测仍待完成。
- `B2_RECOVERY_BOARD_PASS`：recovery run `20260909T110436Z`（HEAD `f7f01b0`）在目标板完成 UART/JTAG/XSCT 恢复，`jtag_recovery_status=2`，timeout/reset/passed/failed=`1/1/1/0`，sequence=`10329`、CRC32=`0xD3E3C978`；manifest SHA-256=`46833A…0922C`，recovery ELF=`f2706099…e0363`，bit/XSA 身份与连续回绕 run 一致。该切片为 `BOARD_PASS`，但 B2-GATE 仍未关闭，间歇/ready 恢复、错误注入和更完整逐帧 PL 观测仍待完成。

- `TICK`：推进一个样本或网络时刻。
- `OBSERVE`/`evidence`：读取已提交学习证据，不读取 live 工作副本。
- `2:4`：每四个连接恰保留两个，提交必须原子完成。
- `issue_mask`：在读取/发射前形成的门控掩码。
- `STATE_CLEAR`：清动态历史但保留剪枝状态。
- `PRUNE_CLEAR`：配置阶段恢复稠密掩码并清 utility。
- `fail-closed`：证据缺失、陈旧或哈希不符时拒绝签核。
- `NP6_PHYSICAL_COST_PARTIAL`：物理成本阶段的正式状态；不是整体时序通过，也不是板级性能结论。
- `NP7`：已合并并签核的共享 BRAM 与共享 lane 阶段；其逻辑/物理证据不能外推为传统 NPU + ENeuron 的集成收益。
- `RTL_DESIGN_REVIEW_WITH_ACTIONS`（历史阶段）：OF4g 修正模型端口冻结边界，`loading/complete` 阻止冻结而 `committed` 允许冻结和推理；OF5 冻结 hard reset 的破坏性清理，丢弃模型/mask/runtime staging、结果与冻结状态并恢复 `epoch=0`、全开 mask、`model_valid=0`。OF6 汇总 OF1-OF5，相关 Python oracle 回归 48/48、CI-Fast 8/8，曾签核合并于 `main@0982ac5`。该阶段的“单时钟 RTL、完整流接口与 Vivado 尚未完成”仅描述当时快照，不覆盖当前 PR #55/OOC 归档状态。
- `VIVADO_OOC_100MHZ_PASS`：当前单时钟 NPU + ENeuron 集成的 OOC 物理状态。V2 绑定 `f744bff`，资源 `2126 LUT / 1916 FF / 0 BRAM / 4 DSP48E1`，100 MHz `WNS=+0.060 ns / TNS=0 / WHS=+0.040 ns`，setup/hold/route/DRC 零失败；不等价于板级签核。
- `DSP_GATE_PASS`：Vivado utilization 为 `DSP=4`，实现网表 `DSP48E1_COUNT=4`，四个 cell 对应 `lane_product_0..3`；只表示强制 DSP 结构合同成立，不代替 setup 签核。
- `TIMING_REPAIR_V1_FUNCTIONAL_GREEN`：TR1-TR6 已实现，共享四 DSP lane、FETCH/EXECUTE/COMMIT、C1-C4、固定 `20×100` 和完整回归均通过；因 setup 失败，该状态不等于物理通过。
- `TIMING_REPAIR_V2_FUNCTIONAL_GREEN`：TR7-TR12 已实施，V2 独立 RED、定向门、固定 `20×100`、完整回归和逐组 WRITEBACK/激活锁存合同均通过；C1-C4 为 `1902/1898/718/1900` 拍。
- `P15_T0_APPROVED / T1_RTL_AUTHORIZED`：方案 A 与 A1-A7 已批准，允许实现纯 RTL wrapper、四条异步 FIFO 和 FIFO 外 AXI-Stream shim；这是实施授权，不是完成证据。当前 T1/T2 仍有全量/外层接口缺口，T3 真实 XPM/xsim 与 XC7Z020 OOC 已签核。
- `T1_PROTOCOL_SLICE_PROVEN / T1_FULL_PENDING`：既有 T1 wrapper、testbench、XPM 仿真模型、manifest 和统一复现入口已进入仓库；T1-02 的 `STATE_CLEAR` exactly-once、`FREEZE_SET` 同步及冻结期间配置拒绝主要路径、T1-06 fence 独立切片，以及 T1-12 四 FIFO 边界切片，已在本机 `e4d48dd` 工作树通过。XPM wrapper 定向回归恢复为 5/5，depth=16+FWFT 的外部可见容量按 17 处理。本机 18 项目标单测与 G0/G1 复现均通过；该状态也不等于 T1-01～T1-12 全量、T2 全矩阵或板级完成。
- `T2_VARIABLE_CLOCK_SLICE_GREEN / T2_CONCURRENT_EPOCH_SLICE_GREEN / T2_EXTENDED_CLOCK_SLICE_GREEN / T2_FIFO_MATRIX_SLICE_GREEN / T2_INTERLEAVE_RESET_SLICE_GREEN`：基础、六组时钟、并发 epoch、FIFO 24/24 scoreboard 和 wrapper 交错/复位 4/4 已分别绑定提交 `a616d60`、`f54e762`、`872fa90`、`ee3a351`、`8457a20`。这些基础切片只证明本机 Icarus/等价模型行为；有限/固定种子随机矩阵与 T3 真实 XPM/OOC 由后续独立条目证明。
- `T2_FINITE_CLOCK_MATRIX_GREEN`：`verify_repository.py --t2-full-matrix` 以 16 组确定性半周期/相位组合复用完整 wrapper 场景并通过；这是有限复现矩阵，不是数学穷举，固定种子随机矩阵已另行通过，仍待更广泛并发交错。
- `T2_RANDOM_CLOCK_MATRIX_GREEN`：`verify_repository.py --t2-random-matrix` 以固定种子 `20260907` 生成 24 个唯一半周期/相位组合并返回 `REPRO_G2_T2_RANDOM_MATRIX_PASS`。结果观察预算按 `2000 + 400 × NPU_HALF` 个 Host 周期缩放，避免慢时钟组合因固定预算过早超时；该状态只证明可复现的有限随机压力集，不代表频率/相位数学穷举。
- `T3_XPM_XSIM_PASS / T3_XC7Z020_OOC_PASS / T3_SIGNOFF_PASS`：真实 AMD XPM/xsim 协同仿真与 `xc7z020clg400-1` OOC 已完成，绑定 Vivado 2024.1、Git HEAD=`c2bc03f`。xsim `RESULT=PASS`，OOC `PHYSICAL_GATE=PASS`；顶层资源为 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`，100 MHz host/npu 双时钟 setup/hold、route、DRC error 均为 0，wrapper 外部 CDC critical/warning 均为 0。XPM 内部 CDC 有 8 个工具 warning，DRC 仅有建议性 warning（DSP 未启用内部流水、无负载提示和 OOC 中未实例化 PS7），不改变 error gate。该签核不覆盖 AXI/DMA/PS7/Ethernet、bitstream、板级 I/O/吞吐、功耗或首次端到端运行。
- `B0_COMPLETE`：当前 bitstream 在同一 target/device 上完成两次program和两次 `PL_LED1/P20` 长窗口测量，中间由JTAG不可访问、可访问器件数0和Vivado `No devices detected`证明完整断电。两次10周期为 `13.42 s`、`13.4 s`，均通过冻结窗口；两次三项DONE均为1且错误位为0，因此B0-GATE通过。
- `P16_B0_COMPLETE / FASTLANE_V1 / B1B_HIGH_DDR_PENDING`：B0已由PR #69进入main。B1拆为B1A/B1B/B1C小PR，按改动运行定向门并复用身份未变的Vivado证据；中间合并不等于B1-GATE通过。当前先关闭B1B高地址DDR边界，再进入B1C。
- `HOST_STATIC_2OF4`：Host 重放冻结的合法 `2:4` mask，用于验证 NPU 门控执行器、mask 位序、epoch 和执行/跳过组计数；不是 ENeuron 自动决策。
- `LIVE_ENEURON`：由当前样本 ENeuron 证据形成组内候选 mask，经 pending bank 与 fence 原子提交，并记录证据、gain、epoch 和生效样本。MVP 使用 `group_4way`；STRICT 才扩展严格连接级 `2:4`。只有实板路径通过才可声称神经元参与局部自动剪枝。Host 合同通过不等于板级通过。
- `LIVE_ENEURON_GROUP_4WAY_HOST`：提交 `fe25a70` 建立 Python/C 现场决策，提交 `82b079e` 用 16 项局部缓存消除 512 次重复 L0 `group_mac`；mask word1=`0x33393335`，logits 与 dense 相同。B3-09 实板已关闭，缓存 ELF 三次板级诊断通过；这仍不是 B3-SPEED-GATE、功耗证据或 B3-08b。
- `T1_NEXT_MINIMAL_SET`：T1-02、T1-06 与 T1-12 已从执行集移出；剩余为 T1-09 的 TLAST 外层 shim/N-A 裁定。若增加外层 shim，需独立验证改变、提前或缺失 TLAST 不改变完整核心结果；若当前 DUT 明确不暴露 TLAST，则记录 N/A 裁定，不得伪造 T1 核心通过。
- `RESOURCE_CUT_DEFERRED_UNTIL_FIRST_END_TO_END_RUN`：资源裁剪候选已完成风险审查，但第一次完整端到端运行成功前不得实施；当前优先以真实 AMD XPM/xsim 和 XC7Z020 OOC 完成 T3 证据，保持功能、CDC、原子性和诊断基线不变。
- `B-V1+V2`：NP7 已批准的单槽弹性流水合同，允许零路径同拍完成及非零结果退出与下一事务接受重叠；其收益只由逐拍账本证明。
- `CI-Fast V1`：按变更路径选择验证范围的 Action 编排；Action 基线已从 `actions/checkout@v4`、`actions/setup-python@v5` 升级为二者 `@v7`（Node 24）。已完成 workflow 全量、文档轻量与 NPU-only 定向路径验证；任何 workflow 变更必须运行全量门，未知代码触发全仓回归，手动运行触发全部专项门。
- `PR Gate`：始终执行的汇总状态；只允许被选专项门 `success` 或 `skipped`，任何失败均拒绝合并。分支保护应只要求该状态。
- `SINGLE_CLOCK_RTL_DECISION_V2`：OF6 后的单时钟 RTL 裁定修订稿。V1 审计暴露了统一命令流中的双 commit 假竞争、未定义 `model_epoch`、样本 framing/首拍 mask 回滚边界、idle 槽位遗漏及过弱随机门槛；V2 固定 8/10 beat 内部计数、删除 `model_epoch`、按单命令流串行化配置、补全 idle 槽位，并恢复 20 个固定 seed × 100 样本门槛。管理员已批准，状态为 `RTL_DESIGN_CONTRACT_V2_APPROVED`；“仅允许 RED/端口骨架，先过 Python/Icarus 逐拍验证，再申请 Vivado”是当时的历史准入规则，当前已推进到 OOC setup 失败与时序修复审核阶段。
- `RTL_SKELETON_IN_PROGRESS`（历史实现阶段）：V2 协议的渐进 RTL 阶段。模型/流、mask epoch、控制三条切片已通过 Icarus；控制切片加入 abort、clear 和严格 idle freeze，冻结仍允许推理但拒绝配置/clear。该状态不代表真实 mask 已控制 MAC，也不包含完整随机逐拍或 Vivado 证据；当前已由 PR #54 的真实计算/随机门和 PR #55 归档的 `VIVADO_OOC_SETUP_FAIL` 证据覆盖。
- `B2_MISSING_TLAST_PASS`：run `20260909T133721Z`（HEAD `b2332a0`）完成 missing-TLAST 错误注入与恢复，observed=`1`，dma_error/reset/recovered/failed=`1/1/1/0`，sequence=`10332/10333`，TLAST=`0/0`、beats=`16/16`；UART/JTAG/XSCT PASS，B2-06/B2-08/B2-GATE 仍未完成。

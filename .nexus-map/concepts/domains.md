# 核心领域概念

B2-08 当前工作树覆盖（2026-09-12）：HEAD=`f070577` 的四流计数、fence 快照和 `0x40430000` 只读 AXI-Lite 状态块已通过功能合同；状态 probe 合同通过；200 MHz routed build 为 `WNS=+0.005 ns/TNS=0/WHS=+0.034 ns/THS=0`、route/DRC hard errors=0。COM15 实板读回 command/sample/response/result=`658/658`、`8/8`、`1/1`、`10 beats/1 packet`，fence snapshot valid；B3 dense 固定向量子门在 `20260912T050553Z` 通过，但 B3-05/06/07、完整 B2-08 ledger、B2-GATE 和 ENeuron A/B 仍未完成。

当前摘要校正（2026-09-12）：仓库 HEAD=`f070577`，P16 当前活动未完成项为 `59`。当前 packet-NPU 200 MHz routed 基线和合法 packet path 已通过；`20260912T040206Z` 完成 `0x40430000` 状态读回，`20260912T050553Z` 完成 B3 dense 固定向量子门。B3-05/06/07、完整 B2-06～B2-10、B2-GATE 和 ENeuron A/B 仍未完成。

当前主线（2026-09-12）：部署目标为 `xc7z020clg484-2`，聚焦 NPU + ENeuron 动态剪枝。`archive/legacy/` 不参与日常门；旧 `xc7z020clg400-1` 的 NP7/T3 物理证据仅作历史参考。B1 高地址 DDR、PHY、UDP 属于板卡资格支线，完整 `B1-GATE` 仍未关闭，但不阻塞低地址 B2-MVP。packet-NPU 合法路径已有实板 smoke，B3 dense 固定向量子门已通过；当前主线是先完成 B3-05 身份核对、B3-06 bypass 对照和 B3-07 full-open 透明性，再接入 Host 静态 mask 与 live-ENeuron A/B，B2-06～B2-10/B2-GATE 发布证据并行补齐。

状态更新（2026-09-12）：mask-scan 优化构建绑定 `0f71f49`，提交态 packet-NPU 物理基线绑定 `97398bf`；后续 packet board smoke 已完成。当前工作树 HEAD=`88bec9e`，B2 packet-NPU 适配器、sample/result E2E、八计数器/fence 快照和 `0x40430000` 状态块功能合同均通过，B2 packet-NPU 合同、状态 probe 和当前物理构建均通过；实板合法路径和 `0x40430000` 部分读回已完成，不是数值 NPU 等价或完整 B2-GATE 证据。

- `ACTIVE_CONTRACT_HIERARCHY`：当前阶段合同为 `docs/planning/NPU_ZYNQ7020_BOARD_VALIDATION_PHASE2_V1.md`；`docs/planning/TODO.md` 的 P16 段、`docs/planning/NPU_PRUNING_TODO.md` 和 `docs/planning/NPU_PRUNING_NP7_TODO.md` 为关联合同。P16 当前活动未完成项为 `59`；当前主线先恢复 B2-08 状态块拓扑的 200 MHz setup 并完成板级读回，再推进 B2-06～B2-10 与 B2-GATE；B2-PHY 已通过。
- `B1_06B6_UART_BASELINE_PENDING`：当前先按 VID/PID 恢复 CH340 UART 接收基准；此前诊断停在 READY 等待 GO，`command=0`、`completed_accesses=0`，尚未进行 DDR 访问。执行链固定为 B1-06B6 UART 基准 → B1-06B7 OCM 高地址最小复现；B1-06B7 高地址探针必须以后续 UART 基准通过为前提。
- `B1_06B6_COM10_PASSIVE_LISTEN_NO_BYTES`：2026-09-08 按 `VID_1A86:PID_7523` 对 COM10 以 115200 8N1 监听 10 秒，读取 0 字节，未见 `ENEURON_B1B_BEGIN`、`ALIVE` 或 `PASS`；未下载 bitstream/ELF、未发送 GO，DDR access=0。该观察保持 `B1-06B6_UART_BASELINE_PENDING`，不是 DDR 失败证据。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-11
provenance: NP4B/NP6/NP7 TODO、工作流状态与 RTL 文件；集成边界来自审核材料包

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
- `LIVE_ENEURON`：由实板 ENeuron 证据形成组内候选和严格 `2:4` mask，经 pending bank 与 fence 原子提交，并记录证据、gain、epoch 和生效样本。只有该路径通过才可声称神经元参与局部自动剪枝。
- `T1_NEXT_MINIMAL_SET`：T1-02、T1-06 与 T1-12 已从执行集移出；剩余为 T1-09 的 TLAST 外层 shim/N-A 裁定。若增加外层 shim，需独立验证改变、提前或缺失 TLAST 不改变完整核心结果；若当前 DUT 明确不暴露 TLAST，则记录 N/A 裁定，不得伪造 T1 核心通过。
- `RESOURCE_CUT_DEFERRED_UNTIL_FIRST_END_TO_END_RUN`：资源裁剪候选已完成风险审查，但第一次完整端到端运行成功前不得实施；当前优先以真实 AMD XPM/xsim 和 XC7Z020 OOC 完成 T3 证据，保持功能、CDC、原子性和诊断基线不变。
- `B-V1+V2`：NP7 已批准的单槽弹性流水合同，允许零路径同拍完成及非零结果退出与下一事务接受重叠；其收益只由逐拍账本证明。
- `CI-Fast V1`：按变更路径选择验证范围的 Action 编排；Action 基线已从 `actions/checkout@v4`、`actions/setup-python@v5` 升级为二者 `@v7`（Node 24）。已完成 workflow 全量、文档轻量与 NPU-only 定向路径验证；任何 workflow 变更必须运行全量门，未知代码触发全仓回归，手动运行触发全部专项门。
- `PR Gate`：始终执行的汇总状态；只允许被选专项门 `success` 或 `skipped`，任何失败均拒绝合并。分支保护应只要求该状态。
- `SINGLE_CLOCK_RTL_DECISION_V2`：OF6 后的单时钟 RTL 裁定修订稿。V1 审计暴露了统一命令流中的双 commit 假竞争、未定义 `model_epoch`、样本 framing/首拍 mask 回滚边界、idle 槽位遗漏及过弱随机门槛；V2 固定 8/10 beat 内部计数、删除 `model_epoch`、按单命令流串行化配置、补全 idle 槽位，并恢复 20 个固定 seed × 100 样本门槛。管理员已批准，状态为 `RTL_DESIGN_CONTRACT_V2_APPROVED`；“仅允许 RED/端口骨架，先过 Python/Icarus 逐拍验证，再申请 Vivado”是当时的历史准入规则，当前已推进到 OOC setup 失败与时序修复审核阶段。
- `RTL_SKELETON_IN_PROGRESS`（历史实现阶段）：V2 协议的渐进 RTL 阶段。模型/流、mask epoch、控制三条切片已通过 Icarus；控制切片加入 abort、clear 和严格 idle freeze，冻结仍允许推理但拒绝配置/clear。该状态不代表真实 mask 已控制 MAC，也不包含完整随机逐拍或 Vivado 证据；当前已由 PR #54 的真实计算/随机门和 PR #55 归档的 `VIVADO_OOC_SETUP_FAIL` 证据覆盖。
- `B2_MISSING_TLAST_PASS`：run `20260909T133721Z`（HEAD `b2332a0`）完成 missing-TLAST 错误注入与恢复，observed=`1`，dma_error/reset/recovered/failed=`1/1/1/0`，sequence=`10332/10333`，TLAST=`0/0`、beats=`16/16`；UART/JTAG/XSCT PASS，B2-06/B2-08/B2-GATE 仍未完成。

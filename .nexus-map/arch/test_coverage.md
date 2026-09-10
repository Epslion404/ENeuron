# 测试面与缺口

状态更正（2026-09-10）：当前仓库 HEAD 为 `bc9ed891a0620a8c1524d14512202eb26d677249`；工作树干净。此前 2026-09-09 条目保留为历史切片说明，其中对 B2-03/B2-04/B2-05 的“未关闭”描述由后续正式边界、压力、背压、回绕、恢复、间歇和 missing-TLAST 证据 supersede。当前测试缺口以 `docs/planning/TODO.md` P16-B2 为准：B2-06/B2-07/B2-08/B2-09/B2-10 与 B2-GATE 尚未完成。最新可复核的 packet-NPU 物理 manifest 绑定 `70e8caf`，响应路径 mask epoch 复制后的 200 MHz setup 仍失败。

TODO 计数更正：`workflow_resume.ps1 -Mode Check` 于 2026-09-10 在 HEAD `bc9ed89` 上报告 `TODO.md:P16=59`；本文其余 `63` 计数均为历史快照。

当前覆盖边界：活动部署目标为 `xc7z020clg484-2`，NPU + ENeuron 动态剪枝证据优先。`archive/legacy/` 材料不参与日常门；旧 `xc7z020clg400-1` NP7/T3 物理结果只作历史参考。B1 高地址 DDR/PHY/UDP 属于板卡资格支线，完整 `B1-GATE` 仍待关闭；低地址窗口满足模型/DMA 容量后可继续 NPU MVP。CH340 以 `VID_1A86:PID_7523` 识别，COM10 仅为现场枚举记录。

合同/统计边界（2026-09-10）：当前阶段合同为 `docs/planning/NPU_ZYNQ7020_BOARD_VALIDATION_PHASE2_V1.md`；P16 TODO、`NPU_PRUNING_TODO.md` 和 `NPU_PRUNING_NP7_TODO.md` 为关联合同，P16 当前活动未完成项为 `59`。当前活动分支为 `codex/b1b-high-ddr-board-repro`、仓库 HEAD=`bc9ed891a0620a8c1524d14512202eb26d677249`。最终 VALID 保持修复的物理门禁已通过（`WNS/WHS=+0.017/+0.014 ns`）；后续正式实板切片已补齐 B2-03/B2-04/B2-05 所需边界、压力、背压、回绕、恢复、间歇和 missing-TLAST 证据。B2-06/B2-07/B2-08/B2-09/B2-10/B2-GATE 仍未关闭，B1 高地址 DDR 访问仍为 0。最新 packet-NPU 构建证据绑定 `70e8caf`，时序失败且尚未上板。

B2 观测器覆盖（2026-09-09）：官方双/单 monitor 的 routed setup 失败分别为 `WNS/TNS=-0.325/-11.113 ns`（127 个端点）和 `-0.284/-22.272 ns`（256 个端点），均不计入正式物理通过。当前工作树覆盖配置 period 非零、zero-stall fail-closed、首个 `input_fire` 启动 phase，以及 `TVALID=1/TREADY=0` 时冻结 phase 保持 VALID/payload；六个 B2 合同测试文件 `51/51` 通过。正式实板 run `20260909T105109Z`（HEAD `f7f01b0`）及 recovery run `20260909T110436Z` 已验证 UART/JTAG/XSCT、受控 S2MM `STALL>0`，并完成连续回绕 `256/256` 帧、`64/64` slot、`rollovers=3`，recovery timeout/reset/passed/failed=`1/1/1/0`、sequence=`10329`、CRC32=`0xD3E3C978`；该切片为 BOARD_PASS，但错误注入、间歇/ready 恢复、更完整逐帧 PL 观测和 B2-03/B2-04/B2-05/B2-GATE 整体关闭仍待完成。

新增监听观察（2026-09-08）：COM10（VID/PID=`VID_1A86:PID_7523`）以 115200 8N1 非侵入式监听 10 秒，读取 0 字节，未收到 `ENEURON_B1B_BEGIN`、`ALIVE` 或 `PASS`；未下载 bitstream/ELF、未发送 GO。该结果维持 `B1-06B6_UART_BASELINE_PENDING`，不构成 DDR 失败或高地址访问证据。

B1B覆盖（2026-09-08）：硬件`29edf6a...`、软件`97ddd1a...`和固定bitstream/XSA/ELF组合完成三次由管理员确认的完整断电冷启动。每轮FPGA配置、ELF下载、COM10 UART begin/end协议、低地址1 MiB DDR九阶段和OCM`status=2/phase=9/fail fields=0`均PASS。覆盖仍不包含`0x10000000`高地址异常、整片DDR容量、PHY、链路或UDP。Hsi检查继续只对临时XSA副本运行。

B1A-HW覆盖（2026-09-08）：干净提交`29edf6a...`的Vivado 2024.1完整构建通过，UART placed IO为Bank 33的V14 INPUT/V15 OUTPUT且均FIXED；资源`136 LUT / 257 FF / 0 BRAM / 0 DSP / 4 BUFG / 1 MMCM`，WNS/WHS=`+0.240/+0.138 ns`，setup/hold失败端点、route error、DRC error/critical warning和RGMII TX缺失output delay均为0。

阶段2 B0校正（2026-09-07）：`xc7z020clg484-2` 最小候选 `df16ed6c...8971` 的实现、两次正式program、两次现场测量和完整断电复测均通过。run-1/run-2的10周期分别为 `13.42 s`、`13.4 s`，均命中 `12.6–14.2 s` 窗口；观察文件SHA-256分别为 `d93bcc25...ab083`、`73c81d86...a25f8`。完整断电探针取得 `target_opened=0`、`accessible_device_count=0` 和Vivado `No devices detected`；run-2恢复后下载前器件为未配置，下载后三项DONE=`1/1/1`且错误位为0。当前覆盖状态为 `B0_COMPLETE`；B1–B4尚未进入实测。

当前校正（2026-09-07）：T3 signoff 已在 `c2bc03f` 重跑并通过；真实 XPM/xsim 与 OOC 摘要均绑定该 HEAD。下方旧快照中的 `822cf93` 不代表当前证据绑定。

当前 T2 增量（2026-09-07）：统一复现入口新增 `--t2-full-matrix`，对 16 组半周期/相位组合运行完整 wrapper 场景并返回 `REPRO_G2_T2_FULL_MATRIX_PASS`。这是有限确定性矩阵，不是频率/相位数学穷举；固定种子随机矩阵已另行通过，仍待更广泛并发交错。

当前 T2 随机矩阵增量（2026-09-07）：统一复现入口 `--t2-random-matrix` 使用固定种子 `20260907` 生成 24 个唯一半周期/相位组合，按 `2000 + 400 × NPU_HALF` 个 Host 周期设置每组观察预算，完整运行后返回 `REPRO_G2_T2_RANDOM_MATRIX_PASS`。该证据记为 `T2_RANDOM_CLOCK_MATRIX_GREEN`，属于可复现的有限随机压力集，不是频率/相位数学穷举。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-10
provenance: repository test names, signoff summaries, workflow state, latest GitHub/Webhook evidence

已覆盖：Python/RTL 协同仿真、有限形式安全与可达性、负向 mutation、Tile/System Vivado OOC、XPM 仿真、NP4B 三模型 60000 事务签核；CI-Fast V1 已完成 workflow 全量、文档轻量和 NPU-only 定向路径验证。CI Action 已升级到 `actions/checkout@v7` 与 `actions/setup-python@v7` 的 Node 24 基线，分类合同要求任何 workflow 变更运行全量门。NPU oracle 新增并通过 `test_zero_activity_with_closed_gate_emits_no_reads_or_macs`、`test_frequent_epoch_switches_never_mix_masks`、`test_pending_slot_backpressure_rejects_overwrite` 三项最坏情况测试。

NP6 结论为部分通过，NP7 已签核。OF1-OF6 Python oracle 保持 48/48。V2 已通过单时钟专项、固定 `20×100` 和完整仓库 `475 tests / OK (skipped=1)`；PR #64 run `33946568679` 的必需门全部成功。Vivado 已确认 4 个 DSP48E1、setup/hold/route/DRC 全部通过；板级性能仍未完成。

P15-T0 方案 A 与 A1-A7 已获批准。既有 T1 wrapper、四条 XPM async FIFO 和复现入口已进入仓库，外层 AXI-Stream shim 尚未实现；T1-12 边界、T1-06 fence、T1-09 N/A 文档与复现扩展已随 `e4d48dd` 纳入基线，T2 参数化可变时钟 testbench 与 `--t2` 入口的基础切片已随 `a616d60` 纳入基线，六组时钟扩展随 `f54e762`，并发 mask epoch 场景随 `872fa90` 纳入。T1 证据覆盖复位、非法字段、模型装载、`STATE_CLEAR`/`FREEZE_SET` 控制、fence 拒绝/成功、固定 8 beat、结果背压和 10 beat 输出等主要路径，另有 T1-12 四 FIFO 边界独立切片（128/128/64/96 bit，depth=16+FWFT 外部容量 17、overflow、回绕和长背压）及 T1-06 独立切片（`T1_FENCE_ACCEPT_PASS`）。T1-09 依据 A2 记录为 `NA_FOR_T1_WRAPPER / OUTER_SHIM_PENDING`，不能外推为当前 TLAST 仿真通过。T2 六组 `(NPU_HALF,PHASE)=(7,2),(9,1),(4,3),(5,0),(11,4),(3,1)` 均输出 `T2_VARIABLE_CLOCKS_PASS`；每组并发 epoch 切片在 `872fa90` 功能基线下通过：epoch=2 在旧样本计算期间发布，旧结果逐 beat 回显 epoch=1，下一 fence 仍回显 active=1，下一样本结果回显 epoch=2。统一入口 `python -X utf8 tools/repro/verify_repository.py --t2` 输出 `REPRO_G2_T2_VARIABLE_CLOCKS_PASS`；这是本机复现的扩展 T2 协同切片，不是数学穷举，也不是 GitHub Actions 结果。T1 全量、更广泛 T2 并发交错、外层 shim、首次端到端和板级验证仍未通过；T3 真实 AMD XPM/xsim 与 `xc7z020clg400-1` OOC 已通过。资源裁剪审查不构成实现证据，且所有裁剪已推迟到第一次完整端到端跑通之后。

FIFO 矩阵切片已提交于 `ee3a351` 并通过 24/24：`tb_xpm_fifo_async_matrix.sv` 固定 8 组时钟/相位（`(2,0)/(3,1)/(4,3)/(5,0)/(7,2)/(9,1)/(11,4)/(13,5)`）× seed `1/7/29`，覆盖填满、排空、随机读写、长背压和中途复位，并对四通道实际写入/读出序列逐项比对。统一入口 `python -X utf8 tools/repro/verify_repository.py --t2-fifo-matrix` 返回 `REPRO_G2_T2_FIFO_MATRIX_PASS`；这只验证 Icarus 等价 FIFO 模型，不是 AMD XPM/xsim 或 T3 证据。

T2 wrapper 交错/复位切片已提交于 `8457a20` 并通过 4/4：`tb_npu_zynq7020_t2_interleave_reset.sv` 固定 `(2,0)/(3,1)/(7,2)/(11,4)` 四组时钟/相位，覆盖命令与样本交错、模型装载中途复位、结果背压期间复位、半帧复位及复位后旧响应/结果清除。统一入口 `python -X utf8 tools/repro/verify_repository.py --t2-interleave-reset` 返回 `REPRO_G2_T2_INTERLEAVE_RESET_PASS`；该结果仅为 Icarus wrapper 切片，不能外推为 T2 全矩阵、AMD XPM/xsim、Vivado T3 或 GitHub Actions 通过。

T2 新增证据已归档：FIFO 矩阵对应 `ee3a351`，wrapper 交错/复位对应 `8457a20`。两者都是本机 Icarus 切片，不改变 T2 全矩阵与 T3 仍待验收的状态。

T3 已完成并通过。真实 AMD XPM/xsim 报告 `vivado_npu_zynq7020_t3_xsim/xsim_signoff_summary.txt` 为 `RESULT=PASS`，绑定 Vivado 2024.1、`xc7z020clg400-1`、`XPM_LIBRARIES=XPM_FIFO`、`REAL_XPM_MODEL=AMD_XPM_FIFO`、HEAD=`c2bc03f`，测试顶层为 `tb_npu_zynq7020_t1_wrapper`。对应 OOC 报告 `vivado_npu_zynq7020_t3_ooc_reports/signoff_summary.txt` 为 `PHYSICAL_GATE=PASS`：顶层资源 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`，host/npu 均 100 MHz，host `WNS=3.639 ns / WHS=0.105 ns`，npu `WNS=0.214 ns / WHS=0.042 ns`，setup/hold failing endpoints、route errors、DRC errors 均为 0，外部 CDC critical/warning 均为 0。XPM 内部 CDC 仍报告 8 个 warning；DRC 有建议性 warning，但没有 error。该 T3 只证明“核心 + 适配器 + 四条真实 XPM 异步 FIFO”的仿真和 OOC，不覆盖 AXI/DMA/PS7/Ethernet、bitstream、板级 I/O/吞吐、功耗或首次端到端运行；Actions 已关闭，远端 checks 为空不作 CI 通过证据。

## 当前签核门（T3 OOC 后）

- 实现与 report head=`f744bff`；C1-C4 的启用组/周期为 `592/1902`、`590/1898`、`0/718`、`591/1900`，逐组 bitmap、模型地址、激活锁存和 WRITEBACK 均通过。
- T3 Vivado 2024.1、`xc7z020clg400-1`、100 MHz 结果为 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`；host `WNS=3.639 ns / WHS=0.105 ns`，NPU `WNS=0.214 ns / WHS=0.042 ns`，setup/hold/route/DRC error 为 0。
- 扩展 50-path 报告中的 22 条 `Slack (VIOLATED)` 已全部核对：14 条经过动态激活选择、DSP48E1 和四乘积求和到 `lane_sum_latched`，8 条从 `compute_group_index` 到 `logit_values` 写使能，不再存在未分类失败端点。外部报告 `eneuron_timing_expand_50.rpt` 的 SHA-256 为 `BE8F1BF268553E9BDAEB31FF7DB348D6F4573011DF6CBDB699D840A71D91F04D`。
- V2 已获 TR7-TR12 批准并完成实施；实施地图为 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V2_IMPLEMENTATION_MAP.md`，KISS 方案复用 signed 32-bit `mac_accumulator`，不新增 `writeback_value_latched`，OOC 已通过。
- T3 真实 XPM/xsim 与 XC7Z020 OOC 已通过；T3 后续缺口是 T1/T2 全量矩阵、外层 AXI-Stream shim、首次完整端到端和板级验证，不得把本次 OOC 结果外推为这些目标已完成。

## V2 审核门（历史/协议背景）

- V2 八项裁定已获管理员批准，曾记录为 `RTL_DESIGN_CONTRACT_V2_APPROVED / RTL_SKELETON_IN_PROGRESS`；该状态属于实现过程历史，当前 RTL 已通过真实计算切片与随机门。
- Python/Icarus、随机逐 beat 和历史 PR 合并门已通过；该条只保留协议背景。当前 TR1-TR6 已实现，新的活动门是 V2 RED、RTL 和功能回归。
- 后续逐拍证据必须覆盖 OF6 确定性边界、统一响应路由、配置/样本背压、freeze/clear/reset、epoch 回绕和负向 mutation；Python 函数级 48/48 不替代这些证据。
# OF6 证据更新（历史记录）

OF4g 修正 `committed` 模型冻结边界，OF5 验证模型/mask/runtime hard reset 丢弃 staging、结果和冻结状态并恢复 `epoch=0`、全开 mask、`model_valid=0`；OF6 对 OF1-OF5 做最终汇总，`test_npu_eneuron_reference.py` 为 48/48、CI-Fast 为 8/8，曾合并至 `main@0982ac5`。该段保留作为协议签核历史；当前权威状态以上方“当前签核门”和 DSP V1 manifest 为准。
B2 missing-TLAST 覆盖（2026-09-09）：正式 run `20260909T133721Z`（HEAD `b2332a0`）在 COM10 实板通过 UART/JTAG/XSCT；missing_tlast observed=1，DMA error/reset/recovered/failed=1/1/1/0，注入/恢复 sequence=10332/10333，MM2S/S2MM TLAST=0/0、beats=16/16，recovery sequence=10329 保持不变。该切片为 `B2_MISSING_TLAST_PASS`，但 B2-06/B2-08/B2-GATE 仍未完成。

B2 packet-NPU 适配器切片（2026-09-09）：提交 `cb9eb66` 的 `b2_npu_packet_adapter.sv` 完成 ingress→T1 wrapper→egress 的 response 基础路径，提交 `62f2d8b` 新增合法 `mask/fence/sample/result` 端到端切片；本机合同测试分别为 4/4、3/3，状态为 `B2_NPU_PACKET_ADAPTER_PASS` 与 `B2_NPU_PACKET_ADAPTER_E2E_PASS`。覆盖仍限于 RTL/Icarus 合同，不是板级证据；B2-07 完整错误矩阵、B2-08 计数账本和 packet path 实板验证仍待完成。

B2 packet 顶层与物理构建边界（2026-09-09）：提交 `ea35d74` 将 `b2_npu_axis_top` 接入 B2 BD，提交 `1d0e3ba` 将源文件固定为 `boards/hellozynq/b2_hw/b2_npu_axis_top.v` 并采用 Verilog BD reference；`test_b2_npu_axis_top_contract.py` 为 3/3。本地 `boards/hellozynq/b2_hw/build/` 现有 bit/XSA/报告仍绑定旧 HEAD `b2332a0`，不是 `1d0e3ba` 后的重建结果；因此只能记录为 `STALE_PRE_PACKET_TOP_BUILD`，不能宣称新 packet-NPU 顶层已通过 `xc7z020clg484-2` 物理门。

B2-07 ingress fail-closed 子门（2026-09-10）：`tb_b2_packet_ingress.sv` 已覆盖坏 magic（错误码 `0x1`）、错误 version（`0x2`）、未知 type（`0x3`）和保留 flags 非零（`0x4`）；四个场景均在帧拒绝后确认无 command/sample/busy 状态泄漏。`test_b2_packet_ingress_contract.py` 为 `4/4 PASS`，T1 复现入口输出 `REPRO_G0_MANIFEST_PASS`、`REPRO_G1_T1_PROTOCOL_SLICE_PASS`。该增量不改变物理边界：新 packet-NPU 顶层仍未完成目标器件 routed timing/DRC、bitstream/XSA 重建或实板验证。

B2 packet-NPU 物理构建（2026-09-10）：HEAD=`1bfeb12`、Vivado 2024.1、`xc7z020clg484-2` 已完成 route 并生成 bit/XSA；route errors=`0`、DRC hard errors=`0`，但 200 MHz `clk_fpga_0` setup 失败，设计时序摘要为 `WNS=-2.750 ns`、`TNS=-8221.926 ns`、`8788` 个失败端点，hold=`WHS=+0.053 ns`、`THS=0`。最差路径为 `egress/response_mem` BRAM `CLKARDCLK`→`egress/crc_state_reg[*]/D`，旧 command FIFO→model staging 路径已不再是最差路径。该构建只能记为 `ROUTED_BIT_XSA_PASS_TIMING_FAIL`；保持槽切片已提交但未签核，不能上板。

B2 packet-NPU egress CRC 分拍后构建（2026-09-10）：HEAD=`8d57e7e` 已完成 route、bit/XSA 和 DRC，`route errors=0`、`DRC hard errors=0`，但 200 MHz setup 失败：`WNS=-1.958 ns`、`TNS=-3308.760 ns`、`5902` 个失败端点，hold=`WHS=+0.055 ns`、`THS=0`。最差路径迁移为 `core/compute_unit_index_reg[0]`→`compute_group_index_reg[2]`，数据延迟 `6.574 ns`，布线占 `5.077 ns`。该构建记为 `ROUTED_BIT_XSA_PASS_TIMING_FAIL`，bit/XSA 不得上板。

B2 packet-NPU 局部 group mask 缓存后构建（2026-09-10）：HEAD=`89cbbf6` 已完成 route、bit/XSA 和 DRC，`route errors=0`、`DRC hard errors=0`，但 200 MHz setup 仍失败：`WNS=-1.168 ns`、`TNS=-1001.103 ns`、`3237` 个失败端点，hold=`WHS=+0.036 ns`、`THS=0`。最差路径为 `compute_unit_index_reg[1]_rep -> model_staging_reg_r1_64_127_9_11/RAMA -> model_word_latched[9] -> lane_product_1/B[1]`，数据延迟 `5.521 ns`，布线占 `4.191 ns`。证据归档于 `artifacts/logs/b2_packet_npu_route_timing_fail_20260910_89cbbf6/`；该构建仍记为 `ROUTED_BIT_XSA_PASS_TIMING_FAIL`，bit/XSA 不得上板。

当前仓库最新完整构建绑定源 HEAD=`0bacdea`，证据归档于 `artifacts/logs/b2_packet_npu_route_timing_fail_20260910_0bacdea/`。route/DRC/bit/XSA 生成成功，但 200 MHz setup 失败（`WNS=-0.489 ns`、`TNS=-121.268 ns`、`885` 个失败端点）；当前 bit/XSA 仅作失败分析，不能写成时序通过或上板输入。

B2 packet-NPU model-write staging 后构建（2026-09-10）：HEAD=`b4b95fa` 已完成 route、bit/XSA 和 DRC，`route errors=0`、`DRC hard errors=0`，但 200 MHz setup 失败：`WNS=-0.589 ns`、`TNS=-45.751 ns`、`363` 个失败端点，hold=`WHS=+0.019 ns`、`THS=0`。最差路径为 `mac_accumulator_reg[0]/C -> mac_accumulator_reg[28]/D`，数据延迟 `5.526 ns`，逻辑 `2.961 ns`、布线 `2.565 ns`。该构建仍为 `ROUTED_BIT_XSA_PASS_TIMING_FAIL`，bit/XSA 不得上板。

B2 packet memory BRAM 化探针（2026-09-10，已归档）：`b2_packet_egress.sv` + `b2_packet_bram.sv` 的 egress OOC 综合报告 `artifacts/logs/b2_packet_memory_ooc_20260910_bram/b2_packet_egress_utilization.rpt` 在 `xc7z020clg484-2` 上给出 `532 LUT / 251 FF / 2 RAMB36 / 1 RAMB18`；层次归因是 `response_mem=2 RAMB36`、`result_mem=1 RAMB18`。相对旧 egress 约 `35944 LUT / 0 BRAM` 的参考，约节省 `35412 LUT`，但尚无完整顶层实现、拥塞或时序结论。ingress 四 bank 改动的报告 `artifacts/logs/b2_packet_memory_ooc_20260910_bram/b2_packet_ingress_utilization.rpt` 为 `2085 LUT / 677 logic LUT / 1408 LUTRAM / 488 FF / 0 BRAM`；因此该改动保留为结构/流水化实验，尚未达到 BRAM 推断目标。`test_b2_packet_memory_inference_contract.py` 是静态结构合同，不证明 Vivado 映射、packet 语义等价或板级行为；尚需运行 ingress/egress 合同回归并在 packet 顶层重建后重新检查 routed timing/DRC。

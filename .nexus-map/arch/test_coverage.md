# 测试面与缺口

> generated_by: nexus-mapper v2 / manual synthesis
> verified_at: 2026-09-16
> provenance: 当前 checkout 路径、分支与提交以 Git 命令实时查询；历史路径、分支和 PR 名称仅作来源。bitstream RTL 身份 `be84596`。证据 `artifacts/logs/b3_mvp_20260912_be84596/`。

## 当前权威覆盖（2026-09-17，CP8 控制链已实现并提交前验证）

器件 `xc7z020clg484-2`。live tree 是本工作树，Git 分支与 HEAD 必须实时查询。B3-MVP-GATE 已在同一份集中 Vivado 2024.1 bitstream 上关闭：RTL 身份 `be84596`，200 MHz FCLK0，WNS=+0.045 ns，TNS=0，WHS=+0.036 ns，THS=0，route/DRC hard errors=0，DSP48E1=4。bit SHA-256=`0ecbe76274c39418f2a60a88358d3ff6f09f5a2ed73a44a3a419c34eb91d3a11`，XSA SHA-256=`135d979d61c629922ee5419e51dd97ef045d9bab79930432816d09f109291d1a`。

B3-11 COM15 hold：MASK_COMMIT 后、下一样本前 `0x54 active=0` / `0x58 pending=1`；样本后 `active=1 pending=0`。pending 必须来自 `mask_state==MASK_PUBLISHED`，不是 `mask_valid`。状态块 `0x40430000`：0x00-0x4C 不变；0x50 runtime_status；0x54/0x58 epoch；0x5C last NPU compute cycles；0x60 protocol errors。

B3-13/14 与历史速度切片保留为旧 fixture 工程证据。QAT CP4 clean 正式对拍完成 397/397 dense/lossless logits 逐元素一致、任务准确率均 88.665%、协议错误 0。CP5a replay 行为、物理门和正式实板已通过；CP5b 397 样本、5 轮纯 PL 分布 replay 亦已通过：dense/lossless 为 `2513.9998/2310.3034 cycles/sample`、吞吐 `1.088168676x`、延迟下降 `8.1025%`，结果帧/logits/CRC 一致、协议错误 0，200 MHz 物理门通过、DSP48E1=4。证据 `artifacts/results/b3_qat_cp5b_pl_distribution_board_pair.json`。`B3-PL-SPEED-GATE=PASS`、顶层 `B3-SPEED-GATE=PASS_PURE_PL_ONLY`；CP4 单样本 packet 路径为 `B3-PACKET-SPEED=MEASURED_WEAK_GAIN_1_008196X`。外部功耗未完成。

CP8 上板前源码闭包补充（2026-09-18）：四态 runner 对所有综合输入继续要求 manifest 字节 SHA 精确匹配；仅非综合 `boards/hellozynq/b2_hw/run_b2_build.ps1` 可在当前 Git clean-filter blob 等于 manifest `git_head:path` blob 时接受回退，并把 `git-blob:` 证明写入 `hardware_source_canonical_fallbacks`。该修复源于 build clean 快照与构建结束源码哈希不原子的时间窗；定向合同 `8 passed`，B2 `129 passed` + T1、`B2_CHECKS_PASS`。

CP8 控制链覆盖（2026-09-17）：`b3_pl_distribution_replay_shim.sv` 的 `CONTINUOUS_REPLAY` 默认 0（CP5b finite 不变），power 模式为 1；`b2_npu_status_probe.v` 唯一可写 `0x74` CP8_CONTROL（READY=`0x43503849`/START=`0x43503853`/RUNNING=`0x43503852`），其余写 SLVERR，AW/W 独立锁存并按 WSTRB 门控；`packet_main.c` 用同一 ELF 经 `0x74` 控制 READY/START/RUNNING，idle 不捕获、full 一次捕获 397 后 PL 持续运行。合同测试 22 passed；B2 全量 129 passed + T1、`B2_CHECKS_PASS`；ARM `B2_PACKET_SW_BUILD_PASS`。DeepSeek 审查发现最后样本 capture 竞态，主代理已加 `wait_cp8_capture_complete` 并复测通过。当前 `CP8_CONTROL_CHAIN_PASS / CP8_PHYSICAL_BUILD_PASS`，尚无实板上板或功耗证据。物理构建覆盖（2026-09-17 clean HEAD `14e8e06`）：dense `build_cp8_dense_14e8e06` 与 lossless `build_cp8_lossless_14e8e06` 两套完整 wrapper 均 PASS（`WNS/TNS/WHS/THS` 分别 `0.01/0/0.036/0` 与 `0/0/0.036/0`、route/DRC=0、signoff=1、DSP=4）；归档证据 `artifacts/logs/b3_cp8_physical_pass_20260917_14e8e06/`，`artifact_sha256.json` 由 Python `hashlib` 复算归档文件、bit 和 XSA。状态 `CP8_CONTROL_CHAIN_PASS / CP8_PHYSICAL_BUILD_PASS`，尚无实板四态控制或功耗证据；下一步先用两套产物完成 dense/lossless idle/full 四态实板控制验证，通过后才开始 B10 至少 5 组交替 paired 功耗测量。此前 HEAD `5c16095` 的 dense PASS / lossless FAIL_CLOSED（`WNS=-0.026`，失败路径 397-sample replay BRAM 到 lossless `core/l0_group_nonzero_reg[*]/D`）已被本次 clean HEAD 重建取代，保留为历史。

B3-09 Host/板级覆盖：`test_eneuron_group4way_live.py` 覆盖每 meta 保留 2/4、粒度、S2 gain 与 live/static 分离；`test_b2_packet_board_contract.py` 冻结 live 标记、禁止静态 mask 表，并检查 L0 dense/evidence 共享 16 项缓存。历史基线已在 `be84596` 关闭；QAT-v3 的 CP0 packing/reference/训练划分合同另由 `test_b3_qat_model_manifest_contract.py` 与 `test_train_qat_split_contract.py` 覆盖，397 样本 standalone PL-auto 仿真为 `397/397`。CP1 dense 已完成 8/64 样本板级逐位对拍，归档于 `artifacts/results/b3_qat_cp1_dense_64_board.json`；当前仍不能把它外推为剪枝精度或 PL-auto 证据。

B3-02 共享固定向量 manifest（2026-09-12）：`test_b3_fixed_vector_manifest_contract.py` 与 `test_b3_fixed_vector_manifest_loader.py` 共 `6 passed`。覆盖目标/schema/634-word 模型、sample ID、8 个输入 beat、dense/full-open/bypass/static mixed 模式、19-word `group_4way` mask、Python 参考输出重建和静态 mixed 组计数；Host PowerShell 读取同一 manifest 并生成 `b3_fixed_vector_generated.h` 的合同也通过。B3-02 已关闭；B3-01 的完整发布身份冻结属于 STRICT，不阻塞保存当次身份的 MVP 实板实验。

B3-08a 覆盖（2026-09-12）：run `20260912T102046Z`、manifest `boards/hellozynq/b2_sw/build/73b12c30baf1507876c6bff01059a2c28c919a8d/direct/runs/20260912T102046Z/run_manifest.json`，同一物理通过 bit/XSA、COM15、`b3_static_mixed` 实板 PASS；logits=`74,-18,14,0,0,0,0,0,0,114`，group_4way execute/skip=`296/296`，fence valid=`1`。该粒度不是严格连接级 `2:4`。严格连接级 `2:4`、10000 样本、完整恢复属于 STRICT；板级功耗目标属于 B3-POWER，网口发布属于 B4。

当前测试分层（2026-09-17）：`B3-MVP-GATE` 已关；`B3-PL-SPEED-GATE` 已由 CP5b 关闭；`B3-POWER-MEASURED/B3-POWER-GATE` 仍开，与 `B3-GOAL-GATE` 共同收口。`B3-STRICT-GATE` 覆盖严格 `2:4`、10000 样本和完整恢复；`B4-RELEASE-GATE` 覆盖网口发布。B2-GATE 的完整错误/复位账本仍开放。CP8 控制链合同已通过；clean HEAD `14e8e06` 的 dense/lossless 两模式物理构建均 PASS（`CP8_PHYSICAL_BUILD_PASS`）；实板四态控制验证与功耗测量待做，通过四态后才开始 B10 至少 5 组交替 paired 测量。

计数器物理覆盖（2026-09-12）：当前下载身份是 `be84596`（WNS=+0.045 ns）。历史 `c3a50eb`（WNS=+0.008 ns）与 `88bec9e` packet smoke 只作前置证据，不覆盖本条。dense/full-open/bypass 实板已读回 execute/skip=`592/0`，B3-00/B3-06/B3-07 已关闭。

历史状态更正（2026-09-12）：当时仓库 HEAD=`fe25a70`。packet smoke 物理身份绑定 `88bec9e9bdbec1de53ef45d2f22e4275308c0237`；`20260912T040206Z` 在 COM15 完成 UART/JTAG/XSCT PASS，634 model words、19 mask words、fence、8-beat sample 和 10-beat result 均通过；状态块读回 command/sample/response/result=`658/658`、`8/8`、`1/1`、`10 beats/1 packet`，fence snapshot valid。该证据仍是合法 packet path 的部分覆盖，不代表 B2-GATE。

TODO 计数更正：`workflow_resume.ps1 -Mode Check` 于 2026-09-10 在 HEAD `bc9ed89` 上报告 `TODO.md:P16=59`；本文其余 `63` 计数均为历史快照。

当前覆盖边界：活动部署目标为 `xc7z020clg484-2`，NPU + ENeuron 动态剪枝证据优先。`archive/legacy/` 材料不参与日常门；旧 `xc7z020clg400-1` NP7/T3 物理结果只作历史参考。B1 高地址 DDR/PHY/UDP 属于板卡资格支线，完整 `B1-GATE` 仍待关闭；低地址窗口满足模型/DMA 容量后可继续 NPU MVP。CH340 以 `VID_1A86:PID_7523` 识别，COM10 仅为现场枚举记录。

历史合同/统计边界（2026-09-12）：当前阶段合同为 `docs/planning/NPU_ZYNQ7020_BOARD_VALIDATION_PHASE2_V1.md`；P16 TODO、`NPU_PRUNING_TODO.md` 和 `NPU_PRUNING_NP7_TODO.md` 为关联合同。当时活动分支为 `codex/b1b-high-ddr-board-repro`。最终 VALID 保持修复的物理门禁已通过（`WNS/WHS=+0.017/+0.014 ns`）；后续正式实板切片已补齐 B2-03/B2-04/B2-05 所需边界、压力、背压、回绕、恢复、间歇和 missing-TLAST 证据。B2-PHY 已关闭，当前缺口为 B2-06/B2-07/B2-08/B2-09/B2-10 与 B2-GATE，B1 高地址 DDR 访问仍为 0。最新 packet-NPU 构建证据绑定 `97398bf`，200 MHz routed timing `WNS=+0.012 ns`、`TNS=0`、`WHS=+0.036 ns`、`THS=0`，route/DRC hard error=0。

B2 观测器历史覆盖（2026-09-09）：官方双/单 monitor 的 routed setup 失败分别为 `WNS/TNS=-0.325/-11.113 ns`（127 个端点）和 `-0.284/-22.272 ns`（256 个端点），均不计入正式物理通过。当时工作树覆盖配置 period 非零、zero-stall fail-closed、首个 `input_fire` 启动 phase，以及 `TVALID=1/TREADY=0` 时冻结 phase 保持 VALID/payload；六个 B2 合同测试文件 `51/51` 通过。正式实板 run `20260909T105109Z`（HEAD `f7f01b0`）及 recovery run `20260909T110436Z` 已验证 UART/JTAG/XSCT、受控 S2MM `STALL>0`，并完成连续回绕 `256/256` 帧、`64/64` slot、`rollovers=3`，recovery timeout/reset/passed/failed=`1/1/1/0`、sequence=`10329`、CRC32=`0xD3E3C978`；该切片为 BOARD_PASS，但更完整错误矩阵和 B2-GATE 仍待完成。

新增监听观察（2026-09-08）：COM10（VID/PID=`VID_1A86:PID_7523`）以 115200 8N1 非侵入式监听 10 秒，读取 0 字节，未收到 `ENEURON_B1B_BEGIN`、`ALIVE` 或 `PASS`；未下载 bitstream/ELF、未发送 GO。该结果维持 `B1-06B6_UART_BASELINE_PENDING`，不构成 DDR 失败或高地址访问证据。

B1B覆盖（2026-09-08）：硬件`29edf6a...`、软件`97ddd1a...`和固定bitstream/XSA/ELF组合完成三次由管理员确认的完整断电冷启动。每轮FPGA配置、ELF下载、COM10 UART begin/end协议、低地址1 MiB DDR九阶段和OCM`status=2/phase=9/fail fields=0`均PASS。覆盖仍不包含`0x10000000`高地址异常、整片DDR容量、PHY、链路或UDP。Hsi检查继续只对临时XSA副本运行。

B1A-HW覆盖（2026-09-08）：干净提交`29edf6a...`的Vivado 2024.1完整构建通过，UART placed IO为Bank 33的V14 INPUT/V15 OUTPUT且均FIXED；资源`136 LUT / 257 FF / 0 BRAM / 0 DSP / 4 BUFG / 1 MMCM`，WNS/WHS=`+0.240/+0.138 ns`，setup/hold失败端点、route error、DRC error/critical warning和RGMII TX缺失output delay均为0。

阶段2 B0校正（2026-09-07）：`xc7z020clg484-2` 最小候选 `df16ed6c...8971` 的实现、两次正式program、两次现场测量和完整断电复测均通过。run-1/run-2的10周期分别为 `13.42 s`、`13.4 s`，均命中 `12.6–14.2 s` 窗口；观察文件SHA-256分别为 `d93bcc25...ab083`、`73c81d86...a25f8`。完整断电探针取得 `target_opened=0`、`accessible_device_count=0` 和Vivado `No devices detected`；run-2恢复后下载前器件为未配置，下载后三项DONE=`1/1/1`且错误位为0。当前覆盖状态为 `B0_COMPLETE`；B1–B4尚未进入实测。

当前校正（2026-09-07）：T3 signoff 已在 `c2bc03f` 重跑并通过；真实 XPM/xsim 与 OOC 摘要均绑定该 HEAD。下方旧快照中的 `822cf93` 不代表当前证据绑定。

当前 T2 增量（2026-09-07）：统一复现入口新增 `--t2-full-matrix`，对 16 组半周期/相位组合运行完整 wrapper 场景并返回 `REPRO_G2_T2_FULL_MATRIX_PASS`。这是有限确定性矩阵，不是频率/相位数学穷举；固定种子随机矩阵已另行通过，仍待更广泛并发交错。

当前 T2 随机矩阵增量（2026-09-07）：统一复现入口 `--t2-random-matrix` 使用固定种子 `20260907` 生成 24 个唯一半周期/相位组合，按 `2000 + 400 × NPU_HALF` 个 Host 周期设置每组观察预算，完整运行后返回 `REPRO_G2_T2_RANDOM_MATRIX_PASS`。该证据记为 `T2_RANDOM_CLOCK_MATRIX_GREEN`，属于可复现的有限随机压力集，不是频率/相位数学穷举。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-12
provenance: 2026-09-12 的仓库测试名、signoff summaries 与 workflow state 历史核对；当前 checkout 身份必须由 Git 命令实时查询

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

B2 packet-NPU 适配器切片（2026-09-09）：提交 `cb9eb66` 的 `b2_npu_packet_adapter.sv` 完成 ingress→T1 wrapper→egress 的 response 基础路径，提交 `62f2d8b` 新增合法 `mask/fence/sample/result` 端到端切片；本机合同测试分别为 4/4、3/3，状态为 `B2_NPU_PACKET_ADAPTER_PASS` 与 `B2_NPU_PACKET_ADAPTER_E2E_PASS`。覆盖仍限于 RTL/Icarus 合同，不是板级证据；B2-07 完整错误矩阵和 packet path 实板验证仍待完成。

B2-08 四流计数器/快照子门（2026-09-11，工作树 `88bec9e`）：adapter 计数、fence 快照及 `0x40430000` 只读 AXI-Lite 状态块仿真通过；统一检查全部 B2 合同 `117 passed`、T1 两门 PASS。错误响应候选统一锁存后的完整 Vivado 重建消除了 `cmd_hold_data -> rsp_payload_reg/CE` 和 `/R` 失败族；最终 `WNS=-0.030 ns/TNS=-0.203 ns/WHS=+0.036 ns/THS=0`，route/DRC hard errors=0、`B2_SIGNOFF_PASS=0`，因此板级读回仍 pending。当前最差路径为 egress `mask_epoch -> payload_word_count/R`。

B2 packet 顶层与物理构建边界（2026-09-09）：提交 `ea35d74` 将 `b2_npu_axis_top` 接入 B2 BD，提交 `1d0e3ba` 将源文件固定为 `boards/hellozynq/b2_hw/b2_npu_axis_top.v` 并采用 Verilog BD reference；`test_b2_npu_axis_top_contract.py` 为 3/3。本地 `boards/hellozynq/b2_hw/build/` 现有 bit/XSA/报告仍绑定旧 HEAD `b2332a0`，不是 `1d0e3ba` 后的重建结果；因此只能记录为 `STALE_PRE_PACKET_TOP_BUILD`，不能宣称新 packet-NPU 顶层已通过 `xc7z020clg484-2` 物理门。

B2-07 ingress fail-closed 子门（2026-09-10）：`tb_b2_packet_ingress.sv` 已覆盖坏 magic（错误码 `0x1`）、错误 version（`0x2`）、未知 type（`0x3`）和保留 flags 非零（`0x4`）；四个场景均在帧拒绝后确认无 command/sample/busy 状态泄漏。`test_b2_packet_ingress_contract.py` 为 `4/4 PASS`，T1 复现入口输出 `REPRO_G0_MANIFEST_PASS`、`REPRO_G1_T1_PROTOCOL_SLICE_PASS`。该增量不改变物理边界：新 packet-NPU 顶层仍未完成目标器件 routed timing/DRC、bitstream/XSA 重建或实板验证。

B2 packet-NPU 物理构建（2026-09-10）：HEAD=`1bfeb12`、Vivado 2024.1、`xc7z020clg484-2` 已完成 route 并生成 bit/XSA；route errors=`0`、DRC hard errors=`0`，但 200 MHz `clk_fpga_0` setup 失败，设计时序摘要为 `WNS=-2.750 ns`、`TNS=-8221.926 ns`、`8788` 个失败端点，hold=`WHS=+0.053 ns`、`THS=0`。最差路径为 `egress/response_mem` BRAM `CLKARDCLK`→`egress/crc_state_reg[*]/D`，旧 command FIFO→model staging 路径已不再是最差路径。该构建只能记为 `ROUTED_BIT_XSA_PASS_TIMING_FAIL`；保持槽切片已提交但未签核，不能上板。

B2 packet-NPU egress CRC 分拍后构建（2026-09-10）：HEAD=`8d57e7e` 已完成 route、bit/XSA 和 DRC，`route errors=0`、`DRC hard errors=0`，但 200 MHz setup 失败：`WNS=-1.958 ns`、`TNS=-3308.760 ns`、`5902` 个失败端点，hold=`WHS=+0.055 ns`、`THS=0`。最差路径迁移为 `core/compute_unit_index_reg[0]`→`compute_group_index_reg[2]`，数据延迟 `6.574 ns`，布线占 `5.077 ns`。该构建记为 `ROUTED_BIT_XSA_PASS_TIMING_FAIL`，bit/XSA 不得上板。

B2 packet-NPU 局部 group mask 缓存后构建（2026-09-10）：HEAD=`89cbbf6` 已完成 route、bit/XSA 和 DRC，`route errors=0`、`DRC hard errors=0`，但 200 MHz setup 仍失败：`WNS=-1.168 ns`、`TNS=-1001.103 ns`、`3237` 个失败端点，hold=`WHS=+0.036 ns`、`THS=0`。最差路径为 `compute_unit_index_reg[1]_rep -> model_staging_reg_r1_64_127_9_11/RAMA -> model_word_latched[9] -> lane_product_1/B[1]`，数据延迟 `5.521 ns`，布线占 `4.191 ns`。证据归档于 `artifacts/logs/b2_packet_npu_route_timing_fail_20260910_89cbbf6/`；该构建仍记为 `ROUTED_BIT_XSA_PASS_TIMING_FAIL`，bit/XSA 不得上板。

当前仓库最新完整构建绑定源 HEAD=`2f2ce03`，证据归档于 `artifacts/logs/b2_packet_npu_route_timing_fail_20260910_2f2ce03/`。route/DRC/bit/XSA 生成成功，但 200 MHz setup 失败（`WNS=-0.279 ns`、`TNS=-8.283 ns`、`141` 个失败端点，`WHS=+0.036 ns`、`THS=0`）；最差路径为 `output_index_reg[3]/C -> response_mem/ENARDEN`。该 bit/XSA 标记为 `analysis_only_no_download`，不能写成时序通过或上板输入。

B2 packet-NPU model-write staging 后构建（2026-09-10）：HEAD=`b4b95fa` 已完成 route、bit/XSA 和 DRC，`route errors=0`、`DRC hard errors=0`，但 200 MHz setup 失败：`WNS=-0.589 ns`、`TNS=-45.751 ns`、`363` 个失败端点，hold=`WHS=+0.019 ns`、`THS=0`。最差路径为 `mac_accumulator_reg[0]/C -> mac_accumulator_reg[28]/D`，数据延迟 `5.526 ns`，逻辑 `2.961 ns`、布线 `2.565 ns`。该构建仍为 `ROUTED_BIT_XSA_PASS_TIMING_FAIL`，bit/XSA 不得上板。

B2 packet memory BRAM 化探针（2026-09-10，已归档）：`b2_packet_egress.sv` + `b2_packet_bram.sv` 的 egress OOC 综合报告 `artifacts/logs/b2_packet_memory_ooc_20260910_bram/b2_packet_egress_utilization.rpt` 在 `xc7z020clg484-2` 上给出 `532 LUT / 251 FF / 2 RAMB36 / 1 RAMB18`；层次归因是 `response_mem=2 RAMB36`、`result_mem=1 RAMB18`。相对旧 egress 约 `35944 LUT / 0 BRAM` 的参考，约节省 `35412 LUT`，但尚无完整顶层实现、拥塞或时序结论。ingress 四 bank 改动的报告 `artifacts/logs/b2_packet_memory_ooc_20260910_bram/b2_packet_ingress_utilization.rpt` 为 `2085 LUT / 677 logic LUT / 1408 LUTRAM / 488 FF / 0 BRAM`；因此该改动保留为结构/流水化实验，尚未达到 BRAM 推断目标。`test_b2_packet_memory_inference_contract.py` 是静态结构合同，不证明 Vivado 映射、packet 语义等价或板级行为；尚需运行 ingress/egress 合同回归并在 packet 顶层重建后重新检查 routed timing/DRC。

B2 packet-NPU 最新物理覆盖（2026-09-10）：`074ed56` egress BRAM 预取重建完成 route、bit/XSA 和 DRC，但 200 MHz setup 失败（`WNS=-0.052 ns`、`TNS=-0.134 ns`、6 个失败端点，`WHS=+0.073 ns`、`THS=0`）；最差路径为 `compute_unit_mask_latched_reg[3]/C -> compute_group_index_reg[1]/D`。该结果只更新失败分析证据，不改变 B2-06/B2-GATE 或 ENeuron A/B 的未完成状态。

# CP8 timing 合同与工作树候选（历史状态，2026-09-17 HEAD e8846a2，已被 14e8e06 取代）

历史状态 HEAD=`e8846a2`：当时 CP8 工作树候选（`b3_pl_distribution_replay_shim.sv` 的 `READ_LATENCY_B` 1→2、`STATE_REPLAY_PREFETCH_READY`、`replay_beat + 3`，以及 `build_b2.tcl` 暂改 `Performance_ExploreWithRemap`）已通过定向合同 `20 passed, 1 skipped`；完整 B2 `129 passed`、T1 PASS、`B2_CHECKS_PASS`；候选未提交、未做 clean HEAD 物理重建，当时仍没有物理时序证据。当时正式 CP8 lossless 构建仍 `FAIL_CLOSED`：`WNS=-0.067 ns`、`TNS=-0.080 ns`（含 `Performance_ExtraTimingOpt` clean build）；`ExplorePostRoute` probe 也失败（`WNS=-0.088 ns`、`TNS=-0.339 ns`），不得称为正式签核。历史状态：当时为 `CP8_CONTROL_CHAIN_PASS / CP8_PHYSICAL_BUILD_PENDING / B3-POWER-GATE=OPEN`；该 pending 已被 clean HEAD `14e8e06` 的 `CP8_PHYSICAL_BUILD_PASS` 取代。当时下一步：提交候选修复，在 clean HEAD 优先正式重建 lossless；通过后再重建 dense；两者都过 200 MHz `xc7z020clg484-2` 时序且 `DSP=4` 后才可四态上板。该重建已由 clean HEAD `14e8e06` 完成，两模式均通过。

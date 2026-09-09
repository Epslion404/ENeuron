# Git 热点

当前门禁边界（中等精简）：`xc7z020clg484-2` NPU + ENeuron 动态剪枝为活动主线；`archive/legacy/` 不触发日常 CI/PR 门。旧 `xc7z020clg400-1` 的 NP7/T3 物理材料仅作历史参考。B1 高地址 DDR、PHY、UDP 是板卡资格支线，仍阻塞板级 `B1-GATE`，但不阻塞低地址容量满足条件下的 NPU MVP；CH340 按 `VID_1A86:PID_7523` 查找而非固定 COM 号。

当前合同层级为阶段合同 `NPU_ZYNQ7020_BOARD_VALIDATION_PHASE2_V1.md`，中等精简后的 P16 TODO 当前活动计数为 `63`；P16-E 公共证据合同和 P16-S 统一停止条件为常驻合同，不计入一次性计数。NP8 是 `DEFERRED_OPTIONAL`，NP9 已并入 P16 的 B2/B3/B4。B2-00 地址布局、B2-D1 DMA 控制和 B2-01 buffer/所有权合同均已冻结，B2 loopback 拓扑和 standalone polling 软件已在 HEAD `bba0936` 完成同源构建；最新证据目录 `boards/hellozynq/b2_sw/build/6f3d40e6f0470bbb57a9a10fb107ffc892add25c/direct/runs/20260909T022102Z/` 已记录 8 帧边界矩阵（7 PASS、1 拒绝、0 失败）和 10000 帧确定性压力（10000 PASS、0 失败、CRC32 XOR=`0x7D51FB01`），UART 为 `COM10:NO_TERMINAL_MARKER`，主线仍需收口 B2-03 的 PL/帧完整性、受控背压和错误恢复。B1 高地址 DDR/PHY/UDP 仅为板卡资格支线。当前活动分支精确 HEAD 以 Git 与 `workflow_resume.ps1 -Mode Check` 为准；B1 诊断执行链仍为 B1-06B6 UART 基准 → B1-06B7 OCM 高地址最小复现，既有诊断未发送 GO，DDR 访问数为 0。

B2-00 已形成可复现的低地址布局合同：窗口 `[0x01000000,0x01100000)`，9 个 4 KiB 区域、总保留 `36 KiB`，最大 DMA frame `4096` bytes；`verify_b2_dma_address_layout.py` 输出 `B2_DMA_LAYOUT_PASS`。状态为 `B2_00_LOW_ADDRESS_LAYOUT_FROZEN`，已进入 B2-D1/loopback 软件执行链。`B1_HIGH_DDR_PENDING` 保持不变，B2-00 不等同于高地址 DDR 或完整 B1-GATE 通过。

B2 loopback Vivado 构建与实板边界/压力已完成：目标 `xc7z020clg484-2`，构建 HEAD `bba093603d501f157169f3c321fb77a62fcf4406` 的 post-route `WNS/WHS=+0.240/+0.036 ns`、`TNS/THS=0/0`、route/DRC error=0，并已生成 bit/XSA（SHA-256=`d694fa02e0e6b5d25dfc72becc302104632268b4dc930b8709780dbebb08d918`/`68dc2b8e0c4e324bc1bacccdecfa384100042f10a94fae9f43d3a1b2b021897a`）；Vitis 2024.1 `axidma_v9_18` standalone 软件压力运行 ELF SHA-256=`b1b8cbc6c8ff262b8764403453c1269b1a5be3b1b39aacdb244c35616de0e79b`。最新证据目录 `boards/hellozynq/b2_sw/build/6f3d40e6f0470bbb57a9a10fb107ffc892add25c/direct/runs/20260909T022102Z/` 的 JTAG ledger 已证明 `0/1/4/16/64/512/1472/4096` bytes 共 8 帧（7 PASS、1 拒绝、0 失败）及 10000 帧确定性压力（10000 PASS、0 失败、CRC32 XOR=`0x7D51FB01`、最后 sequence=`10008`）；UART 为 `COM10:NO_TERMINAL_MARKER`。PL 流计数、TKEEP/TLAST、受控背压、连续回绕和错误恢复仍未覆盖，当前主线执行点为 `B2-03` 完整性收口，`B1_HIGH_DDR_PENDING` 保持不变。

B2 monitor 时序实验与 probe 收敛（2026-09-09）：双 `axi_stream_monitor:1.1` routed setup 失败（`WNS=-0.325 ns`、`TNS=-11.113 ns`、127 个 setup 失败端点），单 monitor 仍失败（`WNS=-0.284 ns`、`TNS=-22.272 ns`、256 个 setup 失败端点）；均为历史实验产物，不可替代正式 B2 物理基线。当前 Tcl/BD 已切换到自有轻量 `axis_stream_probe` 双向 sampler，控制互连 `NUM_MI=3`、AXI-Lite 基址 `0x40410000/0x40420000`，`test_b2_stream_monitor_contract.py` 为 `5/5`、`test_b2_stream_probe_contract.py` 为 `3/3`；新拓扑尚未重建 bit/XSA 或上板。

功能证据校正（2026-09-07，T3=`c2bc03f`，T2 随机矩阵=`ee6c25a`）：PR #64 已合并为 `main@a53a040`；V2 OOC 报告绑定 `f744bff`，GitHub Actions 已关闭。PR #68 的 `55ec08e`/run `33976357259` 是历史可追溯审计快照，不是当前值。P15-T0 的 A1-A7 已获管理员批准，当前为 `P15_T0_APPROVED / T1_RTL_AUTHORIZED / T1_PROTOCOL_SLICE_PROVEN / T1_FULL_PENDING / T2_VARIABLE_CLOCK_SLICE_GREEN / T2_CONCURRENT_EPOCH_SLICE_GREEN / T2_EXTENDED_CLOCK_SLICE_GREEN / T2_FINITE_CLOCK_MATRIX_GREEN / T2_RANDOM_CLOCK_MATRIX_GREEN / T2_FULL_MATRIX_PENDING / T3_XPM_XSIM_PASS / T3_XC7Z020_OOC_PASS / T3_SIGNOFF_PASS`；T3 报告绑定 Vivado 2024.1、`xc7z020clg400-1`、真实 AMD XPM/xsim、顶层 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`、外部 CDC=0、100 MHz setup/hold/route/DRC error=0。T2 功能证据分层绑定为基础切片 `a616d60`、六组扩展 `f54e762` 和并发 epoch 场景 `872fa90`，文档状态同步为 `af520b2`/`1a3c371`/`8eab78e`；统一入口的 T1/T2 通过标记仍仅是本机复现证据，不能写成 CI 通过。T1-09 已记录为 `NA_FOR_T1_WRAPPER / OUTER_SHIM_PENDING`；资源裁剪已记录但推迟至首次完整端到端运行成功后。

T3 权威报告：`vivado_npu_zynq7020_t3_xsim/xsim_signoff_summary.txt` 为 `RESULT=PASS`，`vivado_npu_zynq7020_t3_ooc_reports/signoff_summary.txt` 为 `PHYSICAL_GATE=PASS`。OOC 的 XPM 内部 CDC warning=8 和 DRC 建议性 warning 已与外部 error gate 分开记录；不覆盖 AXI/DMA/PS7/Ethernet、板级 I/O/吞吐、功耗或首次端到端运行。

已提交 `tb_xpm_fifo_async_matrix.sv`（`ee3a351`） 及 `--t2-fifo-matrix` 复现入口：8 组 `(NPU_HALF,PHASE)`×3 个固定 seed 共 24 次，四通道逐序列 scoreboard 均通过，摘要标记为 `REPRO_G2_T2_FIFO_MATRIX_PASS`。该证据绑定已提交 Git commit；它来自 Icarus 等价 FIFO 模型，不是 AMD XPM/xsim 或 Actions 结果。T3 真实 XPM/xsim/OOC 已另行签核，但该切片仍不能清除 `T2_FULL_MATRIX_PENDING`。

已提交 `tb_npu_zynq7020_t2_interleave_reset.sv`（`8457a20`） 及 `--t2-interleave-reset` 复现入口：`(2,0)/(3,1)/(7,2)/(11,4)` 四组配置全部通过，摘要标记为 `REPRO_G2_T2_INTERLEAVE_RESET_PASS`。该证据绑定已提交 Git commit，验证的是 Icarus wrapper 交错/复位切片；它不是 T2 全矩阵、AMD XPM/xsim 或 Actions 结果。T3 真实 XPM/xsim/OOC 已另行签核，但该切片仍不能清除 `T2_FULL_MATRIX_PENDING`。

2026-09-07 归档校正：T2 FIFO 矩阵已提交 `ee3a351`，wrapper 交错/复位切片已提交 `8457a20`；原有“工作树候选”文字为提交前快照，不是当前状态。

2026-09-07 T2 固定种子随机矩阵：证据提交 `ee6c25a` 的入口 `--t2-random-matrix` 以种子 `20260907` 生成 24 个唯一 `(NPU_HALF,NPU_PHASE)` 组合；每组观察预算为 `2000 + 400 × NPU_HALF` 个 Host 周期，结果 `REPRO_G2_T2_RANDOM_MATRIX_PASS`，状态为 `T2_RANDOM_CLOCK_MATRIX_GREEN`。该记录是可复现有限压力证据，不得解释为频率/相位数学穷举或 GitHub Actions 结果。

## V2 历史审计快照（2026-09-05）

该审计快照中 PR #68 为 `OPEN / MERGEABLE / UNSTABLE`。Actions run `33976357259` 在 runner 启动前因账户付款/额度限制阻断，归类为 `NOT_RUN_BILLING_BLOCKED`，不能视为代码失败或通过；仓库外 webhook 已收到同一 SHA 的 `workflow_run completed/failure`，但签名未验证，GitHub Checks/API 为权威来源。2026-09-06 chmlfrp 恢复后，本地/公网 health 均为 200，GitHub 官方 ping delivery `ee543f6e-aa08-11f1-84fd-d4849c4dec76` 返回 200 并写入接收器。V2 OOC 仍绑定 `f744bff2bdde68e138a7b2b348ce103bec1ab469`，资源为 `2126 LUT / 1916 FF / 4 DSP48E1`，100 MHz setup/hold/route/DRC 全部通过；TR7-TR12 已批准。P15-T0 方案 A 和 A1-A7 已批准；T1 协议切片已进入仓库并可由本地 G0/G1 复现，但 T1 全量、T2/T3 仍待证据。当前 PR #68 head=`3006174` 对应 run `34051222089`，GitHub Checks 显示 `Classify changes=fail`、`PR Gate=fail`、`T1 reproducibility slice=skipped`；不得把本地协议切片 PASS 写成 GitHub CI PASS。资源裁剪候选不得在首次完整端到端跑通前实施。用户文件 `np75_tmp_sparse_protocol.ys` 继续排除在提交和 Nexus 文件树之外。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-09
provenance: `.nexus-map/raw/git_stats.json`（最后提交于 `c46320e`；仓库内未发现可复现生成脚本，后续基线由 Git 与 manifest 人工核对）

最近一次 raw 探针快照统计 263 次提交、5 位作者；该数字只代表 `c46320e` 时点。PR #62 已合并为 `main@e8dc947`（merge commit `e8dc9477dbfc7a9311dd00c514a986580ad2b84b`），最终 HEAD `a4832cc3bddd96ba2f94c295ae99c1d12713abf3` 的 Actions run `33915028445` 为 success；Webhook 收到同 SHA，但 `signature_verified=false`，只作到达通知。DSP V1 实现与 OOC report head 为 `5055073`：恰好 4 个 DSP48E1，功能、固定 `20×100` 随机、完整回归、hold/route/DRC 已通过，但 100 MHz setup `WNS=-0.673 ns / TNS=-6.462 ns / 22` 个端点失败。热点已从 V2 审核切换为 V2 实施；实施地图为 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V2_IMPLEMENTATION_MAP.md`，KISS 方案复用 signed 32-bit `mac_accumulator`，不新增 `writeback_value_latched`，仅预计新增四个 signed 8-bit 激活锁存器（约 32 FF）。TR7-TR12 已批准，当前计算 RTL 进入 V2 RED→RTL→回归流程。`np75_tmp_sparse_protocol.ys` 是用户未跟踪文件，不得纳入提交或 Nexus；物理结果不得外推为板级吞吐、功耗或网络性能。

# Git 热点

> generated_by: nexus-mapper v2 / manual synthesis
> verified_at: 2026-09-13
> provenance: 当前 checkout 路径、分支与提交必须由 Git 命令实时查询；历史路径、分支和 PR 名称只作来源。bitstream RTL 身份 `be84596`，raw `git_stats.json` 绑定历史 `c46320e`。

## 当前权威取证（2026-09-13）

当前 checkout 身份以 `git rev-parse --show-toplevel`、`git branch --show-current` 和 `git rev-parse HEAD` 的实时输出为准；PR #88 只是历史来源。下载/签核物理身份仍是 `be845965d7df8b4018e6b32b8b5b4e350fb0488a`（`feat(board): fail-closed B3-04 DSP48E1 count of 4`），不随仓库 HEAD 前移。PR #93 合入 L0 contribution 缓存 Host 诊断（三次同 bit 板级 `ps_us=827/829/828`），证据 `artifacts/logs/b3_live_l0_cache_20260913_82b079e/`。只证明冻结样本 Host 决策成本下降，不关闭 B3-SPEED-GATE / B3-POWER / B3-GOAL。

同一份集中 Vivado 2024.1 bitstream：`xc7z020clg484-2`、200 MHz FCLK0，WNS=+0.045 ns，TNS=0，WHS=+0.036 ns，THS=0，route/DRC hard errors=0，DSP48E1=4。bit SHA-256=`0ecbe76274c39418f2a60a88358d3ff6f09f5a2ed73a44a3a419c34eb91d3a11`，XSA SHA-256=`135d979d61c629922ee5419e51dd97ef045d9bab79930432816d09f109291d1a`。hw_build_manifest 记录 `git_worktree_clean=false`，不得把 dirty tree 回写成 clean release。证据 `artifacts/logs/b3_mvp_20260912_be84596/`。

B3-MVP-GATE 已关。COM15 CH340 `VID_1A86:PID_7523`。B3-11 hold：MASK_COMMIT 后 `active=0 pending=1`，样本后 `active=1 pending=0`。四模式 A/B 两轮一致：dense/full-open 592/0、2494 cycles；static mixed 296/296、1606 cycles、`host_replay_static_mixed`；live-ENeuron 296/296、1606 cycles、`live_eneuron_s2`。只可声称 `group_4way` 动态剪枝正确性 + 局部 NPU 周期差值 888 cycles。不可声称网口加速、测得功耗、严格 `2:4`、B2-GATE。

前置 Host 提交 `fe25a70` 只改 Host/manifest/文档，不含生产 RTL。历史 packet smoke `88bec9e`/`97398bf` 与计数器 `c3a50eb` 只描述当时产物。后文若仍写 B3-09 实板 pending 或未提交 status probe 为唯一身份，以本条为准。

当前门禁边界（中等精简）：`xc7z020clg484-2` 板上 packet-NPU + ENeuron 组级动态剪枝为活动主线；`archive/legacy/` 不触发日常 CI/PR 门。旧 `xc7z020clg400-1` 的 NP7/T3 物理材料仅作历史参考。B1 高地址 DDR、PHY、UDP 仍阻塞完整 `B1-GATE`。CH340 按 `VID_1A86:PID_7523` 查找；双设备时必须显式 COM15。

当前合同层级为阶段合同 `NPU_ZYNQ7020_BOARD_VALIDATION_PHASE2_V1.md`。日常主线是 `B3-SPEED-GATE` 与 `B3-POWER-GATE`，共同汇入 B3-GOAL；B3-STRICT（lane 2:4、10k 样本）独立，B2-GATE 挡 B4 网口发布。

B2-00 已形成可复现的低地址布局合同：窗口 `[0x01000000,0x01100000)`，9 个 4 KiB 区域、总保留 `36 KiB`，最大 DMA frame `4096` bytes；`verify_b2_dma_address_layout.py` 输出 `B2_DMA_LAYOUT_PASS`。状态为 `B2_00_LOW_ADDRESS_LAYOUT_FROZEN`，已进入 B2-D1/loopback 软件执行链。`B1_HIGH_DDR_PENDING` 保持不变，B2-00 不等同于高地址 DDR 或完整 B1-GATE 通过。

B2 loopback身份分层（2026-09-09）：当前正式实板组合绑定 HEAD `55822ae` 的 ELF=`f6fe12ea…e421f` 与 bit/XSA=`ef974000…5175a`/`8419e00e…8ab4185`，对应 run `20260909T094406Z`。Vivado WNS/WHS=`+0.017/+0.014 ns`，UART/JTAG/XSCT/probe 均通过，pressure/backpressure 分别为 `10000/10000` 与 `64/64`，stall_cycles=`83082`、S2MM STALL=`3`；历史 `6f3d40e…`、`20260909T073606Z` UART 缺失证据仍保留作对照。manifest 的 `git_worktree_clean=false` 仅表示本地工作树存在未提交修改，不影响同源身份绑定。

B2 monitor/背压时序实验（2026-09-09）：官方双/单 monitor routed setup 分别为 `WNS=-0.325 ns`、`WNS=-0.284 ns`，均为历史失败实验。当前 `axis_stream_probe.v` 物理构建和同源实板 run 已通过；正式 `20260909T105109Z`（HEAD `f7f01b0`）读到 pressure=`10000/10000`、backpressure=`64/64`、stall_cycles=`83082`、S2MM STALL=`3`，UART marker=PASS，并完成连续回绕 `256/256` 帧、`64/64` slot、`rollovers=3` 与首末地址核对。recovery run `20260909T110436Z` 进一步取得 UART/JTAG/XSCT PASS，timeout/reset/passed/failed=`1/1/1/0`、sequence=`10329`、CRC32=`0xD3E3C978`。连续回绕与 recovery 切片为 BOARD_PASS；多长度逐帧、间歇/ready 恢复、错误注入和 B2-03/B2-04/B2-05/B2-GATE 整体关闭仍待补齐。

功能证据校正（2026-09-07，T3=`c2bc03f`，T2 随机矩阵=`ee6c25a`）：PR #64 已合并为 `main@a53a040`；V2 OOC 报告绑定 `f744bff`，GitHub Actions 已关闭。PR #68 的 `55ec08e`/run `33976357259` 是历史可追溯审计快照，不是当前值。P15-T0 的 A1-A7 已获管理员批准，当前为 `P15_T0_APPROVED / T1_RTL_AUTHORIZED / T1_PROTOCOL_SLICE_PROVEN / T1_FULL_PENDING / T2_VARIABLE_CLOCK_SLICE_GREEN / T2_CONCURRENT_EPOCH_SLICE_GREEN / T2_EXTENDED_CLOCK_SLICE_GREEN / T2_FINITE_CLOCK_MATRIX_GREEN / T2_RANDOM_CLOCK_MATRIX_GREEN / T2_FULL_MATRIX_PENDING / T3_XPM_XSIM_PASS / T3_XC7Z020_OOC_PASS / T3_SIGNOFF_PASS`；T3 报告绑定 Vivado 2024.1、`xc7z020clg400-1`、真实 AMD XPM/xsim、顶层 `2467 LUT / 2301 FF / 6 RAMB36 / 1 RAMB18 / 4 DSP48E1`、外部 CDC=0、100 MHz setup/hold/route/DRC error=0。T2 功能证据分层绑定为基础切片 `a616d60`、六组扩展 `f54e762` 和并发 epoch 场景 `872fa90`，文档状态同步为 `af520b2`/`1a3c371`/`8eab78e`；统一入口的 T1/T2 通过标记仍仅是本机复现证据，不能写成 CI 通过。T1-09 已记录为 `NA_FOR_T1_WRAPPER / OUTER_SHIM_PENDING`；资源裁剪已记录但推迟至首次完整端到端运行成功后。

T3 权威报告：`vivado_npu_zynq7020_t3_xsim/xsim_signoff_summary.txt` 为 `RESULT=PASS`，`vivado_npu_zynq7020_t3_ooc_reports/signoff_summary.txt` 为 `PHYSICAL_GATE=PASS`。OOC 的 XPM 内部 CDC warning=8 和 DRC 建议性 warning 已与外部 error gate 分开记录；不覆盖 AXI/DMA/PS7/Ethernet、板级 I/O/吞吐、功耗或首次端到端运行。

已提交 `tb_xpm_fifo_async_matrix.sv`（`ee3a351`） 及 `--t2-fifo-matrix` 复现入口：8 组 `(NPU_HALF,PHASE)`×3 个固定 seed 共 24 次，四通道逐序列 scoreboard 均通过，摘要标记为 `REPRO_G2_T2_FIFO_MATRIX_PASS`。该证据绑定已提交 Git commit；它来自 Icarus 等价 FIFO 模型，不是 AMD XPM/xsim 或 Actions 结果。T3 真实 XPM/xsim/OOC 已另行签核，但该切片仍不能清除 `T2_FULL_MATRIX_PENDING`。

已提交 `tb_npu_zynq7020_t2_interleave_reset.sv`（`8457a20`） 及 `--t2-interleave-reset` 复现入口：`(2,0)/(3,1)/(7,2)/(11,4)` 四组配置全部通过，摘要标记为 `REPRO_G2_T2_INTERLEAVE_RESET_PASS`。该证据绑定已提交 Git commit，验证的是 Icarus wrapper 交错/复位切片；它不是 T2 全矩阵、AMD XPM/xsim 或 Actions 结果。T3 真实 XPM/xsim/OOC 已另行签核，但该切片仍不能清除 `T2_FULL_MATRIX_PENDING`。

2026-09-07 归档校正：T2 FIFO 矩阵已提交 `ee3a351`，wrapper 交错/复位切片已提交 `8457a20`；原有“工作树候选”文字为提交前快照，不是当前状态。

2026-09-07 T2 固定种子随机矩阵：证据提交 `ee6c25a` 的入口 `--t2-random-matrix` 以种子 `20260907` 生成 24 个唯一 `(NPU_HALF,NPU_PHASE)` 组合；每组观察预算为 `2000 + 400 × NPU_HALF` 个 Host 周期，结果 `REPRO_G2_T2_RANDOM_MATRIX_PASS`，状态为 `T2_RANDOM_CLOCK_MATRIX_GREEN`。该记录是可复现有限压力证据，不得解释为频率/相位数学穷举或 GitHub Actions 结果。

## V2 历史审计快照（2026-09-05）

该审计快照中 PR #68 为 `OPEN / MERGEABLE / UNSTABLE`。Actions run `33976357259` 在 runner 启动前因账户付款/额度限制阻断，归类为 `NOT_RUN_BILLING_BLOCKED`，不能视为代码失败或通过；仓库外 webhook 已收到同一 SHA 的 `workflow_run completed/failure`，但签名未验证，GitHub Checks/API 为权威来源。2026-09-06 chmlfrp 恢复后，本地/公网 health 均为 200，GitHub 官方 ping delivery `ee543f6e-aa08-11f1-84fd-d4849c4dec76` 返回 200 并写入接收器。V2 OOC 仍绑定 `f744bff2bdde68e138a7b2b348ce103bec1ab469`，资源为 `2126 LUT / 1916 FF / 4 DSP48E1`，100 MHz setup/hold/route/DRC 全部通过；TR7-TR12 已批准。P15-T0 方案 A 和 A1-A7 已批准；T1 协议切片已进入仓库并可由本地 G0/G1 复现，但 T1 全量、T2/T3 仍待证据。当前 PR #68 head=`3006174` 对应 run `34051222089`，GitHub Checks 显示 `Classify changes=fail`、`PR Gate=fail`、`T1 reproducibility slice=skipped`；不得把本地协议切片 PASS 写成 GitHub CI PASS。资源裁剪候选不得在首次完整端到端跑通前实施。用户文件 `np75_tmp_sparse_protocol.ys` 继续排除在提交和 Nexus 文件树之外。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-12
provenance: `.nexus-map/raw/git_stats.json` 是最后探针提交于 `c46320e` 的历史快照，仓库内未发现可复现生成脚本。当前 checkout 身份必须由 Git 命令实时查询；未提交源码不进入签核身份。

最近一次 raw 探针快照统计 263 次提交、5 位作者；该数字只代表 `c46320e` 时点。PR #62 已合并为 `main@e8dc947`（merge commit `e8dc9477dbfc7a9311dd00c514a986580ad2b84b`），最终 HEAD `a4832cc3bddd96ba2f94c295ae99c1d12713abf3` 的 Actions run `33915028445` 为 success；Webhook 收到同 SHA，但 `signature_verified=false`，只作到达通知。DSP V1 实现与 OOC report head 为 `5055073`：恰好 4 个 DSP48E1，功能、固定 `20×100` 随机、完整回归、hold/route/DRC 已通过，但 100 MHz setup `WNS=-0.673 ns / TNS=-6.462 ns / 22` 个端点失败。热点已从 V2 审核切换为 V2 实施；实施地图为 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V2_IMPLEMENTATION_MAP.md`，KISS 方案复用 signed 32-bit `mac_accumulator`，不新增 `writeback_value_latched`，仅预计新增四个 signed 8-bit 激活锁存器（约 32 FF）。TR7-TR12 已批准，当前计算 RTL 进入 V2 RED→RTL→回归流程。`np75_tmp_sparse_protocol.ys` 是用户未跟踪文件，不得纳入提交或 Nexus；物理结果不得外推为板级吞吐、功耗或网络性能。

已提交 B2 取证（2026-09-11，历史物理身份）：物理基线绑定 HEAD `97398bf641b49ef2f2ab6b16edd68b6327a14488`，目标 `xc7z020clg484-2`、200 MHz routed timing 全绿（WNS=`+0.012 ns`、TNS=`0`、WHS=`+0.036 ns`、THS=`0`），route/DRC hard error=0，且后续合法 packet smoke 已通过。mask-scan 修复 `0f71f49` 及其回归记录保留为前置开发证据；不得把未提交工作树写成该物理身份。

历史 B2-08 未提交切片取证（2026-09-12、B3-MVP 前）：当时工作树有未提交 status probe / 计数器 RTL，它们不是 HEAD `fe25a70` 的签核源码身份。后续已在提交态物理身份和同源 bit/XSA 上完成计数器与 B3-MVP 实板闭环；本段只保留当时的身份隔离规则。

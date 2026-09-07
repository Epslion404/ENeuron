# Git 热点

当前状态校正（2026-09-07）：PR #64 已合并为 `main@a53a040`；V2 OOC 报告绑定 `f744bff`，GitHub Actions run `33948293095` 全绿。PR #68 的 `55ec08e`/run `33976357259` 是历史可追溯审计快照，不是当前值。P15-T0 的 A1-A7 已获管理员批准，当前为 `P15_T0_APPROVED / T1_RTL_AUTHORIZED / T1_PROTOCOL_SLICE_PROVEN / T1_FULL_PENDING / T2_VARIABLE_CLOCK_SLICE_GREEN / T2_FULL_MATRIX_PENDING`；本机 `a616d60` 已通过 T1-02、T1-06、T1-12 及三组 T2 可变时钟切片，T1-09 已记录为 `NA_FOR_T1_WRAPPER / OUTER_SHIM_PENDING`；资源裁剪已记录但推迟至首次完整端到端运行成功后。

## V2 历史审计快照（2026-09-05）

该审计快照中 PR #68 为 `OPEN / MERGEABLE / UNSTABLE`。Actions run `33976357259` 在 runner 启动前因账户付款/额度限制阻断，归类为 `NOT_RUN_BILLING_BLOCKED`，不能视为代码失败或通过；仓库外 webhook 已收到同一 SHA 的 `workflow_run completed/failure`，但签名未验证，GitHub Checks/API 为权威来源。2026-09-06 chmlfrp 恢复后，本地/公网 health 均为 200，GitHub 官方 ping delivery `ee543f6e-aa08-11f1-84fd-d4849c4dec76` 返回 200 并写入接收器。V2 OOC 仍绑定 `f744bff2bdde68e138a7b2b348ce103bec1ab469`，资源为 `2126 LUT / 1916 FF / 4 DSP48E1`，100 MHz setup/hold/route/DRC 全部通过；TR7-TR12 已批准。P15-T0 方案 A 和 A1-A7 已批准；T1 协议切片已进入仓库并可由本地 G0/G1 复现，但 T1 全量、T2/T3 仍待证据。当前 PR #68 head=`3006174` 对应 run `34051222089`，GitHub Checks 显示 `Classify changes=fail`、`PR Gate=fail`、`T1 reproducibility slice=skipped`；不得把本地协议切片 PASS 写成 GitHub CI PASS。资源裁剪候选不得在首次完整端到端跑通前实施。用户文件 `np75_tmp_sparse_protocol.ys` 继续排除在提交和 Nexus 文件树之外。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-07
provenance: `.nexus-map/raw/git_stats.json`（最后提交于 `c46320e`；仓库内未发现可复现生成脚本，后续基线由 Git 与 manifest 人工核对）

最近一次 raw 探针快照统计 263 次提交、5 位作者；该数字只代表 `c46320e` 时点。PR #62 已合并为 `main@e8dc947`（merge commit `e8dc9477dbfc7a9311dd00c514a986580ad2b84b`），最终 HEAD `a4832cc3bddd96ba2f94c295ae99c1d12713abf3` 的 Actions run `33915028445` 为 success；Webhook 收到同 SHA，但 `signature_verified=false`，只作到达通知。DSP V1 实现与 OOC report head 为 `5055073`：恰好 4 个 DSP48E1，功能、固定 `20×100` 随机、完整回归、hold/route/DRC 已通过，但 100 MHz setup `WNS=-0.673 ns / TNS=-6.462 ns / 22` 个端点失败。热点已从 V2 审核切换为 V2 实施；实施地图为 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V2_IMPLEMENTATION_MAP.md`，KISS 方案复用 signed 32-bit `mac_accumulator`，不新增 `writeback_value_latched`，仅预计新增四个 signed 8-bit 激活锁存器（约 32 FF）。TR7-TR12 已批准，当前计算 RTL 进入 V2 RED→RTL→回归流程。`np75_tmp_sparse_protocol.ys` 是用户未跟踪文件，不得纳入提交或 Nexus；物理结果不得外推为板级吞吐、功耗或网络性能。

# Git 热点

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: `.nexus-map/raw/git_stats.json`（最后提交于 `c46320e`；仓库内未发现可复现生成脚本，后续基线由 Git 与 manifest 人工核对）

最近一次 raw 探针快照统计 263 次提交、5 位作者；该数字只代表 `c46320e` 时点。PR #62 已合并为 `main@e8dc947`（merge commit `e8dc9477dbfc7a9311dd00c514a986580ad2b84b`），最终 HEAD `a4832cc3bddd96ba2f94c295ae99c1d12713abf3` 的 Actions run `33915028445` 为 success；Webhook 收到同 SHA，但 `signature_verified=false`，只作到达通知。DSP V1 实现与 OOC report head 为 `5055073`：恰好 4 个 DSP48E1，功能、固定 `20×100` 随机、完整回归、hold/route/DRC 已通过，但 100 MHz setup `WNS=-0.673 ns / TNS=-6.462 ns / 22` 个端点失败。热点仍是 `NPU_SINGLE_CLOCK_TIMING_REPAIR_V2` 审核；实施地图为 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V2_IMPLEMENTATION_MAP.md`，KISS 方案复用 signed 32-bit `mac_accumulator`，不新增 `writeback_value_latched`，仅预计新增四个 signed 8-bit 激活锁存器（约 32 FF）。TR7-TR12 仍未批准，计算 RTL 保持 `RTL_CHANGES_BLOCKED`。`np75_tmp_sparse_protocol.ys` 是用户未跟踪文件，不得纳入提交或 Nexus；物理结果不得外推为板级吞吐、功耗或网络性能。

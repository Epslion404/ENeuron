# Git 热点

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: `.nexus-map/raw/git_stats.json`（最后提交于 `c46320e`；仓库内未发现可复现生成脚本，后续基线由 Git 与 manifest 人工核对）

最近一次 raw 探针快照统计 263 次提交、5 位作者；该数字只代表 `c46320e` 时点。传统 NPU + ENeuron 的当前基线为 `origin/main@4fc4c71`：PR #60 已于 2026-09-04 合并，HEAD `c0f1bea` 的 CI run `33911646530` 成功。DSP V1 实现与 OOC report head 为 `5055073`。四 DSP、功能回归、hold/route/DRC 已通过，但 setup `WNS=-0.673 ns`、22 个端点失败；热点仍是 `NPU_SINGLE_CLOCK_TIMING_REPAIR_V2` 审核，当前等待 TR7-TR12 批准。`np75_tmp_sparse_protocol.ys` 是用户未跟踪文件，不得纳入提交或 Nexus；物理结果不得外推为板级吞吐、功耗或网络性能。

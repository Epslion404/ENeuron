# Git 热点

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: `.nexus-map/raw/git_stats.json`（最后提交于 `c46320e`；仓库内未发现可复现生成脚本，后续基线由 Git 与 manifest 人工核对）

最近一次 raw 探针快照统计 263 次提交、5 位作者；变更集中在 `progress.md`（100）、`task_plan.md`（81）、`findings.md`（60）、`WORKFLOW_STATE.md`（40）和 `.nexus-map/INDEX.md`（24）。该数字只代表 `c46320e` 时点，不冒充 `origin/main@dc2452b` 的实时统计。结构扇入最高的是 `pulse_mini_reference.py`、`rtl_tile_cosim.py`、`pulse_mini_l2_reference.py`、`neuron_sim.py`、`local_prune_reference.py`；网络层新增的重要枢纽是 `network_sim.py`、`host_bridge_oracle.py` 和 `np7_shared_lane_oracle.py`。传统 NPU + ENeuron 集成已完成 OF1-OF6 Python oracle 签核；PR #54 在 `main@2a33f12` 收口 RTL 与随机门，OOC 报告生成于 `39e41d4` 并由 manifest 绑定，PR #55 将证据合入 `main@dc2452b`。route/DRC 无错误且 hold 通过，但 setup 失败；热点已转为 `NPU_SINGLE_CLOCK_TIMING_REPAIR_V1` 审核，TR1-TR6 批准后才进入关键路径修复与同范围 OOC 重跑。`np75_tmp_sparse_protocol.ys` 是用户未跟踪文件，不得纳入提交或 Nexus；物理结果不得外推为板级吞吐、功耗或网络性能。修改高扇入文件时必须同步机器摘要和 verifier；不要把逻辑访问计数解释成物理收益。

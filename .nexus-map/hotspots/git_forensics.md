# Git 热点

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-04
provenance: `.nexus-map/raw/git_stats.json`

近 90 天共 238 次提交、5 位作者；变更集中在 `progress.md`（91）、`task_plan.md`（73）、`findings.md`（53）、`WORKFLOW_STATE.md`（32）、NP4B 规划（21）和 NP7 证据/摘要。结构扇入最高的是 `pulse_mini_reference.py`、`rtl_tile_cosim.py`、`pulse_mini_l2_reference.py`、`neuron_sim.py`、`local_prune_reference.py`；网络层新增的重要枢纽是 `network_sim.py`、`host_bridge_oracle.py` 和 `np7_shared_lane_oracle.py`。传统 NPU + ENeuron 集成热点已推进至 OF4g：`committed` 模型允许冻结，`loading/complete` 仍拒绝；相关完整 oracle 47/47，修正已合并至 `main@9f6d14b`。当前 `main` 为 `9f6d14b`；`np75_tmp_sparse_protocol.ys` 是用户未跟踪文件，不得纳入提交或 Nexus。当前热点工作仍是单时钟集成前的协议审核。修改高扇入文件时必须同步机器摘要和 verifier；不要把逻辑访问计数解释成物理收益。

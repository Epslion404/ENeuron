# Git 热点

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-03
provenance: `.nexus-map/raw/git_stats.json`

近 90 天共 238 次提交、5 位作者；变更集中在 `progress.md`（91）、`task_plan.md`（73）、`findings.md`（53）、`WORKFLOW_STATE.md`（32）、NP4B 规划（21）和 NP7 证据/摘要。结构扇入最高的是 `pulse_mini_reference.py`、`rtl_tile_cosim.py`、`pulse_mini_l2_reference.py`、`neuron_sim.py`、`local_prune_reference.py`；网络层新增的重要枢纽是 `network_sim.py`、`host_bridge_oracle.py` 和 `np7_shared_lane_oracle.py`。PR #19 HEAD `d6ca094` 对应 CI run `33760749837` 已成功并合并为 `63028d4`；该次仓库外 Webhook 投递曾短暂失败，CI 终态以 GitHub API 为权威。当前热点工作转入传统 NPU + 神经元集成的静态审核。修改高扇入文件时必须同步机器摘要和 verifier；不要把逻辑访问计数解释成物理收益。

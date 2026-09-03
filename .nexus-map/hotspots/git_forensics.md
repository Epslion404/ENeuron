# Git 热点

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-03
provenance: `.nexus-map/raw/git_stats.json`

近 90 天变更集中在验证脚本、规划文档、局部剪枝模型、Vivado 报告和 Host/Tile 协同仿真。扇入最高的是 `pulse_mini_reference.py`、`rtl_tile_cosim.py`、`pulse_mini_l2_reference.py`、`neuron_sim.py`、`local_prune_reference.py`。PR #10 当前 HEAD `cadc3a8` 对应 CI run `33729657078` 已成功，并由仓库外 Webhook 收到终态事件；当前热点工作转入传统 NPU + 神经元集成的静态审核。修改这些高扇入文件时必须同步机器摘要和 verifier；不要把逻辑访问计数解释成物理收益。

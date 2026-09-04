# 系统边界

测试合同更新（2026-09-05）：传统 NPU + ENeuron 集成已进入 `RTL_RANDOM_GATE_GREEN / PR55_MERGED / VIVADO_OOC_SETUP_FAIL / TIMING_REPAIR_REQUIRED / TIMING_REPAIR_V1_REVIEW_REQUIRED / TIMING_REPAIR_TEST_CONTRACT_PREPARED`。`docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_TEST_CONTRACT_V1.md` 状态为 `PREPARED / BLOCKED_BY_TR1_TR6_APPROVAL`，冻结 C1-C4 的启用组数与 V1 延迟：C1 `592/1860`、C2 `590/1856`、C3 `0/676`、C4 `591/1858`。五个现有 watchdog 无需放宽。该状态只代表测试合同准备完成；TR1-TR6 尚未批准，业务 RTL 尚未修改，Vivado 100 MHz setup 仍未通过。

generated_by: nexus-mapper v2 / manual synthesis
verified_at: 2026-09-05
provenance: Python AST/file-tree probe plus SystemVerilog文件树和项目文档人工核对

仓库分为六个边界：神经元 RTL 与 Python 参考模型、Tile/Host 网络、局部剪枝控制器、NP7 共享 BRAM/lane 执行器、传统 NPU + ENeuron 集成参考模型、验证与签核工具。CI-Fast V1 是验证编排边界，不改变业务硬件合同。跨边界的主要合同是逐周期/逐位比较、原子提交、INFER 状态冻结和 fail-closed SHA-256 摘要。

NP6 物理评估正式状态为 `NP6_PHYSICAL_COST_PARTIAL`；NP7 共享 BRAM/lane 已实现并合并。传统 NPU + ENeuron 当前状态为 `RTL_RANDOM_GATE_GREEN / PR55_MERGED / VIVADO_OOC_SETUP_FAIL / TIMING_REPAIR_REQUIRED`。OF1-OF6 Python 合同继续成立；当前 RTL 已包含四 lane 顺序 INT8 MAC、hidden 饱和、logit 槽和 active-mask 门控，并通过定向与固定 `20×100` 随机逐 beat 门。OOC 证据精确绑定 RTL merge=`2a33f12`、report head=`39e41d4`、evidence merge=`dc2452b`，但 setup 失败，因此不得外推 100 MHz 收敛、板级吞吐、动态功耗或部署性能。`np75_tmp_sparse_protocol.ys` 被明确排除在提交、Nexus 文件树和原始探针之外。

状态覆盖：OF4a 至 OF6 属于已签核 Python oracle 历史阶段；当前以 `RTL_RANDOM_GATE_GREEN / PR55_MERGED / VIVADO_OOC_SETUP_FAIL / TIMING_REPAIR_REQUIRED / TIMING_REPAIR_V1_REVIEW_REQUIRED / TIMING_REPAIR_TEST_CONTRACT_PREPARED` 为准。四条 Icarus 切片、固定 `20×100` 随机逐拍签核和完整回归 `469/469（1 skipped）` 已完成；Vivado 2024.1 OOC 已执行但 setup 失败。时序修复测试合同虽已准备，但仍由 TR1-TR6 批准门阻塞；不得据此声称三拍 RTL 已实现或 100 MHz 已收敛。

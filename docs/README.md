# ENeuron 文档索引

当前主线是 `xc7z020clg484-2` 上的 NPU + ENeuron 动态剪枝：先完成单时钟 NPU/ENeuron、局部剪枝和 NP7 共享 lane 的可复现闭环，再进入 B2/B3/B4 板级集成。高地址 DDR、PHY/UDP 属于 B1 板卡资格支线，不作为 NPU MVP 的日常阻塞。

项目根目录只保留项目入口、持久工作流和规划记忆文件。历史研究线和旧器件物理材料统一放在 [`archive/legacy/`](../archive/legacy/README.md)，不再出现在活动门中。

## 设计与合同

- [动态恢复型局部剪枝门控提案](design/DESIGN_PROPOSAL_DYNAMIC_PRUNE_RECOVERY.md)
- [片外 Host 训练协议](design/host_protocol.md)
- [XC7Z020 顶层集成规划 V1](planning/NPU_ZYNQ7020_TOPLEVEL_INTEGRATION_V1.md)
- [XC7Z020 顶层 T0 端口裁定稿](planning/NPU_ZYNQ7020_TOPLEVEL_DECISION_SHEET_V1.md)
- [XC7Z020 实板验证阶段 2 规划](planning/NPU_ZYNQ7020_BOARD_VALIDATION_PHASE2_V1.md)
- [GitHub 可复现性门 V1](planning/GITHUB_REPRODUCIBILITY_GATE_V1.md)
- [局部 2:4 剪枝 RTL 合同](design/LOCAL_PRUNE_RTL_CONTRACT.md)
- [原始 Goal 对齐审核](design/original_goal_alignment_review.md)
- [推荐神经元设计](design/recommended_design.md)
- [RTL 冻结契约](design/rtl_contract.md)

## 专项计划

- [NPU 局部剪枝与动态门控计划](planning/NPU_PRUNING_TODO.md)
- [NP4B 正式集成 TODO](planning/NPU_PRUNING_NP4B_TODO.md)
- [传统 NPU + ENeuron 集成审核稿](planning/NPU_NEURON_INTEGRATION_REVIEW.md)
- [NPU + ENeuron Python Oracle 冻结审核](planning/NPU_ORACLE_FREEZE_REVIEW.md)
- [B1/B1C 实板执行 TODO](planning/TODO.md)
- [NP7 共享 BRAM 与共享 lane TODO](planning/NPU_PRUNING_NP7_TODO.md)
- [NP7 B-V1+V2 管理员决策点](planning/NPU_PRUNING_NP7_DECISION_B_V1_V2.md)
- [NPU 单时钟 DSP V1 时序修复](planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V1.md)
- [NPU 单时钟 DSP V1 测试合同](planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_TEST_CONTRACT_V1.md)
- [NPU 单时钟 V2 时序修复审核稿](planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V2.md)
- [NPU 单时钟 V2 实施地图](planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V2_IMPLEMENTATION_MAP.md)

## 报告

- [HelloZynq B0 实板 smoke 报告](reports/HELLOZYNQ_B0_SMOKE_2026-09-07.md)
- [HelloZynq B1B UART与低地址DDR实板报告](reports/HELLOZYNQ_B1B_UART_DDR_2026-09-08.md)
- [ENeuron 1.0 发布说明](reports/RELEASE_1.0.md)
- [Vivado/XSim 局部剪枝仿真报告](reports/SIMULATION_REPORT.md)
- [局部剪枝 NP4/NP5 RTL](reports/LOCAL_PRUNE_RTL_REPORT.md)

## 验证与签核

- [原始 Goal 完成审计](verification/goal_audit.md)
- [NPU 局部剪枝原始 Goal 签核](verification/NPU_PRUNING_GOAL_SIGNOFF.md)
- [NPU 单时钟 DSP V1 全部失败端点审计](verification/NPU_SINGLE_CLOCK_TIMING_ENDPOINT_AUDIT_V1.md)

## 持续集成

- [PR 自动检查与分支保护配置](CI_PR_GATE.md)
- [Windows + MSYS2 UCRT64 专项测试工具链注明](WINDOWS_MSYS2_XPM_TOOLCHAIN.md)

## 根目录保留文件

- `README.md`：项目入口与快速运行说明。
- `WORKFLOW.md`、`WORKFLOW_STATE.md`：持久工作流及当前状态。
- `task_plan.md`、`findings.md`、`progress.md`：长期规划、事实与执行日志。

文档中的 `docs/...` 路径均以仓库根目录为基准。历史验证数字仍受各报告原有证据边界约束；本次归档不代表重新运行算法、RTL、形式验证或 Vivado。

## 历史入口

- [历史归档总览](../archive/legacy/README.md)
- [旧 ENeuron 1.0 Tile/Host Bridge 材料](../archive/legacy/eneuron_v1_host_bridge/)
- [G4 多任务材料](../archive/legacy/g4/)
- [数字识别材料](../archive/legacy/digit8x8/)
- [NP6 旧物理材料](../archive/legacy/np6_physical/)
- [NP7 旧物理材料](../archive/legacy/np7_physical/)

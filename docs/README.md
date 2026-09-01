# ENeuron 文档索引

项目根目录只保留项目入口、持久工作流和规划记忆文件。设计、专项计划、项目报告与验证结论统一归档在本目录。

## 设计与合同

- [动态恢复型局部剪枝门控提案](design/DESIGN_PROPOSAL_DYNAMIC_PRUNE_RECOVERY.md)
- [G4 多任务能力验证方案](design/g4_capability_validation_proposal.md)
- [G4 T3 执行规格](design/g4_t3_execution_spec.md)
- [Host Bridge V1 设计](design/host_bridge_v1_proposal.md)
- [片外 Host 训练协议](design/host_protocol.md)
- [局部 2:4 剪枝 RTL 合同](design/LOCAL_PRUNE_RTL_CONTRACT.md)
- [原始 Goal 对齐审核](design/original_goal_alignment_review.md)
- [推荐神经元设计](design/recommended_design.md)
- [RTL 冻结契约](design/rtl_contract.md)

## 专项计划

- [Pulse-Mini 开发计划](planning/TODO.md)
- [NPU 局部剪枝与动态门控计划](planning/NPU_PRUNING_TODO.md)
- [NP4B 正式集成 TODO](planning/NPU_PRUNING_NP4B_TODO.md)
- [NP6 物理成本评估 TODO](planning/NPU_PRUNING_NP6_TODO.md)

## 报告

- [当前项目报告](reports/PROJECT_REPORT.md)
- [2026-08-31 阶段性项目报告](reports/STAGE_REPORT_2026-08-31.md)
- [ENeuron 1.0 发布说明](reports/RELEASE_1.0.md)
- [三版本纯仿真比较](reports/SIMULATION_COMPARISON_REPORT.md)
- [Vivado/XSim 局部剪枝仿真报告](reports/SIMULATION_REPORT.md)
- [Pulse-Mini-L/L2 协议与多任务报告](reports/PULSE_MINI_L2_PROTOCOL_REPORT.md)
- [数字识别 D0](reports/DIGIT_RECOGNITION_D0.md)
- [数字识别 D1](reports/DIGIT_RECOGNITION_D1.md)
- [数字识别 D2](reports/DIGIT_RECOGNITION_D2.md)
- [局部剪枝 B1](reports/LOCAL_PRUNE_B1_REPORT.md)
- [局部剪枝 B2](reports/LOCAL_PRUNE_B2_REPORT.md)
- [局部剪枝 B2.1](reports/LOCAL_PRUNE_B21_REPORT.md)
- [局部剪枝 NP2](reports/LOCAL_PRUNE_NP2_REPORT.md)
- [局部剪枝 NP3](reports/LOCAL_PRUNE_NP3_REPORT.md)
- [局部剪枝 NP4/NP5 RTL](reports/LOCAL_PRUNE_RTL_REPORT.md)

## 验证与签核

- [原始 Goal 完成审计](verification/goal_audit.md)
- [NPU 局部剪枝原始 Goal 签核](verification/NPU_PRUNING_GOAL_SIGNOFF.md)

## 根目录保留文件

- `README.md`：项目入口与快速运行说明。
- `WORKFLOW.md`、`WORKFLOW_STATE.md`：持久工作流及当前状态。
- `task_plan.md`、`findings.md`、`progress.md`：长期规划、事实与执行日志。

文档中的 `docs/...` 路径均以仓库根目录为基准。历史验证数字仍受各报告原有证据边界约束；本次归档不代表重新运行算法、RTL、形式验证或 Vivado。

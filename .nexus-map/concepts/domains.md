> generated_by: nexus-mapper v2
> verified_at: 2026-09-02
> provenance: Python AST-backed plus manual RTL/report inspection

# 领域概念

- **神经元状态**：膜电位、迹线、资格迹线和权重组成可更新状态；脉冲触发后按协议复位或泄放。
- **事务**：Host 对 tile 发出的 TICK、SNAPSHOT、MOD_COMMIT、WEIGHT_WRITE、STATE_CLEAR 等原子命令。
- **资格与调制**：片上保存局部资格，片外提供 signed 调制，提交时形成权重更新。
- **局部剪枝**：固定 2-of-4 gate 选择活动通道，并由 commit barrier 保证提交与清状态的原子顺序。
- **证据闭环**：参考模型、RTL 协同仿真、形式证明、Vivado 报告和独立 verifier 的组合。
- **阶段边界**：NP6 只回答物理资源/时序成本；NP7 的共享 lane 结果不等于真实板级吞吐或功耗收益。

> generated_by: nexus-mapper v2
> verified_at: 2026-09-02
> provenance: Static AST/file inspection; execution status comes from tracked workflow and reports

# 测试面

- 单神经元、网络、Pulse-Mini、数字识别和局部剪枝均有 `test_*.py` 套件。
- RTL 协同仿真覆盖单核、tile、Host Bridge、wrapper、网络 tick 与 XPM 流程。
- 形式验证文件覆盖 gate、commit barrier、wrapper、tile protocol 和 Host Bridge controller。
- `verify_goal.py` 聚合回归、M3、形式 BMC、Tile/系统报告；`verify_np4b_signoff.py` 校验哈希绑定的签核摘要。
- NP6/NP7 的物理结论依赖 Vivado 报告目录和阶段摘要；静态 Nexus 生成未运行测试或 Vivado，证据缺口由工作流文件和报告承担。

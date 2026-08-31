# ENeuron 持久工作流状态

模式：`PERSISTENT_WORKFLOW_V1`

最后更新：2026-08-31

状态：`ACTIVE / NEXT_REVIEW_REQUIRED`

## 当前活动目标

NP4B 功能集成证据闭环已经完成；当前等待用户决定是否批准 NP6 Vivado 物理成本阶段。

活动合同：`docs/planning/NPU_PRUNING_NP4B_TODO.md` 第 9 节。

## 当前事实

- 持久工作流已提交：`df0e7bc docs: add persistent project workflow`。
- 已提交 P0：`67b6019 test: prove Pulse pruning wrapper atomicity`。
- 已提交 P2/P3：`c0108a0 test: prove pruning network commit barrier`。
- ENeuron P1 已提交：`c811bcf test: prove ENeuron pruning wrapper atomicity`。
- P1 verifier、3 项定向测试、Python 编译和绝对路径 Icarus `-Wall -tnull` 均通过；正式日志与成功 witness 已入库，cex/tmp 未纳入。
- 三模型各 20,000 条新鲜矩阵、五套 proof/reach 与独立 verifier、8 个 RTL 编译目标和最终全仓 `359/359` 均通过。
- P5 已提交：`e3708af test: add NP4B fail-closed signoff`；总摘要绑定 87 个文件并通过独立 verifier。
- 当前正式状态为 `NP4B_INTEGRATION_PASS / NP6_REVIEW_REQUIRED`。
- NP6 尚未获再次批准，禁止运行 Vivado。
- 根目录 Markdown 已整理归档并推送：`ebd6c0d docs: archive project markdown files`；文档入口为 `docs/README.md`。

## 允许动作

- 只读恢复、状态核对和工作流维护。
- 只读审计、状态恢复和回答用户关于 NP4B 证据的问题。
- 只有用户明确批准 NP6 后，才规划并运行 Vivado 物理成本评估。

## 禁止动作

- 运行 Vivado 或把逻辑计数解释成物理加速、BRAM 跳读或功耗收益。
- 将 cex、tmp 日志或来源不明的历史产物纳入正式证据。
- 清理、覆盖或混入当前工作树中的已有改动。

## 下一动作

停止实施，等待用户再次批准 NP6。此前不调用 Vivado。

## 恢复检查

```powershell
.\workflow_resume.ps1 -Mode Resume
```

恢复脚本通过后，仍需读取活动 TODO 中当前阶段的完整合同，不能只凭本状态摘要实施。

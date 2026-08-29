# ENeuron 持久工作流状态

模式：`PERSISTENT_WORKFLOW_V1`

最后更新：2026-08-29

状态：`ACTIVE / IN_PROGRESS`

## 当前活动目标

完成 NPU 局部剪枝 NP4B 功能集成的最终证据闭环，并在全部硬门通过后停止于 `NP6_REVIEW_REQUIRED`。

活动合同：`NPU_PRUNING_NP4B_TODO.md` 第 9 节。

## 当前事实

- 持久工作流已提交：`df0e7bc docs: add persistent project workflow`。
- 已提交 P0：`67b6019 test: prove Pulse pruning wrapper atomicity`。
- 已提交 P2/P3：`c0108a0 test: prove pruning network commit barrier`。
- ENeuron P1 已提交：`c811bcf test: prove ENeuron pruning wrapper atomicity`。
- P1 verifier、3 项定向测试、Python 编译和绝对路径 Icarus `-Wall -tnull` 均通过；正式日志与成功 witness 已入库，cex/tmp 未纳入。
- P4 三模型矩阵、五套新鲜 proof/reach 和对应 verifier 已通过；证据哈希修复后的第二轮全仓 `356/356` 通过，compileall 与 8 个 RTL 编译目标通过，P5 尚未开始。
- NP6 尚未获再次批准，禁止运行 Vivado。

## 允许动作

- 只读恢复、状态核对和工作流维护。
- 按活动 TODO 的 P4→P5 串行执行。

## 禁止动作

- 运行 Vivado 或把逻辑计数解释成物理加速、BRAM 跳读或功耗收益。
- 将 cex、tmp 日志或来源不明的历史产物纳入正式证据。
- 清理、覆盖或混入当前工作树中的已有改动。

## 下一动作

提交 P4.4/P4.5 状态文档，然后执行 P4.6/P5：建立精确证据索引、总摘要、独立 verifier 和最终项目文档。

## 恢复检查

```powershell
.\workflow_resume.ps1 -Mode Resume
```

恢复脚本通过后，仍需读取活动 TODO 中当前阶段的完整合同，不能只凭本状态摘要实施。

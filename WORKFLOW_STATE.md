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
- P4 三模型矩阵、五套新鲜 proof/reach 和对应 verifier 已通过；首轮全仓 356 项为 355 PASS / 1 stale-hash FAIL，正在修复证据索引，P5 尚未开始。
- NP6 尚未获再次批准，禁止运行 Vivado。

## 允许动作

- 只读恢复、状态核对和工作流维护。
- 按活动 TODO 的 P4→P5 串行执行。

## 禁止动作

- 运行 Vivado 或把逻辑计数解释成物理加速、BRAM 跳读或功耗收益。
- 将 cex、tmp 日志或来源不明的历史产物纳入正式证据。
- 清理、覆盖或混入当前工作树中的已有改动。

## 下一动作

验证 `local_prune_rtl_results.json` 的 gate reach SHA-256 修复，提交后完整重跑 356 项；不得复用首轮失败结果。

## 恢复检查

```powershell
.\workflow_resume.ps1 -Mode Resume
```

恢复脚本通过后，仍需读取活动 TODO 中当前阶段的完整合同，不能只凭本状态摘要实施。

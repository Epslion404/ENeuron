# ENeuron 持久工作流状态

模式：`PERSISTENT_WORKFLOW_V1`

最后更新：2026-08-29

状态：`ACTIVE / IN_PROGRESS`

## 当前活动目标

完成 NPU 局部剪枝 NP4B 功能集成的最终证据闭环，并在全部硬门通过后停止于 `NP6_REVIEW_REQUIRED`。

活动合同：`NPU_PRUNING_NP4B_TODO.md` 第 9 节。

## 当前事实

- 已提交 P0：`67b6019 test: prove Pulse pruning wrapper atomicity`。
- 已提交 P2/P3：`c0108a0 test: prove pruning network commit barrier`。
- ENeuron P1 技术验证已经通过，当前为 `PROOF_PASS / REPOSITORY_CLOSURE_PENDING`。
- 工作树包含 P1 源码、形式脚本、verifier、规划文档以及被 `.gitignore` 忽略的正式日志/witness。
- P4 冻结后全量重跑和 P5 总签核尚未开始。
- NP6 尚未获再次批准，禁止运行 Vivado。

## 允许动作

- 只读恢复、状态核对和工作流维护。
- 执行 P1.7 的精确暂存、证据检查和独立提交。
- P1 入库后按活动 TODO 的 P4→P5 串行执行。

## 禁止动作

- 运行 Vivado 或把逻辑计数解释成物理加速、BRAM 跳读或功耗收益。
- 把 P1 本地证明写成已经提交。
- 将 cex、tmp 日志或来源不明的历史产物纳入正式证据。
- 清理、覆盖或混入当前工作树中的已有改动。

## 下一动作

用户已批准八项决定并要求执行 TODO。当前从 P1.7 开始，不跳到 P4。

## 恢复检查

```powershell
.\workflow_resume.ps1 -Mode Resume
```

恢复脚本通过后，仍需读取活动 TODO 中当前阶段的完整合同，不能只凭本状态摘要实施。

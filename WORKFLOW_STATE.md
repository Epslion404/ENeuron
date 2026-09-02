# ENeuron 持久工作流状态

模式：`PERSISTENT_WORKFLOW_V1`

最后更新：2026-09-02

状态：`ACTIVE / NP7_MERGED / NPU_NEURON_INTEGRATION_REVIEW_REQUIRED`

## 当前活动目标

NP6 物理成本证据已经合并并完成阶段收口，NP7 共享 BRAM 与共享 lane 已合并。当前主线转为传统 INT8 NPU 与神经元控制平面的集成方案审核。

活动合同：`docs/planning/NPU_NEURON_AUGMENTED_TODO.md`（N0-N7 审核稿）。NP7 历史合同见 `docs/planning/NPU_PRUNING_NP7_TODO.md`，NP6 结果见 `docs/planning/NPU_PRUNING_NP6_TODO.md` 与 `docs/reports/LOCAL_PRUNE_NP6_PHYSICAL_COST_REPORT.md`。

## 当前事实

- 持久工作流已提交：`df0e7bc docs: add persistent project workflow`。
- 已提交 P0：`67b6019 test: prove Pulse pruning wrapper atomicity`。
- 已提交 P2/P3：`c0108a0 test: prove pruning network commit barrier`。
- ENeuron P1 已提交：`c811bcf test: prove ENeuron pruning wrapper atomicity`。
- P1 verifier、3 项定向测试、Python 编译和绝对路径 Icarus `-Wall -tnull` 均通过；正式日志与成功 witness 已入库，cex/tmp 未纳入。
- 三模型各 20,000 条新鲜矩阵、五套 proof/reach 与独立 verifier、8 个 RTL 编译目标和最终全仓 `359/359` 均通过。
- P5 已提交：`e3708af test: add NP4B fail-closed signoff`；总摘要绑定 87 个文件并通过独立 verifier。
- NP6 九项冻结决策已获批准；PR #5 已合并为 `241b1d0`。
- NP6 fail-closed verifier 正向通过，12 项 mutation 全部通过；冻结证据 HEAD 为 `7023b15`。
- 7 个 NP6 实现均完成且 route/DRC error 为 0；只有 gate 与 ENeuron 剪枝封装通过 100 MHz，正式状态为 `NP6_PHYSICAL_COST_PARTIAL`。
- NP7 已合并：当前结果证明共享 dense/sparse 执行单元、`1/2/4/8 lane` 协议和既定验证范围；它仍不是完整传统 INT8 NPU 的端到端性能证明。
- 根目录结果归档、当前 RTL Vivado 证据重建和 Goal 审计已推送：提交 `9465142`；随后 NP6 规划提交 `cbff013`，nexus 知识库提交 `c7c5c5b`；文档入口为 `docs/README.md`，知识库入口为 `.nexus-map/INDEX.md`。

## 允许动作

- 只读恢复、状态核对、工作流维护和 `NPU_NEURON_AUGMENTED_TODO.md` 审核准备。
- N0 获批准后，先实现 dense INT8 NPU Python/RTL 基线，再接入神经元控制平面。
- 新的 Vivado 阶段必须在 N1-N5 功能门全部通过后单独执行。

## 禁止动作

- 在 N0 审核前修改传统 NPU/神经元集成 RTL，或在 N1-N5 功能门通过前运行新的 Vivado 实现。
- 把 NP6 的逻辑资源和 vector-less 功耗解释成真实加速、BRAM 跳读或功耗收益。
- 将 cex、tmp 日志或来源不明的历史产物纳入正式证据。
- 清理、覆盖或混入当前工作树中的已有改动。

## 下一动作

等待用户审核并批准 `docs/planning/NPU_NEURON_AUGMENTED_TODO.md` 的 N0 决策。批准前只做静态审计、知识库更新和文档维护；批准后先推进 N1 dense INT8 NPU 基线。

## 恢复检查

```powershell
.\workflow_resume.ps1 -Mode Resume
```

恢复脚本通过后，仍需读取活动 TODO 中当前阶段的完整合同，不能只凭本状态摘要实施。

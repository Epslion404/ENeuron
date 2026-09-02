# ENeuron 持久工作流状态

模式：`PERSISTENT_WORKFLOW_V1`

最后更新：2026-09-03

状态：`ACTIVE / NP7_MERGED / NPU_NEURON_INTEGRATION_REVIEW_REQUIRED`

## 当前活动目标

NP6 物理成本证据已经合并并完成阶段收口；NP7 共享 BRAM 与共享 lane 已完成并合并。PR #9 随后回滚了 PR #7 的 N1 集成基线，下一步重新审核传统 NPU + 神经元集成路线。

活动合同：`docs/planning/NPU_PRUNING_NP7_TODO.md`（NP7 已合并签核，后续进入集成审核）；NP6 结果见 `docs/planning/NPU_PRUNING_NP6_TODO.md` 与 `docs/reports/LOCAL_PRUNE_NP6_PHYSICAL_COST_REPORT.md`。

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
- 根目录结果归档、当前 RTL Vivado 证据重建和 Goal 审计已推送：提交 `9465142`；随后 NP6 规划提交 `cbff013`，nexus 知识库提交 `c7c5c5b`；文档入口为 `docs/README.md`，知识库入口为 `.nexus-map/INDEX.md`。

## 允许动作

- 只读恢复、状态核对、工作流维护和 NP7 方案审核。
- 在 NP7 决策获批后，实现 Python 周期 oracle、RTL 共享 lane、协同仿真、形式检查和软件性能计数。
- NP7 的 Vivado 阶段必须在前述功能门全部通过后单独执行。

## 禁止动作

- 在 NP7 审核前修改共享 lane/BRAM RTL，或在 NP7 功能门通过前运行新的 Vivado 实现。
- 把 NP6 的逻辑资源和 vector-less 功耗解释成真实加速、BRAM 跳读或功耗收益。
- 将 cex、tmp 日志或来源不明的历史产物纳入正式证据。
- 清理、覆盖或混入当前工作树中的已有改动。

## 下一动作

NP7 已完成；下一步是重新审核并批准传统 NPU + 神经元集成计划。批准前只做静态审计、Nexus 更新和文档维护。

## 2026-09-03 PR #10 清单绑定修复

- PR #10 的 CI 失败仅来自 fail-closed 完整性门：`NPU_PRUNING_NP7_TODO.md` 已更新，但 NP7 软件清单仍绑定旧字节；G1-G6、账本覆盖和物理证据门均通过。
- 已在当前提交 `61b694b` 上重新运行 `generate_np7_manifest.py`，仅更新 `artifacts/results/np7_software_cost_manifest.json` 的冻结提交、输入文件哈希和本机工具链记录。
- 生成时显式使用管理员批准的 `C:\msys64\ucrt64\bin` 工具链；未把缺失的旧 `C:\iverilog\bin` 路径写入证据。
- 本地独立验证已重算 G1-G6 全部通过；提交后需再次运行带提交 HEAD 的验证器并等待 Webhook/CI 结果。
- 提交 `5a6825f` 已推送到 PR #10；CI run `33659017501` 的 Python、XPM、NP7 软件和物理证据四道门全部成功，PR 状态为 `OPEN / CLEAN`。
- Webhook 接收器已落盘该 run 的 `workflow_run completed/success` 与四个 `check_run completed/success` 事件；该接收器只提供本机通知落盘，不改变评审权限。

## 恢复检查

```powershell
.\workflow_resume.ps1 -Mode Resume
```

恢复脚本通过后，仍需读取活动 TODO 中当前阶段的完整合同，不能只凭本状态摘要实施。

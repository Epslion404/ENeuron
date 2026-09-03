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

## 2026-09-03 PR #10 当前 HEAD 终态确认

- GitHub Actions run `33712261128` 对应 HEAD `90b7e414da211985c7e8d83872ddc910e1706b18`，已于 2026-09-03 03:55:08 UTC 完成并成功。
- Python/语法、XPM CDC、NP7 功能与证据、NP7 物理证据完整性四道门全部为 `SUCCESS`；形式/突变检查和清单绑定也在当前 HEAD 上完成。
- 仓库外接收器 `C:\Users\Epsilon\ENeuronWebhook` 于 03:55:10 UTC 收到同一 SHA 的 `workflow_run completed/success`；本地 `/healthz` 返回 HTTP 200。
- PR #10 仍为 `OPEN / CLEAN`，本轮只确认具备人工合并条件，不自动 approve 或 merge；合并前不启动新的集成 RTL/Vivado 工作。

## 2026-09-03 PR #10 重跑终态确认

- run `33714262900` 已对 HEAD `15940b5aed8cb1e4127fab8bd904db4b9ab35433` 完成并成功；Python、XPM、NP7 功能/证据和物理证据四道门全部通过。
- NP7 功能门中的 oracle、周期协同仿真、三模型集成、形式与突变检查均成功；其中形式与突变检查于 04:44:35 UTC 完成。
- GitHub PR 汇总状态为 `OPEN / CLEAN`。本机 Webhook 未落盘该次重跑事件，不能作为第二份终态证据；GitHub 结果已独立核实。
- 当前阶段回到等待管理员人工合并；合并前不启动新的传统 NPU + 神经元集成 RTL 或 Vivado。

## 2026-09-02 PR #10 最终 CI 与知识库同步

- GitHub Actions run `33660700397` 已完成并成功：Python and syntax、XPM CDC wrapper、NP7 functional and evidence gate、NP7 physical evidence integrity 四道门全部通过。
- 本地 Webhook `C:\Users\Epsilon\ENeuronWebhook` 收到同一 run 的 `workflow_run`、`workflow_job` 和 `check_run` 事件；服务健康检查 `GET http://127.0.0.1:2355/healthz` 返回 200，接收器仍在仓库外运行。
- `.nexus-map` 已按当前 HEAD `f418c28` 刷新：168 个 Python 文件、39,944 行、解析错误为 0；临时 `.nexus-map/.refresh` 已清理，未进入提交。
- PR #10 仍为 `OPEN / CLEAN`，本轮不自动 approve、不自动 merge；下一步继续等待管理员合并决定，随后重新审核传统 NPU + 神经元集成计划。
- 仓库外 Webhook 接收服务已复核可用：`C:\Users\Epsilon\ENeuronWebhook`，PID `42144`，本地健康检查 HTTP 200；服务文件和日志不属于仓库。
- 2026-09-03 复核时 Webhook 进程曾退出；已从 `C:\Users\Epsilon\ENeuronWebhook\start_webhook.ps1` 重启，健康检查恢复为 HTTP 200，继续作为后续 CI 通知接收器。
- 重启后的 HEAD `9cced26` 对应 run `33711162898` 已由 GitHub 与 Webhook 双重确认成功；四道门全部通过，PR #10 保持 `OPEN / CLEAN`。
- run `33720890399` 对 HEAD `832c785` 已由 GitHub 与仓库外 Webhook 双重确认成功；四道门全部通过，PR #10 仍保持 `OPEN / CLEAN`，等待人工合并。
- run `33723437364` 对 HEAD `d7f7824` 已由 GitHub 与仓库外 Webhook 双重确认成功；四道门全部通过，PR #10 仍保持 `OPEN / CLEAN`，等待人工合并。
- 2026-09-03 发现 Webhook 服务短暂停止，已从 `C:\Users\Epsilon\ENeuronWebhook\start_webhook.ps1` 重启，PID `42136`，本地健康检查 HTTP 200；run `33726255349` 的终态仍以 GitHub 为准，恢复后的事件继续交叉核对。

# ENeuron 持久工作流状态

模式：`PERSISTENT_WORKFLOW_V1`

最后更新：2026-09-04

状态：`ACTIVE / NP7_MERGED / I1_I6_APPROVED / OF1_OF6_V3_APPROVED / OF6_ORACLE_SIGNOFF / RTL_DESIGN_CONTRACT_V2_APPROVED / PR54_MERGED / TR1_TR6_APPROVED / RTL_TIMING_REPAIR_GREEN / FULL_REGRESSION_GREEN / DSP_GATE_PASS / VIVADO_OOC_SETUP_FAIL / TIMING_REPAIR_V2_REVIEW_REQUIRED`

## 当前活动目标

NP6/NP7 已完成并合并；I1-I6、OF1-OF6 V3、单时钟 RTL V2 八项裁定及 TR1-TR6 已批准。当前目标是保存 DSP V1 的真实 OOC 失败证据，并审核下一轮最小时序修复；未经 TR7-TR12 新批准不继续修改 RTL。

活动合同：`docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V1.md`、`docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_TEST_CONTRACT_V1.md` 和 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V2.md`。当前 RTL 已完成共享四 DSP lane、三拍组计算、active-mask 门控和全部功能回归。Vivado 2024.1 OOC 已确认恰好 4 个 DSP48E1，route/DRC 无错误且 hold 通过，但 100 MHz setup 仍未通过；板级、网口、DMA、功耗仍不在本阶段。

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
- DSP V1 实现 HEAD `5055073` 的 Vivado 2024.1 OOC 报告已生成：`2192 LUT / 1904 FF / 0 BRAM / 4 DSP48E1`，DSP 双重硬门通过；setup `WNS=-0.673 ns / TNS=-6.462 ns / 22` 个失败端点，hold `WHS=+0.090 ns / 0` 个失败端点，route errors=0、DRC errors=0。该结果取代旧 OOC 作为当前物理边界，但仍不是 100 MHz 通过证据。

## 允许动作

- 更新当前状态、TODO、任务计划和 Nexus 摘要，保留历史审计记录。
- 基于当前 RTL 的关键路径报告提出并实施最小时序修复，先保持软件/RTL 语义不变，再重跑局部回归和 Vivado OOC。
- 物理门通过后再规划 XC7Z020 顶层；在此之前不把 OOC 结果外推为板级吞吐、功耗或网口性能。

## 禁止动作

- 不把当前 Python 测试通过外推为 INT32 逐位一致、RTL 协议冻结或物理性能收益。
- 不把历史 NP6/NP7 的 Vivado 结果代替当前单时钟 NPU RTL 的 OOC 结果。
- 把 NP6 的逻辑资源和 vector-less 功耗解释成真实加速、BRAM 跳读或功耗收益。
- 将 cex、tmp 日志或来源不明的历史产物纳入正式证据。
- 清理、覆盖或混入当前工作树中的已有改动。

## 下一动作

归档 DSP V1 OOC 报告及哈希，等待管理员审核 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V2.md` 的 TR7-TR12。获批后才进入测试 RED、最小 RTL、定向/随机/全仓回归和同条件 OOC；通过前不进入 XC7Z020 顶层规划。

## 2026-09-04 Vivado OOC 物理门收口

- 使用 `G:\Xilinx\Vivado\2024.1\bin\vivado.bat`、器件 `xc7z020clg400-1`、OOC 顶层 `npu_eneuron_single_clock_skeleton` 和 100 MHz 时钟完成综合、opt、place、route、时序和 DRC。
- 资源：`LUT=2672`、`FF=1879`、`BRAM36=0`、`BRAM18=0`、`DSP=0`。
- setup：`WNS=-5.087 ns`、`TNS=-421.539 ns`、`244` 个失败端点；hold：`WHS=+0.098 ns`、`THS=0`、`0` 个失败端点。
- `ROUTE_ERRORS=0`、`DRC_ERRORS=0`，所以实现流程成功但物理门为 `NOT_PROVEN`；不能写成 100 MHz 收敛。
- OOC 限制：没有真实板级 I/O delay、DMA、PS、Ethernet 或 SAIF 活动；`RTSTAT-10` 与 `ZPS7-1` 为 OOC 环境 warning，不能替代板级签核。
- 当前等效周期至少需要消除约 `5.087 ns` 的 setup 余量；由 WNS 粗略推导的频率约为 `66.3 MHz`，仅作定位参考，不替代频率扫描。

## 2026-09-04 OF4b2b GREEN

- 状态矩阵补强回归覆盖四态下全部非法命令、单次握手、错误响应背压稳定、零副作用和错误消费后恢复；`MaskConfigProtocolRedTest` 共 `9/9` 通过。由于 OF4b2 已覆盖这些行为，本组属于回归补强，不伪称新的 RED 失败。
- `NpuEpochRuntime.bind_mask_port()` 已把 runtime 的运行中样本、结果背压、pending mask 与端口 staging 纳入 freeze 判定；完全 idle 且两侧为空时双端同步冻结。
- frozen 状态仍允许样本推理，但拒绝 mask 配置和 `STATE_CLEAR`；runtime 组合测试 `5/5` 通过，完整 oracle `41/41` 通过。
- 独立审计边界：全局 idle/freeze 只在 Python runtime 组合层证明；单时钟 RTL、Vivado、完整流接口和硬件资源仍未开始。

## 2026-09-04 OF4b2 GREEN

- 已实现最小 `MaskCommand`、`MaskCommandKind`、`MaskConfigPort` 和不可变 `MaskStepResult`。
- 当前 6 条 OF4b2 行为测试全部通过：四态正常流、错误响应稳定背压、保留位同索引重试、`MASK_ABORT`、非法 epoch 和样本边界激活。
- 已补充 `MASK_BEGIN(epoch=active_epoch)` 回归并修正 next-epoch 校验；当前 OF4b2 定向 7/7、完整 oracle 34/34 通过。
- 独立实现审计 PASS；next-epoch 与 `0xffffffff→0` 回绕、错误消费拍不接新命令均已手工复核。
- 完整命令矩阵的剩余非法组合、全局 idle/freeze 上层组合、RTL 和 Vivado 仍未开始。

## 2026-09-04 OF4b2 RED

- 已提交 `3fc3a3f`，新增 3 条公开行为测试；当前基线均按预期失败，确认命令机接口尚不存在。
- RED 覆盖四态 `empty/loading/complete/published`、非法命令一次握手与稳定错误响应、响应背压阻止新命令，以及保留位错误后的同索引重试。

## 2026-09-04 OF4b1 GREEN

- 独立审计 PASS，无阻断；实现只包含不可变 19-word mask 镜像解码，不含 active/staging、epoch、valid/ready、错误响应、逐拍配置或 RTL。
- `decode_mask_words()` 严格要求 19 个 `uint32`，按 LSB-first 解码 `mask0=512 bit` 与 `mask1=80 bit`；`word18[31:16]` 非零时拒绝且无副作用。
- OF4b1 定向测试 `2/2`、完整 oracle `27/27`、CI-Fast `8/8`、`compileall` 与 `git diff --check` 全部通过。
- 本切片未运行 Vivado；物理资源、时序和逐拍配置协议仍待后续阶段。

## 2026-09-04 OF4a 合并与 OF4b1 RED

- OF4a 已通过 PR #37 合并到 `main@59a8dca`；Webhook 与 GitHub API 同 SHA 终态均成功。
- OF4b1 两个测试方法在当前实现上得到 25 errors，原因是 `decode_mask_words()` 尚不存在。
- RED 覆盖 exact 19、首中尾严格 uint32、word18 保留位和全部 592 个 mask bit 的 LSB-first 映射；不涉及四态命令或 epoch。

## 2026-09-04 OF3 合并与 OF4a RED

- OF3 已通过 PR #36 合并到 `main@a93019f`；Webhook 与 GitHub API 均确认同一 HEAD 的 `PR Gate completed/success`。
- OF4a 三个测试方法在当前实现上得到 10 errors，原因是 `decode_model_words()` 与 `load_model_words()` 尚不存在。
- RED 已覆盖 634-word 精确长度、严格 uint32 类型/范围、8 个段边界映射，以及非法 bias 的首次装载/reload 零副作用。
- OF4a 已 GREEN：定向 3/3、完整 oracle 25/25；覆盖两层 bias 首尾的安全窗外值，包含最晚 `word633` 失败不部分发布。

## 2026-09-04 OF1b 合并与 OF3 证据冻结

- OF1b 已通过 PR #35 合并到 `main@6833237`；GitHub run `33831315136` 的 Fast check 与固定 `PR Gate` 成功。
- OF3 三项手算测试首次运行即 3/3 通过，证明当前业务实现已符合 `mask0[h*16+g]`、`mask1[o*8+g]` 和 `mac_count=4*group_reads`；本切片只补冻结证据，不修改核心。
- 内部单 bit 测试加入相邻 bit 负对照；两层 mixed 测试覆盖 mask0/mask1 的首尾线性位置；open+全零测试证明不得做数据相关零跳过。

## 2026-09-04 OF1a 合并与 OF1b RED

- OF1a 已通过 PR #34 合并到 `main@9d0c3e5`；GitHub run `33830336539` 的 Fast check 与固定 `PR Gate` 成功，四个不相关重门按 NPU-only 路径跳过。
- OF1b 四个定向测试在旧实现上得到 20 failures + 2 errors，证明权重隐式转换/裁剪、bias 无安全窗口、V1 参数未固定和 logits 可变。
- `load_weights()` 当前逐字段更新成员；后半段失败可能留下新旧模型混合，GREEN 必须先完整验证四块数据再原子提交。
- OF1b 最小实现已 GREEN：四项定向 4/4、完整 oracle 19/19；合法第二层边界模型精确到达 `INT32_MIN/INT32_MAX`，非法 reload 保留旧模型。

## 2026-09-04 OF1-OF6 V3 管理员批准与 OF1a RED

- 管理员已明确批准 OF1-OF6 V3，Python oracle 实施门解除；RTL 和 Vivado 仍须等待完整 oracle 冻结与后续设计审核。
- OF1a 两项定向测试在旧实现上真实失败：越界/非整数值未统一 fail-closed，`None` 抛出 `TypeError`，非法像素还会错误消费 pending epoch。
- 当前切片只允许修改 `npu_eneuron_reference.py`、`test_npu_eneuron_reference.py` 及必要状态/Nexus 文档。
- OF1a 最小实现已经 GREEN：定向测试 2/2、完整 oracle 15/15；完整回归与 PR CI 仍作为提交/合并硬门。

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

## 2026-09-03 仓库外接收服务与 PR #10 最新终态

- 接收服务实际目录为 `C:\Users\Epsilon\ENeuronWebhook`，绑定 `127.0.0.1:2355`；该目录不属于仓库，服务文件、日志和运行时 PID 不进入 Git。
- 本地 `GET /healthz` 返回 HTTP `200`；带完整 GitHub 事件标头的本地 `workflow_run` 模拟接收返回 HTTP `200`，事件摘要正确写入 `latest.json` 与 `events.jsonl`。
- Webhook 已收到 run `33726377825`、HEAD `6893964a8a7c3c04e683dd8331c399f72df3440a` 的 `workflow_run completed/success`；CI 四道门均已完成成功，PR #10 仍为 `OPEN / CLEAN`。
- 集成审核合同没有改变：`docs/planning/NPU_NEURON_INTEGRATION_REVIEW.md` 仍为 `REVIEW_REQUIRED`，I1-I6 尚未获得管理员批准；在批准前只做静态审计、文档和 Nexus 维护。

## 2026-09-03 集成材料包草案与 CI 收口

- 新增 `docs/planning/NPU_NEURON_INTEGRATION_MATERIALS.md`，给出待管理员裁定的首个传统 NPU 候选（8×8、`64→32→10` INT8 MLP）、定点格式、门控粒度、逐周期接口、最坏情况矩阵和实现顺序。
- 材料包明确：现有 NP7 共享突触执行器不是完整传统 INT8 NPU；网口/DMA/PS 延后到片上单时钟功能闭环之后。
- 集成审核仍为 `REVIEW_REQUIRED`；I1-I6 未批准前不创建集成业务 RTL、不运行新的 Vivado。
- PR #10 HEAD `b5165824275a71008f8acaa820448f675c8df42a` 对应 run `33730940941` 已完成成功；GitHub 与仓库外 Webhook 均收到 `workflow_run completed/success`。
- Nexus 子代理本轮因外部服务配额返回 403，未产生改动；本次状态由主代理按本地证据维护。

## 2026-09-03 `da819cf` CI 与 Webhook 闭环

- 文档与 Nexus 提交 `da819cfdb6b492cd4bcb426aba8af3d8490007f5` 已推送到 PR #10。
- run `33728135382` 已完成成功；Python/语法、XPM CDC、NP7 功能与证据、NP7 物理证据四道门均为 `SUCCESS`。
- 仓库外 Webhook 已收到同一 SHA 的 `workflow_run completed/success` 和四项检查成功事件；接收服务仍由 `C:\Users\Epsilon\ENeuronWebhook` 独立运行。
- PR #10 仍为 `OPEN / CLEAN`，不自动 approve/merge；集成审核 I1-I6 仍为 `REVIEW_REQUIRED`。

## 2026-09-03 `cadc3a8` CI 与 Webhook 最终确认

- 当前文档状态提交 `cadc3a812ee614d7d9e07caf12a3c7e8bbd0eaad` 已推送到 PR #10。
- run `33729657078` 已完成成功，四道 PR 门均为 `SUCCESS`；Webhook 已收到同一 SHA 的 `workflow_run completed/success` 和四项检查成功事件。
- PR #10 仍为 `OPEN / CLEAN`，不自动 approve/merge；集成审核 I1-I6 未获批准，仍禁止集成 RTL/Vivado。

## 2026-09-03 PR #14 合并与接收器修复

- PR #14 已于 `2026-09-03T11:42:44Z` 合并到 `main`，merge commit 为 `b754498a3cba871459eca87f509ff6482a7fc12c`。
- 合并前 HEAD `78062a74bfb42d6d54eea7e18b83425b11a64659` 对应 Actions run `33749767954`；Python/语法、XPM CDC、NP7 功能与证据、NP7 物理证据四道门全部为 `SUCCESS`。
- 仓库外 Webhook `C:\Users\Epsilon\ENeuronWebhook` 已于 `2026-09-03T11:40:22Z` 收到同一 HEAD 的 `workflow_run completed/success`；本机 `GET http://127.0.0.1:2355/healthz` 返回 HTTP 200。
- 接收器仍完全位于仓库外。已修正启动/停止脚本，使其按 `webhook_server.py` 命令行识别真实 Python 监听进程，避免旧 wrapper PID 导致重复启动或误停止；当前监听 PID 为 `3308`。
- 集成审核合同没有改变：`docs/planning/NPU_NEURON_INTEGRATION_REVIEW.md` 仍为 `REVIEW_REQUIRED`，I1-I6 未批准前只做静态审计、文档和 Nexus 维护，不实现集成业务 RTL、不运行新的 Vivado。

## 2026-09-03 PR #15 合并收口

- PR #15 已于 `2026-09-03T12:09:13Z` 合并到 `main`，merge commit 为 `feec6bcb5444c164d7403d66cf1b2e1f7e36ab91`。
- PR #15 HEAD `fc6332597ac34905e2e4a102d92eaa582cb81ef0` 对应 run `33752156575`；四道 CI 门全部成功，仓库外 Webhook 已收到同一 SHA 的 `workflow_run completed/success`。
- 本次合并只包含 PR #14 终态记录、仓库外接收器脚本修复记录和 Nexus 刷新；未修改业务 RTL，未启动新的 Vivado。
- 当前活动门仍为 `NPU_NEURON_INTEGRATION_REVIEW_REQUIRED`；下一项实质工作必须等待管理员批准 I1-I6 与材料包。

## 2026-09-03 PR #16/#17 合并后当前入口

- PR #16 已合并为 `3850df77fd505b871acfc5a9c913aef25ff9bf78`；其 HEAD `46840e8c536b15068b55ae1324abd3a59f774f0a` 对应 run `33753869517`，四道 CI 门全部成功，仓库外 Webhook 已收到同一 SHA 的 `workflow_run completed/success`。
- PR #17 已合并为 `0ca6a50d4b4724b75387188bb3321f27a69caa59`；其 HEAD `5a6b554200e42730674b8b4afe730ba37724b6b7` 对应 run `33755848063`，四道 CI 门全部成功，仓库外 Webhook 已收到同一 SHA 的 `workflow_run completed/success` 与 `pull_request closed`。
- PR #16/#17 只包含文档、持久工作流和 Nexus 状态收口；没有传统 NPU + ENeuron 集成业务 RTL，也没有启动新的 Vivado。
- 当前远端 `main` 为 `0ca6a50d4b4724b75387188bb3321f27a69caa59`，无开放 PR；工作树中的 `np75_tmp_sparse_protocol.ys` 是用户未跟踪文件，不得修改或提交。
- 当前唯一实质入口仍是 `NPU_NEURON_INTEGRATION_REVIEW_REQUIRED`。`docs/planning/NPU_NEURON_INTEGRATION_REVIEW.md` 仍为 `REVIEW_REQUIRED`，I1-I6 尚未批准；批准前只能进行静态审计、文档和 Nexus 维护。
- 仓库外接收服务固定在 `C:\Users\Epsilon\ENeuronWebhook`，监听 `127.0.0.1:2355`；服务文件、日志、PID 和事件摘要不进入本仓库。

## 2026-09-03 PR #18 合并收口与下一入口

- PR #18 `docs: refresh post-PR17 workflow baseline` 已于 `2026-09-03T13:12:29Z` 合并到 `main`，merge commit 为 `1877140c873f02a887c19b2a0cb5c903d4149ac7`。
- PR #18 HEAD `59bef59a473fe2e808328827815c95c43cafb887` 对应 Actions run `33758285464`；Python/语法、XPM CDC、NP7 功能与证据、NP7 物理证据四道门全部为 `SUCCESS`。
- 仓库外 Webhook 已收到同一 SHA 的四项 `check_run completed/success` 和 `workflow_run completed/success`；健康检查服务仍位于 `C:\Users\Epsilon\ENeuronWebhook`，不进入仓库。
- 本地 `main` 已快进到 `1877140` 并与 `origin/main` 一致；工作树唯一条目仍是用户未跟踪文件 `np75_tmp_sparse_protocol.ys`，未修改、未提交、未纳入 Nexus。
- PR #18 仅收口工作流状态与 Nexus 基线，没有新增传统 NPU + ENeuron 业务 RTL，也没有运行新的 Vivado。
- 当前下一入口仍为 `docs/planning/NPU_NEURON_INTEGRATION_REVIEW.md` 的 `REVIEW_REQUIRED`：I1-I6 和材料包未获管理员批准前，只进行静态审计、文档和 Nexus 维护；不得创建集成 RTL 或运行新的 Vivado。

## 2026-09-03 PR #19 合并与 Webhook 运维记录

- PR #19 `docs: record post-PR18 workflow baseline` 已于本日合并到 `main`；当前 merge commit 为 `63028d4`，本地 `main` 已与 `origin/main` 一致。
- PR #19 HEAD `d6ca09415eb857fc02d71131e962dd894fd58f3b` 对应 Actions run `33760749837`；Python/语法、XPM CDC、NP7 功能与证据、NP7 物理证据四道门均为 `SUCCESS`，PR 状态为 `CLEAN / MERGEABLE`。
- 该次 CI 期间 Webhook 服务短暂掉线，GitHub delivery API 记录 `workflow_run`/相关事件因 EOF 投递失败；已从 `C:\Users\Epsilon\ENeuronWebhook\start_webhook.ps1` 恢复服务，本地与公网 `/healthz` 均返回 HTTP 200。当前 gh token 缺少 `admin:repo_hook`，因此未调用官方 redelivery；CI 终态以 GitHub API 为权威证据。
- PR #19 只包含工作流、状态文档和 Nexus 更新，没有业务 RTL、Vivado 或板级测试；用户文件 `np75_tmp_sparse_protocol.ys` 仍未跟踪、未修改、未提交。
- 下一动作不变：等待管理员批准传统 NPU + ENeuron 集成审核 I1-I6；批准前不实现集成业务 RTL，不运行新的 Vivado。

## 2026-09-03 集成审核门静态审计快照

- `workflow_resume.ps1 -Mode Resume` 返回 PASS；当前 HEAD 为 `8d23347`，活动 NP4B TODO 未完成项为 0。
- GitHub 当前无开放 PR；最近 run `33763267873` 的四道 CI 门全部成功，`main` 与 `origin/main` 同步。
- 仓库外 Webhook `C:\Users\Epsilon\ENeuronWebhook` 的 `/healthz` 返回 HTTP 200，服务仍不属于仓库。
- `docs/planning/NPU_NEURON_INTEGRATION_REVIEW.md` 仍为 `REVIEW_REQUIRED`；I1-I6 未获管理员批准。
- 用户文件 `np75_tmp_sparse_protocol.ys` 保持未跟踪、未修改、未纳入 Nexus；批准前继续只做静态审计、文档和 Nexus 维护。

## 2026-09-03 I1-I6 管理员批准

- 管理员已批准 I1-I6，集成审核门从 `REVIEW_REQUIRED` 转为 `PYTHON_ORACLE_IN_PROGRESS`。
- 已冻结首个模型 `64→32→10` INT8 MLP、8×8/4 bit 输入、INT32 累加、隐藏 ReLU/`0..127` 饱和、四权重组门控、样本/批边界原子提交以及 OOC→XC7Z020→DMA/PS/网口顺序。
- 当前只进入 Python 旁路/门控参考模型阶段；bit-exact 和最坏情况矩阵通过前，不创建集成业务 RTL、不运行 Vivado。

## 2026-09-03 PR #21 合并后基线

- PR #21 `docs: audit integration review gate` 已在四道 CI 门和仓库外 Webhook 终态成功后合并，merge commit 为 `588e7d5`。
- PR #21 HEAD `bc546c0` 对应 run `33765822606`；Python/语法、XPM CDC、NP7 功能与证据、NP7 物理证据四道门均为 `SUCCESS`，Webhook 已收到同一 SHA 的 `workflow_run completed/success`。
- 当前本地 `main` 与 `origin/main` 同步到 `588e7d5`，无开放 PR；本次仅收口静态审计、状态文档与 Nexus，不含集成业务 RTL 或 Vivado。
- 集成审核门仍为 `REVIEW_REQUIRED`，I1-I6 尚未获管理员批准；用户文件 `np75_tmp_sparse_protocol.ys` 继续保持未跟踪且不纳入 Nexus。

## 2026-09-03 Python oracle 冻结审核

- I1-I6 已批准，函数级参考模型与 active/pending 协议已完成基础实现。
- 三项新增最坏情况测试覆盖全关零活动、连续 epoch 不混用和 pending 单槽背压；相关 NPU 测试 14/14 通过。
- 独立审计确认 INT32 溢出、固定参数域、mask 位序、不可变结果及逐拍流/复位合同仍是冻结阻断项。
- 当前活动门已由反审计修订为 `OF1-OF6_V2_REVIEW_REQUIRED`；详细方案见 `docs/planning/NPU_ORACLE_FREEZE_REVIEW.md`。
- OF1-OF6 未批准前可以提交现有测试、审计和知识库更新，但不修改上述争议语义、不创建集成业务 RTL、不运行 Vivado。

## 2026-09-03 OF1-OF6 V2 反审计

- 固定拓扑的最坏贡献范围证明：第一层 `[-122880,121920]`，第二层 `[-520192,516128]`。
- OF1 从“正常依赖 INT32 回绕”修订为“配置期拒绝可能溢出的极端 bias”；MAC 主路径不增加饱和逻辑。
- 模型配置改为 634-word 固定顺序一次装载，mask 改为 19-word 固定顺序和 active/staging 双 bank，避免 634/19-bit 完整性 bitmap 与双模型 RAM。
- 明确核心只接受 uint4，外部灰度裁剪属于 Host；prediction/abstain 也由 Host 从 logits 计算。
- 当前仍是审核稿，不修改 Python 业务语义，不创建 RTL，不运行 Vivado。

## 2026-09-03 CI Node 24 action 维护

- PR #31 run `33789363607` 成功，但 GitHub 对 `actions/checkout@v4` 发出 Node.js 20 弃用警告。
- 官方发布接口确认 checkout `v7.0.1`、setup-python `v7.0.0` 为当前稳定版，Node 24 action 的最低 runner 要求为 `v2.327.1`。
- 本切片将 workflow 主版本升级为 `actions/checkout@v7`、`actions/setup-python@v7`，并新增防回退单测。
- workflow 自身变化必须执行全仓、Windows XPM、NP7 功能与 NP7 物理门；全部通过前不合并。

## 2026-09-03 OF1-OF6 V3 二次反审计

- PR #32 已在全量 run `33790397482` 和 Webhook 同 SHA 终态成功后合并为 `1f9d3b7`；CI Node 24 action 基线完成。
- 第二轮独立审计确认 V2 仍缺 634-word 段内映射、非法配置错误响应、mask 四态命令矩阵、freeze 切换、零激活工作量和 Python 严格类型域。
- 审核稿已升级为 V3，当前人工门为 `OF1-OF6_V3_REVIEW_REQUIRED`。
- 获批后的首个实现切片固定为 OF1a uint4 fail-closed；停止点是 15 项 oracle 测试全绿，不顺带修改 bias、mask、协议或 RTL。

## 2026-09-04 真实计算 RTL 切片启动

- 管理员再次确认批准 V2 八项 RTL 设计裁定；合同仍为 `rtl_allowed=true`、`vivado_allowed=false`。
- 模型/流、mask epoch、控制三条 Icarus 切片已在 PR #54 提交；HEAD `8239063` 的快速检查成功，全仓回归仍需等待终态。
- 手算真实计算 tracer 已形成 RED：默认全开 mask 时期望 logit0=137，epoch 1 关闭 L0 bit0 后期望 -117；当前占位 RTL 返回 0。
- 当前允许动作是实现最小四 lane 顺序计算并完成 Python/Icarus 门；不得把该结果外推为 Vivado 资源、时序、功耗或板级性能。
- 最小真实计算路径现已 GREEN：默认 mask 得到 logit0=137，关闭 L0 bit0 后得到 -117；额外最高组向量得到 output9=59，关闭 L1 bit79 后得到 -1。
- 当前四项 RTL 切片联合回归、全仓 Python/语法检查和本地 `20×100` 随机 bit-exact 均已通过；随机 testbench 已提交至 PR HEAD `8ee7fe8`，等待 CI 重验。
- 四项 RTL 切片联合 4/4、Python `compileall`、diff-check 和独立 Icarus 编译已通过；等待完整仓库回归与提交审查。
- 完整仓库回归已通过 `469/469（1 skipped）`；历史 NP4B 证据文件的自动刷新副作用已恢复，不纳入本切片。
- 提交前独立复核发现的 bias 安全窗与运行期 mask 并发阻断已完成 RED→GREEN：四个越界点均同索引拒绝，当前样本保持旧 active mask，下一样本才采用新 epoch。
- 最终完整回归正在重跑；Yosys 仅完成开源前端/过程检查，不改变 `vivado_allowed=false`。
- 最终完整回归终态为 `469/469 OK（1 skipped）`；该条记录属于 OOC 执行前历史快照。当前 Vivado OOC 已完成但 setup 失败，板级证据仍未完成。
- 下一实质门是将随机 testbench 与证据纳入 PR #54 同一 HEAD，等待 GitHub CI 收敛；随后再申请 Vivado OOC。Webhook 当前掉线，GitHub API 为 CI 权威来源。
- PR #54 的原提交 HEAD 检查均成功；随机 testbench 已完成 `20×100` 并纳入 HEAD `8ee7fe8`，但 GitHub CI 尚未返回该 HEAD 的终态；本阶段仍禁止合并，直到 CI 完成。
- 文档/Nexus 状态修正已推送至 PR #54 HEAD `ccfbecc`；该 HEAD 的 CI 正在运行，不能把 `IN_PROGRESS` 视为通过。

## 2026-09-04 PR #54 合并后状态更正

- PR #54 已于 2026-09-04 合并，merge commit 为 `2a33f12`；该提交包含真实单时钟计算 RTL、固定 `20×100` 随机逐 beat testbench 及对应文档。
- 上述“等待随机门 CI”“禁止合并”和“随机门未提交”条目均为历史记录，不再代表当前状态；当前随机门状态为 `RTL_RANDOM_GATE_GREEN / PR54_MERGED`。
- 当前已证明范围：四 lane 顺序 INT8 计算、隐藏层饱和、active-mask 门控、结果背压、sample ID/mask epoch 逐 beat 一致，以及 469/469（1 skipped）仓库回归。
- 当前未证明范围：Vivado 2024.1 OOC 资源/时序/DRC、XC7Z020 顶层、网口/DMA/PS 端到端吞吐、板级功耗和持续学习收益。
- 下一硬门改为 Vivado 2024.1 OOC；所有物理结论必须绑定 `origin/main@2a33f12`、约束、Tcl/runner 和报告 SHA-256。

## 2026-09-04 Vivado OOC 失败后的活动入口

- PR #55 已合并为 `main@dc2452b`；OOC 证据、manifest、报告索引和 Nexus 状态已进入主线。
- 当前物理状态为 `VIVADO_OOC_SETUP_FAIL / TIMING_REPAIR_REQUIRED`：2672 LUT、1879 FF、0 BRAM、0 DSP；setup `WNS=-5.087 ns`、`TNS=-421.539 ns`、244 个失败端点；hold、route 和 DRC 无失败。
- 关键路径分类已完成，当前设计审核稿为 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V1.md`。
- 该历史阶段的人工门为 `TIMING_REPAIR_V1_REVIEW_REQUIRED`：当时等待管理员批准 TR1-TR6，批准前只允许文档审计和测试合同检查。
- 获批后的唯一主链为：测试合同调整 → `FETCH→EXECUTE→COMMIT` 最小分拍 → 定向/固定 `20×100`/全仓回归 → 同器件同约束 Vivado OOC。
- 用户文件 `np75_tmp_sparse_protocol.ys` 保持未跟踪、未修改、未暂存、未纳入 Nexus。

## 2026-09-04 PR #56 合并与测试合同准备

- PR #56 已在独立反审计修正 TR3 后合并为 `main@2a0f2ce`；最终 HEAD `21be24b` 的 Actions run `33893097155` 与仓库外 webhook 同 SHA 均为 success。
- `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V1.md` 仍为 `REVIEW_REQUIRED`，TR1-TR6 未获得管理员批准；合并审核稿不等于批准裁定。
- `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_TEST_CONTRACT_V1.md` 已准备批准后的测试切片：全开/关闭两组/仅关闭 L0 最后一组/全关分别要求 592/590/591/0 次执行和 1860/1856/1858/676 拍计算延迟；五个 watchdog 均无需放宽。
- 当前 `rtl_allowed=false`、`vivado_allowed=false`；允许继续文档、测试合同与 Nexus 审计，不创建 RED testbench、不修改业务 RTL。

## 2026-09-04 TR1-TR6 批准与强制 DSP

- 管理员已批准 TR1-TR6，并附加要求四条乘法 lane 强制使用 XC7Z020 DSP48E1；此前 `TIMING_REPAIR_V1_REVIEW_REQUIRED` 和 `BLOCKED_BY_TR1_TR6_APPROVAL` 已解除。
- 当前状态为 `TIMING_REPAIR_DSP_V1_IN_PROGRESS`，`rtl_allowed=true`；Vivado 只允许在定向、C1-C4、固定 `20×100` 和完整回归通过后执行。
- DSP 合同为四条共享 signed 8×8 乘法 lane，只对乘积施加 `USE_DSP="yes"`，实现报告必须 `DSP=4`。DSP 数不符或 setup 失败均保持物理门未通过。
- 外部协议、INT32、`64→32→10`、整组 mask、epoch 原子性、结果背压、freeze/clear 和 8/10 beat 合同不变。

## 2026-09-04 DSP 三拍 RTL 功能签核

- 已实现 L0/L1 共用的四条 signed 8×8 DSP lane，以及 `FETCH→EXECUTE→COMMIT` 三拍调度；关闭组仍在 FETCH 直接旁路。
- C1-C4 的结果、592/590/0/591 个启用组、1860/1856/676/1858 拍、逐组访问图、模型地址、关闭末组写回均通过。
- 单时钟专项 `8/8`、固定 `20×100` 随机和完整仓库 `473/473（1 skipped）` 通过；最终 RTL/Tcl 反审计无 blocker，测试覆盖 blocker 已补齐。
- 该历史阶段状态是 `VIVADO_PENDING`，当时不能提前声称 `DSP=4` 或 100 MHz 收敛；随后已经由实现提交 `5055073` 完成 OOC。

## 2026-09-04 DSP V1 OOC 终态与 V2 审核门

- Vivado 报告绑定实现提交 `50550733e4af4779f3d6933738fa043ecb919970`；utilization `DSP=4`、实现网表 `DSP48E1_COUNT=4`，强制 DSP 条件成立。
- 资源为 `2192 LUT / 1904 FF / 0 BRAM / 4 DSP48E1`；hold、route 和 DRC 通过。
- setup 未通过：`WNS=-0.673 ns`、`TNS=-6.462 ns`、22 个失败端点，物理状态必须保持 `VIVADO_OOC_SETUP_FAIL`。
- 新最差路径是组号动态激活选择、DSP 乘法和四路求和到 `lane_sum_latched`；残余路径包含 logit 写使能。因此下一轮需同时审核操作数锁存和独立 WRITEBACK。
- `NPU_SINGLE_CLOCK_TIMING_REPAIR_V2.md` 已形成 TR7-TR12 审核稿；当前 `rtl_allowed=false`、`vivado_allowed=false`，等待管理员批准。

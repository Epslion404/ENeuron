# 进度记录

## 2026-09-06 本机验收与计费边界

- 管理员确认当前 GitHub Actions 额度耗尽，后续不再使用 GitHub 付费功能；本阶段不主动触发或等待 GitHub-hosted Actions。GitHub 仍保留版本管理、PR 和人工审查用途。
- 本机回归：`python -X utf8 -m unittest -v test_reproducibility test_ci_fast_v1`，共 12 项，全部通过。
- 隔离复现：`python -X utf8 tools/repro/verify_repository.py --t1`，返回 `REPRO_G0_MANIFEST_PASS`、`REPRO_G1_T1_PROTOCOL_SLICE_PASS`。
- 提交 `88905a9` 已包含非法 fence、mask staging/epoch、FIFO busy 汇合、CDC 二级同步和 fence epoch 回显修复；随后提交 `47a3c1e` 扩展了 T1 背压、epoch 切换和复位重入切片。
- T1 testbench 已扩展并在同频 100 MHz 下通过：响应背压字段稳定、样本进行中 mask epoch 原子性、复位重入旧数据清除；当前切片覆盖 T1-01/03/04/05/07/08/10/11 的主要路径。
- T1-02 主要路径现已通过：`STATE_CLEAR` exactly-once、`FREEZE_SET` 状态同步以及冻结期间拒绝配置；当前切片覆盖范围增加 T1-02。
- T1-12 FIFO 边界切片已通过：四种 payload 宽度均完成空读、17 槽外部可见满写、overflow、回绕、长背压和顺序排空；T1-12 仍需后续与 wrapper 并发账本合并复核。
- T1-06 独立 fence 验收已通过：staging 未闭合时拒绝且不开放窗口，发布后返回 `0xD` 并回显 fence ID/active epoch，`T1_FENCE_ACCEPT_PASS` 已接入本机复现入口；T1-09 仍因 TLAST 位于外层 shim 而待裁定/独立验收。
- T1-09 边界裁定已落档为 `NA_FOR_T1_WRAPPER / OUTER_SHIM_PENDING`；静态合同测试确认当前 wrapper 无 TLAST 端口，外层 shim 尚未实现，因此不把该项写成当前 T1 仿真通过。
- T2 首个三配置可变时钟切片已通过：`NPU_HALF/PHASE=7/2、9/1、4/3`，完成跨域事务、背压、sideband 和复位重入验证；`tb_npu_zynq7020_t2_variable_clocks.sv` 与 `verify_repository.py --t2` 已加入复现闭包。
- 提交 `c55a8b6` 已将 T1 FIFO 边界 testbench、复现清单闭包和本机复现入口推送到 PR #68；远端 head 已核对为该提交，Actions 仍暂停且 checks 为空。
- 已通过 GitHub API 暂停仓库 Actions（`enabled=false`），随后将 `88905a9`、`47a3c1e`、`3227162` 推送到 PR #68 分支；远端 PR head 已核对，未触发或等待任何 hosted runner。
- 保护文件继续保留且不暂存：`local_prune_rtl_results.json`、`np4b_signoff_summary.json`、`np75_tmp_sparse_protocol.ys`。
- 当前状态保持 `T1_PROTOCOL_SLICE_PROVEN / T1_FULL_PENDING`；T1-01～T1-12、T2、T3 和首次完整端到端运行未完成，资源裁剪不得提前实施。

## 2026-09-07 GitHub 可复现性门规划

- 对当前 `HEAD=fc47dc9` 生成 `git archive` 隔离快照，在快照内运行 CI-Fast、NPU Oracle 和 artifact layout，共 57 项通过。
- 确认该结果只覆盖已提交基线的一部分；本地 T1 wrapper 仍不能编译，相关文件尚未全部进入 GitHub，不能宣称 T1 可复现。
- 完成依赖、运行入口、Vivado 路径、manifest、artifact 索引和 Actions 固定方式审计。
- 新增 `docs/planning/GITHUB_REPRODUCIBILITY_GATE_V1.md`，冻结 G0-G3 四层目标并提出 R1-R9 待管理员批准事项。
- 本轮未修改生产 RTL、T1 testbench、GitHub Actions 或 Vivado 报告，未提交用户已有的三个保护文件。

## 2026-09-07 GitHub 可复现性门实施

- 新增统一入口、依赖/工具链锁、仓库 manifest 和 T1 复现检查器。
- T1 wrapper/testbench 由入口在临时目录执行 Icarus 编译与仿真，要求 `T1_PROTOCOL_SKELETON_PASS`。
- CI 分类新增 `t1_repro`，工作流新增 T1 专项 job；合同测试与 CI-Fast 定向测试通过。
- Vivado runner 支持 `-VivadoRoot`/`VIVADO_ROOT`，artifact 索引已修正为当前 `VIVADO_OOC_PASS`。
- 仍未宣称 T1-01～T1-12 完整通过；T2/T3/G3 未完成。

## 2026-09-03 仓库外 Webhook 接收服务复核

- 确认本机接收服务独立部署在 `C:\Users\Epsilon\ENeuronWebhook`，未写入 ENeuron 仓库。
- 服务进程 PID `42144` 正在运行，`127.0.0.1:2355/healthz` 返回 HTTP 200。
- 本地发送 `workflow_run` 探测请求并收到 HTTP 200；事件摘要成功写入服务目录的 `latest.json`。
- 仓库工作树未新增服务文件；当前仍只存在既有未跟踪 `.nexus-map/refresh_raw/` 临时目录。
- 正式 GitHub 接收仍建议配置本机环境变量 `GITHUB_WEBHOOK_SECRET` 与 `WEBHOOK_REQUIRE_SIGNATURE=1`；密钥不得进入仓库。

## 2026-09-03 PR #10 当前 HEAD CI 收口

- 提交 `c8fe1d1` 对应 GitHub Actions run `33717188485` 已于 2026-09-03 05:15 UTC 完成成功。
- Python/全仓测试、XPM CDC、NP7 功能/形式/突变与物理证据四道门全部通过。
- PR #10 仍为 `OPEN / CLEAN`，未自动批准或合并。
- 仓库外接收器收到了 `workflow_job` 完成事件，但 `latest.json` 尚未出现该 run 的完整 `workflow_run` 终态摘要；这项漏收行为保留为后续服务修复 TODO，不能替代 GitHub API 证据。

## 2026-09-03 PR #10 CI 终态确认

- run `33718742404` 已于 2026-09-03 13:39（北京时间）完成成功，HEAD 为 `becada247d386e6ee71d12dd76b6300458719c13`。
- 四道门全部通过：Python/全仓测试、XPM CDC、NP7 功能/形式/突变、NP7 物理证据完整性。
- GitHub API 是本轮终态的权威证据；仓库外 Webhook 的 `latest.json` 仍停留在上一轮 `workflow_job`，因此未将其当作第二份终态证据。

## 2026-09-03 Webhook 服务恢复

- 轮询发现 `127.0.0.1:2355` 曾拒绝连接，确认仓库外接收服务已停止，而 GitHub Hook 配置仍为启用状态。
- 通过 `C:\Users\Epsilon\ENeuronWebhook\start_webhook.ps1` 重启，当前 PID `5108`，健康检查 HTTP 200。
- 因服务在本轮 CI 终态前离线，本轮 Webhook 不具备完整事件证据；继续以 GitHub API 核对 CI，并观察恢复后的后续事件。

## 2026-08-29 NP4B1 ENeuron 正式接入

- `digital_lif_engine.sv` 新增纯组合参数化 committed snapshot 导出；lane 顺序固定，未增加寄存器、读取握手或修改 snapshot/MOD 状态机。
- 新增 `eneuron_local_prune_wrapper.sv`：合法非零 MOD 与 gate OBSERVE 同一接受边界启动，gate backpressure 可阻止核心单独更新。
- snapshot 量化先扩展到 13 位再取绝对值，覆盖 `-2048`；`issue_mask` 在输入送入核心前生效。
- 零 MOD、错误 commit ID、INFER MOD 和响应背压不污染 utility；未剪枝旁路与裸核心逐事务一致。
- 默认 `AUTO_CLEAR_ON_COMMIT=1` 在公开 commit 成功前自动清动态历史；网络实例可设为 0，由公共 barrier 在全部 gate 完成后统一 clear。
- 先后复现缺端口、缺 wrapper、过早响应和缺网络管理参数四类 RED；最终相关 13/13 回归通过，Icarus `-Wall` 无警告。
- NP4B1 只签核单核接入；10 核 ENeuron 网络和端到端事务仍待 NP4B3/NP4B4。

## 2026-08-29 NP4B3 固定一拍网络调度

- 新增 `pruned_network_tick_scheduler.sv`，一次合法 TICK 同拍启动 8 个 detector 和 2 个四输入 output。
- 两个 output 的四路输入固定来自 TICK 接受前的 `pending_hidden`：output0 使用 detector 0..3，output1 使用 detector 4..7；本拍 detector 结果只在 all-done 后成为下一拍 pending。
- 10 个核心响应允许错拍到达，使用 sticky done 汇合；对外 spike 与 pending 路由只在全部响应完成后原子更新。
- route flush 只启动两个 output，不推进 detector；完成后清 pending，避免 episode 最后一拍丢失或重复推进隐藏层。
- 新增两项 Icarus 公开接口测试，均按 RED→GREEN 完成；连同提交屏障共 5/5 通过。
- 当前尚未把三种神经元 wrapper 实例化进网络，也未实现 CAPTURE/FEEDBACK/MOD 等训练命令调度。

## 2026-08-29 NP4B5 Pulse 形式 harness 修复

- 修复 Pulse-Mini-L/L2 旧 harness 的复位矛盾：首拍要求 reset，之后持续 release，不再形成不可满足的正常运行轨迹。
- 响应断言补入背压保持语义，避免把合法多拍 `rsp_valid` 错判为失败。
- 两个核心均新增 TICK、CAPTURE、FEEDBACK、CAPTURE→FEEDBACK 四类成功路径 reach 标记和独立 SAT witness。
- L/L2 depth=20 不变量检查均通过；每个模型找到四个预期 witness，共生成 8 个非空 VCD。
- 新日志 schema 为 `np4b5_v2`，明确 `old_v1_logs_invalid=1`；缺少该标记的历史 Pulse 形式日志不再作为有效证据。
- 专属 verifier 通过，Pulse L/L2 Python 参考回归 26/26 通过。边界仍是有限深度检查，不是无限归纳或活性证明。

## 2026-08-29 NP4B3 网络提交屏障

- 新增参数化 `local_prune_commit_barrier.sv`，默认服务 10 个四输入组。
- 提交前同时检查安全边界、全部 gate ready 和全部核心 clear ready；任一未就绪时返回 UNSAFE，零 gate 启动。
- gate commit 与核心 `STATE_CLEAR` 分别使用 sticky done 屏障，允许响应错拍到达；外部成功、mask 集合和 epoch 只在第二个屏障后公开。
- 清历史失败不回滚已提交 mask，置 sticky internal error 并永久阻止运行/新提交，避免伪造成功。
- 新增三项公开接口 Icarus 测试；先复现缺模块 RED，再完成 GREEN。与公共 gate 测试合计 6/6 通过。
- 该提交只完成 NP4B3 的公共原子屏障；`4→8→2` TICK/训练调度和三模型接线仍未完成。

## 2026-08-29 NPU 局部剪枝 NP4B 八项决定批准

- 用户批准 NP4B 八项实现决定，状态由 `REVIEW_REQUIRED` 转为 `IMPLEMENTATION_APPROVED`。
- 允许增加 ENeuron committed snapshot 只读端口、Pulse 外部 wrapper 和独立 `4→8→2` 测试网络；不修改 Pulse 核心 opcode，不替换现有 `4→2→2` 网络。
- 剪枝保持独立 sideband 通道、每个四输入神经元一个 gate、`STATE_CLEAR` 与 `PRUNE_CLEAR` 分离。
- network `PRUNE_COMMIT` 只有在全部 gate 完成且自动 `STATE_CLEAR` 成功后才对外完成。
- 本批准只开放 NP4B1→NP4B6；NP6 Vivado 仍须完成集成签核后再次批准。

## 2026-08-29 NPU 局部剪枝 NP4B 规划

- 新增 `docs/planning/NPU_PRUNING_NP4B_TODO.md`，状态为 `REVIEW_REQUIRED`；本轮只规划和审计，未修改 RTL，未运行 Vivado。
- ENeuron 接入必须导出 committed snapshot，并在合法 MOD 接受边界与 gate OBSERVE 原子协调；MOD 完成后再读取会遇到 snapshot valid 已清除。
- Pulse-Mini-L/L2 必须在 FEEDBACK 接受沿锁存旧 captured direction，核心返回成功后再 OBSERVE；零反馈和失败响应不更新 utility。
- 固定新建 `4→8→2` 测试网络：8 个四输入 detector、2 个四输入 output、固定一逻辑 tick 路由、每个神经元一个 gate；保留现有 `4→2→2` 网络。
- network `PRUNE_COMMIT` 先全体预检、统一启动，完成全部 gate 与自动 `STATE_CLEAR` 后才对外成功；中间禁止运行命令。
- 规划包含三模型各 20×1000 端到端事务、四类负向实现、Pulse 旧形式 harness 修复和进入 NP6 的九项签核门。
- 下一步等待用户批准八项 NP4B 实现决定；批准前不写集成 RTL。

## 2026-08-29 NPU 局部剪枝 NP4A/NP5 公共控制器

- 新增独立 `local_prune_gate_2of4.sv`：S2-only、四路 4-bit utility、四拍 top-2、一次原子严格 `2:4` 提交。
- 新增三种固定 gain 适配器，ENeuron/Pulse-Mini-L/Pulse-Mini-L2=`1/2/1`；公共控制器不包含模型选择或权重绝对值比较器。
- `issue_mask` 在读取/发射边界前组合形成，hidden/output 的稠密请求、实际读取/操作和结构节省分别计数。
- 三模型各完成 20 seeds × 1000 逐事务 Python/Icarus 协同仿真，总计 60000 条，零差异。
- 非原子提交与反向同分规则两个故障变体均产生预期反例。
- Yosys 0.56 depth=32 有限形式检查通过；独立可达性检查强制 `mask_commits=1`，证明不是空证明。
- 当前只签核公共控制器。ENeuron snapshot evidence 旁路、Pulse FEEDBACK 前证据锁存和真正四输入输出组仍待实现，NP6 Vivado 未启动。

## 2026-08-29 NPU 局部剪枝 NP4 V1 接口批准

- 用户批准 B2.1 推荐的六项 V1 决定，NP4 从 `REVIEW_REQUIRED` 转为 `IMPLEMENTATION_APPROVED`。
- 隐藏层与输出层统一严格 `2:4`；三模型 evidence gain 固定为 ENeuron/Pulse-Mini-L/Pulse-Mini-L2=`1/2/1`。
- 每组只允许一次原子 `PRUNE_COMMIT`，V1 不实现渐进剪枝状态机或整 detector/channel enable。
- 输出稀疏后的权重恢复只走既有 TRAIN/FEEDBACK 事务，不增加直接恢复写口。
- `issue_mask` 必须在权重读取和计算发射前形成，隐藏层与输出层结构节省分别计数。
- 下一步先冻结独立控制器周期合同并测试先行实现 NP4；NP5 通过前不进入 Vivado，也不宣称剪枝硬件成立。

## 2026-08-28 NPU 局部剪枝原始 Goal 签核

- 按原始范围逐项审计 NP0 八项批准、三模型独立运行、文档记录和分阶段提交，证据全部闭合。
- NP2/NP3/B2.1 机器结果源码哈希仍与当前工作树一致；全仓回归 312/312 通过。
- 原始 Goal 状态改为完成；NP4-NP9 是新的后续工程阶段，不以软件结果替代 RTL/Vivado/功耗证明。
- NP4 六项 V1 决定仍为 `REVIEW_REQUIRED`，明确批准前不创建剪枝 RTL。

## 2026-08-28 NPU 局部剪枝 B2.1

- 三模型完成 output-2:4、detector-3:4、detector-2:4 与 10 个共享随机 mask 对照。
- 三候选 BAcc/coverage 均为 100%；全网读取/发射分别为 120/120/80，相对稠密减少 50%/50%/66.67%。
- 输出稀疏后每输出使用两次正常训练事务恢复，零直接权重和阈值写入，被剪输出权重不变。
- 工作量节省分解互不重叠，输入本来为零不计为结构收益。
- 所有 learned/random mask 都为 100%，结论限定为冗余消除，不宣称评分优于随机。
- 按 KISS 选择 output-2:4；NP2/NP3/B2.1 联合门允许启动 NP4 设计审核，RTL 仍未实现。
- 机器结果绑定提交 `d03cc6b`，九个源码和两个前置结果哈希全部匹配。

## 2026-08-28 NPU 局部剪枝 NP3

- 三模型完成一次 `2:4`、软件渐进 `3:4→2:4` 和错误符号三分支，全部共享各自父 checkpoint 和两次微调预算。
- 一次/渐进分支 BAcc/coverage 均为 100%，最终 mask 相同；按 KISS 冻结为一次剪枝。
- 错误符号真实进入 ENeuron modulator 与 Pulse FEEDBACK，三模型 BAcc/coverage 均降为 0%。
- 完整账本证明零 Host mask 写入、每 detector 一次 commit、被剪权重/历史冻结、mask 微调稳定及同分支 INFER 指纹冻结。
- NP3 三模型全部通过；正常全网读取仍为 160，下一步只剩三模型 B2.1 输出侧工作量门。
- 机器结果绑定提交 `5652576`，八个运行时源码哈希全部匹配。

## 2026-08-28 NPU 局部剪枝 NP2

- 完成三模型 gain=`1/2/3` 固定量化扫描，禁止按 seed、detector 或样本调参。
- 最小合格配置为 ENeuron/L/L2=`1/2/1`；三模型 BAcc/coverage 均为 100%，10/10 seed 不低于共享随机对照。
- Pulse-Mini-L 的 `0→0, 1→2` 映射使重复证据产生净累计，撤销 B2 阶段的累计评分永久 `NO_GO`。
- 入选配置的边界同分、clip、最终占满均为 0%，前缀稳定性和误导保持率均为 100%。
- 三模型全网络读取/发射仍为 160，相对 240 只减少 33.33%；NP4 继续禁止，下一步完成 NP3 和三模型 B2.1。
- 机器结果绑定提交 `bb15296`，八个运行时源码哈希全部匹配。

## 2026-08-28 NPU 局部剪枝 B2

- 新增固定 `4→8→2` 冗余 detector 压力任务；所有 10 个神经元仍是四输入，输出要求至少 3/4 同类 detector 同时响应。
- 10 seed 结果：ENeuron S2/S3 median BAcc 100%、随机 75%；L2 S2/S3 100%、随机 25%；L S2/S3 0%、随机 25%。
- ENeuron/L2 的 S2 均为 10/10 seed 不低于随机，算法门通过；L 仅 3/10，不通过。
- S3 相对 S2 没有精度增益，按 KISS 删除 S3 额外复杂度；ENeuron/L2 只保留 S2 软件候选。
- 负对照：过早剪枝均为 50%；S1 均为 0%；分数打乱 median 为 ENeuron 50%、L/L2 25%。
- 工作量：ENeuron/L2 保持精度时全网络读取由 240 降至 160，仅减少 33.33%；L 降至 80 但 BAcc 为 0%，不算有效节省。
- 三模型联合决定均为 `rtl_go=false`。下一步先在软件层验证输出 detector/通道门控，使有效全网络减少跨过 45%，并补 NP3 剩余负对照。
- B2 机器结果绑定代码提交 `6f52a7a`；schema v2 已补 coverage 门和 `local_prune_b1.py` 依赖哈希，本阶段不进入 Vivado。

## 2026-08-28 NPU 局部剪枝 B1

- 完成 ENeuron、Pulse-Mini-L、Pulse-Mini-L2 三个薄适配器；未修改三个神经元方程或已签核 RTL。
- Pulse 网络增加 `core_type` 注入，使 L/L2 共用同一个 P8 结构、训练顺序和一拍路由；默认 L 行为保持不变。
- 三模型从各自单一稠密 checkpoint 公平分支 dense/random/S0-S3；随机 seed 1016 和掩码 `1001/1100` 跨模型一致。
- 三模型 dense 与 S0-S3 均为 20/20、coverage 100%；随机均为 10/20。S0-S3 全部选择 `0011/0011`，所以 B1 通过协议闭环但不能选择评分算法。
- 全网络发射计数相对 dense 仅减少 ENeuron 18.21%、Pulse-Mini-L/L2 19.78%，未达到 45% 系统收益门；输出层保持稠密且活跃通道被保留是主要原因。
- 修正审计漏洞：补一拍 output route flush；不应期不计权重读取或结构节省；Pulse 直接写权重计数来自真实核心日志；checkpoint 哈希绑定控制器、utility 和 mask；工作量按阶段差分并标注全网络 scope。
- B1 机器结果绑定代码提交 `2b8bd55`；相关专项实现回归 87/87 通过。下一步只进入 B2 软件实验，不进入剪枝 RTL。

## 2026-08-28 NPU 局部剪枝 NP1

- 完成独立 `LocalPrune2of4` 黄金模型：S0-S3、严格 `2:4`、TRAIN/CONFIG/INFER 模式、16 位 commit/observation ID、V1 禁止自动长回和确定性事务日志。
- 动态门控在发射前执行 `structural_mask & activity_mask`；账本分开记录稠密请求、真实权重读取、突触操作、结构节省、全零不活动组和结构完全跳过组。
- B0 扩展为 19 项测试，覆盖 16 种活动输入、16 种配置掩码、6 种合法输出、S0-S3 区分、饱和/衰减、exactly-once、原子拒绝和 INFER 冻结。
- 固定 `local_prune_b0_vectors.json` 与 `artifacts/results/local_prune_b0_results.json`，摘要绑定四个源文件 SHA-256；NP1 已达到软件黄金模型硬门。
- 下一步进入 NP2/NP3：三种神经元从同一稠密 checkpoint 分支 dense/random/S0-S3，先跑 B1 协议闭环，再设计有辨识力的多 seed B2。

## 2026-08-28 NPU 局部自动剪枝规划

- 新增 `docs/planning/NPU_PRUNING_TODO.md`，状态为 `REVIEW_REQUIRED`；本轮只规划，不修改已签核神经元 RTL。
- V1 主线冻结为待审核的四输入组 `2:4`：训练期本地评分生成结构掩码，推理期与活动掩码相交，并要求在 BRAM 读取与计算发射前生效。
- 评分先比较 S0 权重幅度、S1 单次资格迹、S2 资格迹累计和 S3 低成本组合；若 S3 没有明确优于 S0，按 KISS 删除额外神经评分逻辑。
- TODO 拆为 NP0-NP9，覆盖黄金模型、软件消融、剪枝微调、独立 RTL、协同/形式验证、Vivado、共享 lane 真跳算、可选恢复和系统签核。
- 当前 D2 图像稠密基线失败，明确禁止在稠密任务通过前用剪枝结果声称图像识别有效。
- 用户已批准 NP0 八项决策；规划状态改为 `APPROVED`。
- 执行范围扩展并冻结为三条独立实验线：ENeuron、Pulse-Mini-L、Pulse-Mini-L2。三者共享数据与验收合同，但不得用其中一个版本的成功代替另两个版本的结果。

## 2026-08-26 当前项目报告

- 新增 `docs/reports/PROJECT_REPORT.md`，统一汇总原始 Goal M1-M4、ENeuron/Host Bridge/Tile 架构、Pulse-Mini 系列、FPGA 资源与时序、验证证据和 8×8 数字识别 D0-D2。
- 报告以生成前 HEAD `be062e0` 和仓库内冻结产物为依据，明确区分 routed 实测、协同仿真、有限形式验证、软件基线、估算和未证明项。
- 结论冻结为：ENeuron 已是经过验证的数字可塑神经元与固定小网络硬件基石；数字识别 D2 未通过，大规模自主学习、共享 RAM/lane、板级闭环与实测功耗仍未完成。
- 本轮仅修改文档，没有重跑完整回归或 Vivado；完成引用文件存在性检查与 `git diff --check`。

## 2026-08-26 FPGA 图像识别性能评估

- 完成 8×8 D2 与代表性 28×28 网络的资源、状态和吞吐量级估算。
- 结论：8×8 在 XC7Z020 上具备硬件可行性，但当前 D2 算法未过门；28×28 不能直接复制现有寄存器核，需要 BRAM 状态与 8/16 条共享 lane。
- 建议验收顺序冻结为：软件多种子准确率与负对照、共享 lane bit-exact、Vivado routed、最后板级 30/60 fps 与功耗实测。

## 2026-08-19 Pulse-Mini L1

- 已确认当前 Pulse-Mini 的关键能力缺口是胞体无泄漏，稀疏事件可无限累加。
- 已实现共享膜电位泄放计时器：只随成功 `TICK` 推进，先泄放、后输入、再阈值判断；`STATE_CLEAR`、自然发放和硬复位清零。
- Python 黄金模型 17 项定向测试、单核 20000 事务、固定网络 272 命令和 32/64/128 阵列指标均通过。
- 预注册扫描 `{0,1,2,4,8,12}`：周期 8 是满足当前密集命中、稀疏误发放、训练权重一致和网络合同的最小候选；周期 4 会损失弱连接 `+1` 的密集命中。
- 已生成 `docs/reports/SIMULATION_COMPARISON_REPORT.md` 与 `artifacts/results/comparison_simulation_results.json`，并完成 200 项 Python 回归、Pulse-Mini 单核 20000 事务、固定网络 272 命令、形式深度20证明。
- 统一比较已补齐第三方键名：`eneuron`、`pulse_mini` 和 `pulse_mini_l`；收敛、负对照、噪声、稀疏度、共同网络与原生网络协议均同时输出三者。
- 正式执行 `python compare_simulation.py --seeds 20 --rtl-cosim` 通过；报告明确区分黄金模型三方消融与默认 Pulse-Mini-L RTL 旁证，没有把局部教师训练写成纯全局 reward 能力。
- 报告新增“网络层优缺点”表，分别列出 ENeuron、Pulse-Mini 与 Pulse-Mini-L 在状态表达、复制/路由、稀疏事件和全局 reward 方面的取舍。

## 2026-08-13

- 启动 G4 能力边界调研；当前只形成可审核实验方案，不修改核心训练模型或 RTL。
- 审计确认现有训练仅有两个固定模板，所谓 noisy test 与训练模板同源；teacher sweep 也没有 20 个独立初始化。
- 确认历史 `artifacts/results/network_sweep_results.json` 早于当前 `network_sim.py`，且未被 `verify_goal.py` 纳入门槛，不能作为当前签核结果。
- 冻结下一步为三任务只读探测、原始资料核对、统计门槛和硬件映射方案；用户审核后才进入正式实现。
- 主会话独立复跑 3 任务 x 3 模式 x 10 seeds，与子任务结果和数据集抽样 SHA-256 完全一致；未创建临时实验文件。
- 探测确认 Spatial teacher/hybrid 为 100%，Spatial reward 为 15%；Temporal 全部为 0%，XOR 仅 hybrid seed 9 命中 8/256，且失败主要表现为无输出 spike。
- 核对 e-prop 与 GEM 原始资料，形成 `docs/design/g4_capability_validation_proposal.md` 审核稿；方案增加活动率校准、strict decoder、direct-weight 容量对照、当前 RTL/no-WTA 与 Python/WTA 分组，以及持续学习 ACC/BWT/FWT。
- 完成固定全 2 初态的 burst calibration 探测：`B=1` 无活动，`B=2` 三任务均达到 100% hidden/output activity，并与 `RtlReferenceNeuron` 的 300 样本 spike count 完全一致。
- 随机初始化探测确认继续增大 burst 不能保证救活所有 seed；V2 将 calibration 限定为固定初态编码正对照，各训练模式必须独立验收 activity/coverage。
- 完成任务/统计反例审查：旧 Temporal 首事件泄漏标签，label shuffle 可被全 abstain 伪通过，持续学习排列不是独立样本；已在 V2 中分别修正。
- 完成 Host Bridge/P5 反例审查：reward 可与 action 恢复二分类标签，hybrid 只能冻结隐藏权重，Host 无法读回完整内部学习状态；已冻结纯全局 reward、黑盒/白盒证据边界及逐 seed 权重装载合同。
- `docs/design/g4_capability_validation_proposal.md` 已修订为 V2 审核稿；核心 Python 模型与所有 RTL 均未修改，当前等待用户批准五项冻结决策。
- 对 V2 做第二轮独立反证审计，确认 Temporal 仍有单位置/半程计数/bigram 确定性泄漏，P4 未冻结 Host replay 权限，P5 存在同源 oracle 自证和真实 XPM 层级混称风险。
- 独立枚举验证新的 10-symbol 循环 Temporal motif：两类在逐位置 unigram/bigram、前后半计数和全局 1..3-gram 分布上完全相同，类别差异从 4-gram 开始。
- 审核稿已升级为 V3：episode 改为 64 tick；P4 增加 no-replay 与 joint-training 上限；P5 拆为接口等价 FIFO 完整 cohort 和真实 XPM 短 cohort；新增 P6 共享 RAM 多参数点扩展性硬门。
- 核心 Python 模型和 RTL 仍未修改；旧 48-tick `B=2` 结果只保留为探索证据，等待用户审核 V3 六项冻结决策。
- 完成 V3 Temporal 64-tick 只读活动探针：128 样本下 `B=2/3/4` 均 100% active，高层/RTL-reference spike count 全一致；固定全 2 权重的 strict decoder 仍全 abstain。
- 完成 Temporal 容量预判：225 个有效隐藏权重形成 137 种唯一签名；6929 个隐藏组合 x 全 225x225 输出读出器中最好为 25/32，独立高层重放一致。该结果记录为风险，不作容量否证。

- `verify_goal.py` 一键审计通过：43 项前的软件回归、10000 个 Tile 混合事务和最终 Vivado routed 报告均满足既定 G1/G2 门槛；脚本明确保留 G3/G4 与形式等价为未证明。
- 独立协议审查发现并由 Icarus 定向测试复现 Tile 并发命令优先级 bug：非法高优先级 SNAPSHOT 可与低优先级合法 WEIGHT 同周期发生，Tile 报错但子核仍写权重。
- 修正组合派发逻辑：命令存在决定优先级，合法性只决定是否产生子核请求，使其与时序仲裁一致。
- 完整 Python/Icarus 回归增加至 43 项并全部通过；20 seeds x 500 Tile 混合事务再次通过，共 10000 事务。
- Yosys 0.56 使用真实四核和敌对任意命令输入完成 24 拍协议 BMC：约 451 万变量、1252 万子句，无反例。
- 报告时间戳门正确拒绝旧 Vivado 报告；经官方 `vivado.bat` 重跑后，100 MHz setup `+0.053 ns`、hold `+0.026 ns`、route error 0，资源 3144 LUT / 1971 FF。
- `verify_goal.py` 已把 24 拍 BMC 纳入硬门槛；最终结论仍限定为 G1 与固定 4->2->2 G2，G3/G4 和全状态形式等价未证明。
- 完成 G3 前端调研：现有 Python 有事件 FIFO/背压，Tile 只有聚合 mask，缺少可综合桥接、响应保持与 CDC。
- 确认 Python `flush_route()` 只推进输出层，普通零输入 Tile TICK 语义不等价；V1 必须新增 `ROUTE_FLUSH`。
- 形成 `docs/design/host_bridge_v1_proposal.md` 审核稿：128-bit 双流、两个 XPM async FIFO、episode/tick staging、单槽 snapshot 背压和 exactly-once 响应合同；尚未开始 RTL 实现。
- 完成 Host Bridge 第二轮只读反例审查，发现响应 opcode 截断、TRAIN EP_END 部分提交、hard reset 清权重、txn_id 无重传去重、ABORT 未冻结、tick 回绕、零 pending flush、组合权重读和 XPM reset-busy 等 10 项合同缺口。
- 修订 `docs/design/host_bridge_v1_proposal.md`：改为同构 128-bit 响应；EP_END 先完整预检；明确 17-bit tick 尾态、无条件 ROUTE_FLUSH、两拍 WEIGHT_READ、破坏性 hard reset 与有序 ABORT；当前仍处于用户审核阶段，未开始 Host Bridge RTL。

## 2026-08-11

- 完成空项目检查。
- 确定比较对象：无泄漏 IF 基线、二因子 STDP LIF、三因子资格迹线 LIF。
- 完成标准库 Python 模拟、单元测试和硬件复杂度代理指标。
- 完成 10 种训练顺序和 100 组输入扰动实验。
- 推荐三因子 LIF 作为面向自训练与推理的最小可塑单元。
- 完成 4->2->2 两层事件网络，隐藏到输出固定 1 tick 路由延迟。
- 完成 Host `commit_id` + eligibility 快照协议，验证训练提交与主机延迟解耦。
- 完成 20 seeds 初始网络 sweep：可寻址目标调制 100% 成功；未加 WTA 的全局 reward 约 50%。
- 增加数字逐 tick WTA 和随机初始权重；纯全局 reward 仍只有 22.5%，确认 WTA 不等于信用分配。
- 增加两阶段 Host 训练：目标调制隐藏层、reward 训练输出层；20 seeds 干净/扰动准确率均为 100%。
- 修正不应期输入门控，使原型与推荐规格一致；回归测试和 sweep 结果保持不变。
- 增加 `cycle_transport.py` 有界 FIFO/背压周期模型和 `docs/design/rtl_contract.md`。
- 周期协议测试覆盖同 tick 原子提交、一拍输出路由、输出时间戳、未排空 FIFO 拒绝新 episode、延迟 commit 快照；总测试数 22 项。
- 增加 `digital_lif_core.sv` 单神经元 RTL 参考核、`rtl_smoke.py` 和 `artifacts/results/rtl_smoke_results.json`；静态接口检查通过，但本机无 HDL 编译/综合工具。
- 开始 Goal 证明审计；当前回归为 27 项中 25 通过、1 失败、1 错误，失败均位于新增 RTL 参考验证层。
- 确认当前 Python RTL 参考与 SystemVerilog 核存在多处状态更新语义差异，尚不能建立 bit-exact 证据。
- 尝试执行 `git diff --stat` 失败：当前目录不是 Git 仓库；后续以工作区文件、测试日志和工具报告作为审计证据。

## 2026-08-12

- 恢复多周期 RTL 工作上下文，读取计划、发现、现有黄金模型与冻结契约。
- 使用 Icarus Verilog 编译最新 `digital_lif_engine.sv`，返回码为 0。
- 重跑完整基线回归，38 项全部通过；这些测试尚未覆盖多周期 FSM。
- 初审发现零调制错误清除 snapshot，以及非二次幂输入数的地址宽度配置风险。
- 新增多周期事务级 Icarus/Python 协同仿真；5 个 seed × 128 个事务和 `N_INPUTS=1/3/5` 边界通过。
- 扩大到 20 个 seed × 1000 个混合事务，共 20000 个事务全部通过。
- 完整回归增加至 40 项并全部通过；Yosys 初检发现地址临时变量多驱动，正在修正。
- 第一次增加周期/原子性断言的整块补丁因上下文不匹配未应用；已改为逐段小补丁，不重复原失败操作。
- 修正地址临时变量多驱动后，Yosys `check` 只剩数组展开提示，不再报告结构问题。
- 依次根据 Vivado 最差路径完成突触两拍流水、定宽 eligibility/trace/state 衰减和 resolve 三段流水。
- 最终 Vivado 2024.1 post-route 达到 100 MHz：WNS +0.469 ns、TNS 0、setup/hold 零失败；资源 813 LUT / 544 FF / 0 BRAM / 0 DSP。
- 完整回归 40 项全部通过；新增原子性和精确周期合同后，10 seeds × 256 事务继续通过。
- 新增 4->2->2 Tile RTL 与独立 Python tile oracle；seed 0 的 24 事务冒烟和 `test_rtl_tile_cosim.py` 当前单测通过。
- Tile 结构复查第一次调用因当前 PowerShell `PATH` 中没有 `yosys` 而中止；这是工具定位问题，尚未形成新的结构检查结论。
- Tile 扩大随机协同仿真通过 20 seeds × 500 个混合事务，共 10000 个事务；完整回归增加至 41 项并全部通过，`compileall` 通过。
- Tile Vivado 首次启动在 PowerShell `.bat` 调用边界失败，Vivado 尚未读取设计；运行器已改为经 `cmd.exe /d /c` 调用官方 wrapper。
- Tile 首次 Vivado OOC 实现已路由成功：+0.231 ns setup、+0.128 ns hold，3157 LUT / 1972 FF；因缺 `HD.CLK_SRC`，已补 OOC 时钟上下文并准备重跑，最终报告以后一次为准。
- 补充 `HD.CLK_SRC` 后重跑最终 Tile OOC：WNS +0.148 ns、TNS 0、WHS +0.057 ns、THS 0、3861 个端点零失败、route error 0；资源 3156 LUT / 1972 FF / 0 BRAM / 0 DSP。
- Tile DRC 仅有 OOC `CFGBVS-1` warning；methodology 的 162 个 `TIMING-18` 均来自未设置真实顶层 I/O delay。功耗 0.104 W、Medium confidence、无活动文件。
- 增加固定黄金回归，明确断言一 tick 路由、非零 eligibility、合法 MOD 后的已知权重、过期 commit 拒绝、零调制和 INFER 冻结；完整回归 42 项通过。
- 更新 RTL 合同、推荐设计、README 和 Goal 审计；当前结论分为 G1 学习基石已验收、固定 G2 Tile 原型已验收、G3 板级系统与 G4 通用自训练未完成。
- 增加 `verify_goal.py` 一键审计：重跑软件回归与 10000 个 Tile 事务，并硬检查 Vivado timing、route、DRC、资源和功耗报告；成功结果仍明确标记 G3/G4 未证明。

## 2026-08-13

- 完成 Host Bridge V1 第三轮终审，修正 STATUS 两页覆盖、EP_END 动态字段优先级、response_accept 提交边界、flush spike 保持和 sticky fatal 语义。
- 直接核对本机 Vivado 2024.1 `xpm_fifo_async` 源码和官方实例模板，冻结 FWFT 为 `FIFO_READ_LATENCY=0`；根据“`rst` 必须同步于写时钟”修正双域 reset 方案，并保留 reset-busy 双侧门控合同。
- 在 `docs/design/host_bridge_v1_proposal.md` 增加七类实现任务依赖图和逐项权威验收证据表；当前仍未修改 Tile/Bridge RTL，等待用户批准五项架构决策。
- 记录两次工具/补丁异常：一次并行 Vivado 路径检索因不存在目录返回非零，改为精确读取 XPM 源码；一次上下文补丁未匹配且未产生部分写入，改用精确小补丁完成。
- 最终放行复核发现 XPM reset 重入合同缺失；已冻结为两个 FIFO 的 write-side `wr_rst_busy` 均退出后才允许再次断言 `bridge_rst`，并将断言和随机合法重入加入 T4 验收。
- T1 Tile `ROUTE_FLUSH` 已完成：Icarus 定向回归 5/5、真实四核 24 拍 BMC 无反例；Vivado 2024.1 OOC 为 3152 LUT / 1972 FF、WNS +0.213 ns、WHS +0.026 ns、TNS/THS 0、route error 0。
- T3 controller 已通过 Icarus 语法检查；当前 RED 测试明确缺少 `host_bridge_controller_cosim.py`，下一步用真实 controller + Tile + 四个 `digital_lif_engine` 建立逐命令 scoreboard。
- T2 Host Bridge oracle 终检完成：32 项测试通过，包含 1000 个 codec 随机向量与 10 seeds x 1000 混合命令；全量 discovery 的唯一错误仍是 T3 缺失 cosim 模块。
- T3 新增 `host_bridge_controller_cosim.py`，实例化真实 controller、Tile 和四个 `digital_lif_engine`；定向流及 20 seeds x 1000 混合命令逐响应、逐架构状态、逐 Tile/核心状态 bit-exact。
- T3 的随机 testbench 对每条响应施加 0..4 周期背压，断言 `rsp_data` 保持、Host architectural state 在 `response_accept` 前不提交；定向 MOD 响应确认返回更新后 `weight_epoch=1`。
- 修正 `static_bad_field()` 的隐式模块寄存器依赖，MOD 编码合法性现在直接检查函数局部 `arg1`，保持函数纯度。
- T3 定向流扩展为 64 条命令，并硬性覆盖全部 V1 非保留、非 `INTERNAL_FATAL` 状态码；`INTERNAL_FATAL` 留给显式 Tile 故障注入/formal，不用正常 Tile 行为伪造。
- T4 新增 `digital_snn_host_bridge.sv` 与接口等价 `xpm_fifo_async_sim.sv`；两个 128-bit depth-16 FWFT FIFO 的满队列、40 项回绕、双向背压、合法 hard reset 和非法 reset 重入三项测试通过。
- T4 首轮测试曾因仿真 FIFO 的 `full -> write_accept -> wr_gray_next -> full` 组合环在 delta-cycle 死锁并超时 120 秒；将 full 改为写时钟域寄存状态后，定向 transport 单测 0.054 秒通过，根因闭环。
- T6 controller formal：负向环境控制在 depth 4 复现无请求 `tile_done` 反例；加入抽象 Tile 合同后 depth 20 safety BMC 无反例（1,459,959 variables / 3,970,672 clauses）。
- T6 六类非空 witness 均可达：response stall 8 拍、architectural commit 10 拍、protocol error 8 拍、fatal 14 拍、WEIGHT_READ 12 拍、TRAIN EP_END 20 拍；仍不等于无限时域或 CDC 证明。
- 新增 `digital_snn_host_bridge_system.sv`，显式集成 transport、controller 与真实四核 Tile；Icarus 全层次 elaboration 通过，Vivado 2024.1 OOC 综合无 black box、0 error/critical warning，资源 3722 LUT / 2574 FF / 4 RAMB36 / 0 DSP。
- T5 新增 `host_bridge_system_cosim.py` 与双时钟系统回归；20 seeds x 2000 flit（共 40000 命令）在随机非整数时钟比、随机相位、producer/consumer 背压下逐响应与 Python oracle 一致，且命令/响应背压均被实际覆盖。
- T5 hard reset 固定回归通过：reset 前写权重并验证饱和值，response 阻塞时形成 12 个 outstanding 命令，hard reset 后旧 ledger/响应丢弃且权重恢复 INIT_WEIGHT=2。
- T5 首个 hard-reset RED 是测试手写期望错误：请求权重 9 被硬件合法饱和为 7；改由独立 oracle 生成期望后通过，未修改 RTL。
- 修复 Icarus FWFT 预取槽模型：RAM 搬入预取槽独立推进读指针；T4 三项全部通过，完整回归保持 85/85。
- 真实 Vivado 2024.1 XPM xsim 完成双向容量 17、排空、64 字回绕、背压和 hard reset；日志无 fatal/reset misuse/overflow/underflow，综合确认仿真断言未入网表。
- 系统双时钟 cosim 重跑通过：20 seeds x 2000 flit，共 40000 命令；`compileall` 和全量 85 项回归通过。
- 完成 Host 50 MHz / Tile 100 MHz 系统 post-route：Host WNS/WHS +14.306/+0.105 ns，Tile WNS/WHS +0.081/+0.058 ns；两域 TNS/THS 0，route/DRC 0。
- 系统 CDC 8 条全部限定在官方 XPM 内部；XPM 外 Critical/Unsafe/Warning 均为 0。资源为 3682 LUT / 2486 FF / 4 RAMB36 / 0 DSP。
- 升级 `verify_goal.py`：发现不少于 85 项回归，运行 Tile/Controller 两套有限 BMC，审计真实 XPM 与完整系统 routed 报告；继续明确板级、无限时域和通用 AI 未证明。
- 最终执行 `python verify_goal.py` 退出码 0：85 项回归、Tile depth-24 BMC、Controller depth-20 BMC 与 6 类 witness、额外 10000 个 Tile 事务、真实 XPM 17/17 容量和系统 post-route/CDC/DRC 全部通过，打印 `GOAL_AUDIT_PASS`。

## 2026-08-13 V3 批准后实施

- 用户批准 V3 六项冻结决策，Goal 保持 active；G4 与 P6 完成前不得标记 complete。
- 已启动 T0：审计确认 `verify_goal.py` 尚未检查独立 Tile，旧文档数字也与最新原始报告漂移。
- 已将 `vivado_tile_synth.tcl` 改为生成机器可读摘要并执行时序、路由、白名单告警和资源预算硬门。
- 已将 `run_vivado_tile_synth.ps1` 改为使用 `$PSScriptRoot`、限定清理固定目录、检查必需产物与新鲜度。
- T1 测试和 T0 验证器测试由两个独立任务按文件边界并行编写，主线不修改其目标测试文件。
- T0 独立 Tile Vivado 2024.1 最终硬门通过：3152 LUT / 1972 FF、WNS/WHS +0.213/+0.026 ns、route error 0、白名单 DRC/methodology、0.103 W Medium-confidence vector-less 估算。
- 修复 XPM 摘要解析：首行必须精确为 `VIVADO_XPM_WRAPPER_PASS`，后续继续使用严格 `KEY=VALUE`；定向 7 项与真实 XPM 报告通过。
- Temporal RED 反例覆盖 `label_hint`、duplicate+nonce、跨 split/label 的 B、非法 IID/OOD 区间、伪造 seed/sample/skeleton provenance、skeleton ID 复用和 manifest 源路径伪造。
- Breaking API 冻结为共享数据集：`generate_temporal_split(master_seed, split, burst_width)`；model seed 只改变模型初始化/训练随机性，统计按 paired model-seed。
- Temporal validator 增加精确 schema、全局冻结 B、直接 skeleton ID 配对和按冻结参数重放认证；manifest V2 增加 input/example 双哈希并绑定真实生成器源码。
- 重生成 `g4_temporal_development_manifest.json`：1312 个唯一输入与完整样本，SHA-256 `97A57856E3038E5AAC8FE32E435735742081AE2FD7D6EE0EC63F65782D6281AA`；仍只是 development cohort，不代表 P0a/P0b 或 G4 通过。
- 完整 156 项回归、两套 formal、额外 10000 个 Tile 事务、独立 Tile 和真实 XPM 均通过后，一键审计在系统 `cdc_classification.txt` 的固定首行 `CDC_CLASSIFICATION` 处失败；未把该解析失败误报为系统签核失败。
- 新增系统 CDC 专用严格解析器与 3 项合同测试；通用 `KEY=VALUE` 和 XPM 专用解析器保持不变。真实系统报告重新验证通过，discovery 增至 159 项。
- 最终执行 `python verify_goal.py` 用时约 274 秒并以退出码 0 完成：159 项回归、Tile depth-24 BMC、Controller depth-20 BMC 与 6 类 witness、20 seeds x 500 Tile 压力、独立 Tile、真实 XPM 和系统 routed/CDC/DRC 全部通过，打印 `GOAL_AUDIT_PASS`。
- 最终审计仍明确打印 `NOT_PROVEN`：无限时域/全状态等价、板级 I/O/异步复位源、bitstream 在板闭环、真实活动功耗与 G4 通用 AI 自训练未证明。
- T0/T1/T2 已收口；下一阶段是 T3 训练策略与 P0-P4，P5/P6 仍按已批准的分层 RTL cohort 和 Host V2/共享 RAM 架构执行。Goal 保持 active。
- 收齐 T3 的 Tile 协议、Host API 和容量/运行成本三路只读审计；未修改训练实现或 RTL。
- 新建 `docs/design/g4_t3_execution_spec.md` 审核稿，明确 12 项二级冻结决策、当前 inference freeze FAIL、Temporal 容量风险、精确统计算法和批准后的测试先行任务顺序。
- `task_plan.md` 已增加 T3 二级审核 gate；在用户批准前不创建正式训练 runner。Goal 保持 active。
- 收齐 T3 三路独立反证；确认原审核稿存在公共置换统计失真、P3 comparator 未定义、canonical 枚举不可复现和按“权重实际改变”计 commit 可能不终止等批准阻断项。
- 修订 `docs/design/g4_t3_execution_spec.md` 的 12 项二级合同：加入信用状态机、公共 permutation、GEM 公式、80-tick 计分边界、`python -I -S` worker、model-only bundle、RandomPlan、确定性 direct search、完整 Spatial/XOR canonical 数据合同、clone checkpoint 和 fresh-run commit 预算。
- 本轮只修改执行规格与计划记录；未修改训练实现、神经元方程或 RTL。V3 六项保持已批准，T3 十二项仍等待用户审核，Goal 保持 active。
- 本机补测 `python -I -S`：`sys.path` 只含 Python 标准库，直接执行旧 `network_sim.py` 无法导入同目录模块。已据此把 D5 worker 收紧为自包含单入口/受控 bootstrap，而不是降低隔离强度。
- T3 Host/no-replay 最终复核发现 D5 的原审计钩子合同会同时阻断合法 bundle 首次加载；本机 Python 3.14.2 审计事件探针复现 `compile` 与 `exec` 事件。已把规格改为哈希冻结 bootstrap + 单文件 bundle、一次性 `LOADING_VERIFIED_BUNDLE -> SEALED` 状态机，并保持 T3 十二项状态为 `REVIEW_REQUIRED`；未创建 runner、未修改神经元方程或 RTL。
- D5 修订后通过独立 Host/no-replay 终审；三路 T3 反证审计均无剩余 P0/P1。最终规格 SHA-256 为 `D88EBE4A64C34DAE42E5C16888E2F786F4C560D6BE0B90EBFF1F48749009DE0C`；D1-D12 计数、`g4_rng_v1` golden vector、D10 空间/golden skeleton 和 `compileall` 均通过，核心模型及 Temporal manifest 哈希未变化。当前等待用户明确批准 T3 十二项二级决策。
- 按用户要求回到原始 Goal 做证据复核，不继续扩写 T3。确认当前核心仍是寄存器化固定 4->2->2，Host `WEIGHT_WRITE` 可直接写权重，历史 Hybrid 还会直接重置输出权重；因此后续必须把“初始化权限”和“训练权限”分离，以命令轨迹证明训练期只经 eligibility snapshot + MOD_COMMIT 更新，并将共享 RAM/共享流水线 P6 提升为原始 Goal 的核心硬门。
- 新建 `docs/design/original_goal_alignment_review.md` 审核稿：把原始 Goal 主线收敛为 C1 训练来源封印、C2 真实 RTL 任务闭环、C3/C4 共享 RAM 三参数点扩展、C5 板级 golden loop；T3/G4 的纯 reward、持续学习、no-replay 和复杂统计保留为后续研究，不再作为核心硬件前置门。审核前不修改 Host/RTL。
- 对对齐稿做第二次第一性原理修订：撤销把 `RUN_SEAL`、共享 RAM 三参数点和板级 bitstream 列为最小基石必要门槛。核心完成条件改为 M1-M4，其中唯一未完成的是现有 Host Bridge + Tile 上的任务级 RTL 训练/局部更新/冻结推理闭环及学习来源账本；扩展性、板级和 G4 均改为后续独立声明。

## 2026-08-14 原始 Goal M1-M4 批准后实施

- 用户明确批准原始 Goal M1-M4 四项决策；`docs/design/original_goal_alignment_review.md` 状态改为 `APPROVED`。
- 实施顺序冻结为 C1 最小任务合同、C2 真实双时钟 RTL 任务闭环、C3 学习来源审计、C4 独立验收器。现有神经元方程和 RTL 默认保持不变，以 RED 测试决定是否需要最小修正。
- C1 只读复核完成：两轮、四次 `MOD_COMMIT` 是最小可靠训练量；训练前全 abstain，训练后 clean 与冻结扰动均正确，训练命令中 `WEIGHT_WRITE=0`。
- 新增 `m3_task.py`/`test_m3_task.py` 的 oracle 合同和 `m3_training_ledger.py`/`test_m3_training_ledger.py` 的命令哈希链审计；新增 `run_command_sequence()` 作为真实双时钟 RTL 连续命令入口。相关 4 项测试已通过。
- C2/C3 已通过：真实双时钟 RTL 连续执行 957 条命令，四次提交逐次读回全部 12 权重，20/20 扰动推理正确，训练期 `WEIGHT_WRITE=0`，最终权重冻结。
- 新增 `m3_acceptance.py` 与反例测试，冻结四次 eligibility/定点 delta/饱和向量、命令 SHA、响应账本 SHA 和 hash-chain 尾值；篡改快照、账本或任务结果均会失败。
- `verify_goal.py` 已加入 M3 独立硬门和 `m3_signoff_summary.txt` 生成，回归数量下限提高到 169；文档结论更新为原始 Goal M1-M4 已成立，扩展性、板级和通用 AI 仍未证明。
- 最终执行 `python verify_goal.py` 用时 294.8 秒并以退出码 0 完成：169/169 回归、Tile depth-24 BMC、Controller depth-20 BMC 与 6 类 witness、10000 个 Tile 压力事务、957 条 M3 双时钟闭环，以及 Tile/XPM/系统 Vivado 报告全部通过，打印 `GOAL_AUDIT_PASS: 原始 Goal M1-M4 最小硬件基石门槛通过`。

## 2026-08-19 ENeuron 1.0 与 Pulse-Mini

- 用户授权完全访问并明确要求先提交当前版本，再规划 Pulse-Mini 并形成 `docs/planning/TODO.md`。
- 恢复并复核既有计划文件、M1-M4 对齐稿、README、M3/T0 摘要和 Zynq-7020/Vivado 实测报告。
- 确认当前目录尚未初始化 Git；版本提交将从 `main` 分支的首个提交开始。
- 识别到发布可复现性约束：不能整目录忽略 Vivado 证据，必须保留 `verify_goal.py` 默认读取和新鲜度检查依赖的最小产物集合。
- 记录两次只读 PowerShell 命令写法错误，均未修改项目文件；已改用精确路径和中间变量完成审计。
- 独立发布审查定位 `docs/design/rtl_contract.md` 的旧 Tile 资源/时序数字，已与当前 Vivado 冻结摘要统一，并在 README/发布说明中补充干净检出的 `--rerun-vivado` 要求。
- 发布前完整执行 `python verify_goal.py`，退出码 0：169/169 回归、Tile/Controller 有限 BMC、10000 个 Tile 事务、957 条 M3 命令和 Vivado 报告审计全部通过；`docs/planning/TODO.md` 此时仍不存在。
- 创建根提交 `499fc8a`：`release: ENeuron 1.0 verified hardware baseline`，并创建 annotated tag `v1.0`；标签后工作区干净且 `docs/planning/TODO.md` 不存在，满足先发布再规划的顺序。
- 标签完成后才创建 `docs/planning/TODO.md`：逐模块审计原始计数/分频方案，提出固定四输入 Pulse-Mini 的直接有符号事件累加、同步不应期、presence flag 本地历史、单槽反馈和 CONFIG/TRAIN/INFER 合同。
- Pulse-Mini 当前保持 `REVIEW_REQUIRED`；未创建 RTL。计划将资源估算、目标预算和未来 Vivado 实测严格分开，并以 260 LUT / 140 FF / 0 BRAM / 0 DSP / 100 MHz 为单核硬门。
- 独立 Pulse-Mini 语义审查发现 8 项阻断：跨样本分频与清除冲突、三态顺序歧义、signed 更新未定义、STDP 窗口未冻结、无 ID exactly-once 过强、分立事务接口不闭合、clear/freeze 污染和网络声明缺 P8 证据。
- 已按审查结果修订 `docs/planning/TODO.md`：主路径改为直接有符号事件累加；presence flag 替代三态累加；统一 cmd/rsp；明确 TICK 顺序、窗口端点、非法编码、clear 集合和单生产者 exactly-once；新增固定 `4->2->2` P8 网络闭环门。
- 修订后 `docs/planning/TODO.md` 仍保持 `REVIEW_REQUIRED`，未创建 Pulse-Mini RTL；下一步应由用户审核 P0 冻结决策。

## 2026-08-19 Pulse-Mini 实施

- P1 原始方案 RTL、Python 定向测试和 Vivado 2024.1 OOC 已完成：183 LUT / 85 FF / 0 BRAM / 0 DSP，100 MHz WNS -1.605 ns；该结果仅作为原始成本/缺陷基线。
- P2 黄金模型与 14 项测试完成；固定四输入、-7..+7、阈值 6、窗口 3、不应期 1、presence flag、单槽反馈和 INFER 冻结均有固定向量。
- P3 `pulse_mini_core.sv` 完成；Icarus/Python 20 seeds × 1000 transactions（20000 条）bit-exact 通过。修复了不应期内把候选阈值误当自然 post 的边界错误。
- P4 Yosys 0.56 有限 BMC depth=20 通过；负向控制证明去掉 pending exactly-once 门后可构造重复反馈反例。
- P5 最小监督任务通过：训练前 10/20 严格 abstain，训练后 20/20，20 个留出扰动全部正确；无反馈、反向反馈、标签打乱均未通过门槛，训练期直接权重写入为 0。结论限定为神经元级局部监督，不是纯全局 reward。
- P6 Pulse-Mini 单核 XC7Z020 routed 实测：182 LUT / 76 FF / 0 BRAM / 0 DSP，WNS +0.463 ns、TNS 0、WHS +0.205 ns、THS 0，独立摘要审计通过。
- P7 采用 `keep_hierarchy/dont_touch` 后重新得到真实复制结果：32 核 5867 LUT / 2432 FF / WNS +0.151 ns；64 核 11699 LUT / 4864 FF / WNS -0.131 ns；128 核 23342 LUT / 9728 FF / WNS -0.466 ns。资源报告完成，但简单广播阵列的 64/128 核 100 MHz 硬门未通过，128 核容量声明保持 NOT_PROVEN。
- P8 Python 固定 4->2->2 网络闭环通过：训练前双类 abstain，训练后正/负类 10+10 留出样本全对，一拍 pending 路由可观察，INFER 权重/学习字段冻结，训练账本直接权重写入为 0；结论是固定小网络原型，不外推通用 AI。
- 修正 P8 RTL 协同仿真的训练教师时序：输出层教师事件必须放在第 6 个 tick，等待隐藏层重复脉冲窗口结束；第 1 个 tick 会造成正负 presence 同时出现，方向被正确抵消。修正后 RTL 输出层权重与 Python 黄金模型一致为 `+3`。
- P8 RTL 网络协同仿真通过：`PULSE_MINI_NETWORK_RTL_COSIM_PASS commands=272 one_tick_route=1 positive=1 negative=2`；推理连续 8 tick，正类只产生输出位 1，负类只产生输出位 2。
- 新增 `pulse_mini_signoff.py` 和 `pulse_mini_signoff_summary.json`，摘要绑定 Pulse-Mini RTL、黄金模型、协同仿真、形式验证、负向控制、任务和网络 RTL 文件哈希；P4 机器可读签核摘要完成。
- P0 合同状态由历史 `REVIEW_REQUIRED` 收口为 `APPROVED`：所有固定参数、TICK 顺序、presence 冲突、模式、clear、不应期和统一事务接口均已由现有黄金模型/RTL/测试实现并验证。
- P7 新增 `pulse_mini_array_metrics.py`：32/64/128 核均实测单条 TICK 响应延迟 1 周期、持续命令接受率 0.5 命令/周期；全广播时一次 TICK 可同时产生 N 个输出脉冲，反馈一次广播更新 N 个 pending 核。
- P7 新增 `pulse_mini_lane_model.py` 与 `verify_pulse_mini_p7.py`，比较全并行与共享 lane 的周期上限，并生成 `pulse_mini_p7_signoff_summary.json`。结论是 100 MHz routed 最大并行规模 32 核；64/128 核仍为 NOT_PROVEN，lane 模型不冒充物理签核。
- `docs/planning/TODO.md` 所有待办 checkbox 已完成，状态改为 `APPROVED` / `P7_CAPACITY_BOUNDARY_DOCUMENTED`；该状态明确表示 TODO 已执行完毕，同时保留 128 并行容量未证明这一负向结论。
## 2026-08-19 P1 原始计数/分频基线

- 新增 `pulse_original_core.sv`：固定四输入、每路 8 位学习计数器与 8 位分频进度、16 位胞体、4 位同步睡眠；学习计数上限回绕和只能增强语义按原始方案保留，未加入 Pulse-Mini 的负权重、反馈、模式或 pending 功能。
- 新增 `test_pulse_original.py` 与 `tb_pulse_original.sv`。Python 定向测试 4/4 通过，覆盖学习上限回绕、计数越大分频周期越短、阈值发放/同步睡眠和正向学习局限。
- 新增 `vivado_pulse_original_synth.tcl` 与 `run_vivado_pulse_original_synth.ps1`，使用 Vivado 2024.1、`xc7z020clg400-1`、100 MHz OOC 完成综合、布局布线、资源/时序/功耗报告。
- 当前真实 routed 资源：183 LUT、85 FF、0 BRAM、0 DSP；WNS `-1.605 ns`、TNS `-30.454 ns`、WHS `+0.150 ns`、THS `0 ns`。负 WNS 记录为原始基线时序不足，不能据此宣称 100 MHz 通过；主要路径受字面宽整数比较/饱和组合逻辑影响，后续 Pulse-Mini 应采用窄位宽显式算术。
## 2026-08-19 两版本纯仿真比较

- 用户要求仅通过仿真进一步比较 ENeuron 1.0 与 Pulse-Mini，并形成完整报告。
- 比较范围暂不包含 Vivado 综合、布局布线、LUT/FF、BRAM/DSP、功耗或板级证据。
- 计划使用相同四输入事件数据和相同训练样本预算，分别测量准确率、收敛、扰动鲁棒性、时间间隔敏感性、冲突证据和推理冻结。
- 新增 `compare_simulation.py` 与 `test_compare_simulation.py`，统一生成共同任务、收敛、反馈负对照、结果延迟、证据次数、稀疏事件、冲突证据、四类噪声和固定网络结果。
- 正式执行 20 seeds：共同单神经元任务两版均从 10/20 提升到 20/20；一次正负训练重复后均达到满分。
- 结果延迟扫描显示：两版当前实际权重更新窗口均为 gap 0..2；ENeuron eligibility 在 gap 3..9 仍非零，但定点右移后权重变化为 0。
- 重复证据扫描显示：1到8次事件使 ENeuron eligibility 从16增长到189、单次提交权重变化从2增长并饱和到7；Pulse-Mini 始终只记录方向1并更新一步。
- 稀疏事件扫描显示：各训练一次后，Pulse-Mini 的六个事件即使间隔12 tick仍发放；ENeuron 在间隔2 tick起不再发放，体现无泄漏累计与泄漏时间过滤的差异。
- 固定共同网络上，ENeuron 20/20 seeds训练后均为100%，Pulse-Mini为20/20；两版推理权重均冻结。
- 原生网络上，ENeuron教师与混合协议均为100%，纯全局reward均值22.5%；Pulse-Mini局部教师为20/20，纯全局reward保持未测试。
- Icarus/Python 旁证通过：ENeuron/Pulse-Mini 单核各20000事务、ENeuron Tile 10000事务、Pulse-Mini网络272命令。
- 生成 `artifacts/results/comparison_simulation_results.json` 与 `docs/reports/SIMULATION_COMPARISON_REPORT.md`；完整196项回归、`compileall` 和 `git diff --check` 通过。

## 2026-08-19 Pulse-Mini-L2 实现与协议实验

- 用户批准 Pulse-Mini-L2，目标扩展为 L/L2 训练协议重设计、多类别/非二分类仿真和及时提交。
- 新增 `pulse_mini_l2_reference.py`：PN2 正/负证据计数、-2..+2 捕获幅度、现有 cmd/rsp 与泄放合同保持不变。
- 新增 `pulse_mini_l2_core.sv`、`tb_pulse_mini_l2*.sv`、`pulse_mini_l2_cosim.py`；L2 20 seeds x 1000 事务 bit-exact 通过。
- 新增 `formal_pulse_mini_l2.sv/.ys` 和 runner；Yosys 0.56 depth=20 SAT 无反例，修复了首版 harness 对内部数组层次引用的隐式线网警告。
- 新增 `pulse_mini_protocol_experiments.py`，冻结 local_teacher / global_scalar_reward 两类协议，覆盖三类通道、四类组合、三类时间顺序和四位多标签；生成 `artifacts/results/pulse_mini_protocol_experiments.json` 与 `docs/reports/PULSE_MINI_L2_PROTOCOL_REPORT.md`。
- 实验结果：三类通道两版 local teacher 100%；四类组合 L 覆盖 0%，L2 覆盖约 66.9% 且覆盖样本准确率 100%；时间顺序两版均失败；多标签 L2 略优于 L1；全局标量奖励没有形成有效覆盖。
- 使用 Vivado 2024.1 XC7Z020 完成 L2 OOC routed：366 LUT / 91 FF / 0 BRAM / 0 DSP，WNS -4.690 ns、WHS +0.152 ns；相对 L1 增加 184 LUT、15 FF，真实 setup 失败，不能宣称 L2 100 MHz 通过。

## 2026-08-19 ENeuron 图像识别 D0

- 用户批准固定 8×8 灰度十分类、rank-order `K=16/T=16`、`64→16→4→10` 30 核拓扑、逐事件 replay 局部教师和能力/强门。
- 新增 `digit8x8.py`、`generate_digit8x8_fixture.py`、`digit8x8_fixture.json`、`digit8x8_manifest.json`、`test_digit8x8.py` 和 `docs/reports/DIGIT_RECOGNITION_D0.md`。
- fixture 共 1797 个样本，train/validation/test 为 1252/270/275；三路 split 互不相交且各含 10 类，fixture SHA-256 为 `6fa95b5b7493856708b0ab66814ef98a8f151efc2d9245ca10286860f9d21f5e`。
- D0 编码合同通过：每图恰好 16 个事件、同亮度按像素编号稳定打破平局、2×2 patch mask 可无损还原、编码不读取标签和全局随机状态。
- `python -m unittest -v test_digit8x8.py`：6/6 通过。D0 仍不包含数字识别准确率、ENeuron 网络训练或 RTL/Vivado 证据。

## 2026-08-19 ENeuron 图像识别 D1

- 新增 `digit8x8_experiment.py`、`artifacts/results/digit8x8_d1_results.json`、`test_digit8x8_experiment.py` 和 `docs/reports/DIGIT_RECOGNITION_D1.md`。
- 最近质心 + rank-order 发放 tick 在测试集达到 balanced accuracy 79.80%、accuracy 80.00%、macro-F1 79.46%、coverage 100%。
- 总事件数、首 tick、末 tick 对照没有有效覆盖；标签打乱后的 balanced accuracy 为 8.69%，接近十分类机会水平。
- D1 通过，说明固定输入编码具有可学习信息且没有明显总脉冲量/标签泄漏；尚未证明 ENeuron 网络训练能力。
- D1 专项回归为 10/10 通过；全量回归将在 D2 变更后重跑。

## 2026-08-19 ENeuron 图像识别 D2 启动

- 用户批准进入 D2：固定前两层，只训练十个输出神经元。
- 先复跑全量回归并核对现有 `ThreeFactorNeuron` 接口；D2 不修改已签核 RTL 或既有神经元方程。
- 训练协议采用显式 teacher-post 事件，禁止把自然 spike 当教师；训练期权重变化必须可由资格迹快照与调制值解释。
- 当前状态：实现与测试进行中。

## 2026-08-19 ENeuron 图像识别 D2 收口

- 新增 `digit8x8_d2.py`：固定 `64→16→4` 特征层，仅训练 10 个输出单元；显式 `teacher-post` 采用“输入→下一 tick 教师→3 个空 tick”微窗口。
- 新增 `digit8x8_d2_acceptance.py`、`test_digit8x8_d2_acceptance.py`、`test_digit8x8_d2_contract.py`、`run_digit8x8_d2.py` 和 `test_run_digit8x8_d2.py`。
- 协议/账本相关 14 项测试通过；训练自然 spike=0、训练期直接写权重=0、账本可按 `old + delta = new` 重算、推理权重冻结。
- 正式 10 seed × 3 epoch 结果写入 `artifacts/results/digit8x8_d2_results.json`；validation BAcc 均值 4.61%、coverage 均值 56.04%，0/10 seed 达到基础门；test BAcc 均值 4.74%、coverage 均值 52.18%。
- D2 结论：`D2_FAIL_GENERALIZATION`，部分 seed 为 `D2_FAIL_ACTIVITY`。失败原因是固定特征与当前十分类局部调制使输出权重趋同，严格 abstain 合同因此拒绝伪造分类结果。
- `docs/reports/DIGIT_RECOGNITION_D2.md` 已更新为完整失败报告；D3 暂停，下一步需单独批准最小的输出层信用分配修正。

## 2026-08-19 Pulse-Mini 规划收口

- 用户要求先提交当前版本，再评估原始方案并形成 Pulse-Mini 规划。
- 复核确认工作树原本已干净，`v1.0` 指向 ENeuron 1.0 提交 `499fc8a`，当前 Pulse-Mini 基线为 `64aff70`；未制造空提交。
- 将原始计数/分频核 `183 LUT / 85 FF / WNS -1.605 ns`、Pulse-Mini-L `182 LUT / 76 FF / WNS +0.463 ns`、L2 `366 LUT / 91 FF / WNS -4.690 ns` 和阵列 32/64/128 核边界写入 `docs/planning/TODO.md`。
- 新增 P9-P13：数字识别软件门、输入扇入与共享存储、L2 时序修复、阵列系统化、板级与持续学习边界。
- `python -m unittest discover -v`：208/208 通过；`git diff --check`：通过。

# 2026-08-29 NP4B 续作

- 恢复并复核 `docs/planning/NPU_PRUNING_NP4B_TODO.md`、Git 状态和并行实现状态；NP4B1 已提交，NP4B2 与 ENeuron `4→8→2` 顶层仍在实施。
- Pulse-L/L2 wrapper 公开接口和 FEEDBACK exactly-once 当前 2/2 通过。
- 新增的 commit→clear 双部署合同首次复验为 RED：单核自动 clear 模式在 `PRUNE_COMMIT` ready 等待超时；已把该失败交回实现任务按 TDD 修复。
- NP6 Vivado 仍未获再次批准，本阶段没有运行物理实现。

## 2026-08-29 NP4B2 Pulse wrapper 收口

- 新增共享 `pulse_mini_prune_bridge.sv` 与 L/L2 两个薄 wrapper；原 Pulse 核心和 3-bit opcode 未修改，剪枝仍走独立 sideband。
- FEEDBACK 接受沿锁存旧 captured direction；只有核心成功的非零反馈才提交一次 OBSERVE，utility 更新完成后才公开原反馈成功响应。
- 零反馈、`NO_PENDING`、响应背压、`AUTO_CLEAR_ON_COMMIT=1/0`、TICK 输入门控、不应期独立分账及未提交 mask 旁路均已定向通过。
- `test_pulse_mini_prune_wrapper.py`：5/5 通过；L/L2 裸核心各自 20 seeds × 1000 协同事务通过。
- clear 故障注入、观察 ID 耗尽、非法 direction 动态注入及 wrapper/network 形式检查明确留给 NP4B5，不冒充本阶段已证明。

## 2026-08-29 NP4B3 ENeuron 4→8→2 顶层

- 新增严格 `4→8→2` ENeuron 顶层：8 个隐藏和 2 个输出均实例化四输入剪枝 wrapper，输出分别固定读取旧 `pending[3:0]` 与 `[7:4]`。
- 复用公共 TICK/flush 调度器和十参与者 commit barrier；commit 期间阻塞 TICK、flush 与 Host 命令，全体 gate 完成后广播十核 `STATE_CLEAR`，最后统一公开响应。
- Host 只广播/寻址转发 CLEAR、SNAPSHOT、MOD、WEIGHT，不在 tile 内生成标签、损失、reward 或调制值。
- wrapper 增加默认 `LAYER_OUTPUT=0` 参数；顶层分别汇总 hidden/output 的 dense、issued、saved，定向结果为首拍 hidden `32/16/16`、output `0/0/0`，次拍 output `8/4/4` 且 hidden 不变。
- 顶层与相关回归 13/13 通过；当前子状态为 `NP4B3_ENEURON_NETWORK_PASS`，Pulse-L/L2 网络与 NP4B4 长事务仍未完成。

## 2026-08-29 NP4B3/NP4B4 恢复检查

- 当前未提交区包含 ENeuron 只读审计端口/随机 oracle 草稿，以及 Pulse-L/L2 网络公开接口骨架；已确认这些内容不能视为完成证据。
- Pulse 网络公开接口编译已通过，但共享控制面仍把 `host_cmd_ready` 常量拉低；综合行为测试稳定 RED 于首次广播 `MODE_SET`，尚未实例化十 wrapper 或接入 scheduler/barrier。
- ENeuron 网络已有十 gate ID 与核心状态公开测试草稿通过，但 `20 seeds × 1000` 随机协同模块尚未完成；继续按最小 tracer 扩展。
- 本阶段继续禁止运行 NP6 Vivado。

## 2026-08-29 NP4B3 Pulse-L/L2 网络收口

- 新增一个共享 `pulse_mini_pruned_network_4x8x2` 控制面和 L/L2 两个薄顶层；十个实例均为四输入 wrapper，核心与 3-bit opcode 未修改。
- Host 支持广播/寻址 MODE、WEIGHT、CAPTURE、FEEDBACK；接受沿锁存目标与字段，sticky barrier 汇合错拍响应，任意非零 3-bit 核心状态都能正确上传。
- 复用固定一拍 TICK/flush scheduler 与十参与者 commit barrier；commit 先全体预检，再完成十 gate exact-two 和十核 `STATE_CLEAR`，最后统一公开响应。
- hidden/output dense、issued、saved 分层汇总，响应背压期间字段稳定；bridge sideband ready 改为 idle 时不依赖 valid，以支持 barrier 的 valid 前原子预检。
- Pulse 网络 3/3、wrapper 5/5、scheduler/barrier 5/5 通过；相关 13 项定向回归与 `git diff --check` 通过。NP4B3 状态更新为 `PASS`。

## 2026-08-29 NP4B4 ENeuron 长事务收口

- 新增独立 `ENeuronPrunedNetworkReference` 和 Python/Icarus 随机网络协同驱动，不复用 RTL 控制状态、不读取层次路径。
- 逐事务比对十 gate utility/mask/observation+commit ID、十核 membrane/threshold/snapshot、pending 路由、六项分层账本以及 40 个公开寻址权重；逐周期检查 mask 前置、commit 阻塞、exact-two 和三类响应背压。
- `test_eneuron_pruned_network_random_cosim.py`：64 事务 tracer 与正式 20 seeds × 1000 均通过；主线程新鲜复验 `Ran 2 tests in 43.495s`。
- 正式 20,000 事务中，被剪权重变化 0、utility 变化 0；committed snapshot 合法 nonzero→0 发布 277 次、0→非零 0 次。
- NP4B4 当前只签核 ENeuron；Pulse-L 与 Pulse-L2 各自 20,000 事务仍待完成。

## 2026-08-29 NP4B5 四类负向控制

- 新增四个最小错误实现及对应验收器：事后读 evidence、只掩 TICK 数值路径、逐 gate 公开部分 epoch、两输入 output 伪 `2:4`。
- 每个验收器均先拒绝错误实现，再接受正确合同模型；结构验收器直接检查当前 `eneuron_pruned_network_4x8x2.sv` 的两组四输入输出接线。
- 主线程独立复验负向控制与相关正向回归 9/9 通过，Python 编译和 `git diff --check` 通过。
- 该结果只证明验收器能识别四类指定错误，不代替 wrapper/network 形式验证或长事务协同仿真。

## 2026-08-29 Pulse NP4B4 只读审计端口

- 为避免 Pulse 长事务依赖 RTL 层次路径，bridge/wrapper 纯组合导出 4-bit `issue_mask`；网络顶层公开十核 40-bit issue mask、leak timer、post age 和统一 120-bit captured direction。
- L 的每 lane 2-bit captured direction 在顶层符号扩展为 3-bit，L2 原 3-bit 值保持不变，使同一随机驱动可比较两种模型。
- 补丁不修改核心、opcode、FSM 或事务延迟；wrapper/network 完整 8/8 定向测试通过。
- 首轮测试生成器曾因 `.*` 缺新信号和脆弱字符串替换导致 5 项 RED；已补全所有 TB 声明并恢复行为测试，未通过删除断言绕过。

## 2026-08-29 NP4B TODO 规划复核

- 按 `planning-with-files` 执行 session catch-up，并复核 `task_plan.md`、`docs/planning/NPU_PRUNING_TODO.md`、`docs/planning/NPU_PRUNING_NP4B_TODO.md` 与当前工作树。
- 关键只读验证：ENeuron 最小随机 tracer 1/1 通过；Pulse-Mini-L/L2 网络接口与定向合同 3/3 通过。
- 当前只规划、不运行 Vivado；待合并并行审计结果后冻结新的可执行 TODO 和验收门。

## 2026-08-29 NP4B 收口 TODO 冻结

- 恢复检查确认当前未提交工作分为两组：Pulse-L/L2 网络随机协同仿真初版，以及 Pulse-L wrapper depth=32 形式证明。
- Pulse 随机基础设施已落盘，但 Pulse-L `1×64` tracer 尚未运行，Pulse-L2 入口与两模型各 `20×1000` 正式矩阵均未完成，因此 NP4B4 仍为未通过。
- 主线程已复验 Pulse-L wrapper 形式 session 完成：exactly-once 不变量无反例，成功非零 FEEDBACK witness 可达，verifier 标记通过；该证据不外推到 L2、ENeuron 或十核网络。
- `docs/planning/NPU_PRUNING_NP4B_TODO.md` 新增 A→D 四段收口顺序和四个建议提交边界；执行过程中继续同步四份规划文档。
- 本轮只更新规划，不运行新仿真矩阵，不调用 Vivado；下一步从 Pulse-L `1×64` tracer 开始。

## 2026-08-29 NP4B4 Pulse 长事务收口

- 新增 Pulse-L/L2 共用但模型状态独立的 `4→8→2` Python oracle、随机 Icarus 驱动、四项 unittest、正式 signoff runner、两个机器摘要和摘要 verifier。
- 首轮 RED 暴露三类测试基础设施错误：事务号进制误解、INFER flush 遗留训练位且漏检错误响应、新增常量漏导入；均按根因修复，没有放宽任何状态字段或 RTL 合同。
- Pulse-L seed 201..220、Pulse-L2 seed 301..320 各完成 20×1000；12 项 wrapper/network/random 联合回归在 53.862 秒内通过，摘要 verifier 报告 `models=2 transactions=40000`。
- 两模型各有 20 次 commit、133,400 次 exact-two 检查、266,800 次被剪 lane 检查；被剪权重、evidence、utility 变化均为 0，INFER 固定学习状态无变化。
- 机器摘要明确 `logical_functional_cosim_only`，并把 physical speedup、BRAM skip、power reduction 均标记为未证明；本阶段未运行 Vivado。

## 2026-08-29 NP4B5 Pulse wrapper 形式收口

- Pulse-L 与 Pulse-L2 分别建立公开端口 harness、depth=32 不变量脚本、成功路径脚本、PowerShell runner 和独立 verifier。
- Pulse-L 初版只显式约束 OBSERVE 计数；主线程补强为与 L2 相同的 utility 顺序、失败零观察和响应背压期间 utility 稳定合同后，重新运行证明。
- 两模型不变量均为 `SAT proof finished - no model found: SUCCESS!`，成功路径均找到非空模型；L witness 为 15,561 bytes，L2 witness 为 16,787 bytes。
- 两个 verifier 分别输出 `PULSE_PRUNE_WRAPPER_FORMAL_CONTRACT_PASS` 与 `PULSE_L2_PRUNE_WRAPPER_FORMAL_CONTRACT_PASS`。证明范围只到单 wrapper，不外推十核 commit barrier。

## 2026-08-29 NP4B 当前续跑规划

- 依据当前工作树和三路只读审计，将剩余工作冻结为 P0→P5：Pulse 证据固化、ENeuron wrapper 原子性、十参与者 barrier 组合证明、INFER/负向补强、冻结后全量重跑、fail-closed 总签核。
- 计划显式区分“形式证明已通过”和“正式证据已签入”；C1/C2 当前属于前者，不得提前计入最终仓库签核。
- 收紧 C3：内部同拍接受由验证专用 bind/断言证明，公开端口只证明事务级结果；非空 witness 必须由公开命令产生非零 snapshot 和 utility 更新。
- 收紧 C4：barrier 不自行验证 exact-two，最终结论必须组合公共 gate 证明；真实顶层阻塞由协同仿真验证，不能用编译替代。
- 总摘要将采用 fail-closed 精确键集合，绑定三模型结果、全部形式 proof/reach、witness、runner、测试和工具版本；本轮只更新规划，未运行 Vivado、未执行签核。

## 2026-08-29 P0 Pulse wrapper 证据固化

- 使用当前源码并行重跑 Pulse-L/L2 的 Yosys 0.56 depth=32 invariant 与 reach；两套 runner 均以退出码 0 完成。
- Pulse-L verifier 输出 `PULSE_PRUNE_WRAPPER_FORMAL_CONTRACT_PASS`；L2 verifier 输出 `PULSE_L2_PRUNE_WRAPPER_FORMAL_CONTRACT_PASS`；两个 verifier 的 Python 编译检查通过。
- 正式日志分别为 551,887 和 580,073 bytes；非空成功 witness 分别为 15,561 和 16,787 bytes。
- P0 提交只纳入正式 harness、proof/reach 脚本、runner、verifier、日志和成功 witness；明确排除旧 cex 与 tmp 日志，未运行 Vivado。
- Yosys 原始日志的 ASCII 横幅自带行尾空格；为保持证据原样，不清洗日志。源码、脚本和文档仍执行严格 `git diff --check`，日志完整性留给最终 SHA-256 摘要。

## 2026-08-29 P1/P2/P3 并行启动

- P0 已提交为 `67b6019 test: prove Pulse pruning wrapper atomicity`，提交后工作树干净。
- P1、P2、P3 按独立文件边界并行：ENeuron wrapper proof/reach、N=10 barrier 组合证明、真实 RTL mutation 负向控制；三路均禁止提交和运行 Vivado，由主线程统一审计。
- 主线程复核确认 ENeuron 顶层已有 runtime-blocked 形式断言，Pulse 顶层已有同等组合阻塞逻辑；后续仍需机器化验证，不以目视检查代替。

## 2026-08-29 P2 barrier 与 P3 负向控制收口

- 真实 `local_prune_commit_barrier` 固定 N=10 完成 depth=32 proof/reach；成功 witness 覆盖 gate 错拍、response 背压和响应消费后 runtime 解除阻塞。
- 新增公共 gate 独立 verifier，并把 reach 固定为第 8 拍 exact-two mask=`0011`，生成 11,288-byte 成功 witness；barrier verifier 会实际调用 gate verifier，不再只检查脚本文本存在。
- barrier proof/reach 日志分别为 255,927/193,918 bytes，成功 witness 为 12,944 bytes；三个真实顶层均通过 `iverilog -Wall` elaboration 与 runtime-ready 合同绑定。
- P3 新增三类真实 RTL 源码 mutation 和三模型输出路由结构 mutation；7/7 负向控制、35 项相关 wrapper/network 回归通过，正式 RTL 未因测试而改写。
- 完整三模型 INFER 学习状态冻结继续由 P4 各 20,000 条新鲜矩阵签核，不用当前小范围回归冒充最终长事务证据。

## 2026-08-29 P1 ENeuron wrapper 形式收口

- `eneuron_local_prune_wrapper.sv` 仅增加 `FORMAL` 条件内部断言，不改变综合接口、神经元方程或普通 RTL 数据通路。
- depth=32 invariant 证明合法非零 MOD 的核心更新与 gate OBSERVE 同拍接受，失败路径不部分启动，公开事务状态与剪枝响应背压稳定。
- reach witness 从公开 TRAIN TICK 产生非零 eligibility，随后公开 SNAPSHOT、非零 MOD、utility 非零变化与成功 done；未 assume 内部 snapshot 或 utility。
- 主线程新鲜重跑 runner，正式日志 862,510 bytes、witness 24,069 bytes；独立 verifier、2 项 wrapper 回归、Python 编译和 `iverilog -Wall -tnull` 全通过。

## 2026-08-29 NP4B 最终收口 TODO 规划

- 本轮只规划，不运行仿真矩阵、形式 runner 或 Vivado。
- 复核仓库状态：P0 已提交为 `67b6019`，P2/P3 已提交为 `c0108a0`；P1 技术验证通过但仍未形成独立提交。
- 将剩余工作收敛为唯一串行主链：P1 证据入库 → 固定三组 seed 并冻结源码 → 三模型各 20,000 条新鲜重跑 → 全部形式 runner/verifier → 全仓回归/编译 → fail-closed 总摘要与文档签核。
- 最终状态仍只能停在 `NP4B_INTEGRATION_PASS / NP6_REVIEW_REQUIRED`；NP6 未再次批准前禁止调用 Vivado。

## 2026-08-29 NP4B 最终收口获批

- 用户明确批准八项决定并要求执行 TODO、控制任务粒度、及时更新文档和提交。
- 持久工作流状态由 `REVIEW_REQUIRED` 切换为 `IN_PROGRESS`；第一项执行任务固定为 P1.7 ENeuron wrapper 形式证据独立入库。
- 授权不包含 NP6；P4/P5 完成前及再次批准前仍禁止调用 Vivado。

## 2026-08-29 持久工作流与 P1.7 提交前复验

- 新增 `WORKFLOW.md`、`WORKFLOW_STATE.md` 和只读 `workflow_resume.ps1`；Check/Resume 两种模式均通过并确认未修改仓库。
- 持久工作流已独立提交为 `df0e7bc docs: add persistent project workflow`，未混入 P1 形式证明文件。
- P1 独立 verifier 输出 `ENEURON_PRUNE_WRAPPER_FORMAL_CONTRACT_PASS`；wrapper/formal 联合回归 3/3 通过，Python 编译通过。
- 当前 PowerShell `PATH` 不含 Icarus；改用 `C:\msys64\ucrt64\bin\iverilog.exe` 后，ENeuron wrapper `-g2012 -Wall -tnull` 编译通过。

## 2026-08-29 P1 仓库闭环

- P1 精确暂存集合包含 ENeuron wrapper、formal harness、proof/reach 脚本、runner、verifier、定向测试、正式日志、成功 witness 和同步文档。
- staged 审计确认 `cex/tmp` 为零，人工维护文件 `git diff --check` 通过。
- 已提交为 `c811bcf test: prove ENeuron pruning wrapper atomicity`；P1 状态从 `PROOF_PASS / REPOSITORY_CLOSURE_PENDING` 更新为 `PASS`。

## 2026-08-29 P4.1 冻结

- 新增 ENeuron 独立正式 runner、严格摘要 verifier 和两项快速合同测试；复用现有 `run_matrix`，未修改 RTL、黄金模型或协同仿真语义。
- 快速合同测试 2/2、Python 编译和人工文件 `git diff --check` 通过。
- 基础设施提交为 `33e0aed test: add ENeuron pruning signoff runner`；该提交是 P4 三模型新鲜重跑的源码、runner 和 seed 冻结点。

## 2026-08-29 P4.2 三模型新鲜矩阵

- 从冻结点 `33e0aed` 并行运行 ENeuron seed `101..120`、Pulse-L seed `201..220`、Pulse-L2 seed `301..320`，每个 seed 1000 条；三个进程均退出码 0。
- ENeuron 20,000 条：零 RTL/Python 差异、零 strict `2:4` 违反、零 INFER 冻结违反、零被剪权重/utility 变化；合法 snapshot nonzero→0 发布 277 次，0→非零为 0。
- Pulse-L 与 L2 各 20,000 条：各 20 次 commit、133,400 次 exact-two 检查、266,800 次被剪 lane 检查；被剪权重/evidence/utility 变化均为 0。
- `verify_eneuron_pruned_network_summary.py` 与 `verify_pulse_pruned_network_summaries.py` 均通过；三模型结果继续标记为 `logical_functional_cosim_only`，不外推物理收益。

## 2026-08-29 P4.3 新鲜形式证据

- 从 P4 冻结版本并行重跑 ENeuron wrapper、Pulse-L wrapper、Pulse-L2 wrapper、公共 gate和 N=10 commit barrier 的 proof/reach runner，五个进程退出码均为 0。
- 五个独立 verifier 分别输出 ENeuron/Pulse-L/Pulse-L2 wrapper contract PASS、公共 gate depth=32 + reach depth=8 PASS、barrier depth=32 participants=10 PASS。
- 所有成功 witness 非空：ENeuron 24,069 bytes，Pulse-L 15,561 bytes，Pulse-L2 16,787 bytes，gate 11,288 bytes，barrier 12,944 bytes。
- 原始日志内容在确定性重跑后与仓库版本逐字一致，因此 Git 无日志 diff；五份 witness 由本批次重新生成并产生 tracked 修改。最终 P5 摘要仍需记录本批次命令和退出码。

## 2026-08-29 P4.4 首轮全仓回归

- 全仓实际执行 `Ran 356 tests in 372.990s`，355 项通过，1 项失败；测试数量已超过 318 门槛，但本轮整体判定为失败。
- 唯一失败是 `local_prune_rtl_results.json` 仍绑定 `formal_local_prune_gate_reach.ys` 的旧 SHA-256；当前脚本哈希为 `00c18c...74aecb`。同一批次 gate proof/reach 与独立 verifier 均已通过，因此根因是机器摘要索引陈旧，不是 RTL 或形式性质失败。
- 按 fail-closed 规则首次更新 reach 哈希后，定向测试继续捕获 `run_formal_local_prune_gate.ps1` 的旧哈希；随后枚举对比全部 11 个绑定文件，确认仅剩这一项并精确更新。定向测试通过后仍必须完整重跑 356 项，首轮结果不得计入 P4 PASS。

## 2026-08-29 P4.4/P4.5 最终回归

- 证据索引修复提交为 `9f31fcd test: refresh prune controller evidence hashes`；随后从干净 HEAD 完整重跑全仓。
- 第二轮结果为 `Ran 356 tests in 362.228s / OK`，零失败、零错误，超过 `N >= 318` 硬门；首轮 355/356 不计入通过结论。
- `python -m compileall -q .` 通过；Icarus 对公共 gate、barrier、ENeuron/Pulse-L/Pulse-L2 wrapper 和三个 `4→8→2` 顶层共 8 个目标执行 `-g2012 -Wall -tnull`，全部通过。
- P4 全部硬门完成；下一步只做 P4.6/P5 证据索引、fail-closed 总摘要、独立 verifier 和文档签核，不运行 Vivado。

## 2026-08-29 P5 总摘要初版

- 新增总摘要生成器、独立 verifier 和 3 项失败敏感测试；初次生成绑定 87 个精确文件，三项摘要合同测试通过。
- 总 verifier 首次运行在公共 gate verifier 接口处失败：该模块公开 `verify()` 而非 `main()`；前置的三模型结果和三个 wrapper verifier 已通过。
- 仅修正接口调用，不改证据合同；由于 verifier 本身位于哈希集合中，必须重新生成摘要后再运行总 verifier 和测试。

## 2026-08-29 P5 fail-closed 证据闭环

- 最终完整 discovery 纳入新增的 3 项 P5 失败敏感测试，结果为 `Ran 359 tests in 378.291s / OK`；外层命令墙钟 378.676 秒。
- `np4b_signoff_summary.json` 精确绑定 87 个文件，覆盖 RTL、oracle/cosim、定向与负向测试、五套 formal proof/reach、正式日志、成功 witness、三模型结果、runner 和 verifier 自身。
- 总 verifier 复用三模型摘要 verifier 和五套形式证据 verifier，检查固定 seed、各 20,000 条、逻辑账本恒等式、精确哈希键集合、非空 witness、冻结提交祖先关系及未证明边界。
- 最终输出 `NP4B_SIGNOFF_VERIFY_PASS models=3 transactions=60000 tests=359 formal=5 next=NP6_REVIEW_REQUIRED`；3 项摘要正/负向测试通过。

## 2026-08-29 NP4B 最终文档签核

- NP4B1→NP4B6 全部功能硬门完成；最终总 verifier、359 项回归、五套形式证据、三模型 60,000 条独立矩阵和 8 个 RTL 编译目标均通过。
- 项目状态更新为 `NP4B_INTEGRATION_PASS / NP6_REVIEW_REQUIRED`；进入 NP6 的用户审批仍未发生。
- 本阶段从头到尾未调用 Vivado，未声明物理 BRAM 跳读、真实周期缩短、功耗下降或 XC7Z020 时序收益。

## 2026-08-29 GitHub 首次推送准备启动

- 用户要求检查 `.gitignore` 并准备推送到 `git@github.com:Epslion404/ENeuron.git`；本阶段默认停在 push 前，不产生远端写入。
- 初始检查：`main` 位于 `4b7f146`，工作树干净，无 remote；仓库当前文件约 12.8 MB，历史最大 blob 约 1.91 MB，无 GitHub 超限对象。
- `.gitignore` 当前命中 88 条本地产物；12 份已跟踪 ignored 文件是 NP4B 的正式日志与成功 witness，不清理、不取消跟踪。
- 当前与完整 Git 历史的高置信度凭证扫描均为零命中；`git fsck --full` 无损坏，仅报告不可达旧 blob。
- 初次 GitHub 发布身份检查只测试了默认 key 和 `~/.ssh/github`，均返回公钥拒绝；没有尝试 push。
- 用户补充 GitHub/Gitee 共用 `~/.ssh/id_ed25519_gitee` 后，显式 SSH 测试成功认证 `Epslion404`；目标仓库 `ls-remote` 退出码为 0 且无 refs，确认它存在并为空。
- 已把用户指定地址写为本仓库 `origin`；将使用仓库局部 `core.sshCommand` 选择已验证 key，不修改全局 SSH 配置。push 仍保持未执行。
- `.gitignore` 已补充虚拟环境、coverage、`.env`/本地密钥、编辑器状态和通用 Vivado 工程产物；固定例外 DCP、XPM transcript 与 12 份已跟踪正式形式证据均未被误排除。
- 本地发布准备的提交边界固定为 `.gitignore`、`task_plan.md`、`findings.md`、`progress.md`；不混入 RTL、结果或工具证据，提交后停在 `push` 前。

## 2026-08-30 PR #1 第二轮复审启动

- 已回读 PR 最新元数据、协作者回复、两个新增提交和 7 文件差异范围；当前 HEAD 为 `169003684b260aaabf98fb3b6e70866cb0c24bed`。
- 协作者已处理首轮架构偏离和生成物问题，但当前公开证据来自 Vivado 2024.2，不满足指定 2024.1 的原始要求。
- 下一步在隔离 worktree 审查实际代码和摘要绑定，再使用本机 Vivado 2024.1 复现；复审完成前不批准、不合并、不修改协作者分支。

## 2026-08-30 PR #1 第二轮复审执行结果

- 完整 Vivado 2024.1/XSim 回归通过：版本 `Vivado Simulator v2024.1`，45 cases、5 mutants、6447 transactions、154728 fields，154 次工具调用退出码全为 0。
- 静态检查、Python 编译、17 项 simulator-free 新测试及现有三模型 Icarus 协同仿真均通过；`git diff --check` 无问题。
- 相关 24 项回归仍有 1 项失败：旧机器摘要未随 `local_prune_gate_cosim.py` 更新，且工作树字节哈希受 Windows `core.autocrlf` 影响，不能在新鲜检出稳定复验。
- 评审结论保持 `CHANGES_REQUESTED`：要求修复跨 EOL 的哈希新鲜度合同、刷新被修改 cosim 的摘要绑定，并更正反例用例的命名/报告口径；不合并、不修改协作者分支。
- 新 review 已绑定 PR HEAD `169003684b260aaabf98fb3b6e70866cb0c24bed`，GitHub 回读确认正文完整、状态为 `CHANGES_REQUESTED`；隔离 worktree 已安全清理。

## 2026-08-30 PR #1 第三轮复审结果

- 最新 HEAD `fd5aa9622bcb8b3c5e1bedbfc0639199a23026a9` 的 28 项针对性回归通过；设置 `VIVADO_ROOT=G:/Xilinx/Vivado/2024.1` 后真实 XSim 集成测试也通过。
- 本机独立运行 `python verify_local_prune_rtl.py`：三模型 60,000 条 Icarus cosim、32 拍 Yosys 形式验证均退出 0。
- 本机独立运行最新 HEAD 的完整 Vivado 2024.1 runner：45 个正常用例、5 个 mutants、6447 条事务、154728 个字段，154 次工具调用全为退出码 0。
- 最新 HEAD 的全仓 `python -m unittest discover -v` 为 `Ran 381 tests in 906.922s`，失败 2 项，均为 `test_verify_np4b_signoff` 的 formal ENeuron witness 字节数不一致（24069/22922）。
- 根因与 PR 新增 `.gitattributes` 直接相关：`*.vcd text eol=lf` 改变已跟踪 VCD 工作树字节，而 `verify_np4b_signoff.py` 仍按原始 `stat().st_size` 和原始 SHA-256 校验 `np4b_signoff_summary.json`，造成完整签核链失效。
- 另发现 `verify_local_prune_rtl.py` 的正常 `build_summary(run_checks=True)` 路径不输出 `tool_availability`，执行正式重验证后会删除该 v2 字段；现有测试未覆盖此回归。
- 已向 PR 提交新的中文 `CHANGES_REQUESTED`，要求固定正式证据字节或统一 NP4B canonical 策略、刷新总摘要、补充完整 discover 复跑，并保持 v2 元数据字段完整。

## 2026-08-30 PR #1 审查口径调整

- 已按用户要求允许不同 Vivado 版本的仿真结果，精简审查反馈；GitHub 最新 review 仍为 `CHANGES_REQUESTED`。
- 不再要求 2024.1/2024.2 版本一致，只要求明确记录版本、命令、退出码和测试统计。

## 2026-08-31 PR #1 第四轮精简复审启动

- 本轮只检查 NP4B VCD 证据策略与 v2 元数据保留两个硬问题，并运行完整回归。
- 首次 GitHub GraphQL 读取被远端重置，已切换 REST API；尚未形成审查结论。

## 2026-08-31 PR #1 第四轮关键验证

- 隔离检出最新 HEAD `46fc59e`，35 项关键回归通过；Vivado 2024.1 XSim 短回归为 16 cases、482 条事务、零失败。
- `python verify_local_prune_rtl.py` 通过三模型 60,000 条 cosim 和 32 拍形式验证，v2 元数据字段完整保留。
- 随后 `python verify_np4b_signoff.py` 因正式重验证改写 formal 日志而失败；当前隔离工作树保留该可复现状态，正在另建干净检出运行完整 discovery。

## 2026-08-31 PR #1 第四轮精简复审完成

- 干净提交态完整回归 `385/385 OK`；上一轮两个具体缺陷已经修复。
- 顺序复验确认唯一阻断：总签核 PASS、正式 local-prune 重验证 PASS、总签核再次 FAIL。
- 已提交中文 `CHANGES_REQUESTED` review `5065226301`，绑定最新 HEAD `46fc59edae7ec0ae4ae56afed4de2d9a8e1d2049`；回读状态和正文均正确。
- 本轮没有合并或关闭 PR，没有修改协作者分支；Vivado 版本差异不作为阻断。

## 2026-08-31 PR #1 第五轮复审完成

- 最新 `4fec2aa` 的修复已通过三步 signoff 顺序复验。
- 干净提交态 `python -m unittest discover -v`（未导出 `VIVADO_ROOT`）为 386/386 通过、跳过 1 项；Vivado 2024.1 短回归单独重跑通过。
- 发现并记录协作者评论中“2 errors / exit 1 仍称全绿”的表述矛盾；不作为代码阻断，但建议更正审查记录。
- 本轮拟提交 `APPROVE`，并附一条精简的事实更正说明；不合并 PR。

## 2026-08-31 PR #1 第五轮回复复核完成

- 协作者已通过评论 `5477928602` 更正 discover / 四态矩阵 / 权威复审的统计口径；声明无代码改动。
- 复核确认新评论与实际结果一致，PR HEAD 未变，既有 `APPROVED` review 仍有效。
- 未执行合并或关闭操作。

## 2026-08-31 PR #1 合并后结果复核

- GitHub 已合并，`origin/main=92b70f9`。
- 结果说明功能级剪枝合同和三模型协同仿真闭环成立；Pulse-L/L2 约 31% 的逻辑工作计数可省，ENeuron 保持剪枝后状态冻结。
- 结果不能外推到 FPGA 实际加速、BRAM 跳读、面积或功耗；这些仍是后续 Vivado 物理实现阶段的独立验收项。

## 2026-08-30 PR #1 第三轮复审启动

- 协作者声称已解决摘要陈旧、跨 EOL 哈希和反例命名问题，最新证据提交为 `fd5aa96`。
- 本轮将以最新 HEAD 为唯一对象，先做 v2 摘要/验证器静态审查，再执行本机 Vivado 2024.1 真实复跑；不因其 2024.2 或未重跑 Icarus/Yosys 的声明而自动批准。

## 2026-08-31 PR #2 处理记录

- 已读取 PR #2 元数据：open、mergeable clean，初始 HEAD `d9902ad`，base 为 `0eb2efe`，目标是让 Vivado 短回归覆盖 `eneuron/pulse_mini_l/pulse_mini_l2` 三模型。
- 已在隔离 worktree `D:\Documents\Code\ENeuron_pr2_review` 运行本机 Vivado 2024.1 针对性测试：32 项全部通过，真实 XSim 三模型短回归通过。
- 测试副作用改写了 `local_prune_rtl_results.json` 与 `np4b_signoff_summary.json`，已在隔离 worktree 恢复，未混入修复提交。
- 已将 PR 分支复现命令从 `pull/1/head:pr-1` 修为 `pull/2/head:pr-2`，并推送提交 `f975cd7` 到 `feature/vivado-full-models-20260831`。
- 尝试直连 GitHub REST review、`gh pr review` GraphQL 和 REST issue comment 均因 `api.github.com` 连接重置失败；随后发现本机 `127.0.0.1:7897` 代理可读 PR 元数据。
- 代理下 `gh pr review` 的 GraphQL 仍 EOF，curl REST comment 仍 TLS 失败；改用代理下 `gh api --method POST repos/Epslion404/ENeuron/issues/2/comments` 成功提交评论 `5479989535`。
- 当前状态：代码与仓库报告文件已修复且本机验证通过；PR 页面已有中文评论，剩余人工口径问题是 PR 描述里的全量 discover 表述。

## 2026-08-31 PR #2 后续复核

- 远端 PR 分支更新到 `699acae`，新增生成器修复 `858d79e` 和报告重渲染 `699acae`；复现命令修复不再只是手工改报告。
- 已在最新 HEAD 的隔离 worktree 轻量验证：Python 编译通过、报告重新渲染后仍输出 `pull/2/head:pr-2`、`git diff --check` 通过。
- 已使用代理下 `gh api --method PATCH repos/Epslion404/ENeuron/pulls/2` 修正 PR 描述，去掉“386/386 OK”对全量 discover 的不实预期。
- 已使用代理下 `gh pr review 2 --approve` 提交批准，命令退出码 0；随后 reviews/body 回读 API 反复 EOF，未能二次确认 review 页面状态。

## 2026-08-31 阶段性报告重新生成

- 远端 `main` 已快进到 `e5bbbc5`，PR #2 已合并。
- 已更新 `docs/reports/STAGE_REPORT_2026-08-31.md`，补充 PR #2 三模型 Vivado 短回归、本机 2024.1 复核、报告生成器修复和当前边界。
- 本次只更新阶段性报告和进度记录，未重跑完整回归或 Vivado 长矩阵。
## 2026-08-31 根目录 Markdown 整理归档启动

- 已读取 `planning-with-files` 与 `karpathy-guidelines`，在 `task_plan.md` 冻结目标、阶段、验收标准和约束。
- 已确认 `main...origin/main`，开始时只有阶段报告和本进度文件存在未提交修改。
- 已盘点 34 个根目录已跟踪 Markdown；仓库尚无 `docs/` 目录。
- 已冻结根目录保留候选：`README.md`、三个持久规划文件、`WORKFLOW.md`、`WORKFLOW_STATE.md`；其余文件待固定路径引用审计后归档。
- 已完成第一轮引用审计：识别出 Goal 解析、NP4B 哈希、三个报告生成器和恢复脚本的固定文件名依赖；下一步先确认正式摘要级联范围，再冻结最终迁移表。
- 总摘要级联审计确认 `np4b_signoff_summary.json` 绑定 `local_prune_rtl_results.json`；首次按猜测文件名读取生成器失败，已记录并切换为文件清单定位真实入口。
- 已用 `git mv` 将 29 个 Markdown 显式迁入四类 `docs/` 子目录；随后路径替换检查捕获 16 处 NPU TODO 路径重复，已定位为 `TODO.md` 后缀二次替换，修复前未提交。
- Goal 的两个 T0 定向测试在新嵌套路径上 RED：均因测试临时目录未创建 `docs/design`/`docs/verification` 父目录；已只修正测试夹具建目录动作，待原命令复验 GREEN。
- T0HandoffSummaryTests 已按原命令复验 2/2 GREEN；异常重复归档路径扫描为 0。
- 已新增 `docs/README.md`，根目录 Markdown 从 35 个收敛为 6 个，29 个文档全部通过显式 Git rename 归档。
- 验证首轮：Python 编译通过；工作流 Check 因 Windows PowerShell 5.1 无 BOM 中文注释邻接变量赋值而 RED；局部剪枝测试捕获签名刷新态未正式重验证。两项均保持原验收门，分别进入最小修复/正式重验证。
- 工作流首个 ASCII 注释修复不足，第二次 Check 在后续中文字符串继续出现跨行误解析；已确认需对整个脚本增加 UTF-8 BOM，而不是逐行英文化。
- 增加 BOM 后脚本已进入状态检查，第三次 Check 发现 PowerShell 5.1 默认代码页读取无 BOM Markdown；已在所有 Markdown 读取点显式指定 UTF-8，待同一命令复验。
- 工作流 Check 最终通过；41 项 Goal/局部剪枝/NP4B 定向测试用时 61.344 秒全部通过；NP4B 独立 verifier 再次通过，Markdown 37 文件链接零断链。
- 旧根路径审计第二次运行捕获的是合法 NPU 路径内的 `TODO.md` 后缀，不是实际断链；已改用“先剥离合法归档路径，再查残留旧名”的无歧义算法。
- “剥离合法路径”方案仍有 58 项假阳性，已按三次失败规则弃用；最终只检查裸旧文件名边界，不再为一次性审计增加复杂状态。
- 首次报告一致性命令因包含临时文件删除而被进程策略拒绝，未执行；已切换为不删除的系统唯一临时文件方案。
- 报告生成器成功写入系统临时文件；与正式报告的差异来自缺少评审期控制台日志、当前未提交树无法重建旧分支清单及最新签名基线。正式报告未被降级输出覆盖。
- 提交前验证完成：工作流 Check PASS；41/41 定向测试 PASS；NP4B 独立 verifier PASS；Python compileall PASS；37 个 Markdown 零断链；`git diff --check` PASS；未运行 Vivado。
- 已创建并推送实质归档提交 `ebd6c0d docs: archive project markdown files`，远端 `main` 从 `e5bbbc5` 前进到 `ebd6c0d`；推送退出码 0。
- 本条与任务完成勾选将作为纯工作流记录提交，不修改归档结构、验证结论或功能代码。
## 2026-09-01 根目录非 Markdown 文件归档调研启动

- 用户要求继续归档其它文件，让根目录更干净。
- 已读取 `planning-with-files` 与 `karpathy-guidelines`；本轮先做只读盘点和固定路径审计，形成 V1 方案后提请审核，批准前不移动文件。
- 已启动一项并行只读审计，重点区分必须留根、可安全迁移、应忽略生成物和机器证据绑定文件。
- 初步盘点：根目录 287 个已跟踪文件，以 Python 151、SystemVerilog 41、JSON 28 为主；另有大量已忽略的 VVP、失败 VCD、临时日志和工具缓存。
- 初步方向收敛为“小步清噪 + 证据归档”，暂不把 Python/RTL 全量拆包；下一步统计候选结果和 Vivado 目录的固定路径依赖。
- 已统计候选引用：47 个 ignored 根生成物可清理；30 个 JSON/TXT 和 11 个已跟踪 Vivado 证据目录均存在固定路径依赖；12 个正式形式日志/VCD还受 NP4B 签名和 runner 重写路径约束。
- 当前 V1 倾向排除形式日志/VCD和源码拆包，只处理 ignored 噪声、JSON/TXT 与 Vivado 证据目录。
- 已形成 30 个 JSON/TXT 的无遗漏分类：data 4、results 15、signoff 11；Vivado 目录迁移涉及 runner、Tcl、verifier、测试、忽略例外和文档，适合拆为独立切片。
- 已形成 V1 审核稿：只迁移 30 个 JSON/TXT、增加 artifacts 索引并清理 ignored 根噪声；正式形式证据和 Vivado 目录延期。批准前不实施。
- 并行只读审计完成并将方案继续收缩：只有 15 个结果 JSON 适合 V1；data/manifest、signoff 摘要、正式形式证据和 Vivado 目录全部延期。
- V1 审核稿已更新并提请用户批准；当前未移动、清理、提交或推送任何非规划文件。

## 2026-09-01 根目录归档 V1 获批

- 用户明确回复“批准 V1”。
- 冻结执行范围：迁移 15 个普通结果 JSON、增加 artifacts 索引、清理 47 个 ignored 根文件和纯缓存目录；不移动签核、形式或 Vivado 证据，不运行 Vivado。
- 已按 TDD 分解 T1→T7；先锁定新默认路径合同，再实施迁移。
- T1 完成：15/15 文件已跟踪且不进入六类当前签核摘要；47 个 ignored 根文件白名单已冻结；工作树无来源不明修改。
- T2 RED 完成：`python -m unittest -v test_artifact_layout` 运行 1 项、失败 1 项，唯一失败为 `artifacts/results` 尚不存在，符合预期。
- 已 Git rename 15 个结果到 `artifacts/results/` 并新增 `artifacts/README.md`；正在同步四类路径引用。
- T3/T4 完成：15 个结果已唯一归档，writer、reader、测试和文档路径已同步；布局测试转为 GREEN。
- 路径改动使 B0、NP2、NP3、B2.1 的源码哈希链按设计失效；已使用正式生成器依次重建，相关定向测试全部通过。
- T5 完成：精确清理 47 个 ignored 根文件和 5 个批准目录；全量回归产生的 ignored 文件也已再次清理。12 个 tracked formal log/VCD 未改动。
- 全量 `python -m unittest discover -v`：387 项通过、1 项真实 Vivado 用例按未设置环境变量跳过；`verify_np4b_signoff.py`、compileall、工作流 Check 均通过。
- `verify_goal.py` 的软件/M3 阶段通过，但最终报告审计失败：2026-08-29 更新的 Tile RTL 晚于 2026-08-19 的 Vivado Tile 报告。该历史陈旧关系与 V1 无关，但冻结合同要求 verifier 失败即停止提交；且 V1 禁止运行 Vivado，因此 T6/T7 暂停等待用户决策。
- 用户选择严格闭环方案 1，明确批准使用 Vivado 2024.1 重建当前 RTL 的 Tile、XPM、System 证据；执行仅限 `verify_goal.py` 冻结的三个 runner，不启动 NP6。
- Vivado Tile OOC 重建通过：Vivado 2024.1、xc7a35tcpg236-1、100 MHz，WNS +0.213 ns、WHS +0.026 ns、TNS/THS 0、setup/hold 0 失败、route error 0；3152 LUT、1972 FF、0 BRAM、0 DSP，功耗为 vector-less 0.103 W（Medium），不解释为真实活动功耗。
- 真实 XPM xsim/综合通过：命令与响应 FIFO 均完成容量 17、排空和回绕验证；`digital_snn_host_bridge` 综合成功，使用 4 个 RAMB36E1，网表中仿真专用 reset-reentry assertion 计数为 0。
- 双时钟 System OOC 重建通过：Host 50 MHz / Tile 100 MHz，Host WNS +14.306 ns、WHS +0.105 ns，Tile WNS +0.081 ns、WHS +0.058 ns，TNS/THS 0、setup/hold 0 失败、route error 0、DRC error 0；外部 CDC critical/unsafe/warning 均 0，XPM CDC critical/unknown 均 0。
- 完整 `python verify_goal.py` 已退出 0：387 项 unittest 全部通过、1 项按未设置 `VIVADO_ROOT` 跳过；Tile 协议形式证明通过；Host Bridge 控制器 20 拍安全证明和 6 类可达性见证通过；Tile 10000 事务、System 957 命令协同仿真通过；最终输出 `GOAL_AUDIT_PASS`。
- 全量验收对 `local_prune_rtl_results.json` 和 `np4b_signoff_summary.json` 产生的日期/基线刷新属于验证副作用，提交前精确恢复，不混入 V1 归档；当前 RTL 对应的 Tile/XPM/System Vivado 正式报告和 `t0_signoff_summary.txt` 保留为严格重建证据。
- 提交前轻量门全部通过：`verify_np4b_signoff.py`、Python compileall、持久工作流 Check、`git diff --check` 均退出 0；随后按 dry-run 白名单精确清理本轮重新生成的 ignored 缓存、形式临时文件和 Vivado 工作产物，受跟踪的 XPM `simulate.log` 保持存在。

## 2026-09-01 PR #3 NP6 静态审查

- [x] 读取 PR #3 元数据、提交 `b139a99`、文件差异和 CI 状态；PR 为 open，未报告自动检查。
- [x] 核对 NP6 runner 审计中的脚本、顶层和报告目录存在性；确认该 PR 仅是静态审计/冻结草案，没有调用 Vivado。
- [x] 发现两处事实口径问题：把并非所有既有目录都存在的 `signoff_summary.txt` 写成统一约定；静态审计声称已排除陈旧 RTL，但没有执行新鲜度验证。
- [x] 通过 GitHub issue comment `5491242843` 提交中文阻断反馈；修正后再重新审查，不建议当前合并。
- [x] 协作者提交 `34e7c9c` 修正两处口径；复核确认最新 HEAD `e979675`，通过 GitHub review `APPROVED`，PR 保持 open，未合并。
- [x] 协作者后续回复确认 PR 仍严格限定为 NP6.1 静态审计/NP6.0 冻结草案；最新 HEAD `734faf9` 仅同步 main，无新增代码或证据。复核维持 `APPROVED`，PR 仍 open、未合并。

## 2026-09-01 PR #5 首轮回复复核

- 用户明确确认 NP6 九项冻结决策全部同意；此前审查中的授权溯源阻断随之解除。
- GitHub 实时核对确认不存在 PR/Issue #4；唯一开放 PR #5 出现协作者评论，但 HEAD 仍为 `a7e8b09`，没有技术修复提交。
- 下一步仅在 PR #5 记录批准确认；保持 `CHANGES_REQUESTED`，等待其余三项修复形成新 HEAD 后再复验。
- 已通过评论 `5492928792` 逐项确认九项冻结决策，并要求冻结文件引用该仓库内批准记录；GitHub 回读确认正文完整。
- 新 HEAD `61988e2` 已完成隔离复验：compileall 通过；只读 verifier 正向 PASS；manifest 不变且工作树干净；mutation suite 10/10 PASS。
- 复验仍发现冻结字节绑定漏洞和两处文档状态陈旧，准备提交新的精简 `CHANGES_REQUESTED`；未运行 Vivado、未修改协作者分支。
- 最新 HEAD `550ec26` 已完成隔离复验：正向 verifier PASS、manifest/工作树不变、12 项 mutation 全通过，冻结后 RTL/runner 联合篡改被拒绝，权威文档状态一致。
- 本轮无需重跑 Vivado；准备对 PR #5 提交 `APPROVE`，但批准仅表示证据链和报告口径可合并，不改变 100 MHz 时序仅部分通过的事实。

## 2026-09-01 NP6 收口与 NP7 审核稿

- PR #5 已合并到远端 main；本地 review 记录提交后成功 rebase 到 `origin/main`。
- 持久恢复检查通过，但发现 `WORKFLOW_STATE.md` 和 NP6 TODO 仍停在未批准状态。
- 已更新 NP6.0-NP6.8 的真实完成状态、总剪枝 TODO、文档索引和工作流指针。
- 已新增 NP7 共享 BRAM/lane 审核稿；当前停在八项用户决策门，未修改业务 RTL，未运行新的 Vivado。
- 本轮首次占位 PowerShell 命令误写 `constNotUsed=0`，立即失败且未改变仓库；后续未重复该写法。
- Nexus 子代理完成增量更新；主代理将 AST 上限从 500 提高到 2500 后重建，最终 155 文件、1682 节点、2310 边、parse errors=0、无截断，并恢复 INDEX 的完整强制路由块。
- 发现并修复 NP6 mutation 测试夹具问题：复制仓库会让受跟踪 VCD 产生假脏状态；改用 `git clone --no-hardlinks` 后，干净提交态 `MUTATION_SUITE PASS checks=12`。该修复尚未提交，待最后 commit/push。
- 最终干净提交态（HEAD `03bb19c`）复验完成：NP6 verifier `PASS configs=7`、mutation `PASS checks=12`、manifest/工作树不变；Resume、compile、diff-check、Markdown 链接和 Nexus 检查均通过。当前停在 NP7 八项用户审核门，未运行新的 Vivado。

## 2026-09-01 PR #6 NP7 审查启动

- 发现开放 PR #6，HEAD `398dc1a`，标题声明 NP7.1–NP7.6 完成、G3 未达标、NP7.7 停在功能阶段。
- 用户称协作者完成了 Vivado 仿真；需核对是否为 NP7 Vivado、已有 Vivado 回归或仅标题表述差异。
- 已锁定隔离 worktree 并完成静态/动态复核：Python 编译、11 项 oracle 单测和三模型集成通过；软件 verifier 无完整性拒绝，但因 G3 全部 12 项低于 25% 正确退出 1。
- Windows 默认编码下突变套件复现失败并崩溃；显式启用 UTF-8 后 13/13 PASS，定位为测试入口的编码环境缺陷。
- 本机 Vivado 2024.1 真实 `xvlog` 检查证明 RTL 文件可分析，但主 testbench 因变量声明顺序报 `VRFC 10-3380`，负向 testbench 有同类源代码问题；PR 当前没有可运行的 Vivado 仿真链。
- RTL 审查确认非法 CONFIG 数据仍会写入 RAM，且 sparse 的 `checked_lat` 未初始化/未逐事务清零；现有正向测试和形式假设没有覆盖。
- 已向 PR #6 提交 `CHANGES_REQUESTED` 并回读确认，远端 `reviewDecision=CHANGES_REQUESTED`；未修改协作者分支、未合并、未运行 NP7.7 综合。
- 已完成两类裁定的依赖分析：确认八项只关闭授权链，A/B/D 分别会改写决策 7、决策 5、决策 6/7；只有 C 保持八项原文不变。
- 已按工程量、全量重跑范围、G3 余量、硬件风险和结论可信度比较 A/B/C/D；推荐坚持原目标时选择 B-V1，快速取得物理数据时才考虑 A，不建议 D。
- 已进一步把软件周期数字映射为实际效果：当前 100 MHz 串行模型约节省 70–77 ns/tick；1→2 lane 仅再改善约 1.25%，4/8 lane 无额外收益；A/D 不改变硬件，B 才改变真实周期。
- 已记录端到端边界：局部 22.3% 改善只有在共享执行单元占主要系统时间时才能接近整机 22%；BRAM 映射、功耗、网络吞吐仍需 Vivado 与系统级测量。
- 用户以仓库管理员身份正式选择 B-V1+V2；已新建 DP-NP7-001 决策文档，更新文档索引和 NP7 TODO 状态。
- 已向 PR #6 提交管理员裁定评论 `5498372499` 并回读确认：G3 保持 25%，A/C/D 不采用，旧 NP7.1–NP7.6 证据失效，修复后全量重跑。
- PR 仍保持 `CHANGES_REQUESTED`，HEAD 仍为 `398dc1a`；本轮未提交、未推送、未合并，也未运行 NP7.7 Vivado。

## 2026-09-02 PR 自动检查工作流

- 新增 `.github/workflows/pr-gate.yml`：只读 `pull_request` 触发，包含 Python/语法、NP7 软件/形式、物理证据完整性三道状态门；不自动 approve、不自动 merge、不使用 `pull_request_target`。
- 新增 `docs/CI_PR_GATE.md`：记录工作流设计、状态含义、本地复现命令和 main 分支保护配置教程；`docs/README.md` 已加入索引。
- 本地 YAML 解析、Python compileall、git diff --check 均通过；NP7 job 对尚未包含 NP7 文件的普通 PR 显式跳过专项门，避免误报。

## 2026-09-02 PR #6 持续监控

- 03:00:43.486（UTC+8）按真实墙钟完成管理员裁定后的首次 10 分钟远端读取。
- PR HEAD 仍为 `398dc1aedc401ede04b9ec8a6b79e4c740cb2d1d`，最后活动仍是 OWNER 评论 `5498372499`；无协作者新提交、无协作者新回复、无 checks。
- PR 仍为 `OPEN / MERGEABLE / CHANGES_REQUESTED`。本周期不重复测试、不重复评论，Goal 保持 active；下一次读取锚定为 03:10:43.486（UTC+8）。
- 03:10:44.249（UTC+8）完成第二次精确轮询：HEAD、最后评论、reviews、checks 和合并状态均未变化；继续执行已验证等待，下一次读取锚定为 03:20:44.249（UTC+8）。
- 03:20:44.557（UTC+8）完成第三次精确轮询：HEAD 仍为 `398dc1a`，无协作者新提交/回复、无 checks，状态仍为 `OPEN / MERGEABLE / CHANGES_REQUESTED`；下一次读取锚定为 03:30:44.557（UTC+8）。

## 2026-09-02 管理员追加裁定

- 管理员裁定：允许在 lane 内插入一拍流水，以解决 L4/L8 的 100 MHz 关键路径问题。
- 管理员裁定：NP7.7 必须要求 dense/sparse × L=1/2/4/8 共 8/8 配置全部 100 MHz 收敛，不接受当前 4/8 部分通过口径。
- 已向 PR #6 提交 OWNER `CHANGES_REQUESTED` review，review id `PRR_kwDOUIH1ms8AAAABLx8fCg`；要求流水化后全量重跑 NP7.1–NP7.7，PR 暂不得合并。

## 2026-09-03 PR #10 清单绑定修复

- 读取 PR #10 run `33655668879` 失败日志，确认失败原因为 `NP7_VERIFY_REJECT: input_files 磁盘字节偏离清单 docs/planning/NPU_PRUNING_NP7_TODO.md`，不是 NP7 功能门失败。
- 在分支 `codex/record-np7-merged-after-revert` 上运行 `python -X utf8 generate_np7_manifest.py`，将清单重新绑定到当前 HEAD `61b694b`；G1-G6 与 `overall=PASS` 保持不变。
- 首次本机生成误探测旧 Icarus 路径，已废弃该结果；随后显式加入 `C:\msys64\ucrt64\bin` 重生成，记录实际 Icarus/Yosys 版本。
- 当前待提交文件仅为 manifest 与本轮工作流记录；未运行新的 Vivado，未修改业务 RTL。
- 提交 `5a6825f` 已推送；本地 `verify_np7_software_cost.py HEAD` 返回 `rejects=0 / overall=PASS`。
- GitHub Actions run `33659017501` 已成功：Python 全量测试、XPM CDC、NP7 功能/证据和物理完整性全部通过；Webhook 已收到对应终态事件。
- PR #10 当前为 `OPEN / CLEAN`，未自动批准或合并；后续仍需管理员决定是否合并文档/证据修复，再进入传统 NPU + 神经元集成审核。

## 2026-09-02 PR #10 CI 与 Webhook 收口

- 继续等待既有 CI run `33660700397`，没有因观察超时而重启任务。
- GitHub Actions 四项检查最终全部成功；NP7 形式/突变、软件清单重算和物理证据完整性均在当前 PR HEAD 上闭环。
- 本机仓库外 Webhook 服务在 `127.0.0.1:2355` 保持监听，并收到对应 `workflow_run`、`workflow_job` 和 `check_run` 事件；本地测试 POST 也返回 HTTP 200。
- Nexus 子代理完成增量刷新，更新索引、架构、测试覆盖和原始 git 统计；刷新临时目录已清理。
- 当前仓库仍无业务 RTL 改动，PR #10 未自动批准或合并；状态回到“等待管理员合并后重新审核传统 NPU + 神经元集成”。
- 2026-09-03 复核发现 Webhook 进程短暂停止，已重启并验证 `GET /healthz` 返回 200；不会把服务进程或事件文件纳入仓库。
- run `33711162898` 在 2026-09-03 03:38:56（本地记录对应 GitHub UTC 时间）完成成功；四道 CI 门均通过，当前没有待修复的 CI 问题。

## 2026-09-03 PR #10 HEAD 终态与 Webhook 双重确认

- run `33712261128` 已完成成功，HEAD 为 `90b7e414da211985c7e8d83872ddc910e1706b18`；四道 CI 门全部成功。
- Webhook `latest.json` 已记录同一 HEAD 的 `workflow_run` completed/success，时间为 03:55:10 UTC；与 GitHub run 结果一致。
- PR #10 仍保持 `OPEN / CLEAN`，仅具备人工合并条件；下一步仍是等待管理员决定，合并前不实现新的集成业务 RTL。

## 2026-09-03 PR #10 重跑完整成功

- 重跑 run `33714262900` 对提交 `15940b5` 完整成功，四道 CI 门及 NP7 形式/突变检查均通过。
- GitHub 结果证明当前提交的 NP7 软件、协同仿真和证据完整性闭环成立；Webhook 未收到重跑终态，已记录为接收器缺口。
- PR #10 保持 `OPEN / CLEAN`，下一步等待管理员人工合并，不自动 approve/merge。

## 2026-09-03 PR #10 当前 HEAD 最终收口

- run `33720890399` 已对当前 HEAD `832c785a35bd68e4d2add5a9b49b9f69b5621eba` 完成并成功。
- Python/语法、XPM CDC、NP7 功能与证据、NP7 物理证据完整性四道门全部通过；NP7 形式与突变检查也在该 HEAD 上成功。
- 仓库外 Webhook `C:\Users\Epsilon\ENeuronWebhook` 已收到同一 SHA 的 `workflow_run completed/success`，本机 `/healthz` 返回 HTTP 200，GitHub 与本机事件形成双重终态证据。
- PR #10 仍为 `OPEN / CLEAN`，具备人工合并条件；本轮不自动 approve/merge，合并前不启动传统 NPU + 神经元集成 RTL 或新的 Vivado。

## 2026-09-03 Nexus 更新提交 CI 收口

- run `33723437364` 已对 HEAD `d7f782451aecf4872eb875fa3900dd1e1c780f71` 完成并成功。
- Python/语法、XPM CDC、NP7 功能与证据、NP7 物理证据完整性四道门全部通过；形式与突变检查、软件证据清单验证均成功。
- 仓库外 Webhook 已收到同一 SHA 的 `workflow_run completed/success`，与 GitHub 结果一致。
- PR #10 仍为 `OPEN / CLEAN`，等待管理员人工合并；不自动 approve/merge，也未启动集成 RTL/Vivado。

## 2026-09-03 Webhook 再次恢复

- 发现新提交 `33248ff` 触发的 run `33726255349` 后，仓库外接收服务曾停止，`127.0.0.1:2355` 健康检查暂时拒绝连接。
- 已使用 `C:\Users\Epsilon\ENeuronWebhook\start_webhook.ps1` 重启，当前 PID `42136`，`GET /healthz` 返回 HTTP `200`。
- 服务恢复前的少量事件可能未落盘；后续 CI 终态仍以 GitHub run 为主，并继续用恢复后的 Webhook 做交叉核对。

## 2026-09-03 仓库外接收服务复核与 PR #10 终态

- 仓库外接收服务固定在 `C:\Users\Epsilon\ENeuronWebhook`，监听 `127.0.0.1:2355`；服务脚本、事件日志和 PID 文件均不在 `D:\Documents\Code\ENeuron` 内。
- 本地 `GET /healthz` 返回 HTTP `200`；带 `X-GitHub-Event: workflow_run` 和 `X-GitHub-Delivery` 标头的模拟请求返回 HTTP `200`，并正确落盘 `event=workflow_run` 摘要。
- Webhook 已收到 PR #10 HEAD `6893964a8a7c3c04e683dd8331c399f72df3440a` 对应 run `33726377825` 的 `workflow_run completed/success`，同时收到 `NP7 functional and evidence gate` 的成功事件；该事实与 GitHub PR 检查结果一致。
- PR #10 仍为 `OPEN / CLEAN`，不自动 approve 或 merge。传统 NPU + 神经元集成仍停在 `NPU_NEURON_INTEGRATION_REVIEW_REQUIRED`，未获 I1-I6 管理员裁定前不实现集成 RTL、不运行新的 Vivado。

## 2026-09-03 `da819cf` CI 与 Webhook 闭环

- 文档/Nexus 提交 `da819cfdb6b492cd4bcb426aba8af3d8490007f5` 已推送到 PR #10。
- GitHub Actions run `33728135382` 完成成功；Python/语法、XPM CDC、NP7 功能与证据、NP7 物理证据四道门全部通过。
- 仓库外接收器已收到同一 SHA 的 `workflow_run completed/success`，并收到四个检查的成功事件；这次复核消除了此前“重跑终态可能漏收”的观察缺口。
- PR #10 仍为 `OPEN / CLEAN`，等待管理员人工合并；集成审核 I1-I6 仍未批准，继续禁止新的集成 RTL 与 Vivado。

## 2026-09-03 `cadc3a8` CI 与 Webhook 最终确认

- 状态记录提交 `cadc3a812ee614d7d9e07caf12a3c7e8bbd0eaad` 已推送到 PR #10。
- GitHub Actions run `33729657078` 已完成成功；Python/语法、XPM CDC、NP7 功能与证据、NP7 物理证据四道门全部通过。
- 仓库外 Webhook 已收到同一 SHA 的 `workflow_run completed/success` 以及四个检查成功事件；本地接收服务仍在 `C:\Users\Epsilon\ENeuronWebhook`，不属于仓库。
- PR #10 仍为 `OPEN / CLEAN`，等待管理员人工合并；传统 NPU + 神经元集成继续停在 I1-I6 `REVIEW_REQUIRED`。

## 2026-09-03 集成材料包草案

- 完成 `docs/planning/NPU_NEURON_INTEGRATION_MATERIALS.md`：推荐固定 8×8 灰度、`64→32→10` 两层 INT8 MLP，明确 INT32 累加、ReLU/INT8 饱和、四权重组门控和样本边界原子提交。
- 第一阶段只做片上单时钟 OOC；网口、DMA、PS 和异步 FIFO 延后，避免把供数问题混入门控 bit-exact 证明。
- 已列出全开、全关、零活动、频繁切换、背压、清除、推理冻结和非法配置矩阵及验收门槛。
- PR #10 run `33730940941` 对 HEAD `b5165824` 已由 GitHub 和本机 Webhook 双重确认成功。

## 2026-09-03 CI 与仓库外接收服务闭环

- GitHub Actions run `33740218942` 对 HEAD `15d289e08bbd37f3c1dcc3e9eb9865153f6756fb` 已完成成功。
- Python/语法、XPM CDC、NP7 功能与证据、NP7 物理证据四道门全部通过；形式与突变检查、仓库单元测试均成功。
- 仓库外接收服务 `C:\Users\Epsilon\ENeuronWebhook` 在 `127.0.0.1:2355` 保持监听，`/healthz` 返回 HTTP 200。
- Webhook 已收到同一 SHA 的 `workflow_run completed/success`，与 GitHub 结果交叉一致；服务脚本、日志、PID 和事件摘要均不属于仓库。
- 本轮未启动传统 NPU + 神经元集成 RTL 或 Vivado；该工作仍等待管理员批准 I1-I6。

## 2026-09-03 PR #10 合并收口

- PR #10 已于 `2026-09-03T10:32:24Z` 合并到 `main`，merge commit 为 `a076160d8c3d4378ed7ad71e14f53658d43a4d71`。
- 合并前 HEAD `0f6b0ad9` 的 run `33742796085` 已完成成功，GitHub 与仓库外 Webhook 均已确认同一 SHA 的终态。
- 合并只收口 NP7 文档/状态记录，不改变集成审核门；`NPU_NEURON_INTEGRATION_REVIEW.md` 仍为 `REVIEW_REQUIRED`，I1-I6 未批准前不实现集成业务 RTL、不运行新的 Vivado。
- 仓库外接收服务仍固定于 `C:\Users\Epsilon\ENeuronWebhook`，监听 `127.0.0.1:2355`，不进入仓库。

## 2026-09-03 PR #11 合并收口

- PR #11 已于 `2026-09-03T10:52:28Z` 合并到 `main`，merge commit 为 `f48f4b693dc6e5af05f35c448963db88ba2a16ea`。
- PR #11 的四道 CI 门全部成功，且 Webhook 已收到同一 HEAD `2153bfca` 的检查完成与 PR closed 事件。
- 本次仅合并状态/Nexus 文档，不改变 I1-I6 集成审核门；管理员批准前仍不实现传统 NPU + 神经元集成业务 RTL、不运行新的 Vivado。

## 2026-09-03 PR #12 合并收口

- PR #12 已于 `2026-09-03T11:08:25Z` 合并到 `main`，merge commit 为 `bc839b5feca25935ec541871c1c34e1ab9c572d3`。
- PR #12 的四道 CI 门全部成功；Webhook 已收到同一 HEAD `0ce0dce` 的 workflow 完成和 PR closed 事件。
- 本次仍只更新文档与 Nexus 状态，I1-I6 集成审核门保持 `REVIEW_REQUIRED`，未启动集成 RTL 或 Vivado。

## 2026-09-03 PR #13 合并与阶段收口

- PR #13 已于 `2026-09-03T11:26:10Z` 合并到 `main`，merge commit 为 `1a8d0f2733c65e26ce293a2f0affd15ef57a3e94`。
- PR #13 的四道 CI 门全部成功；Webhook 已收到同一 HEAD `6da8748b` 的 workflow 完成和 PR closed 事件。
- 文档/Nexus 收口已完成，后续不再为重复状态创建新 PR；下一项实质工作是管理员批准 I1-I6 后实现 INT8 NPU 参考模型。

## 2026-09-03 PR #14 合并与仓库外接收器回归

- PR #14 已合并到 `main`，merge commit 为 `b754498a3cba871459eca87f509ff6482a7fc12c`；合并前 HEAD 为 `78062a74bfb42d6d54eea7e18b83425b11a64659`。
- Actions run `33749767954` 已完成成功；四道门（Python/语法、XPM CDC、NP7 功能与证据、NP7 物理证据）全部通过。
- 仓库外 Webhook 已收到同一 HEAD 的 `workflow_run completed/success`，时间为 `2026-09-03T11:40:22Z`；本地健康检查仍为 HTTP 200。
- 复核发现旧 `webhook.pid` 可能指向 wrapper shell；已在 `C:\Users\Epsilon\ENeuronWebhook\start_webhook.ps1` 与 `stop_webhook.ps1` 中加入真实 Python 命令行识别和安全回收逻辑，并完成停止/启动/POST 回归。服务目录、日志、PID 和事件摘要均未进入仓库。
- 本轮仍未启动传统 NPU + 神经元集成 RTL 或 Vivado；当前下一步保持为等待管理员对 I1-I6 和材料包的明确裁定。

## 2026-09-03 PR #15 合并收口

- PR #15 已于 `2026-09-03T12:09:13Z` 合并到 `main`，merge commit 为 `feec6bcb5444c164d7403d66cf1b2e1f7e36ab91`。
- HEAD `fc6332597ac34905e2e4a102d92eaa582cb81ef0` 的 run `33752156575` 已完成成功；四道 CI 门及仓库外 Webhook 终态均一致。
- 本次合并只收口文档/Nexus 与仓库外接收器维护证据，没有越过传统 NPU + 神经元集成审核门；I1-I6 未批准前不实现集成 RTL、不运行新的 Vivado。

## 2026-09-03 PR #16 合并与下一阶段入口

- PR #16 已于 `2026-09-03T12:30:06Z` 合并到 `main`，merge commit 为 `3850df77fd505b871acfc5a9c913aef25ff9bf78`；合并前 HEAD 为 `46840e8c536b15068b55ae1324abd3a59f774f0a`。
- Actions run `33753869517` 的四道门全部成功：Python/语法、XPM CDC、NP7 功能与证据、NP7 物理证据完整性；仓库外 Webhook 于 `2026-09-03T12:29:09Z` 收到同一 HEAD 的 `workflow_run completed/success`。
- 本次合并仍只做状态/Nexus 收口，没有实现传统 NPU + ENeuron 集成 RTL，也没有启动新的 Vivado。
- 当前唯一实质入口仍是 `NPU_NEURON_INTEGRATION_REVIEW_REQUIRED`：管理员需要先批准 I1-I6；批准后按材料包顺序实现 `64→32→10` INT8 MLP 的 Python 旁路/门控参考模型。
- 仓库外接收服务继续固定在 `C:\Users\Epsilon\ENeuronWebhook`，监听 `127.0.0.1:2355`；本轮本地回归事件保存在仓库外，不进入 Git。
# 2026-09-03 PR #18 合并与工作流收口

- PR #18 已在四道 CI 全部成功、Webhook 收到同 SHA 工作流终态后合并到 `main`，merge commit 为 `1877140c`。
- 本地 `main` 已与 `origin/main` 同步；用户文件 `np75_tmp_sparse_protocol.ys` 保持未跟踪且未纳入提交。
- 当前唯一实质入口仍是传统 NPU + ENeuron 集成审核，I1-I6 尚未批准；本轮没有创建集成业务 RTL，也没有运行新的 Vivado。

## 2026-09-03 PR #19 合并与 Webhook 恢复

- PR #19 已在 GitHub API 确认四道 CI 全部成功后合并到 `main`，merge commit 为 `63028d4`。
- CI 期间仓库外 Webhook 投递因本地服务/隧道短暂掉线而出现 EOF；已重启 `C:\Users\Epsilon\ENeuronWebhook`，本地和公网健康检查均恢复 200。由于 gh token 未授予 `admin:repo_hook`，未执行 redelivery，保留 GitHub API 作为本次终态权威来源。
- 当前主线无业务代码变更，集成审核 I1-I6 仍待管理员批准。

## 2026-09-03 集成审核门静态审计快照

- `workflow_resume.ps1 -Mode Resume` 返回 PASS；当前 HEAD 为 `8d23347`，活动 NP4B TODO 未完成项为 0。
- GitHub 当前无开放 PR；最近 run `33763267873` 的四道 CI 门全部成功，主线与 `origin/main` 同步。
- 仓库外 Webhook `C:\Users\Epsilon\ENeuronWebhook` 的 `/healthz` 返回 HTTP 200。
- `docs/planning/NPU_NEURON_INTEGRATION_REVIEW.md` 仍为 `REVIEW_REQUIRED`；I1-I6 未批准前不创建集成业务 RTL、不运行新的 Vivado。
- 用户文件 `np75_tmp_sparse_protocol.ys` 仍保持未跟踪、未修改，未纳入本次文档提交。

## 2026-09-03 I1-I6 获批，启动 Python oracle

- 管理员已批准 I1-I6，正式冻结 `64→32→10` INT8 MLP 集成参数与验证顺序。
- 当前阶段从“等待审核”进入“Python 旁路/门控参考模型”；尚未创建 RTL，尚未运行 Vivado。
- 下一硬门是旁路/全开门控逐样本 bit-exact，并覆盖全关、零活动、epoch 原子切换、背压、清除、推理冻结和非法索引。

## 2026-09-03 Python oracle 首个纵向切片

- 新增 `npu_eneuron_reference.py`：实现 `64→32→10`、4 bit 输入、INT8 权重、INT32 累加、隐藏 ReLU/`0..127` 饱和和四权重组门控。
- 新增 `test_npu_eneuron_reference.py`：旁路全开逐输出检查、全关保留 bias 且零 MAC/零组读取检查均通过。
- 当前仍未创建 RTL，下一切片是补齐饱和、旁路/全开等价和门控计数的边界测试。

## 2026-09-03 Python oracle 边界测试完成

- 新增全开 gated 与 bypass 的完整 `InferenceResult` 等价测试，确认门控路径不会改变数值结果或计数语义。
- 新增隐藏层饱和测试，确认 ReLU/`0..127` 饱和发生在输出层计算之前；全相等 logits 正确触发 abstain。
- `python -X utf8 -m unittest -v test_npu_eneuron_reference.py`：4/4 通过；`git diff --check` 通过。
- 当前硬门完成：Python oracle 的基础 bit-exact、全关门控、饱和边界已具备；下一步补齐 epoch 原子切换、背压/清除和非法索引合同，再进入 RTL。

## 2026-09-03 CI-Fast V1 实施

- 管理员批准 CI-Fast V1；将原四个独立必跑 job 改为路径分类、定向门和固定 `PR Gate` 汇总门。
- 新增 `tools/ci/classify_changes.py` 与 `test_ci_fast_v1.py`，覆盖文档、NPU oracle、XPM、NP7、未知代码和 workflow 变更矩阵。
- Windows MSYS2 专项不再每个 PR 强制启动，仍保留固定 `C:/msys64/ucrt64/bin` 检查；NP7 相关改动仍保留功能与物理门。
- 本地分类/模型测试 10/10 通过，YAML 可解析，`compileall` 与 `git diff --check` 通过；尚未以 GitHub Action 验证分类结果。
- PR #25 首轮发现 Windows 门在 `Verify fixed toolchain` 失败：`update: false` 时 action 输出目录不保证是 `C:/msys64/ucrt64`。已恢复原有 MSYS2 UCRT64 目录探测、联接/复制兜底，仅保留按需启动专项门的加速策略。

## 2026-09-03 CI-Fast V1 GitHub 验收

- PR #25（`381849d1`）已通过并合并为 `c46320e`；Webhook 收到同 SHA 的 `workflow_run completed/success`。
- workflow 自身变更按预期启动全量门：分类、快速、全仓、Windows XPM、NP7 功能、NP7 物理和 `PR Gate` 均成功。
- 实测作业耗时：分类 6 秒、快速 7 秒、Windows XPM 75 秒、物理门 17 秒、全仓 12 分 26 秒、NP7 功能约 14 分钟；重门由 workflow 变更触发，不能代表普通文档 PR 的耗时。
- GitHub API 对私有仓库 ruleset/branch protection 返回 403（需升级套餐或公开仓库）；因此 `PR Gate` 目前只能作为统一状态和人工合并纪律，不能由服务端强制锁定。

## 2026-09-03 NPU-only 快速路径验证准备

- 新增 4-bit 输入边界测试：负值裁剪为 0，超过 15 的值裁剪为 15，并验证裁剪后的结果进入完整两层计算。
- 该改动只触碰 `test_npu_eneuron_reference.py`，预期 CI 仅执行 NPU oracle 定向单测、快速门和 `PR Gate`。

## 2026-09-03 NPU oracle epoch/背压协议

- 新增 `npu_eneuron_protocol.py`：双版本门控（active/pending）和单槽结果运行时参考模型。
- 新增样本边界切换、结果背压、状态清除、推理冻结、epoch/完整 mask 校验测试；与既有 NPU/CI 测试合计 17 项通过。
- 将 `npu_eneuron_protocol.py` 纳入 NPU oracle 定向 CI 分类，避免该协议文件误触发全仓重门。

## 2026-09-03 NPU oracle 接受原子性修正

- 将运行结果改为 runtime 内部 `_inflight` 所有，`complete_sample()` 只能提交该事务自己的结果，调用者不能注入伪造结果。
- pending mask 在有效样本接受沿原子切换；图片长度非法时 active epoch、pending、running 和输出槽均保持不变。
- 输出槽同时锁存 inference 与 epoch；背压期间二者保持同一对象，不会被下一样本覆盖。
- NPU/协议与 CI 分类合计 18 项测试通过，`compileall` 和 `git diff --check` 通过。

## 2026-09-03 PR #21 合并收口

- PR #21 已合并到 `main`，merge commit 为 `588e7d5`；合并前 HEAD `bc546c0` 的 run `33765822606` 四道 CI 门全部成功。
- 仓库外 Webhook 已收到同一 SHA 的 `workflow_run completed/success`；本地 `main` 与 `origin/main` 已同步，无开放 PR。
- 本次仅收口集成审核静态审计和 Nexus 基线，没有创建传统 NPU + ENeuron 集成 RTL，也没有运行新的 Vivado。
- 集成审核 I1-I6 仍待管理员批准；`np75_tmp_sparse_protocol.ys` 继续保持未跟踪、未修改和未纳入提交。

## 2026-09-03 Python oracle 最坏情况测试与冻结复核

- 新增三项不依赖后续协议裁定的测试：全关零活动不产生读取/MAC、epoch 1/2/3 连续切换不混用 mask、pending 单槽满时拒绝覆盖。
- `test_npu_eneuron_reference.py` 当前 14/14 通过，`test_ci_fast_v1.py` 7/7 通过，`git diff --check` 通过。
- 独立只读审计发现当前 oracle 仍使用 Python 无限精度累加，非整除配置会在推理中触发 `IndexError`，mask 位序和逐拍流协议也没有独立冻结证据。
- 新增 `docs/planning/NPU_ORACLE_FREEZE_REVIEW.md`，把当前门更新为 `OF1-OF6_REVIEW_REQUIRED`；本切片不修改参考模型、不创建 RTL、不运行 Vivado。
- 用户未跟踪文件 `np75_tmp_sparse_protocol.ys` 保持原样，不纳入提交或 Nexus。

## 2026-09-03 OF1-OF6 V2 反审计

- 独立计算固定拓扑最坏范围：第一层乘加贡献 `[-122880,121920]`，第二层 `[-520192,516128]`。
- 原 OF1 的正常回绕建议会允许极端 bias 翻转 logit 排序；V2 改为配置期安全范围拒绝，逐拍饱和不进入 MAC 关键路径。
- 原任意地址配置需要 19-bit mask bitmap 和 634-bit model bitmap；V2 改为固定顺序流，分别只需 5-bit/10-bit 计数器。
- V2 明确 mask staging 与 published pending、commit/首 beat 互斥、partial staging 阻止 freeze、STATE_CLEAR 非 abort、hard reset 只使 RAM 失效而不承诺物理清零。
- 本轮只修订审核材料；Python 业务代码、RTL 和 Vivado 均未改变。

## 2026-09-03 CI Node 24 action 升级

- PR #31 的快速 run 首次给出 checkout v4 的 Node.js 20 弃用 annotation；该 run 本身成功，警告不影响既有证据。
- 通过 GitHub 官方 release API 核对 checkout `v7.0.1`、setup-python `v7.0.0` 与 runner `v2.337.0`；Node 24 action 最低 runner 要求为 `v2.327.1`。
- 将 6 处 checkout 和 5 处 setup-python 升级到 v7；新增单测固定数量并拒绝 v4/v5 回退。
- 该改动触碰 workflow，CI-Fast 按设计必须运行所有重门；不能把本地语法检查替代真实 GitHub run。
- 本地 `test_ci_fast_v1.py` 8/8、YAML/JSON 解析、compileall 和 `git diff --check` 均通过；分类结果为 full/XPM/NP7 功能/NP7 物理全部启用。

## 2026-09-03 OF1-OF6 V3 审核稿

- PR #32 的 workflow run `33790397482` 在同一 HEAD 上 7/7 成功，Webhook 收到 `completed/success`；已合并为 `1f9d3b7`。
- 两路独立只读审计复核 V2 与当前 Python/测试，确认安全 bias、634/19-word 数量、epoch 回绕和 hard reset 方向正确，同时发现 6 个会造成实现分叉的合同空白。
- 将审核稿升级为 V3：补齐模型 word 线性映射、非法配置错误响应与重试、mask 四态命令矩阵、运行中预装下一版本、freeze 切换、固定工作量计数和严格 Python 类型域。
- 更新 `PROJECT_REPORT.md`，把陈旧的 NP7 人工门改为传统 NPU + ENeuron 集成基线及 OF1-OF6 V3 人工门。
- 本切片只修改文档和持久状态；未修改 Python 业务语义、未创建 RTL、未运行 Vivado，且未触碰 `np75_tmp_sparse_protocol.ys`。
- 本地分类器确认 `npu_oracle/full_repository/xpm_cdc/np7_functional/np7_physical` 全为 `false`，PR 应只运行 Fast check 与固定 `PR Gate`。
- V3 文档提交已推送并创建 PR #33；后续只接受同一最新 HEAD 的 Fast check、`PR Gate` 和 Webhook 终态作为合并证据。

## 2026-09-04 OF1a 实施

- 管理员明确批准 OF1-OF6 V3；从 `main@1ef8b9f` 创建 `codex/of1a-uint4-core-20260904`。
- 先替换旧裁剪测试并增加 pending epoch 原子性测试；旧实现运行 2 项测试得到 6 failures + 1 error，RED 成立。
- 最小实现删除核心隐式转换/裁剪，新增严格 uint4 校验；OF1a 定向 2/2、完整 oracle 15/15、oracle + CI-Fast 23/23、Python 编译和差异检查均通过。
- Nexus 只更新 6 个相关摘要，`concept_model.json` 有效，`.nexus-map` 差异检查通过；未运行 Vivado，未触碰用户未跟踪文件 `np75_tmp_sparse_protocol.ys`。
- OF1a PR #34 已由 GitHub NPU-only 快速路径验证并合并，merge commit 为 `9d0c3e5`；本地 `main` 已同步。
- 从该基线创建 `codex/of1b-fixed-model-contract-20260904`，新增固定参数、严格权重、安全 bias、原子 reload 和不可变 logits 的 RED 测试；旧实现定向结果为 20 failures + 2 errors。
- 完成 OF1b 最小实现并按独立审计补强原子性与 INT32 极值测试；定向 4/4、完整 oracle 19/19、Python 编译和差异检查通过。
- 本切片未修改 `npu_eneuron_protocol.py`、mask 语义或任何 RTL，未运行 Vivado，未触碰 `np75_tmp_sparse_protocol.ys`。
- 最终本地复验：OF1b 4/4、oracle 19/19、CI-Fast 8/8，合计 27 项；compileall、Nexus JSON 和 `git diff --check` 全部通过，独立复审 PASS。
- OF1b PR #35 已合并为 `6833237`；从该基线创建 `codex/of3-mask-order-cost-20260904`。
- 新增 3 项 OF3 手算冻结测试，首次运行 3/3 通过；独立只读审计确认核心索引和 open group 计数原已符合，未修改 `npu_eneuron_reference.py`、协议、RTL，未运行 Vivado。
- OF3 最终本地复验：oracle 22/22、CI-Fast 8/8、compileall、Nexus JSON 与完整 diff-check 全通过；Nexus 仅更新 6 个相关摘要。
- OF3 PR #36 已合并为 `a93019f`；从该基线创建 `codex/of4a-model-word-map-20260904`。
- 新增 634-word 精确映射、严格 uint32 域和非法 bias 原子载入测试；当前实现定向结果为 3 个方法、10 errors，OF4a RED 成立。
- 实现 `DecodedModel`、`decode_model_words()` 与 `load_model_words()`，完整镜像先快照/验证/解码再原子载入；OF4a 3/3、oracle 25/25、compileall 与 diff-check 通过。
- 本切片未实现 ready/valid、配置响应、`MODEL_COMMIT`、19-word mask 或任何 RTL，未运行 Vivado，未触碰用户临时 `.ys`。
- 独立首轮复审因内部 word 覆盖不足暂判 FAIL；已补为全 634 项逐位置核对，并增加 `word633=None/2^32` 经 loader 失败后旧模型对 0/1 输入保持不变。补强后 OF4a 3/3、oracle 25/25。
- OF4a 终审 PASS：512 个第一层和 80 个第二层权重 word 图样分别全唯一，全部 bias 逐项核对；核心、mask、runtime 状态机和 RTL 均无越界改动。
- OF4a 最终本地复验：oracle 25/25、CI-Fast 8/8，合计 33 项；compileall、Nexus JSON 和完整 diff-check 全通过。
- OF4a PR #37 已合并为 `59a8dca`；从该基线创建 `codex/of4b1-mask-word-map-20260904`。
- 新增 exact 19、严格 uint32、word18 保留位和全 592-bit canonical packing 测试；当前实现为 2 个方法、25 errors，OF4b1 RED 成立。
- OF4b1 已完成 GREEN：新增 `DecodedMasks` 与 `decode_mask_words()`；定向 2/2、完整 oracle 27/27、CI-Fast 8/8、compileall/diff-check 通过，独立审计 PASS。下一阶段为 OF4b2 四态命令机，不在本提交中混入逐拍协议或 RTL。
- OF4b2 RED 已提交为 `3fc3a3f`：3 条测试在基线均按预期失败，覆盖四态流转、错误响应稳定背压和保留位失败后的同索引重试；准备实现最小 Python 命令端口。
- OF4b2a 实现已完成首轮：`MaskConfigPort` 支持四态、单槽错误响应、非法 epoch/保留位零副作用、同索引重试和样本边界激活；6 条 OF4b2 测试及既有 oracle 共 33/33 通过，独立审计待完成。
- 审计后补齐 `MASK_BEGIN(epoch=active_epoch)` 回归，修正 BEGIN 与 COMMIT 的 next-epoch 校验；OF4b2 定向 7/7、完整 oracle 34/34、compileall/diff-check 通过，等待最终独立复审。
- OF4b2 GREEN 已签核：独立审计 PASS，确认 epoch 回绕和错误消费拍语义；下一步为完整状态矩阵与 runtime idle/freeze 组合，不扩大到 RTL/Vivado。
- OF4b2b 完成：状态矩阵新增回归 9/9（基于已有实现直接通过），runtime 组合 5/5；实现 `bind_mask_port` 与双端 freeze 同步，完整 oracle 41/41。下一阶段 OF4c 为单时钟端口表和 RTL 设计审核材料。
- 2026-09-04 OF4c 设计审核稿：在 OF4b2b 合并后冻结单时钟同步复位、128-bit 命令/响应、sample/result 流、19/634-word 地址、逐拍优先级、错误背压和零副作用合同；尚未创建集成 RTL，未运行 Vivado。
- 2026-09-04 OF4d 设计稿：补充模型配置口的 634-word 顺序装载、非法 word 同索引重试、单槽响应背压、`MODEL_COMMIT` 原子发布与 reset-only reload 合同；仍未实现 RTL、未运行 Vivado。
- 2026-09-04 OF4e GREEN：`NpuEpochRuntime` 绑定 `ModelConfigPort`，模型 staging 非空时拒绝 freeze 切换；与既有 mask/runtime 组合共同通过 45/45。未创建 RTL，未运行 Vivado。
- 2026-09-04 OF4f：冻结单时钟同拍仲裁优先级，明确配置提交不得与样本首拍双重生效；后续 RTL 必须按该优先级实现。未运行 Vivado。
- 2026-09-04 OF4g GREEN：发现并修正已提交模型被误判为 staging 占用的问题；`committed` 允许冻结，`loading/complete` 仍拒绝。相关回归 47/47 通过，修正已合并至 `main@9f6d14b`。
- 2026-09-04 OF5 GREEN：新增模型端口、mask 端口和 runtime 的 hard reset；复位丢弃 staging/published/运行结果，恢复全开 mask、epoch=0、model_valid=0，未提交模型拒绝推理。相关回归 48/48 通过。
- 2026-09-04 OF6 签核：OF1-OF5 相关 Python oracle 回归 48/48、CI-Fast 8/8、compileall、diff-check 全通过；形成最终证据摘要。该签核不外推 RTL/Vivado/物理性能，下一步仅进入单时钟 RTL 设计审核。
- 2026-09-04 单时钟 RTL 设计审核稿：新增 `docs/planning/NPU_SINGLE_CLOCK_RTL_DESIGN_REVIEW_V1.md`，冻结四 lane 共享引擎、634-word/双 mask 存储边界、状态机、仲裁、复位/冻结和验证顺序；等待管理员审核，未创建 RTL、未运行 Vivado。
- 2026-09-04 设计审核前静态审计：新增 `NPU_SINGLE_CLOCK_RTL_DESIGN_AUDIT_V1.md`，确认 Python 合同与设计稿已对齐的 7 类内容，并列出 8 项逐拍接口/状态细节缺口；因此设计状态改为 `REVIEW_WITH_ACTIONS`，仍未创建 RTL、未运行 Vivado。
- 2026-09-04 裁定表：新增 `NPU_SINGLE_CLOCK_RTL_DECISION_SHEET_V1.md`，为 8 项缺口提供推荐接口、仲裁、`mask_valid`、`model_valid` 和验证门；全部标为管理员待批准，仍未创建 RTL、未运行 Vivado。
- 2026-09-04 provisional 合同：新增 `npu_single_clock_contract_provisional.json`，把 8 项建议转为机器可读字段，明确 `status=admin_review_required`、`rtl_allowed=false`、`vivado_allowed=false`；未改变冻结合同。
- 2026-09-04 RTL 裁定 V2：独立审计确认 V1 的 `model_epoch`、双 commit 竞争和 framing/idle 定义存在缺口；新增 `NPU_SINGLE_CLOCK_RTL_DECISION_SHEET_V2.md` 与 `npu_single_clock_contract_provisional_v2.json`，仍禁止 RTL/Vivado。
- 2026-09-04 管理员批准 RTL 裁定 V2 八项决策：V2 合同状态更新为 `approved_by_admin`，允许开始测试先行的单时钟 RTL 骨架；Vivado 仍须等待 Icarus/Python 功能门通过。
- 2026-09-04 单时钟 RTL 第一条垂直切片：新增 `npu_eneuron_single_clock_skeleton.sv`、`tb_npu_eneuron_single_clock_skeleton.sv`、`test_npu_single_clock_skeleton.py` 与端口字段表。Icarus 使用 `C:\\msys64\\ucrt64\\bin\\iverilog.exe`/`vvp.exe` 实际通过模型无效拒收、634-word 顺序提交、非法响应背压、配置优先样本、8-beat 输入和 10-beat 零结果输出；当前仍未接入真实 MAC、mask 双 bank 或 Vivado。
- 2026-09-04 CI 修正：PR #54 的 Linux 全仓回归因测试硬编码 Windows Icarus 路径失败；测试现为 Windows 优先固定 `C:\\msys64\\ucrt64\\bin\\iverilog.exe`/`vvp.exe`，非 Windows 回退 PATH，保留工具路径日志与同一协议断言。
- 2026-09-04 mask epoch 垂直切片：新增 19-word staging/published/首拍激活、`mask_valid`、结果 epoch 锁存、word18 保留位错误同索引重试和连续两样本验证；修复样本 beat 计数归零及错误响应 126→128 位字段错位。Icarus 两项切片测试通过，仍未接入真实 MAC 或 Vivado。
- 2026-09-04 控制垂直切片：新增 `MASK_ABORT`、`STATE_CLEAR`、`FREEZE_SET`、`infer_frozen` 与清除计数；Icarus 证明冻结仍可推理、配置/clear 零副作用拒绝、结果占用时 freeze 延迟至 idle。三项 RTL 切片测试通过，真实计算与 Vivado 仍未开始。
- 2026-09-04 管理员再次确认批准 V2 八项 RTL 裁定。PR #54 HEAD `8239063` 的快速检查成功，全仓回归查询时仍在运行；本地工作树仅有两个真实计算测试和用户临时 `np75_tmp_sparse_protocol.ys`，临时文件保持未跟踪。
- 2026-09-04 真实计算 RED tracer 已建立并复现：当前占位输出为 0，手算期望 logit0=137；下一步只实现 64×uint4 缓存、active mask、32 个隐藏值、10 个 logit 和四 lane 顺序计算，不提前扩展 DMA/网口/Vivado。
- 2026-09-04 只读统计发生两次命令构造错误：一次 JavaScript 模板误解析、一次把 `.nexus-map` 当文件读取；均未修改仓库，已改为安全的目录读取方式。
- 2026-09-04 真实计算最小 GREEN：`npu_eneuron_single_clock_skeleton.sv` 已加入输入缓存、active mask bank、四 lane 分组引擎、hidden/logit 缓存和 compute busy；手算 tracer 通过 137/-117，同时通过最后组 59、L1 bit79 关闭后 -1 和 busy ready/idle 断言。
- 2026-09-04 原有 skeleton/mask/control 三项协议测试已改用全零模型并全部通过；尚未执行完整仓库回归、随机 20×100 bit-exact 门或 Vivado。
- 2026-09-04 四项单时钟 RTL 测试联合 4/4、`compileall`、`git diff --check` 和 Icarus `-Wall -tnull` 均通过。Icarus 仅报告 `always_comb` sensitivity 扩大提示及受保护仿真 `$display` 的综合 warning，不影响本轮功能结论。
- 2026-09-04 完整仓库回归 `469/469 OK（1 skipped）`，耗时约 465 秒；运行期间被历史验证器刷新过的 `local_prune_rtl_results.json` 与 `np4b_signoff_summary.json` 已恢复到提交前内容，避免混入无关证据变更。
- 2026-09-04 首次直接调用 `yosys` 因 PowerShell PATH 不含工具而未执行；下一次使用 `C:\msys64\ucrt64\bin\yosys.exe` 明确路径，不运行 Vivado。
- 2026-09-04 bias/并发合同补充 RED：unsafe L0 bias 被错误接受；计算中 mask 配置因 ready 关闭导致 watchdog。bias 最小修复已先转绿；并发首次修复暴露 ready 对未呈现 opcode 的依赖，现改为 valid=0 乐观 ready、valid=1 分类仲裁。
- 2026-09-04 乐观 ready 会让忙态 `cmd_ready` 无请求时抬高，并被 freeze 逐拍测试正确拒绝；最终保持 RTL 的 opcode 分类 ready，改由并发测试 Host 先呈现 valid/payload 再等 ready，符合标准源端握手责任。
- 2026-09-04 提交前复核两项阻断已修复：模型 word 512..543/624..633 增加 signed bias 安全窗；mask begin/data/commit/abort 可在部分输入、计算或结果输出期间握手，active bank 仍只在下一样本首 beat 切换。
- 2026-09-04 定向验证覆盖 L0/L1 上下界外一点共四个非法 bias、错误背压与同索引重试；并发 mask 在样本 0x101 运行时发布但结果仍携带 epoch0，样本 0x102 才采用 epoch1。四项 RTL 回归 4/4、Yosys 过程检查返回 0。
- 2026-09-04 最终完整仓库回归再次通过 `469/469 OK（1 skipped）`，耗时约 546 秒；端口表已移除“结果零占位/真实计算待接入”的过时描述。历史 NP4B 自动刷新文件再次恢复，不纳入提交。
- 2026-09-04 提交前差异审查完成：独立复核无剩余阻断；用户 `np75_tmp_sparse_protocol.ys` 明确排除，历史 JSON 规范化后与索引无差异。
- 2026-09-04 启动 20×100 随机 bit-exact 门设计；计划每个 seed 独立编译/运行 Icarus，运行期发布下一 mask 并施加结果背压，避免只证明静态手算向量。
- 2026-09-04 随机门首轮在 Python mask 打包边界处失败，原因是 592 有效位与 608 位物理容器未区分；已修正为 word18 高 16 位零填充，尚未开始 DUT 运行。
- 2026-09-04 随机 seed0 首样本失败经层间诊断确认为 testbench 时钟采样竞态，DUT `logit_values[0..3]` 已与黄金完全相同；结果消费检查改为 negedge 预采样 + posedge 握手。
- 2026-09-04 PR #54 合并门复核：GitHub API 确认当前 HEAD `084f849` 的相关检查全部成功且 PR `OPEN / MERGEABLE / CLEAN`，但随机 testbench 仍未跟踪、未通过；因此暂不合并。
- 2026-09-04 修正随机门 TODO：将“随机文件已创建”和“20×100 已签核”拆为独立状态；首 beat 问题记录为 ready/valid 观察竞态，下一步先做两样本无背压消费者，不再盲调等待拍。
- 2026-09-04 已提交并推送文档/Nexus 状态修正：本地提交 `d6e3ce0`、`ccfbecc`，PR #54 HEAD 更新为 `ccfbecc`；新 CI 正在运行，随机门仍未签核。
- 2026-09-04 重写随机结果消费者后，完整固定 `20 seeds × 100 samples = 2000` 逐 beat 门通过；首 beat、末 beat、sample ID、mask epoch、结果背压和 mask 轮换均通过。随机 testbench 尚未提交，需先纳入 PR 再等待同一 HEAD CI。

## 2026-09-04 PR #54 合并后 TODO 收口

- PR #54 已合并为 `2a33f12`；随机 testbench 已进入主线，固定 `20×100` 随机逐 beat 门与 CI 证据闭环完成。
- 修正持久状态口径：当前不再等待 PR 合并或随机门 CI，下一硬门为当前 HEAD 的 Vivado 2024.1 OOC 物理签核。
- TODO 已拆分为“已完成的软件/RTL 仿真门”和“待完成的 OOC 物理门”，明确不把历史 NP6/NP7 结果代偿当前 RTL，也不把 OOC 外推为板级、网口、DMA、PS 或功耗结论。
- 用户未跟踪文件 `np75_tmp_sparse_protocol.ys` 继续保持原样，未修改、未暂存、未提交。
# 2026-09-04 P14 Vivado OOC 物理门收口

- 当前分支以 `39e41d4` 运行 Vivado 2024.1 OOC；RTL 与冻结基线 `origin/main@2a33f12` 相同，未纳入用户临时文件 `np75_tmp_sparse_protocol.ys`。
- 真实流程已完成：综合、优化、布局、布线、setup/hold 时序和 DRC 均执行成功，route errors=0、DRC errors=0。
- 资源：2672 LUT、1879 FF、0 BRAM36、0 BRAM18、0 DSP。setup：WNS -5.087 ns、TNS -421.539 ns、244 个失败端点；hold：WHS +0.098 ns、0 个失败端点。
- 结论：当前 RTL 具备完整 OOC 实现证据，但 100 MHz setup 门失败，状态更新为 `VIVADO_OOC_SETUP_FAIL / TIMING_REPAIR_REQUIRED`。不进入顶层、网口、DMA、PS 或板级功耗阶段。
- 已将 P14 活动 TODO 改为：提取关键路径 → 设计最小流水化/分拍 → 重跑 bit-exact 回归 → 重跑同器件同约束 Vivado OOC。失败结果保留，不用历史 NP6/NP7 报告代偿。

## 2026-09-04 时序修复 TODO 与审核稿

- 已从 `timing_impl.rpt` 完成最差路径分类：前 20 条均属于 `compute_group_index` 到 `hidden_values` 写回的同类长路径，最差 14.775 ns、23 级逻辑。
- 已审计现有 RTL，确认长链在 `COMPUTE_L0_GROUP_ACCUM` 内同时承担四 lane 乘加、INT32 累加、末组饱和和写回。
- 已新增 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V1.md`，提出 `FETCH→EXECUTE→COMMIT`、共用 `lane_sum_latched`、外部协议不变和 LUT-only 优先的 TR1-TR6 六项裁定。
- 已修正 `docs/planning/TODO.md`：关键路径分析和方案形成标记为完成，当前人工门改为 `TIMING_REPAIR_V1_REVIEW_REQUIRED`。
- 已同步 7 份 `.nexus-map` 人工摘要/机器概念文件：当前权威基线为 `origin/main@dc2452b`，并分别记录 RTL merge=`2a33f12`、OOC report head=`39e41d4`、evidence merge=`dc2452b`；JSON 解析与 diff-check 通过。
- 提交前轻量回归通过：`test_ci_fast_v1` 8/8、`test_artifact_layout` 1/1；确认文档/Nexus 变更继续走 fast gate，OOC manifest 仍被唯一归档和索引。
- 本轮未修改业务 RTL、未运行新的 Vivado，也未触碰用户文件 `np75_tmp_sparse_protocol.ys`。
- PR #56 首轮 HEAD `c1c774e` 的 GitHub run `33891809535` 与仓库外 webhook 同 SHA 均为 success；PR 为 `CLEAN / MERGEABLE`，但该结果只证明文档门通过，不代表 TR1-TR6 已批准。
- 独立反审计发现并修正 TR3 的关闭组矛盾，同时把 V1 失败后的升级改为按新最差路径选择 `WRITEBACK` 或 DSP；该修订需要新的 PR HEAD CI。
- PR #56 修订 HEAD `21be24b` 的 GitHub run `33893097155` 与 webhook 同 SHA 成功后已合并，当前 `main@2a0f2ce`。
- 已完成允许范围内的测试合同准备：新增三种确定性 mask 的组计数、精确计算延迟、白盒状态稳定、全关 bias 结果和 watchdog 预算；尚未创建 RED testbench、修改 RTL或运行 Vivado。
- 子代理复核了五个 testbench：确认无固定计算延迟依赖、V1 无需放宽 watchdog，并发现 L0 关闭末组的非零累加定向缺口；合同已扩为 C1-C4 四种样本补齐该证据。
- `.nexus-map` 已同步测试合同编号、周期、watchdog 与阻断状态；6 个摘要文件 diff-check 和 3 个 JSON 解析均通过，raw 探针保持历史 provenance。
- 测试合同提交前轻量回归通过：`test_ci_fast_v1` 8/8、`test_artifact_layout` 1/1；确认本切片继续只触发文档 fast gate，OOC manifest 索引未受影响。

## 2026-09-04 TR1-TR6 批准与 DSP V1 启动

- 管理员批准 TR1-TR6，并要求强制使用 DSP48E1；持续目标已从 blocked 恢复为 active。
- 已核对官方 DSP48E1 容量和 Vivado `USE_DSP="yes"` 推断规则；V1 固定为四条共享 signed 8×8 DSP lane，物理硬门为 `DSP=4`。
- 已创建实施分支 `codex/npu-timing-repair-dsp-v1-20260904`；用户文件 `np75_tmp_sparse_protocol.ys` 保持未跟踪。

## 2026-09-04 DSP 探针完成并进入 RED

- Vivado 2024.1 独立探针已完成，确认四个内部乘积信号逐个标注 `use_dsp="yes"` 是稳定得到 `DSP=4` 的最简写法；函数局部属性不可用。
- 已冻结实现边界：L0/L1 共享四条 signed 8×8 lane，`EXECUTE` 锁存组和，`COMMIT` 只消费 `lane_sum_latched`；外部协议和 INT32 数值合同不变。
- 当前开始扩展 C1-C4、精确周期和白盒状态合同；Vivado OOC 仍必须等功能与完整回归全部通过后执行。
- RED 已实测：旧版 C1-C4 数值/协议门 `1/1` 通过；三拍合同在 Icarus 展开阶段因 `dut.lane_sum_latched` 不存在失败；四个显式 DSP 乘积检查因实际 `0/4` 失败。失败均精确命中待实现结构，未出现无关功能回归。
- 首轮三拍 GREEN 在 C2 发现 active mask 为 589 而非 590。定位到 compute TB 的 `send_cmd` 在 `cmd_ready` 由非 mask payload 切换时于 negedge 采样存在 delta-cycle 竞态，可能让首个 mask data 重复接受并额外关闭 bit32。修正为 posedge 判定握手、negedge 撤销 valid；不修改 DUT 协议或期望组数。
- 修正 testbench 握手后，compute 专项 `3/3` 通过：旧功能 C1-C4 bit-exact、三拍状态/稳定性/精确周期、四个显式 DSP 乘积属性均 GREEN。实测周期与冻结合同一致：1860、1856、676、1858。
- RTL 已采用连续状态编号 `0..10`，L0/L1 共享四条 signed 8×8 lane；`lane_sum_latched` 仅在两层 EXECUTE 写入，COMMIT 消费锁存结果，关闭组继续在 FETCH 旁路。
- Vivado OOC Tcl 已增加双重 DSP 硬门：utilization 的 `DSP` 与实现网表 `REF_NAME=DSP48E1` cell 数都必须精确为 4；摘要新增 `EXPECTED_DSP`、`DSP48E1_COUNT`、`DSP_GATE`，并输出 cell/LOC 清单。对应静态门与 compute 专项合计 `4/4` 通过。
- 五项单时钟回归实际执行为 `8/8` 通过；固定随机门输出 `RANDOM_BIT_EXACT_PASS seeds=20 samples=2000`。模型、mask epoch、控制、C1-C4、结果 metadata/背压均未因三拍与 DSP lane 改动而回归。
- 完整仓库回归完成：`Ran 473 tests in 423.687s / OK (skipped=1)`；固定 NPU 随机门仍为 20 seeds、2000 samples，既有五组 RTL cosim seed 也全部通过。按冻结顺序，现已允许启动 Vivado 2024.1 OOC。
- 完整回归中的历史 NP4B verifier 会刷新两个受版本绑定的已跟踪摘要；已用精确小补丁恢复 `local_prune_rtl_results.json` 与 `np4b_signoff_summary.json` 到基线，避免把无关证据刷新纳入本切片。用户文件仍未触碰。
- OOC runner 的 `GIT_HEAD` 来自当前提交而非工作树内容；已决定先完成两路只读反审计并提交实现，再运行 Vivado，使物理报告能真实绑定修复后的 RTL/Tcl 哈希。
- RTL/Tcl 最终反审计未发现 blocker。测试反审计发现“仅总数可能漏过重复零权重组、模型地址未核对、C3 FETCH 为空真”三项 blocker；已补 592-bit FETCH/EXECUTE/COMMIT 访问图、每层计数、模型实际地址核对和关闭组逐拍旁路检查，强化后 compute 专项仍为 `4/4`。
- 最终源文件完整回归再次通过：`Ran 473 tests in 418.737s / OK (skipped=1)`，NPU 固定随机仍为 20 seeds / 2000 samples。回归再次触发的两份历史 NP4B 摘要刷新已精确恢复，不纳入实现提交。

## 2026-09-04 DSP V1 Vivado OOC 与 V2 停止点

- 实现提交 `5055073` 已使用 Vivado 2024.1、`xc7z020clg400-1`、100 MHz 约束完成 OOC 综合、布局布线、时序和 DRC。
- 强制 DSP 合同真实通过：`DSP=4`、`DSP48E1_COUNT=4`；资源为 2192 LUT、1904 FF、0 BRAM。
- hold、route 和 DRC 通过；setup 仍为 `WNS=-0.673 ns`、`TNS=-6.462 ns`、22 个失败端点，最终 `PHYSICAL_GATE=NOT_PROVEN`。
- 最差路径已从旧版写回长链转移为“组号动态选择激活值 → DSP48E1 → 四乘积求和 → lane_sum_latched”；另有约 -0.071 ns 的 logit 写使能路径。
- 已更新 OOC manifest 和报告哈希，并形成 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V2.md`。当前停在 TR7-TR12 管理员审核门，未继续修改 RTL。

## 2026-09-04 PR #58 发布反审计

- 两次提交已推送并创建 PR #58；初始 HEAD `3c91d68` 的分类与快速检查成功，全仓回归按预期执行，XPM/NP7 三项无关门跳过。
- 仓库外 webhook 已收到同一 SHA 的事件，但 `signature_verified=false`，因此只用作到达提示；GitHub API/checks 仍是合并权威来源。
- 独立发布审计确认提交边界、manifest 哈希、报告与 RTL 绑定无 blocker；独立 V2 审计发现三项文档 blocker：写回寄存器语义不唯一、只报告前 20 条却过度外推全部 22 个端点、持久计划遗留 V1 待执行状态。
- 已修正为共享 signed 32-bit `writeback_value_latched` 的唯一语义，明确前 20 条为 14 条 DSP/求和路径和 6 条写使能路径，并将 V1 执行链标记为“已执行但 setup 失败”。本轮仍未修改 RTL。
- 修订 HEAD `c7e1247` 的 Actions run `33907986001` 完成成功：全仓运行 473 项、CI 环境 3 项跳过，固定随机 `20×100` 通过，最终 `PR Gate` 成功；Webhook 收到同 SHA completed/success。
- 合并前 GitHub API 确认 `CLEAN / MERGEABLE`，两路独立审计无 blocker；PR #58 已于 2026-09-04 合并为 `main@999038f`。合并口径保持“DSP V1 功能/结构通过，100 MHz setup 仍失败，转入 V2 审核”。

## 2026-09-04 全部 22 个 setup 失败端点审计

- 使用现有 routed checkpoint 扩展输出最多 50 条时序路径，实际准确展开全部 22 个失败端点；没有重新综合、布局或布线。
- 独立提取结果为 14 个 `lane_sum_latched` 端点和 8 个 `logit_values` 写使能端点，修正此前冻结报告只能看到 14+6、剩余2个未知的证据缺口。
- 新增 `docs/verification/NPU_SINGLE_CLOCK_TIMING_ENDPOINT_AUDIT_V1.md`，记录 checkpoint/Tcl/报告 SHA-256、复现命令、完整端点表和证据边界；同步 V2 审核稿、TODO、持久状态与 Nexus。
- 独立发布审计逐项重算三个 SHA-256、22 个 destination/slack 和时序摘要，确认文档一致、原 manifest/冻结报告无 diff、当前状态未误写为 100 MHz 通过；结论无 blocker。
- 本轮仅补证和文档化，未修改 RTL、测试、约束或 OOC manifest；下一门仍为管理员批准 TR7-TR12。

## 2026-09-04 PR #60 端点审计收口

- 端点审计提交为 `c0f1bea`；PR #60 的 Actions run `33911646530` 完成成功，分类、Fast Python/diff check 与 PR Gate 均通过，无关重门按 CI-Fast V1 跳过。
- 仓库外 Webhook 收到同一 HEAD 的 `workflow_run completed/success`，`signature_verified=false`，继续只作为到达通知；GitHub API/Checks 为合并权威。
- PR #60 在 `CLEAN / MERGEABLE`、两路独立审计无 blocker 后合并为 `main@4fc4c71`。活动门正式收口为 TR7-TR12 管理员批准；未修改计算 RTL。

## 2026-09-04 V2 审核材料 KISS 收口

- 复核当前本地、`main` 与 `origin/main` 均为 `bef5979`；`local_prune_rtl_results.json` 的行尾/stat 异常和用户文件 `np75_tmp_sparse_protocol.ys` 均保持未暂存、未修改内容。
- 新增 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V2_IMPLEMENTATION_MAP.md`，把激活锁存、统一 WRITEBACK、物理末组语义、唯一数组写点、日志和白盒测试要求映射到 RTL。
- 修订 V2 审核稿：复用现有 signed 32-bit `mac_accumulator`，删除新增 `writeback_value_latched` 的计划，预计新增状态由约 64 bit 降为约 32 bit；四 DSP 硬门和每样本 42 拍代价不变。
- 修正 `NPU_PRUNING_TODO.md` 的历史漂移：NP4B 三项正式接入改为完成，NP7 六项改为完成，并明确 160,000 事务与 Vivado 2024.2 八配置 8/8 的证据边界。
- 现有子代理仅同步 `.nexus-map` 七个文件，记录 `main@bef5979`、DSP V1 失败边界、TR7-TR12 审批门和 accumulator 复用方案；Markdown diff check 与 JSON 解析通过。
- `git diff --check`、Nexus `concept_model.json` 解析和 `python -X utf8 -m unittest -v test_ci_fast_v1` 均通过，CI-Fast 为 8/8。
- 一次只读 watchdog 搜索包含不存在的 `tb_npu_eneuron_single_clock.sv`，`rg` 因该路径返回 1；已确认其他三个 testbench 的 9000/6000/5000 拍常量，后续改用文件枚举寻找 skeleton testbench。未产生文件修改。
- 独立只读反审计发现并修复一个文档 blocker：审核阶段允许写 V2 周期合同，但批准前禁止把周期常量落地到 testbench；同时将 `LOCAL_PRUNE_RTL_REPORT.md` 明确限定为 NP4A 历史基线。其余 accumulator、42 拍、C1-C4、watchdog、NP7 证据边界均无 blocker。
- 本轮未修改计算 RTL、testbench、周期常量或 Vivado manifest；独立反审计 blocker 已闭合，下一步是提交并创建仅文档 PR。
- 审核材料已提交为 `b6676b4`，推送到 `codex/timing-repair-v2-readiness-20260904` 并创建 PR #62；两个用户文件继续显式排除。等待最终 PR HEAD 的 GitHub Checks/API 结果。
- PR #62 最终 HEAD `a4832cc` 对应 Actions run `33915028445`：Classify、Fast Python/diff 和 PR Gate 成功，按 docs-only 分类跳过无关重门；GitHub API 确认 `CLEAN / MERGEABLE`。
- 仓库外 Webhook 健康检查返回 HTTP 200，并收到同一 SHA 的 `check_run completed/success`；因 `signature_verified=false` 只作触发提示。PR #62 已合并为 `main@e8dc947`。

## 2026-09-05 TR7-TR12 批准与 V2 实施启动

- 管理员批准 TR7-TR12，并明确继续强制且仅使用 4 个 DSP48E1；时序修复从审核门切换为 V2 实施阶段。
- 已更新 `WORKFLOW_STATE.md`、`docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V2.md`、实施地图、`docs/planning/TODO.md` 和 `task_plan.md`：状态为 `IMPLEMENTATION_APPROVED / RTL_IN_PROGRESS`，Vivado 仍必须等待功能门。
- 实施顺序冻结为：独立 V2 测试合同在旧 RTL 上精确 RED → TR7-TR9 最小 RTL → 定向/固定 `20×100`/全仓回归 → Vivado 2024.1 OOC。
- 当前工作树仍只保留用户已有的 `local_prune_rtl_results.json` 修改和 `np75_tmp_sparse_protocol.ys` 未跟踪文件；二者不修改、不暂存、不提交。
- V2 RED 已建立：旧 RTL 在 `TIMING_REPAIR_V2_CONTRACT` 下实际返回码为 1，首样本报告 `WRITEBACK count mismatch l0=0/32 l1=0/10`；结构门同时确认不存在四个激活锁存器、L0/L1 WRITEBACK 状态且数组存在多个写点。该失败符合预期，证明新合同确实能区分旧实现。
- 已完成 TR7-TR9 RTL 垂直切片：四个 FETCH 激活锁存器、EXECUTE 稳定操作数、L0/L1 独立 WRITEBACK 和单一数组写点均已落地；V2 计算合同、协议骨架、mask、control、随机 `20×100` 逐 beat 共 10 项专项全部通过。V1 旧合同现在只作为预期失败的历史反证，不再误报为当前周期合同。
- V2 白盒合同已补强为逐组核对：FETCH 锁存值必须匹配对应 input/hidden 数组，EXECUTE→COMMIT 期间四个激活锁存器保持不变；定向V2与历史V1反证均通过。
- 完整仓库回归已完成：`python -m unittest discover -q` 共 `475 tests`，`OK (skipped=1)`，耗时约 416.8 秒；固定随机门仍报告 `seeds=20 samples=2000`。功能门全部通过，下一步进入同器件 Vivado OOC。
## 2026-09-05 V2 实施与 OOC 签核完成

- TR7-TR12 已落实：FETCH 激活锁存、EXECUTE 稳定操作数、L0/L1 独立 WRITEBACK，继续复用四个 DSP48E1 和 `mac_accumulator`。
- 单时钟定向门、固定 `20×100=2000` 样本逐 beat 随机门和完整仓库回归通过：`475 tests / OK (skipped=1)`；C1/C2/C3/C4 为 `1902/1898/718/1900` 拍。
- Vivado 2024.1 OOC 绑定提交 `f744bff2bdde68e138a7b2b348ce103bec1ab469`，器件 `xc7z020clg400-1`、100 MHz：`2126 LUT / 1916 FF / 0 BRAM / 4 DSP48E1`。
- post-route 时序与实现硬门通过：`WNS=+0.060 ns / TNS=0 / WHS=+0.040 ns / THS=0`，setup/hold 失败端点均为 0，route/DRC errors 均为 0，`PHYSICAL_GATE=PASS`。
- manifest 已更新并与当前 RTL/报告 SHA-256 一致。PR #64 的 GitHub Actions run `33946568679` 全绿，并于 2026-09-05 合并为 `main@a53a040`。
- Webhook 当前掉线；该状态只影响本机到达提示，不影响 GitHub Checks/API 权威结果。OOC 仍不覆盖板级 I/O、DMA、PS、Ethernet、SAIF 活动、动态功耗或持续学习。
- 2026-09-05：PR #64 合并为 `main@a53a040`，PR #65 合并为 `main@618c1e4`，PR #66 合并为 `main@a1457bb`。V2 OOC 与 P15 顶层规划均已入库。
- 2026-09-05：P15-T0 形成端口与适配边界裁定稿，推荐方案 A（128-bit 命令/响应 + 独立 32-bit 样本/结果 FIFO，AXI 在 FIFO 外）。该文档只提出方案，不授权 T1 RTL；等待管理员批准。

## 2026-09-05 P15-T0 阻断审计补充

- 完成四流、ready/valid、复位、AXI 外置和现有核心字段的只读审计，并新增 `docs/planning/NPU_ZYNQ7020_TOPLEVEL_T0_AUDIT_V1.md`。
- 确认样本/结果完整 FIFO payload 分别为 64/96 bit；同时发现命令字段布局、V1/V2 framing、跨 FIFO fence、reset-busy 汇合、TLAST/TUSER 错误语义、FIFO 参数和目标器件七项尚未冻结。
- 现有随机 TB 仅覆盖串行样本/结果与 mask 操作，不能替代新四 FIFO 并发顺序验证。
- 未修改 RTL；T1 顶层实现仍被 `P15_T0_REVIEW_REQUIRED` 阻塞。

## 2026-09-05 PR #68 CI 调度结果

- PR #68（`ed4d55b`）的 `Classify changes` 成功，正确识别为文档变更并跳过无关重门。
- `Fast Python and diff check` 与最终 `PR Gate` 两次均在 runner 启动前失败；GitHub annotation 明确原因为账户近期付款失败或 spending limit 需要提高，`runner_id=0` 且无任何执行步骤。
- 已重跑失败 job，结果相同；该 CI 结果只能标记为 `NOT_RUN_BILLING_BLOCKED`，不能视为代码失败或通过。PR #68 暂不合并，等待计费/额度恢复后重新运行。
- 已新增 `docs/planning/NPU_ZYNQ7020_TOPLEVEL_T0_DECISION_ADDENDUM_V1.md`，将七项阻断转成 A1-A7 可逐项批准的建议；在管理员确认前仍不授权 T1 RTL。
- 已新增 `docs/planning/NPU_ZYNQ7020_TOPLEVEL_T0_TEST_CONTRACT_V1.md`，为 A1-A7 定义 T1/T2/T3 的正向、负向、CDC、资源和停止条件；仍未创建 RTL。

## 2026-09-05 P15-T0 附录二次复核与修订

- 只读复核确认 8 个新增阻断：fence 编码/响应未完整冻结、严格 TLAST 与流式丢弃矛盾、fence 前样本预填边界、命令完成层级、busy 对 valid 稳定性的影响、A1 错误优先级、32-bit epoch 原子 CDC、XPM 参数集合不一致。
- 已修订 A1-A6 建议：T1 TLAST 改为外层提示；明确 `SAMPLE_FENCE` 编码和单样本窗口；禁止 fence 前预填；busy 只禁止新握手；epoch 只经原子 FIFO/响应；补齐 XPM 参数和错误优先级。
- Nexus 二次复核摘要已由子代理更新；未修改 RTL，T1 仍被阻塞。

## 2026-09-05 fence 条件再校正

- 核对 skeleton 状态逻辑后，修正 A3 中过严的 `runtime_idle` 条件；改用 `sample_ready`、结果/响应空闲、wrapper 窗口和 staging 闭合条件，避免已发布 mask 等待首 beat 时死锁。
- 同步修订 T0 测试合同和 findings；仍未创建 RTL，等待管理员批准。

## 2026-09-06 P15-T0 当前审批门复核

- 再次核对 PR #68：管理员尚未回复 A1-A7，当前仍为 `P15_T0_REVIEW_REQUIRED / NO_RTL_AUTHORIZATION`，因此不创建 T1 顶层 RTL。
- 提交 `8cac035` 触发的 Actions run `33975784335` 是一次历史观测：Classify changes 与 PR Gate 在 runner 启动前因账户付款/额度问题失败，其余 job 被跳过；GitHub annotation 已确认原文，按 `NOT_RUN_BILLING_BLOCKED` 记录，不能当作代码失败或通过。
- 本机 webhook 恢复初检时 `/healthz` 已返回 HTTP 200，而 `latest.json` 尚停留在历史 PR #63；随后已由官方 ping 和真实 PR 推送完成全链路验收。
- 轻量本地验证通过：CI-Fast `8/8`、`git diff --check` 和 P15-T0 文档锚点检查；一次附加探针误把决策状态要求到测试合同，已确认是探针职责错误而非文档漂移。
- Nexus 审计发现 `.nexus-map/hotspots/git_forensics.md` 仍把已合并 PR #64 写成 OPEN，`concept_model.json` 的状态指针停在 PR #66；已修正为 PR #68 的提交绑定审计快照。
- PR #68 的 HEAD/run 不再被描述为自动更新的“当前值”：快照绑定 `55ec08e` 与 run `33976357259`；后续提交不会使该历史证据失真。
- 仓库外 webhook 已收到该 SHA 的 `workflow_run completed/failure`，与 GitHub API 的计费阻断结论一致；签名仍未验证，只作触发提示。
- 本地接收器原先由短命 `Start-Process` 间接拉起，会随宿主回收。现已注册 Windows 计划任务 `ENeuronWebhook`，直接托管 `C:\Python314\python.exe -u webhook_server.py`；任务状态持续为 `Running`，`/healthz` 返回 HTTP 200。
- 隧道侧随后定位为 `ChmlFrpc` 未运行，GitHub hook `last_response=502 connection_error`。用户恢复 ChmlFrpLauncher 后，本地与公网 `/healthz` 均为 HTTP 200。
- GitHub 官方 ping delivery `39fa1340-aa08-11f1-8930-aff79715b2ab` 和 `ee543f6e-aa08-11f1-84fd-d4849c4dec76` 均返回 HTTP 200；后者已写入 `latest.json`，hook `last_response` 恢复为 `200 active`。
- 清理了诊断阶段产生的重复 frpc：保留 ChmlFrpLauncher 管理的实例，停止额外计划任务实例；公网健康检查在单实例状态下继续通过。
- 恢复后的真实推送 HEAD `a409512629717845ddbaa42dd6addfb4fab563f7` 触发 run `34043097374`；webhook delivery `6ece08a0-aa09-11f1-944a-b2b2aad065d2` 收到同 SHA 的 `workflow_run completed/failure`，GitHub annotation 仍为账户付款/额度阻断，通知链与权威 API 结论一致。
- 随后提交 `c2523a9ab396013f9df7454314cdba4305f67050` 触发 run `34043377382`；GitHub API 显示 `Classify changes`、`PR Gate` 均 `steps=[]`，其余门跳过，状态继续为 `NOT_RUN_BILLING_BLOCKED`。webhook 收到该 run 的 requested/completed delivery（`2e16b130-aa0a-11f1-86ef-dd7a956d4ed9` / `3201ce10-aa0a-11f1-8238-2c657afd3f1d`）和本次 PR 评论 delivery `4be59cd0-aa0a-11f1-88f2-e2e0e3608dc3`，证明通知链仍然工作。
- 2026-09-07：完成 `docs/planning/NPU_ZYNQ7020_RESOURCE_CUT_REVIEW_V1.md`。本轮只做基于 RTL/Vivado 证据的方案审查，没有修改计算 RTL；当前工作树用户已有的 `local_prune_rtl_results.json`、`np4b_signoff_summary.json`、`np75_tmp_sparse_protocol.ys` 未纳入任何提交。
- 2026-09-07：管理员确认资源裁剪暂缓，等第一次完整端到端运行成功后再评估；当前优先完成 T1/T2/T3 功能、双时钟、Vivado OOC 和端到端证据。
- 2026-09-07：完成 T2 并发 epoch 原子性切片。`tb_npu_zynq7020_t2_variable_clocks.sv` 在三组非整数时钟/相位下验证 pending epoch=2 与当前样本计算重叠时不污染旧结果；下一 fence/样本才激活 epoch=2。`python -X utf8 tools/repro/verify_repository.py --t2` 返回 `REPRO_G0_MANIFEST_PASS` 与 `REPRO_G2_T2_VARIABLE_CLOCKS_PASS`。T2 全矩阵、T3、Vivado 和板级闭环仍未完成。
- 2026-09-07：将 T2 确定性时钟覆盖扩展到六组 `(7,2)/(9,1)/(4,3)/(5,0)/(11,4)/(3,1)`；统一入口仍返回 G0/G2 PASS。状态为扩展切片绿色，随机频率/相位全矩阵、FIFO scoreboard、T3、Vivado 和板级闭环仍未完成。
- 2026-09-07：T2 FIFO 压力矩阵按测试先行原则先加入复现合同测试；当前已故意 RED，因为 manifest 和 `verify_repository.py` 还没有新矩阵文件与 `--t2-fifo-matrix` 入口。下一步是实现隔离四 FIFO scoreboard，不修改生产 RTL。
- 2026-09-07：T2 FIFO 矩阵实现并通过 24/24 固定配置；T1、现有 T2 wrapper 六组切片和 19 项相关单测也通过。新文件为 `tb_xpm_fifo_async_matrix.sv`，统一入口为 `--t2-fifo-matrix`；当前状态是 FIFO 切片 GREEN，T2 wrapper 并发命令/多位置 reset、T3 和板级仍待完成。
- 2026-09-07：新增 `tb_npu_zynq7020_t2_interleave_reset.sv`，在4组代表性时钟配置下验证命令/sample 交错和三类 reset 注入；统一入口返回 `REPRO_G2_T2_INTERLEAVE_RESET_PASS`。与 FIFO 矩阵一样，这是本机 Icarus 切片，T2 全矩阵、T3、Vivado 和板级仍未完成。

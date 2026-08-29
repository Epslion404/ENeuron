# 进度记录

## 2026-08-29 NPU 局部剪枝 NP4B 规划

- 新增 `NPU_PRUNING_NP4B_TODO.md`，状态为 `REVIEW_REQUIRED`；本轮只规划和审计，未修改 RTL，未运行 Vivado。
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
- 固定 `local_prune_b0_vectors.json` 与 `local_prune_b0_results.json`，摘要绑定四个源文件 SHA-256；NP1 已达到软件黄金模型硬门。
- 下一步进入 NP2/NP3：三种神经元从同一稠密 checkpoint 分支 dense/random/S0-S3，先跑 B1 协议闭环，再设计有辨识力的多 seed B2。

## 2026-08-28 NPU 局部自动剪枝规划

- 新增 `NPU_PRUNING_TODO.md`，状态为 `REVIEW_REQUIRED`；本轮只规划，不修改已签核神经元 RTL。
- V1 主线冻结为待审核的四输入组 `2:4`：训练期本地评分生成结构掩码，推理期与活动掩码相交，并要求在 BRAM 读取与计算发射前生效。
- 评分先比较 S0 权重幅度、S1 单次资格迹、S2 资格迹累计和 S3 低成本组合；若 S3 没有明确优于 S0，按 KISS 删除额外神经评分逻辑。
- TODO 拆为 NP0-NP9，覆盖黄金模型、软件消融、剪枝微调、独立 RTL、协同/形式验证、Vivado、共享 lane 真跳算、可选恢复和系统签核。
- 当前 D2 图像稠密基线失败，明确禁止在稠密任务通过前用剪枝结果声称图像识别有效。
- 用户已批准 NP0 八项决策；规划状态改为 `APPROVED`。
- 执行范围扩展并冻结为三条独立实验线：ENeuron、Pulse-Mini-L、Pulse-Mini-L2。三者共享数据与验收合同，但不得用其中一个版本的成功代替另两个版本的结果。

## 2026-08-26 当前项目报告

- 新增 `PROJECT_REPORT.md`，统一汇总原始 Goal M1-M4、ENeuron/Host Bridge/Tile 架构、Pulse-Mini 系列、FPGA 资源与时序、验证证据和 8×8 数字识别 D0-D2。
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
- 已生成 `SIMULATION_COMPARISON_REPORT.md` 与 `comparison_simulation_results.json`，并完成 200 项 Python 回归、Pulse-Mini 单核 20000 事务、固定网络 272 命令、形式深度20证明。
- 统一比较已补齐第三方键名：`eneuron`、`pulse_mini` 和 `pulse_mini_l`；收敛、负对照、噪声、稀疏度、共同网络与原生网络协议均同时输出三者。
- 正式执行 `python compare_simulation.py --seeds 20 --rtl-cosim` 通过；报告明确区分黄金模型三方消融与默认 Pulse-Mini-L RTL 旁证，没有把局部教师训练写成纯全局 reward 能力。
- 报告新增“网络层优缺点”表，分别列出 ENeuron、Pulse-Mini 与 Pulse-Mini-L 在状态表达、复制/路由、稀疏事件和全局 reward 方面的取舍。

## 2026-08-13

- 启动 G4 能力边界调研；当前只形成可审核实验方案，不修改核心训练模型或 RTL。
- 审计确认现有训练仅有两个固定模板，所谓 noisy test 与训练模板同源；teacher sweep 也没有 20 个独立初始化。
- 确认历史 `network_sweep_results.json` 早于当前 `network_sim.py`，且未被 `verify_goal.py` 纳入门槛，不能作为当前签核结果。
- 冻结下一步为三任务只读探测、原始资料核对、统计门槛和硬件映射方案；用户审核后才进入正式实现。
- 主会话独立复跑 3 任务 x 3 模式 x 10 seeds，与子任务结果和数据集抽样 SHA-256 完全一致；未创建临时实验文件。
- 探测确认 Spatial teacher/hybrid 为 100%，Spatial reward 为 15%；Temporal 全部为 0%，XOR 仅 hybrid seed 9 命中 8/256，且失败主要表现为无输出 spike。
- 核对 e-prop 与 GEM 原始资料，形成 `g4_capability_validation_proposal.md` 审核稿；方案增加活动率校准、strict decoder、direct-weight 容量对照、当前 RTL/no-WTA 与 Python/WTA 分组，以及持续学习 ACC/BWT/FWT。
- 完成固定全 2 初态的 burst calibration 探测：`B=1` 无活动，`B=2` 三任务均达到 100% hidden/output activity，并与 `RtlReferenceNeuron` 的 300 样本 spike count 完全一致。
- 随机初始化探测确认继续增大 burst 不能保证救活所有 seed；V2 将 calibration 限定为固定初态编码正对照，各训练模式必须独立验收 activity/coverage。
- 完成任务/统计反例审查：旧 Temporal 首事件泄漏标签，label shuffle 可被全 abstain 伪通过，持续学习排列不是独立样本；已在 V2 中分别修正。
- 完成 Host Bridge/P5 反例审查：reward 可与 action 恢复二分类标签，hybrid 只能冻结隐藏权重，Host 无法读回完整内部学习状态；已冻结纯全局 reward、黑盒/白盒证据边界及逐 seed 权重装载合同。
- `g4_capability_validation_proposal.md` 已修订为 V2 审核稿；核心 Python 模型与所有 RTL 均未修改，当前等待用户批准五项冻结决策。
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
- 形成 `host_bridge_v1_proposal.md` 审核稿：128-bit 双流、两个 XPM async FIFO、episode/tick staging、单槽 snapshot 背压和 exactly-once 响应合同；尚未开始 RTL 实现。
- 完成 Host Bridge 第二轮只读反例审查，发现响应 opcode 截断、TRAIN EP_END 部分提交、hard reset 清权重、txn_id 无重传去重、ABORT 未冻结、tick 回绕、零 pending flush、组合权重读和 XPM reset-busy 等 10 项合同缺口。
- 修订 `host_bridge_v1_proposal.md`：改为同构 128-bit 响应；EP_END 先完整预检；明确 17-bit tick 尾态、无条件 ROUTE_FLUSH、两拍 WEIGHT_READ、破坏性 hard reset 与有序 ABORT；当前仍处于用户审核阶段，未开始 Host Bridge RTL。

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
- 增加 `cycle_transport.py` 有界 FIFO/背压周期模型和 `rtl_contract.md`。
- 周期协议测试覆盖同 tick 原子提交、一拍输出路由、输出时间戳、未排空 FIFO 拒绝新 episode、延迟 commit 快照；总测试数 22 项。
- 增加 `digital_lif_core.sv` 单神经元 RTL 参考核、`rtl_smoke.py` 和 `rtl_smoke_results.json`；静态接口检查通过，但本机无 HDL 编译/综合工具。
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
- 在 `host_bridge_v1_proposal.md` 增加七类实现任务依赖图和逐项权威验收证据表；当前仍未修改 Tile/Bridge RTL，等待用户批准五项架构决策。
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
- 新建 `g4_t3_execution_spec.md` 审核稿，明确 12 项二级冻结决策、当前 inference freeze FAIL、Temporal 容量风险、精确统计算法和批准后的测试先行任务顺序。
- `task_plan.md` 已增加 T3 二级审核 gate；在用户批准前不创建正式训练 runner。Goal 保持 active。
- 收齐 T3 三路独立反证；确认原审核稿存在公共置换统计失真、P3 comparator 未定义、canonical 枚举不可复现和按“权重实际改变”计 commit 可能不终止等批准阻断项。
- 修订 `g4_t3_execution_spec.md` 的 12 项二级合同：加入信用状态机、公共 permutation、GEM 公式、80-tick 计分边界、`python -I -S` worker、model-only bundle、RandomPlan、确定性 direct search、完整 Spatial/XOR canonical 数据合同、clone checkpoint 和 fresh-run commit 预算。
- 本轮只修改执行规格与计划记录；未修改训练实现、神经元方程或 RTL。V3 六项保持已批准，T3 十二项仍等待用户审核，Goal 保持 active。
- 本机补测 `python -I -S`：`sys.path` 只含 Python 标准库，直接执行旧 `network_sim.py` 无法导入同目录模块。已据此把 D5 worker 收紧为自包含单入口/受控 bootstrap，而不是降低隔离强度。
- T3 Host/no-replay 最终复核发现 D5 的原审计钩子合同会同时阻断合法 bundle 首次加载；本机 Python 3.14.2 审计事件探针复现 `compile` 与 `exec` 事件。已把规格改为哈希冻结 bootstrap + 单文件 bundle、一次性 `LOADING_VERIFIED_BUNDLE -> SEALED` 状态机，并保持 T3 十二项状态为 `REVIEW_REQUIRED`；未创建 runner、未修改神经元方程或 RTL。
- D5 修订后通过独立 Host/no-replay 终审；三路 T3 反证审计均无剩余 P0/P1。最终规格 SHA-256 为 `D88EBE4A64C34DAE42E5C16888E2F786F4C560D6BE0B90EBFF1F48749009DE0C`；D1-D12 计数、`g4_rng_v1` golden vector、D10 空间/golden skeleton 和 `compileall` 均通过，核心模型及 Temporal manifest 哈希未变化。当前等待用户明确批准 T3 十二项二级决策。
- 按用户要求回到原始 Goal 做证据复核，不继续扩写 T3。确认当前核心仍是寄存器化固定 4->2->2，Host `WEIGHT_WRITE` 可直接写权重，历史 Hybrid 还会直接重置输出权重；因此后续必须把“初始化权限”和“训练权限”分离，以命令轨迹证明训练期只经 eligibility snapshot + MOD_COMMIT 更新，并将共享 RAM/共享流水线 P6 提升为原始 Goal 的核心硬门。
- 新建 `original_goal_alignment_review.md` 审核稿：把原始 Goal 主线收敛为 C1 训练来源封印、C2 真实 RTL 任务闭环、C3/C4 共享 RAM 三参数点扩展、C5 板级 golden loop；T3/G4 的纯 reward、持续学习、no-replay 和复杂统计保留为后续研究，不再作为核心硬件前置门。审核前不修改 Host/RTL。
- 对对齐稿做第二次第一性原理修订：撤销把 `RUN_SEAL`、共享 RAM 三参数点和板级 bitstream 列为最小基石必要门槛。核心完成条件改为 M1-M4，其中唯一未完成的是现有 Host Bridge + Tile 上的任务级 RTL 训练/局部更新/冻结推理闭环及学习来源账本；扩展性、板级和 G4 均改为后续独立声明。

## 2026-08-14 原始 Goal M1-M4 批准后实施

- 用户明确批准原始 Goal M1-M4 四项决策；`original_goal_alignment_review.md` 状态改为 `APPROVED`。
- 实施顺序冻结为 C1 最小任务合同、C2 真实双时钟 RTL 任务闭环、C3 学习来源审计、C4 独立验收器。现有神经元方程和 RTL 默认保持不变，以 RED 测试决定是否需要最小修正。
- C1 只读复核完成：两轮、四次 `MOD_COMMIT` 是最小可靠训练量；训练前全 abstain，训练后 clean 与冻结扰动均正确，训练命令中 `WEIGHT_WRITE=0`。
- 新增 `m3_task.py`/`test_m3_task.py` 的 oracle 合同和 `m3_training_ledger.py`/`test_m3_training_ledger.py` 的命令哈希链审计；新增 `run_command_sequence()` 作为真实双时钟 RTL 连续命令入口。相关 4 项测试已通过。
- C2/C3 已通过：真实双时钟 RTL 连续执行 957 条命令，四次提交逐次读回全部 12 权重，20/20 扰动推理正确，训练期 `WEIGHT_WRITE=0`，最终权重冻结。
- 新增 `m3_acceptance.py` 与反例测试，冻结四次 eligibility/定点 delta/饱和向量、命令 SHA、响应账本 SHA 和 hash-chain 尾值；篡改快照、账本或任务结果均会失败。
- `verify_goal.py` 已加入 M3 独立硬门和 `m3_signoff_summary.txt` 生成，回归数量下限提高到 169；文档结论更新为原始 Goal M1-M4 已成立，扩展性、板级和通用 AI 仍未证明。
- 最终执行 `python verify_goal.py` 用时 294.8 秒并以退出码 0 完成：169/169 回归、Tile depth-24 BMC、Controller depth-20 BMC 与 6 类 witness、10000 个 Tile 压力事务、957 条 M3 双时钟闭环，以及 Tile/XPM/系统 Vivado 报告全部通过，打印 `GOAL_AUDIT_PASS: 原始 Goal M1-M4 最小硬件基石门槛通过`。

## 2026-08-19 ENeuron 1.0 与 Pulse-Mini

- 用户授权完全访问并明确要求先提交当前版本，再规划 Pulse-Mini 并形成 `TODO.md`。
- 恢复并复核既有计划文件、M1-M4 对齐稿、README、M3/T0 摘要和 Zynq-7020/Vivado 实测报告。
- 确认当前目录尚未初始化 Git；版本提交将从 `main` 分支的首个提交开始。
- 识别到发布可复现性约束：不能整目录忽略 Vivado 证据，必须保留 `verify_goal.py` 默认读取和新鲜度检查依赖的最小产物集合。
- 记录两次只读 PowerShell 命令写法错误，均未修改项目文件；已改用精确路径和中间变量完成审计。
- 独立发布审查定位 `rtl_contract.md` 的旧 Tile 资源/时序数字，已与当前 Vivado 冻结摘要统一，并在 README/发布说明中补充干净检出的 `--rerun-vivado` 要求。
- 发布前完整执行 `python verify_goal.py`，退出码 0：169/169 回归、Tile/Controller 有限 BMC、10000 个 Tile 事务、957 条 M3 命令和 Vivado 报告审计全部通过；`TODO.md` 此时仍不存在。
- 创建根提交 `499fc8a`：`release: ENeuron 1.0 verified hardware baseline`，并创建 annotated tag `v1.0`；标签后工作区干净且 `TODO.md` 不存在，满足先发布再规划的顺序。
- 标签完成后才创建 `TODO.md`：逐模块审计原始计数/分频方案，提出固定四输入 Pulse-Mini 的直接有符号事件累加、同步不应期、presence flag 本地历史、单槽反馈和 CONFIG/TRAIN/INFER 合同。
- Pulse-Mini 当前保持 `REVIEW_REQUIRED`；未创建 RTL。计划将资源估算、目标预算和未来 Vivado 实测严格分开，并以 260 LUT / 140 FF / 0 BRAM / 0 DSP / 100 MHz 为单核硬门。
- 独立 Pulse-Mini 语义审查发现 8 项阻断：跨样本分频与清除冲突、三态顺序歧义、signed 更新未定义、STDP 窗口未冻结、无 ID exactly-once 过强、分立事务接口不闭合、clear/freeze 污染和网络声明缺 P8 证据。
- 已按审查结果修订 `TODO.md`：主路径改为直接有符号事件累加；presence flag 替代三态累加；统一 cmd/rsp；明确 TICK 顺序、窗口端点、非法编码、clear 集合和单生产者 exactly-once；新增固定 `4->2->2` P8 网络闭环门。
- 修订后 `TODO.md` 仍保持 `REVIEW_REQUIRED`，未创建 Pulse-Mini RTL；下一步应由用户审核 P0 冻结决策。

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
- `TODO.md` 所有待办 checkbox 已完成，状态改为 `APPROVED` / `P7_CAPACITY_BOUNDARY_DOCUMENTED`；该状态明确表示 TODO 已执行完毕，同时保留 128 并行容量未证明这一负向结论。
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
- 生成 `comparison_simulation_results.json` 与 `SIMULATION_COMPARISON_REPORT.md`；完整196项回归、`compileall` 和 `git diff --check` 通过。

## 2026-08-19 Pulse-Mini-L2 实现与协议实验

- 用户批准 Pulse-Mini-L2，目标扩展为 L/L2 训练协议重设计、多类别/非二分类仿真和及时提交。
- 新增 `pulse_mini_l2_reference.py`：PN2 正/负证据计数、-2..+2 捕获幅度、现有 cmd/rsp 与泄放合同保持不变。
- 新增 `pulse_mini_l2_core.sv`、`tb_pulse_mini_l2*.sv`、`pulse_mini_l2_cosim.py`；L2 20 seeds x 1000 事务 bit-exact 通过。
- 新增 `formal_pulse_mini_l2.sv/.ys` 和 runner；Yosys 0.56 depth=20 SAT 无反例，修复了首版 harness 对内部数组层次引用的隐式线网警告。
- 新增 `pulse_mini_protocol_experiments.py`，冻结 local_teacher / global_scalar_reward 两类协议，覆盖三类通道、四类组合、三类时间顺序和四位多标签；生成 `pulse_mini_protocol_experiments.json` 与 `PULSE_MINI_L2_PROTOCOL_REPORT.md`。
- 实验结果：三类通道两版 local teacher 100%；四类组合 L 覆盖 0%，L2 覆盖约 66.9% 且覆盖样本准确率 100%；时间顺序两版均失败；多标签 L2 略优于 L1；全局标量奖励没有形成有效覆盖。
- 使用 Vivado 2024.1 XC7Z020 完成 L2 OOC routed：366 LUT / 91 FF / 0 BRAM / 0 DSP，WNS -4.690 ns、WHS +0.152 ns；相对 L1 增加 184 LUT、15 FF，真实 setup 失败，不能宣称 L2 100 MHz 通过。

## 2026-08-19 ENeuron 图像识别 D0

- 用户批准固定 8×8 灰度十分类、rank-order `K=16/T=16`、`64→16→4→10` 30 核拓扑、逐事件 replay 局部教师和能力/强门。
- 新增 `digit8x8.py`、`generate_digit8x8_fixture.py`、`digit8x8_fixture.json`、`digit8x8_manifest.json`、`test_digit8x8.py` 和 `DIGIT_RECOGNITION_D0.md`。
- fixture 共 1797 个样本，train/validation/test 为 1252/270/275；三路 split 互不相交且各含 10 类，fixture SHA-256 为 `6fa95b5b7493856708b0ab66814ef98a8f151efc2d9245ca10286860f9d21f5e`。
- D0 编码合同通过：每图恰好 16 个事件、同亮度按像素编号稳定打破平局、2×2 patch mask 可无损还原、编码不读取标签和全局随机状态。
- `python -m unittest -v test_digit8x8.py`：6/6 通过。D0 仍不包含数字识别准确率、ENeuron 网络训练或 RTL/Vivado 证据。

## 2026-08-19 ENeuron 图像识别 D1

- 新增 `digit8x8_experiment.py`、`digit8x8_d1_results.json`、`test_digit8x8_experiment.py` 和 `DIGIT_RECOGNITION_D1.md`。
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
- 正式 10 seed × 3 epoch 结果写入 `digit8x8_d2_results.json`；validation BAcc 均值 4.61%、coverage 均值 56.04%，0/10 seed 达到基础门；test BAcc 均值 4.74%、coverage 均值 52.18%。
- D2 结论：`D2_FAIL_GENERALIZATION`，部分 seed 为 `D2_FAIL_ACTIVITY`。失败原因是固定特征与当前十分类局部调制使输出权重趋同，严格 abstain 合同因此拒绝伪造分类结果。
- `DIGIT_RECOGNITION_D2.md` 已更新为完整失败报告；D3 暂停，下一步需单独批准最小的输出层信用分配修正。

## 2026-08-19 Pulse-Mini 规划收口

- 用户要求先提交当前版本，再评估原始方案并形成 Pulse-Mini 规划。
- 复核确认工作树原本已干净，`v1.0` 指向 ENeuron 1.0 提交 `499fc8a`，当前 Pulse-Mini 基线为 `64aff70`；未制造空提交。
- 将原始计数/分频核 `183 LUT / 85 FF / WNS -1.605 ns`、Pulse-Mini-L `182 LUT / 76 FF / WNS +0.463 ns`、L2 `366 LUT / 91 FF / WNS -4.690 ns` 和阵列 32/64/128 核边界写入 `TODO.md`。
- 新增 P9-P13：数字识别软件门、输入扇入与共享存储、L2 时序修复、阵列系统化、板级与持续学习边界。
- `python -m unittest discover -v`：208/208 通过；`git diff --check`：通过。

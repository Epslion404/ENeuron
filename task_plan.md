# 单神经元硬件基石模拟计划

## 目标

在本项目中用本机 Python 模拟并比较几种单神经元候选，平衡硬件复杂度与“可构建 AI 自训练和推理”的能力，最终确定推荐的最小可塑神经元设计。

## 阶段

- [x] 检查项目现状与约束
- [x] 实现基线 IF、二因子 STDP、三因子可塑 LIF
- [x] 运行同一脉冲任务并比较训练/推理结果
- [x] 计算状态位数与近似事件操作数
- [x] 形成推荐规格、取舍和后续 RTL 分解

## 网络阶段

- [x] 实现 4->2->2 两层数字事件网络
- [x] 隐藏到输出增加固定 1 tick 路由
- [x] 定义片外目标/奖励和可寻址 modulator 协议
- [x] 增加 `commit_id` 与 eligibility 快照
- [x] 完成 20 seeds 目标调制/全局奖励对照实验
- [x] 实现固定 4->2->2 RTL，并与 Python tile oracle 逐事务 bit-exact
- [x] 增加 WTA/侧向抑制后重新验证 reward-only 模式

## 验收标准

- Python 脚本可直接运行，不依赖第三方包
- 训练模式能改变权重，推理模式不会改变权重
- 推荐设计能区分训练脉冲模式与对照模式
- 能输出候选设计的能力、状态位数和事件操作数
- 所有结论都对应可复现实验输出

## NPU 局部剪枝 NP4/NP5 实施阶段（2026-08-29）

- [x] 用户批准 NP4 V1 六项决定：隐藏/输出统一严格 `2:4`、gain=`1/2/1`、一次原子提交、无 detector gate、只走既有训练恢复、读取/发射前形成 `issue_mask`
- [x] 冻结独立控制器的命令、端口、拒绝规则和逐周期合同
- [x] 测试先行实现 `local_prune_gate_2of4.sv`，不侵入已签核神经元核心
- [x] 实现 ENeuron、Pulse-Mini-L、Pulse-Mini-L2 的固定 gain 适配边界
- [x] 实现隐藏层/输出层统一门控接口和互不重叠的结构节省计数
- [x] 完成三模型共 60000 个混合事务的 Python/Icarus 逐事务协同仿真
- [x] 完成原子提交、INFER 冻结、非法命令无副作用、有限形式和负向反例检查
- [x] 实现 ENeuron snapshot evidence 与 Pulse FEEDBACK evidence 的正式 wrapper
- [x] 建立真正四输入的输出 `2:4` 分组并完成三模型端到端集成协同仿真
- [ ] NP4/NP5 通过后再提请审核是否进入 NP6 Vivado 物理成本

## NPU 局部剪枝 NP4B 规划阶段（2026-08-29）

- [x] 复核 NP4A/NP5 公共控制器签核范围和现有 `4→2→2` 输出扇入限制
- [x] 只读审计 ENeuron committed snapshot 与 MOD 消费时序
- [x] 只读审计 Pulse-Mini-L/L2 FEEDBACK 接受沿证据清理与响应时序
- [x] 冻结 `4→8→2` 两层严格 `2:4` 测试拓扑、固定一拍路由和 10-gate all-done barrier
- [x] 形成 `docs/planning/NPU_PRUNING_NP4B_TODO.md`，列明八项待批准决定、TDD 顺序、负向控制和停止条件
- [x] 用户批准 NP4B 八项实现决定
- [x] 按 NP4B1→NP4B6 测试先行实施并完成；未运行 NP6 Vivado

### NP4B 当前执行顺序

- [x] NP4B1：ENeuron committed snapshot 端口、量化与原子 MOD/OBSERVE wrapper
- [x] NP4B2：Pulse-Mini-L/L2 共享 bridge 与两个薄 wrapper
- [x] NP4B3：公共 `4→8→2` 调度、固定一拍路由、三模型十 wrapper 接线和 10-gate 原子屏障
- [x] NP4B4：ENeuron、Pulse-L、Pulse-L2 分别完成 20×1000 端到端协同事务
- [x] NP4B5：负向实现、Pulse/ENeuron wrapper 与网络 barrier 非空形式检查全部通过
- [x] NP4B6：359 项全仓回归、机器摘要和文档签核完成；NP6 二次审批待用户决定

### NP4B 当前细粒度 TODO

- [x] 校准 Pulse-L `1×64` tracer，不放宽任何公开状态比较
- [x] 增加并校准 Pulse-L2 `1×64` tracer
- [x] Pulse-L 独立完成 20000 条正式事务并提交
- [x] Pulse-L2 独立完成 20000 条正式事务并提交
- [x] 提交并复验 Pulse-L wrapper depth=32 非空形式证据
- [x] 完成 Pulse-L2 wrapper exactly-once 非空形式证据
- [x] 完成 ENeuron MOD/OBSERVE 原子接受非空形式证据并提交为 `c811bcf`
- [x] 完成公共十参与者 commit/clear barrier 抽象证明与真实顶层绑定
- [x] 三模型各自重跑 20000 条、全仓 359 项、编译/lint/formal 全通过
- [x] 生成 87 文件 SHA-256 机器摘要并停在 `NP6_REVIEW_REQUIRED`，未运行 Vivado

### 2026-08-29 当前续跑批次（执行中）

- [x] P0：独立签入已完成的 Pulse-L/L2 wrapper proof/reach、正式日志、非空 witness 与 verifier；排除 cex/tmp 产物
- [x] P1：ENeuron wrapper 同拍 MOD/OBSERVE 内部握手证明、公开事务结果证明和非零成功 witness
- [x] P2：真实 N=10 barrier 小状态证明、公共 gate exact-two 组合绑定、三个真实顶层 runtime 阻塞验证
- [x] P3：INFER 控制级形式检查、真实 RTL mutation 负向控制和 P4 三模型共 60,000 条完整随机冻结均通过
- [x] P4：源码冻结后重跑三模型各 20000、全部 formal runner/verifier、最终 359 项全仓、compileall/8 个 iverilog 目标/diff-check
- [x] P5：fail-closed 总摘要、精确 SHA-256 集合和最终文档签核完成；停在 `NP6_REVIEW_REQUIRED`

当前阶段已完成。唯一剩余人工门是用户再次批准 NP6；批准前禁止调用 Vivado。

批准后唯一执行主链：P1 独立入库 → 固定 seed `101..120/201..220/301..320` → 三模型各 20,000 条 → 全部形式 runner/verifier → 全仓回归与编译 → fail-closed 摘要 → 文档签核。任何硬门失败均停在当前阶段，不运行 Vivado。

### NP4B 实施错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| P5 总 verifier 首次调用公共 gate verifier 的不存在 `main()` 接口 | 1 | gate 模块公开 `verify()`；只修正调用接口，因 verifier 自身被摘要哈希绑定，随后重新生成摘要并重跑全部 P5 测试 |
| P4.4 首轮全仓 356 项中 `test_source_hashes_are_current` 发现 gate 形式文件哈希索引陈旧 | 2 | 首轮定位 reach 脚本后，定向测试继续捕获 runner 哈希；改为枚举比较全部 11 个绑定文件，确认只剩 runner 一项后统一修正，再重跑精确键集合测试和完整 356 项 |
| P1.7 复验直接调用 `iverilog` 时当前 PowerShell `PATH` 找不到命令 | 1 | 不重复同一调用；定位并使用 `C:\msys64\ucrt64\bin\iverilog.exe`，`-Wall -tnull` 编译通过 |
| NP4B 最终 TODO 首次使用跨四文件整包补丁时，`task_plan.md` 上下文不匹配 | 1 | 补丁工具原子拒绝且未产生部分修改；改为逐文件小补丁并按当前精确行更新 |
| `hardware-design-flow` 按技能清单中的 `.agents` 路径不存在 | 1 | 从同一清单给出的 `.codex/skills/hardware-design-flow` 实际路径完整读取，不跳过技能 |
| PowerShell 下 `rg ... *.py` 把通配符作为非法 Windows 路径 | 1 | 后续先用 `rg --files -g '*.py'` 或直接指定文件，不重复该写法 |
| Pulse wrapper 自动 clear 定向测试首次在 `PRUNE_COMMIT` ready 上超时 | 1 | 修正 bridge 的 sideband 接受/响应槽次序；L/L2 的自动 clear 与网络管理 clear 共四种实例全部通过 |
| 把 `pulse_mini_cosim.py`/`pulse_mini_l2_cosim.py` 误写成 unittest 模块名 | 1 | 不重复错误调用；改为直接执行两个脚本，分别通过 20 seeds × 1000 事务 |
| Pulse audit 端口补丁后旧 `.*` testbench 缺少新信号，且行为 TB 模板替换未匹配新增 audit 代码 | 1 | 保留 5 项 RED；补全所有公开 testbench 声明，并把公共声明模板与 `initial` 行为体拆开，禁止依赖脆弱字符串替换 |
| Pulse 随机 tracer 第 10 笔仅事务号出现 `actual=16 / expected=10` | 1 | RTL `$display` 的事务号为十进制，解析器误按十六进制读取；只修首字段为十进制，其余状态仍按十六进制比较 |
| Pulse-L `1×1000` 在首个 INFER flush 出现 output0 leak timer 少推进一拍 | 1 | flush testbench 遗留上一笔 `output_train_post`，使 output0 在 INFER 返回 `BAD_MODE`，且旧 task 漏检状态；flush 现显式清训练输入并检查状态/背压 |
| 新增 Pulse 长事务不变量检查时报 `NameError: Mode` | 1 | 显式从既有 `pulse_mini_reference` 导入冻结枚举，不复制模式数值 |
| 同一新增检查继续报 `NameError: N_NEURONS` | 1 | 从独立网络 oracle 导入唯一拓扑常量，避免在 cosim 重复定义十核规模 |
| Pulse-L wrapper 初版形式 harness 只显式证明 OBSERVE 计数 exactly-once | 1 | 补充 utility 更新完成、失败零观察和响应背压期间 utility 稳定断言，再重新生成正式证明与 witness |
| 首次追加 P0→P5 规划时补丁上下文与 `task_plan.md` 当前行不一致 | 1 | 补丁工具原子拒绝且未产生部分修改；改为逐文件小补丁并使用当前精确上下文 |
| 正式 Yosys `.log` 纳入普通 `git diff --check` 时报告 ASCII 横幅行尾空格 | 1 | 不清洗原始工具证据；源码/脚本/文档独立执行 diff-check，日志由固定文件名和 SHA-256 保真 |
| P2 barrier 首版断言要求上一拍十路 clear response 同时为高 | 1 | 真实屏障允许错拍并用 sticky seen 汇合；断言改为检查小状态参与者累计 `clear_replied==10'h3ff`，DUT 不改 |
| P2 reach 脚本无法解析 harness 层次信号 `reached_success` | 1 | 正在改用正确转义/选择方式；保持成功 witness 需覆盖错拍、背压与解除阻塞的要求，不放宽性质 |
| 恢复执行时误调用不存在的 `functions.wait` cell | 1 | 该调用立即失败且未改状态；后续只对真实 session 使用 `write_stdin`，代理等待使用 `collaboration.wait_agent` |
| P1 并行验证中的临时 VVP 创建/删除 PowerShell 命令被进程策略拒绝 | 1 | 未执行到 RTL 检查；改用 Icarus `-tnull` 无输出编译，避免临时文件和复杂 shell 转义 |

## Goal 证明审计阶段

- [x] 重跑完整 Python 回归并记录失败项
- [x] 将算法、RTL、形式验证、物理实现和任务能力分层
- [x] 明确区分学习基石、网络原型、板级系统和通用自训练
- [x] 修正并冻结 RTL 与黄金模型的事务语义
- [x] 使用真实 HDL 工具完成编译、仿真、综合签核和 24 拍 Tile 协议 BMC
- [ ] 用多任务、多种子和留出集验证“自训练与推理”能力边界

## G4 能力边界调研阶段（2026-08-13）

- [x] 审计现有训练数据、随机种子、留出集和信用分配证据
- [x] 复现空间、时间顺序和 XOR 三类任务的只读能力探测
- [x] 形成数据拆分、负对照、统计门槛、持续学习指标和硬件映射 V1 审核稿
- [x] 完成 burst calibration 探测和任务/统计/Host Bridge 反例审查
- [x] 将 `docs/design/g4_capability_validation_proposal.md` 修订为 V2 审核稿
- [x] 对 V2 做独立 Temporal、Host 权限、P5 和 Goal 扩展性反证审计
- [x] 将审核稿修订为 V3：四阶 Temporal motif、no-replay P4、双层 P5、P6 扩展性
- [x] 用户审核 V3 的六项冻结决策
- [x] 用户审核后拆分正式 Python、RTL 和验证任务

## V3 批准后实施阶段（2026-08-13）

- [x] T0：独立 Tile 报告硬门、机器摘要、新鲜度检查与文档同步
- [x] T1：冻结 G4 seed、hash、decoder、Temporal、split 和推理状态测试合同
- [x] T2：实现 `g4_benchmark.py` 与可复现 manifest
- [x] 重跑 T0、G4 新测试、`compileall` 和既有完整回归
- [x] T3 前置：完成 Tile/Host/容量只读审计并形成 `docs/design/g4_t3_execution_spec.md` 审核稿
- [x] 收齐三路独立反证并修订 T3 审核稿：公共置换、RandomPlan、80-tick 计分、no-replay、canonical 数据、确定性搜索、checkpoint 与 commit fresh-run
- [ ] 用户审核 T3 的 12 项二级冻结决策
- [ ] T3：在冻结 benchmark 上实现训练策略与 P0-P4 能力门槛
- [ ] P5：完成接口等价 FIFO cohort 与真实 XPM cohort 的隔离验收
- [ ] P6：冻结 Host 协议 V2，并实现共享 RAM 可扩展架构验收

## 原始 Goal 对齐复核（2026-08-13）

### 2026-09-03 I1-I6 Python oracle 执行状态

- [x] 建立 `64→32→10` INT8 MLP 参考模型与四权重组门控
- [x] 通过旁路全开、全关门控和隐藏层饱和边界测试
- [ ] 补齐 epoch 原子切换、背压/清除、推理冻结和非法索引测试
- [ ] 冻结 oracle 后实现集成 RTL

### 2026-09-03 CI-Fast V1

- [x] 管理员批准路径分类、定向专项门和固定 `PR Gate`
- [x] 抽取可测试的 `tools/ci/classify_changes.py`
- [x] 增加分类矩阵单测并通过本地验证
- [x] 更新 `docs/CI_PR_GATE.md` 的分支保护配置说明
- [x] 推送 PR #25 并以 GitHub/Webhook 终态验证 workflow 自身全量路径（run `33778976730`，merge `c46320e`）
- [ ] 以独立文档 PR 验证轻量路径；以 NPU/NP7 改动 PR 验证各专项路径
- [ ] 若仓库套餐允许，启用唯一 required check `PR Gate`；当前 API 返回私有仓库套餐 403

#### CI-Fast V1 错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| 整文件删除/新增补丁命中同一路径被 `apply_patch` 拒绝 | 1 | 改为先删除、再新增两个原子补丁；未产生部分文件 |
| 跨文档补丁使用错误的步骤编号上下文而被原子拒绝 | 1 | 读取当前精确行后拆成小补丁；未产生部分修改 |
| CI-Fast 首轮 Windows 门固定路径检查失败 | 1 | `update: false` 不保证 action 输出树位于固定路径；恢复既有探测/联接/复制兜底，并保留专项门按需触发 |

- [x] 从当前 RTL、Host 协议和验证产物重建“数字神经元/神经网络硬件基石”的实际证据
- [x] 区分固定 4->2->2 原型、训练真实性、可扩展架构和板级闭环，不沿用宽泛总称
- [x] 形成并反审计 `docs/design/original_goal_alignment_review.md`，把板级部署、共享 RAM 大规模化和 G4 研究从最小基石必要条件中移出
- [x] 用户批准原始 Goal M1-M4 四项决策
- [x] C1：冻结最小任务、初态、训练顺序、严格解码和命令账本合同
- [x] C2：真实 Host Bridge + Tile 双时钟 RTL 完成训练、权重提交、读回和冻结推理
- [x] C3：证明初始化后无成功 `WEIGHT_WRITE`，逐次核对本地 eligibility 权重更新
- [x] C4：将 M3 结果纳入独立验收器并更新 M1-M4 结论

### 复核后的主线约束

- T3 的统计/no-replay 合同只用于排除伪学习，不得继续扩张为项目主产物。
- `WEIGHT_WRITE` 可用于初始化、checkpoint 恢复和诊断；正式训练证据必须证明训练区间权重变化只来自 `snapshot + MOD_COMMIT`，不要求新增恶意 Host 防护协议。
- 固定 4->2->2 Tile 足以证明最小单元可组成小网络，但不能外推实用规模资源；共享 RAM 扩展性作为后续独立声明。
- 原始 Goal 的 M3 缺口已由同一真实 RTL run 闭合；P6、板级和 G4 仍是后续独立声明。

### V3 已冻结决策

- 当前 RTL 主结论限定 no-WTA；Hybrid 只冻结隐藏权重
- Temporal 使用低阶统计严格配平的四阶 motif
- P3 只接受四核相同的纯全局 reward；固定反馈单列 feedback-alignment
- P4 使用 task-aware、no-replay，并单列 joint-training 上限
- P5 分为接口等价 FIFO 完整 cohort 和真实 XPM 短 cohort，隔离 golden-vector/scoreboard
- P6 新建可寻址 Host 协议 V2 和共享 RAM 扩展架构

### 本阶段约束

- 审核前不修改 `network_sim.py` 的学习规则、核心参数或任何 RTL
- 探测失败属于有效边界证据，不以降低门槛或泄漏测试集方式制造通过
- P0/P1 通过只证明固定 4->2->2 网络在限定任务上的监督训练与留出泛化，不等于 G4 完成
- reward-only、持续学习、扩展性和 RTL 任务闭环分别验收，禁止用宏平均或其他模式代偿
- `reward_global_no_wta` 才能作为纯 reward-only 主结论；可寻址固定反馈只能称 feedback-alignment
- P5 的 Host 黑盒可见状态与 testbench 白盒内部状态分开验收，不虚构 wire-level 可观测性
- V3 三任务统一改为 64 tick；旧 48-tick `B=2` 结果仅作探索记录，正式 P0b 必须重跑
- P0-P5 只签固定 4->2->2；可扩展基石声明由 P6 共享 RAM 多参数点独立验收
- Host Bridge V1 地址和四路 modulator 均为固定 4->2->2；P6 必须先冻结可寻址流式协议 V2
- 所有能力结论按训练模式和 P0-P6 门槛绑定；禁止 Teacher、Hybrid、reward、Python 和 RTL 证据互相代偿
- V3 Temporal 已完成活动正对照与有限容量预判；正式实现仍须重跑 manifest 化 P0b 和预注册 direct-weight 对照
- T3 正式编码前必须批准 `docs/design/g4_t3_execution_spec.md`；当前全调用逐字段等价已被定向探针判定为 FAIL，待以 EP_START 白名单复位 + 推理区间冻结的精确合同验收
- V3 六项决策已经批准；T3 十二项二级决策仍为 `REVIEW_REQUIRED`，两级批准状态不得混淆

## 多周期 RTL 阶段（2026-08-12）

- [x] 编译当前 `digital_lif_engine.sv`，确认 SystemVerilog 语法可被 Icarus 接受
- [x] 建立事务级 Python/Icarus 协同仿真，只在 `done` 后比较完整架构状态
- [x] 修正 TICK、SNAPSHOT、MOD、CSR、STATE_CLEAR 与推理冻结的事务语义
- [x] 增加 busy 隔离、单次接受/单次完成、spike 有效周期和地址边界断言
- [x] 使用 Vivado 2024.1 完成多周期核 post-route 100 MHz 时序、DRC 与资源对照
- [x] 在单核通过后实现 4->2->2 tile RTL 与 all-done barrier

### 本阶段验收门槛

- 至少 5 个随机 seed、每个不少于 100 个混合事务，与 `RtlReferenceNeuron` 逐事务一致
- `ready` 仅在空闲态有效；busy 期间命令不得改变当前事务；每次接受恰好产生一次 `done`
- `spike` 只在 TICK 的 `done` 周期有效；INFER 冻结全部学习状态
- Vivado post-route：`WNS >= 0`、`TNS = 0`、setup/hold 零失败、DRC 零 error/critical warning

## 4->2->2 Tile RTL 阶段

- [x] 同时启动 2 个隐藏核和 2 个输出核，并用 sticky done mask 实现 all-done barrier
- [x] 输出层在 tick t 读取旧 `pending_hidden`，隐藏层 tick t 结果写入下一 pending，保持一逻辑 tick 路由
- [x] TICK、STATE_CLEAR、SNAPSHOT 和按 neuron 寻址 MOD 事务在 tile 层串行化
- [x] 输出 `done` 时原子给出 `output_spikes`，busy 期间拒绝第二事务
- [x] 与四个 `RtlReferenceNeuron` 组成的独立 Python tile oracle 做扩大随机事务协同仿真（20 seeds × 500 事务通过）
- [x] 使用 Vivado 2024.1 完成 tile 的 post-route 100 MHz 时序和资源报告

## Host Bridge / G3 前端阶段（2026-08-13）

- [x] 审计 Python 事件传输模型与 Tile RTL 的接口差距
- [x] 形成传输无关的 128-bit 双流、CDC/FIFO 和 `ROUTE_FLUSH` V1 审核稿
- [x] 完成第二轮反例审查并修订响应、EP_END、reset、ABORT、计数边界和 XPM 握手合同
- [x] 完成第三轮终审，收敛 STATUS、response_accept、错误优先级、flush spike、modulator 和 sticky fatal 语义
- [x] 形成七类实现任务依赖图与逐项权威验收证据表
- [x] `docs/design/host_bridge_v1_proposal.md` 的冻结决策已落实到 RTL、oracle、测试和报告
- [x] RTL、参考模型、协同仿真、formal/CDC 和 Vivado 任务已完成
- [x] 实现并签核固定 4->2->2 Host Bridge 数字前端；具体板卡适配仍需目标板和物理链路信息

### Host Bridge V1 实现任务

- [x] T1：Tile 增加 `ROUTE_FLUSH`、只读 commit 元数据导出、定向回归、24 拍 BMC 与 Vivado OOC
- [x] T2：冻结 Python Host Bridge oracle 与协议首错链；32 项定向/压力测试通过
- [x] T3：完成 controller 与真实四核 Tile 的单时钟逐命令协同仿真；20 seeds x 1000 命令 bit-exact
- [x] T4：实现两个 depth-16 `xpm_fifo_async` wrapper 与同步 reset/reset-busy 合同；Icarus 和真实 XPM xsim/综合通过
- [x] T5：完成非整数双时钟、随机相位、producer/consumer 背压端到端仿真；20 seeds x 2000 flit 通过
- [x] T6：完成 controller 抽象 formal 与系统 Vivado `report_cdc`；所有 XPM 外部 CDC 硬门槛通过
- [x] T7：完成 Bridge + XPM 双时钟 Vivado OOC 资源、时序、route 与 DRC 签核
- [x] 汇总 G3a 数字前端证据并更新 `verify_goal.py`、`docs/verification/goal_audit.md` 和项目文档

### 本阶段错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| 当前 PowerShell `PATH` 中找不到 `yosys` | 1 | 不重复相同命令；改为定位既有 Yosys 绝对路径，Vivado 结构/实现检查不受此环境问题阻塞 |
| 独立子代理协议审查连接中断 | 1 | 未产生设计结论；由主会话继续交叉审查并依赖可复现测试/工具报告 |
| PowerShell 直接调用 `vivado.bat` 报 `BadExpression`，Vivado 未启动 | 1 | 改为通过 `%ComSpec% /d /c` 执行同一个官方 wrapper |
| `cmd.exe` 将分离传入的 `-mode` 误解析为新命令，Vivado 未启动 | 2 | 先用 `"vivado.bat" -version` 验证 wrapper，再把完整 Vivado 命令作为 `/d /s /c` 后的单一字符串传入 |
| Windows PowerShell 将无 BOM UTF-8 中文注释与下一行 `$vivado` 赋值合并解析，路径变量为空，Vivado 未启动 | 3 | 用 ASCII 注释重建运行器并保证赋值独占物理行；引号构造经逐字符检查无误 |
| 定向证据探针误读 `RtlReferenceNeuron.state` | 1 | 模型状态是直接属性；改读 `weights/eligibility/eligibility_snapshot`，确认有效学习、拒绝和冻结路径 |
| Yosys SAT 无法直接导入 SystemVerilog `$check` | 1 | 改用 `async2sync` 自动 lower `$check` 后进入 SAT 求解 |
| 非法高优先级命令可泄漏低优先级子核请求 | 1 | Icarus 定向回归已复现；统一组合派发与时序仲裁的命令优先级 |
| formal harness 层次引用被 Yosys 当成隐式线网 | 1 | 将私有 `core_*` 断言移入 Tile 的 `FORMAL` 条件块，24 拍 BMC 通过 |
| 并行读取计划、XPM 和 Vivado 版本时有一个子命令返回非零，导致编排调用整体失败 | 1 | 拆分为独立只读命令定位；不重复同一并行调用 |
| wire-level 字段表补丁因前一轮已改写目标句而上下文不匹配 | 1 | 读取当前行后拆成小补丁，未发生部分写入 |
| 并行只读编排被 `rg` 无匹配返回码 1 整体中止 | 1 | 将可空搜索显式转换为成功返回，并对每个读取独立收集结果 |
| PowerShell 直接调用 `iverilog` 时当前 `PATH` 未包含工具目录 | 1 | 后续统一复用 `rtl_tile_cosim.find_tool()` 返回的绝对路径，不把环境定位失败误判为 RTL 失败 |
| FWFT 模型首次预取未推进内部读指针，17 项 transport 测试超时 | 1 | 将 RAM 到预取槽的推进与外部 `read_accept` 分离；T4 三项和全量回归通过 |
| 真实 XPM xsim 首轮在 4.770 us 出现无协议文本的内核异常 | 1 | 增加阶段时间戳后同一官方 XPM 测试稳定通过；保留为未复现工具波动，不据此修改 RTL |
| 重复 system OOC runner 清理刚生成的报告目录 | 1 | 等待第二个 runner 自然完成，确认无残留进程并使用更晚的一致报告签核 |
| G4 开发 cohort 探测把 `int(c0 or c1)` 当作活动布尔值，输出活动率可大于 1 | 1 | 准确率/coverage 不受影响；废弃该次 active 字段，改为 `int((c0 + c1) > 0)` 后重跑 |
| V3 Temporal 无落盘活动探针在汇总前使用未导入的 `Counter` | 1 | 探针未产出结果且未改文件；把标准库导入移到脚本开头后重跑 |
| V3 Temporal 容量探针把 `(correct, coverage)` 与整数最优值比较 | 1 | 未产出容量结论且未改文件；统一最优键为二元元组，先运行小规模性能探测 |
| 一次并行读取中 `rg` 未命中/路径检查返回 1 导致聚合调用失败 | 1 | 后续改为逐项捕获退出码，不把预期的无匹配当作项目错误 |
| PowerShell 下把 `*.py *.md` 直接传给 `rg` 导致 Windows 通配符路径错误 | 1 | 改用 `rg -g '*.py' -g '*.md'`，查询成功 |
| 动态临时目录探针因同一命令创建并递归删除路径被策略拒绝 | 1 | 未改文件；改用现有模块执行只读 `python -I -S` 导入探针 |
| `python -I -S network_sim.py` 无法导入同目录 `neuron_sim.py` | 1 | 这是预期安全路径边界；T3 worker 冻结为自包含单入口或标准库 bootstrap 显式加载已验 bundle，禁止复用旧模块树 |
| 最终静态复核把带 Markdown 行尾双空格的状态行按精确字符串匹配 | 1 | 规格状态正确；检查器改用正则/逐项打印，避免把排版空格误报为合同失败 |
| PowerShell here-string 中的中文状态正则进入 Python 后报 `nothing to repeat` | 1 | 未改规格；最终检查改为逐行 `strip()` 精确比较，绕开正则/编码边界 |
| Python here-string 中直接嵌入中文状态字面量比较仍返回 false | 1 | 文件实际行为正确；改为检查头部 ASCII token `REVIEW_REQUIRED`，最终静态验证通过 |
| D5 audit hook 无条件拒绝动态代码加载，导致已验证 bundle 也无法首次加载 | 1 | 固定 bootstrap 预载标准库后安装 hook；只在一次性 `LOADING_VERIFIED_BUNDLE` 状态允许路径、源码哈希和 code object 精确匹配的一次 compile/exec，并在 bundle 执行前切到 `SEALED` |
| 缓存隐藏响应后的容量探针仍逐候选创建输出神经元对象，120 秒超时 | 1 | 不把超时解释为容量失败；改用 NumPy 批量模拟全部 225 个输出权重对 |
| 一键审计把 XPM 固定 PASS marker 当成 `KEY=VALUE` | 1 | 保持通用解析严格，增加 XPM 专用 marker + 键值正文解析与反例测试 |
| 一键审计把系统 CDC 固定 marker 当成 `KEY=VALUE` | 1 | 增加 `CDC_CLASSIFICATION` 专用解析与反例测试；真实系统报告单独复核通过 |

### T0/T1/T2 收口证据

- `python -m unittest discover -v`：159/159 通过。
- `python -m compileall -q .`：通过。
- `python verify_goal.py`：退出码 0；Tile 24 拍 BMC、Controller 20 拍 BMC 与 6 类 witness、额外 10000 个 Tile 事务、独立 Tile、真实 XPM 和系统 Vivado 报告全部通过。
- `g4_temporal_development_manifest.json`：1312 个唯一输入/完整样本，manifest V2 SHA-256 为 `97A57856E3038E5AAC8FE32E435735742081AE2FD7D6EE0EC63F65782D6281AA`。
- 当前只完成 V3 的 T0/T1/T2；T3、P5、P6 仍待实施，Goal 保持 active。
- T3 执行规格已完成三路独立终审并消除 D5 bundle 加载 P0；当前签核 SHA-256 为 `D88EBE4A64C34DAE42E5C16888E2F786F4C560D6BE0B90EBFF1F48749009DE0C`。T3 十二项仍为 `REVIEW_REQUIRED`，获明确批准后才生成配置并进入 T3.0。

## ENeuron 1.0 与 Pulse-Mini 规划（2026-08-19）

- [x] 恢复既有计划、发现和进度记录，确认当前目录尚未初始化 Git
- [x] 复核 M1-M4、M3 账本、Vivado 报告和 1.0 声明边界
- [x] 创建 1.0 版本文件和可审计的生成物忽略规则
- [x] 运行 `python verify_goal.py`，以当前源码重建最终签核摘要
- [x] 初始化 `main` 分支并提交 `ENeuron 1.0`，创建 annotated tag `v1.0`
- [x] 标签完成后评估原始计数/分频方案，形成独立 `docs/planning/TODO.md`
- [x] 复核 Pulse-Mini 资源预算、阶段门槛和非目标，单独提交规划

### 本阶段顺序约束

- `v1.0` 只包含已经通过 M1-M4 的当前实现、验证资产和签核证据。
- `docs/planning/TODO.md` 必须在 `v1.0` 标签之后创建，作为后续开发规划单独提交。
- 1.0 不宣称共享 RAM 扩展、板级闭环、G4 或通用 AI 已完成。
- Git 忽略规则只排除缓存、临时仿真产物和可重建的大型工程文件；`verify_goal.py` 实际读取的文本报告、摘要、Tile DCP 和真实 XPM 仿真日志必须保留。

### 本阶段错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| PowerShell 将传给 `rg` 的 `run_vivado_*.ps1` 和 `*.md` 当作非法路径通配符 | 1 | 改用 `rg -g` 或精确文件列表，不重复 Windows 路径通配写法 |
| PowerShell 在 `foreach` 表达式后直接接管道时报空管道元素 | 1 | 先把循环结果赋给 `$rows`，再单独送入 `Format-Table` |
| 只读并行审查脚本中 PowerShell 字符串未正确转义，导致 JavaScript 编排语法错误 | 1 | 拆成三个独立 `exec_command` 并显式转义字符串，审查成功 |
| 误用 `functions.wait` 等待不存在的 cell `noop` | 2 | 停止调用 cell wait，改用 `collaboration.wait_agent` 等待代理消息 |
| Pulse-Mini 初稿把跨样本分频进度、三态冲突抵消和无 ID exactly-once 写得过强 | 1 | 独立语义审查后收敛为直接有符号事件累加、presence flag、统一 cmd/rsp 和单生产者有序 exactly-once |

## Pulse-Mini 实施阶段（2026-08-19）

- [x] P1：完成原始计数器/分频基线 RTL、Python 定向测试和 Vivado OOC runner 初版
- [x] P2：完成固定宽度 Python 黄金模型、14 项行为/事务测试和结构化日志
- [x] P3：完成统一 cmd/rsp、一槽响应、饱和胞体、presence 证据和反馈 RTL
- [x] P4 前置：完成 Icarus/Python 20 seeds × 1000 transactions bit-exact 协同仿真（20000 条）
- [x] P4：有限 BMC、负向反例和机器可读签核摘要
- [x] P5：训练前后任务、留出扰动、负对照和训练账本
- [x] P6：XC7Z020 Vivado 综合/布局布线/时序/DRC/功耗签核
- [x] P7：32/64/128 核阵列资源、路由和吞吐报告；容量边界与共享 lane 周期模型已形成，128 并行 routed 保持 NOT_PROVEN
- [x] P8：固定 4->2->2 Pulse-Mini 网络端到端训练与冻结推理

## Pulse-Mini 规划收口阶段（2026-08-19）

- [x] 核对当前工作树、`v1.0` 标签和 Pulse-Mini 实施基线
- [x] 复核原始计数/分频方案的真实 Vivado 资源与时序边界
- [x] 将 Pulse-Mini-L、L2、阵列和数字识别规模约束写入 `docs/planning/TODO.md`
- [x] 新增 P9-P13 的可执行路线与硬门
- [x] 完成 208 项回归和 `git diff --check`
- [x] 提交本次规划更新

## 三版本纯仿真比较阶段（2026-08-19）

- [x] S0：冻结比较口径、共同数据集和不可直接比较项
- [x] S1：实现单神经元统一实验 runner
- [x] S2：完成空间、时间、噪声、冲突和反馈延迟扫描
- [x] S3：完成固定 4->2->2 软件网络对照与既有 RTL 协同仿真复核
- [x] S4：生成 JSON 原始数据、Markdown 完整报告和可复现命令

### 本阶段验收结果

- `python compare_simulation.py --seeds 20 --rtl-cosim` 通过；未调用 Vivado。
- 共同单神经元任务：ENeuron 1.0、无泄放 Pulse-Mini 和 Pulse-Mini-L 均由 10/20 提升到 20/20，推理权重冻结。
- 固定 `4->2->2` 共同任务：三者训练后均满分；两个 Pulse 版本训练权重逐位一致。
- RTL 协同仿真旁证：ENeuron 单核 20000 事务、ENeuron Tile 10000 事务、默认 `LEAK_PERIOD=8` 的 Pulse-Mini-L 单核 20000 事务和网络 272 命令均与黄金模型一致。
- `python -m unittest discover -v`：200 项通过；`python -m compileall -q .` 通过；Pulse-Mini 有限形式验证 depth 20 无反例。
- 完整报告为 `docs/reports/SIMULATION_COMPARISON_REPORT.md`，原始数据为 `artifacts/results/comparison_simulation_results.json`。

### 本阶段错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| PowerShell 不支持 Bash heredoc `python - <<'PY'` | 1 | 临时探针改用 PowerShell here-string；未修改项目源文件 |
| 两次误用 `functions.wait` 等待不存在的 cell | 2 | 停止使用 cell wait，统一用 `write_stdin` 轮询真实会话 |
| 报告测试要求出现精确短语“仅仿真”，初稿只有“纯仿真” | 1 | 在范围声明中加入明确的“仅仿真评估”字样 |

## Pulse-Mini L1 泄放升级阶段（2026-08-19）

- [x] 冻结膜电位泄放定时器合同与可关闭的无泄放对照
- [x] 为 Python 黄金模型增加 leak_timer，并补齐边界黄金向量
- [x] 将同一语义映射到 Pulse-Mini RTL、阵列/网络包装器和协同仿真
- [x] 完成 LEAK_PERIOD 扫描、单元任务、4->2->2 网络和推理冻结比较
- [x] 更新纯仿真报告、原始 JSON 和阶段证据

### 本阶段冻结决策

- L1 默认 `LEAK_PERIOD=8`；`0` 仅用于无泄放消融对照。初始候选 `4` 经弱连接密集事件扫描淘汰。
- 只在接受成功的逻辑 `TICK` 上计时，不使用派生时钟。
- 到期时膜电位向零移动一个单位；顺序为“先泄放，再加入本 tick 输入，再判阈值”。
- 不应期内泄放计时器暂停；自然发放和 `STATE_CLEAR` 都清零计时器。
- `CAPTURE/FEEDBACK`、权重范围、训练/推理冻结和一拍网络路由合同不变。

## Pulse-Mini-L2 证据强度升级阶段（2026-08-19）

- [x] 冻结 PN2 正/负证据计数与 `-2..+2` 幅度反馈协议
- [x] 更新 Python 黄金模型、RTL、事务回归、协同仿真和形式验证
- [x] 完成三类、四类、多标签和时间顺序任务的 local_teacher / global_scalar_reward 对照
- [x] 完成 XC7Z020 Vivado 2024.1 routed 资源与时序复核
- [x] 同步最终报告数字并记录 100 MHz setup 失败边界

### 本阶段验收结果

- 参考模型 8/8、20 seeds × 1000 transactions（20000 条）协同仿真和 Yosys depth-20 SAT 通过。
- L2 在四类组合任务达到约 66.9% coverage，covered accuracy 100%；时间顺序任务仍失败；全局标量奖励没有形成有效 coverage。
- 最终硬件实测为 366 LUT / 91 FF / 0 BRAM / 0 DSP，WNS -4.690 ns、WHS +0.152 ns；L2 不是 100 MHz setup 通过版本。

## ENeuron 固定图像数字识别阶段（2026-08-19）

- [x] 用户批准 8×8、K=16、64→16→4→10、逐事件局部教师和能力门五项冻结决策
- [x] D0：生成固定 8×8 数字 fixture、分层 manifest 和 SHA-256
- [x] D0：实现 rank-order latency 编码与 2×2 patch mask 往返合同
- [x] D0：完成确定性、恒定事件数、标签独立和 split 防泄漏测试
- [x] D1：无学习基线、软件可分性上限和十分类解码
- [x] D2：固定特征、只训练 10 个输出神经元（协议 PASS，性能 FAIL_GENERALIZATION）
- [ ] D3：分层局部教师训练与 ENeuron/L2/STDP 对照
- [ ] D4：dropout、时间抖动、遮挡和平移鲁棒性
- [ ] D5：8×8 图像 wrapper Python/RTL bit-exact 与 30 核 routed
- [ ] D6：16×16 共享 lane/RAM 扩展评估

### D0 冻结边界

- 首轮真实输入是固定 8×8 灰度十分类，不覆盖 TODO 中较小的 `4→8→10` 协议探针。
- 图像网络目标形状为 `64→16→4→10`，共 30 个四输入 ENeuron；该规模目前只有资源估算，没有 routed 证据。
- 现有 ENeuron 单核和 Pulse-Mini 合同不修改；图像输入使用新增 wrapper。

### D1 结果

- 最近质心 + rank-order 发放 tick：测试集 balanced accuracy 79.80%、accuracy 80.00%、macro-F1 79.46%、coverage 100%。
- 只看总事件数、首 tick、末 tick 的基线均无有效覆盖；标签打乱后 balanced accuracy 8.69%，接近十分类机会水平。
- D1 判定 `PASS`，允许进入 ENeuron 输出层训练；软件上限不能替代神经元训练证据。

### D2 当前实施口径

- 前 20 个单元（64→16→4）使用冻结参数，只生成固定特征脉冲。
- 仅十个输出单元参与学习；训练期间禁止直接权重写入。
- 每个输入事件后显式注入一个教师 post 事件，再留出三个空 tick；教师事件不计入自然发放统计。
- 每次提交记录样本、类别、输出单元、资格迹快照、调制值和权重变化，形成训练来源账本。
- 推理阶段关闭学习和调制，权重与所有学习字段必须保持不变。

### D2 结果

- D2 协议/账本合同测试 14 项通过；训练期自然输出为 0，直接权重写入为 0，固定特征指纹不变，推理并列严格 abstain。
- 10 个固定 seed、每个 3 epochs 的正式实验已落盘 `artifacts/results/digit8x8_d2_results.json`；validation BAcc 均值 4.61%、最小 1.11%，coverage 均值 56.04%、最小 39.26%，达到 `BAcc≥70% 且 coverage≥90%` 的 seed 为 0/10。
- test BAcc 均值 4.74%、coverage 均值 52.18%；固定权重与标签打乱对照均未达到主门槛。
- 结论为 `D2_FAIL_GENERALIZATION`，部分 seed 同时属于 `D2_FAIL_ACTIVITY`；在批准输出层信用修正并重新通过 D2 前，不进入 D3 解冻隐藏层。

### D2 错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| PowerShell 不支持 Bash heredoc `python - <<'PY'` | 1 | 未修改源文件；改用 `python -c` 进行同一只读探针 |
| 结果汇总探针误把列表推导变量写成未定义的 `x` | 1 | 未修改结果文件；改用独立列表变量 `z` 重跑统计 |
| D2 结果 JSON 初次生成时记录了提交前 HEAD | 1 | 复核后将 `git_commit` 修正为包含 D2 模型源码的提交，并单独提交修正 |

## 当前项目报告阶段（2026-08-26）

- [x] 冻结报告范围：目标、架构、三个神经元版本、验证、资源、数字识别、边界与路线
- [x] 复核仓库 HEAD、签核摘要和机器结果
- [x] 生成 `docs/reports/PROJECT_REPORT.md`
- [x] 校验报告中的实测/估算/未证明口径与仓库链接

### 报告口径

- Vivado routed、协同仿真、有限形式验证和软件任务结果分别陈述，禁止互相代偿。
- `v1.0` 是完整三因子最小硬件基石；后续 Pulse-Mini 与数字识别实验单列。
- D2 失败属于有效能力边界，不能通过放宽 abstain、挑 seed 或引用 D1 软件基线改写为通过。

### 报告阶段错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| PowerShell 将 `vivado_*_reports` 作为 Windows 非法路径通配符交给 `rg` | 1 | 改为 `Get-ChildItem -Directory` 枚举后逐目录读取，不重复相同通配写法 |
| XC7Z020 N2/N4 报告目录没有 `signoff_summary.txt` | 1 | 直接从 `utilization_impl.rpt` 和 `timing_impl.rpt` 提取资源与时序 |

## FPGA 图像识别性能评估（2026-08-26）

- [x] 复核当前 D1/D2 能力结果与 8×8 网络规模
- [x] 用 XC7Z020 routed 数据计算直接复制边界
- [x] 估算共享 BRAM/lane 下的状态容量与事件吞吐
- [x] 区分 8×8 概念验证与 28×28 实用原型的验收指标
- [x] 形成“算法先过门、再实现共享硬件”的建议顺序

### 评估口径

- 当前 30 核资源与共享 lane 数据均为估算，不能写成 routed 结论。
- 图像识别首先由 BAcc、coverage 和负对照验收；硬件吞吐不能补偿分类失败。
- 8×8 目标沿用 D2 强门；28×28 仅给出代表性 `784->128->10` 容量点，不冻结最终网络。

## NPU 局部自动剪枝规划（2026-08-28）

- [x] 核对现代 N:M 稀疏执行与迭代剪枝的官方约束
- [x] 审计 ENeuron/Pulse-Mini 可复用状态和真实跳算位置
- [x] 比较逐权重、固定 N:M、整神经元三种门控粒度
- [x] 冻结最小实验合同、负对照、精度与硬件收益门槛
- [x] 形成 `docs/planning/NPU_PRUNING_TODO.md`，并在 `docs/planning/TODO.md` 增加待审核入口
- [x] 用户批准 NP0 八项决策，并要求 ENeuron、Pulse-Mini-L、Pulse-Mini-L2 三种神经元全部运行
- [x] NP1：统一黄金模型与不可作弊工作量计数（19 项 B0 测试、固定向量和 SHA-256 摘要通过）
- [x] NP2：三种神经元完成 S0-S3、gain 1/2/3 扫描及同分/clip/稳定性统计；选择 `1/2/1`
- [x] NP3：三模型一次/渐进/错误符号和完整 TRAIN/INFER 冻结账本通过；选择一次剪枝
- [x] B2.1：三模型三候选均通过；output-2:4 为 120 次读取/发射，按 KISS 选为 V1
- [x] 原始 Goal 完成审计：NP0 八项、三模型软件实验、文档和分阶段提交均有权威证据
- [x] NP4A/NP5：公共 `2:4` 控制器、60000 条协同事务、有限检查和负向反例已通过
- [x] NP4B：三模型 wrapper、严格 `4→8→2` 网络、各 20,000 条、五套形式证据、359 项回归和总摘要全部通过；状态为 `NP6_REVIEW_REQUIRED`

### 本阶段错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| Git 因仓库所有者为 Administrators 拒绝普通命令 | 1 | 不修改全局配置；后续只用单次 `git -c safe.directory=...` 读取状态 |
| 首次并行发布审计脚本把顶层 `await` 放入 `eval()`，V8 拒绝执行 | 1 | 不重复该包装；改为直接使用顶层 `Promise.all`，四项只读审计随后通过 |
| 初次 GitHub SSH 检查只测试默认 key 与 `~/.ssh/github`，均被拒绝 | 1 | 用户说明 GitHub/Gitee 共用 `~/.ssh/id_ed25519_gitee`；显式复验成功认证 `Epslion404`，目标空仓库读取通过 |

## GitHub 首次推送准备（2026-08-29）

- [x] 核对当前 `main`、干净工作树和空 remote 列表
- [x] 审计 `.gitignore` 与被强制跟踪的正式 log/VCD 证据
- [x] 审计当前文件和完整历史的大对象上限
- [x] 扫描已跟踪内容与历史中的明显凭证、私钥和敏感文件名
- [x] 补齐最小通用 Vivado/编辑器/本地凭证忽略规则，并验证正式证据不受影响
- [x] 配置 `origin=git@github.com:Epslion404/ENeuron.git`
- [x] 核对 GitHub SSH 身份与目标仓库；共用 key 成功认证 `Epslion404`，目标仓库存在且当前无 refs
- [x] 提交发布准备改动并停在执行 `push` 前

### 推送准备约束

- 用户给出的目标已规范化并配置为 `origin=git@github.com:Epslion404/ENeuron.git`；本仓库局部指定已验证的共用 key，正式 push 仍单独执行。
- 已跟踪的 12 份正式 proof/reach `.log`/`.vcd` 是 fail-closed 签核证据，不因通用忽略规则而移除。
- 不改写 Git 历史；只有发现真实凭证或 GitHub 禁止的大对象时才另行提请审核。

## PR #1 第二轮复审（2026-08-30）

- [x] 回读协作者回复、最新 PR SHA、文件列表与既有 review 状态
- [x] 在隔离 worktree 审查 runner、oracle、测试和机器摘要的一致性
- [x] 使用本机 Vivado 2024.1 对 PR 当前 SHA 执行真实 XSim 复现
- [x] 核对 exact-two、原子提交、INFER 冻结、非法输入无副作用和随机逐事务对拍
- [x] 根据事实向 PR 提交中文要求修改反馈

### 本轮验收口径

- 评审对象固定为 PR 当前 HEAD `169003684b260aaabf98fb3b6e70866cb0c24bed`；若远端 SHA 变化，已有结论作废并重新核查。
- 协作者的 Vivado 2024.2 结果只能作为补充证据，不能替代项目指定的 Vivado 2024.1 复现。
- 真实复现必须直接编译当前 PR 提交的 RTL/testbench，并检查 `xvlog -> xelab -> xsim` 的实际退出码和最终标记。
- 不因报告自称 PASS 而批准；必须同时审查 runner 是否真的逐事务比较 RTL 与独立 Python oracle。

### 本轮错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| Git 因目录所有者为 Administrators 拒绝普通命令 | 1 | 不修改全局配置；本轮继续使用单次 `git -c safe.directory=D:/Documents/Code/ENeuron` |
| 完整 Vivado 命令的外层包装含删除旧临时摘要，被权限策略拒绝 | 1 | 仿真尚未启动；改用全新唯一摘要路径且不执行删除，随后完整运行成功 |
| 首次 PowerShell 哈希诊断的 `foreach` 后直接接管道触发解析错误 | 1 | 改用 Python 读取工作树字节与 `git show HEAD:<file>` blob 分别计算 SHA-256 |

## PR #1 第三轮复审（2026-08-30）

- [x] 回读协作者新回复、最新提交、文件列表和审查状态
- [x] 在隔离 worktree 检查 v2 摘要、EOL 规范化、provenance 和反例命名修复
- [x] 使用本机 Vivado 2024.1 对最新 HEAD 重新运行真实 XSim
- [x] 在可用工具范围内复跑相关回归，确认未重跑项被正确标记且没有静默继承
- [x] 根据事实向 PR 提交中文批准或继续要求修改

## PR #1 第四轮精简复审（2026-08-31）

- [x] 回读最新回复、HEAD 与改动范围
- [x] 隔离检出并验证两个剩余硬问题
- [x] 运行针对性测试和完整回归（35 项关键回归与 385 项完整 discovery 均通过）
- [x] 提交精简中文审查结论

### 本轮错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| GitHub GraphQL 连接被远端重置 | 1 | 改用 `gh api` REST 端点分别读取 PR、评论、提交和 reviews |
| 正式 `verify_local_prune_rtl.py` 通过后改写三份已签名 formal 产物，使 `verify_np4b_signoff.py` 立即哈希失败 | 1 | 保留隔离现场作为复现证据；另建干净 worktree 运行提交态完整回归，区分提交态与复验流程问题 |
| `gh api` 的 REST/GraphQL HTTPS 连接均被远端重置 | 2 | 不重复同一网络栈；改用已登录 `gh` token 配合 PowerShell `Invoke-RestMethod`，review 提交与回读成功 |
| 最新 HEAD 全仓启用 Vivado 的首轮短 XSim 出现退出码 3221225477 | 1 | 单独重跑同一 `test_short_real_vivado_regression_passes` 通过；无 Vivado 的全仓 386/386 通过，记录为工具进程稳定性而非代码失败 |

## PR #2 三模型 Vivado 短测复审（2026-08-31）

- [x] 读取 PR #2 元数据、分支、HEAD 和文件差异
- [x] 在隔离 worktree 运行本机 Vivado 2024.1 针对性回归
- [x] 审查 `docs/reports/SIMULATION_REPORT.md`、`TEST_MATRIX.json` 和 `test_local_prune_gate_vivado.py`
- [x] 修复报告中的 PR #1 复现命令残留并推送到 PR 分支
- [x] 通过 GitHub 页面提交中文 review/comment

### 本轮错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| GitHub REST review 提交 TLS EOF | 2 | 改用 `gh pr review` 与 curl REST comment 尝试 |
| `gh pr review` GraphQL 被远端重置 | 1 | 改用 REST issue comment endpoint |
| curl REST issue comment 连接被重置 | 1 | 发现 `127.0.0.1:7897` 代理后改用 `gh api --method POST`，评论 `5479989535` 提交成功 |

### 当前剩余事项

- PR 描述中 `386 tests / 0 failures / 2 errors / exit 1` 与“386/386 OK”并列，需更正为环境性失败对照；仓库文件和测试代码已由提交 `f975cd7` 修复。

### 后续复核

- [x] 确认 PR 分支新增生成器修复，`make_local_prune_report.py` 不会再渲染回 PR #1 命令
- [x] 轻量复核最新 HEAD：Python 编译、报告重渲染和空白检查
- [x] 通过代理 PATCH PR 描述，修正全量 discover 口径
- [x] 通过代理提交 `APPROVE` review 命令
- [ ] 回读确认 GitHub review 状态

| 错误 | 尝试 | 处理 |
|---|---:|---|
| PowerShell 使用 `< $tmp` 输入重定向失败 | 1 | 改用 `gh api -f body=...` PATCH PR 描述 |
| `APPROVE` 后回读 GraphQL/REST 多次 EOF | 3 | 只记录 approve 命令退出码 0，不伪造回读确认 |
## 2026-08-31 根目录 Markdown 整理归档

### 目标

将根目录中的阶段报告、设计规格、验证记录和历史规划迁入 `docs/` 的稳定分类目录；根目录只保留项目入口与持久工作文件，并修复全部仓库内 Markdown 引用后提交、推送到 `origin/main`。

### 执行阶段

- [x] 恢复现有计划并盘点根目录 Markdown 与 Git 状态
- [x] 冻结归档分类和保留在根目录的文件集合
- [x] 使用 Git 可追踪移动完成归档，并修复文档引用
- [x] 检查 Markdown 链接、工作树差异和仓库状态
- [x] 提交归档改动并推送 `origin/main`

### 验收标准

- 根目录只保留 `README.md`、持久工作流/计划文件及必要入口文档
- 所有迁移文件按用途进入 `docs/design/`、`docs/reports/`、`docs/verification/` 或 `docs/planning/`
- 仓库内相对 Markdown 链接不存在因迁移导致的断链
- 不覆盖现有 `docs/reports/STAGE_REPORT_2026-08-31.md`、`progress.md` 未提交内容，二者随本次文档归档一起审计提交
- `git diff --check` 通过；提交成功且本地 `main` 与 `origin/main` 一致

### 约束

- 只整理 Markdown 及其路径引用；Python/PowerShell/JSON 只允许修改文档路径常量或刷新既有签名，不改功能逻辑、RTL、测试语义或生成证据内容
- 保留 Git 历史，不删除项目事实记录
- 不运行 NP6 Vivado，不扩大既有验证结论

### 冻结归档结构

- 根目录保留：`README.md`、`WORKFLOW.md`、`WORKFLOW_STATE.md`、`task_plan.md`、`findings.md`、`progress.md`
- `docs/design/`：设计提案、协议、执行规格、推荐设计和 RTL 合同
- `docs/planning/`：Pulse-Mini、NPU 剪枝与 NP4B 专项 TODO
- `docs/reports/`：数字识别、仿真、局部剪枝、项目阶段与 1.0 发布报告
- `docs/verification/`：Goal 审计和 NPU 剪枝签核
- `docs/README.md`：按上述四类提供可点击索引，并说明根目录保留规则

### 错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| 审计命令假定总摘要生成器名为 `make_np4b_signoff_summary.py`，该文件不存在 | 1 | 未产生文件修改；改用 `rg --files` 查找真实生成/刷新入口，不重复调用不存在路径 |
| 首轮全局路径替换把后缀键 `TODO.md` 再次应用到两个已替换的 NPU TODO 路径 | 1 | `rg` 稳定复现 16 处重复 `docs/planning`，后缀关系审计确认仅影响两个 NPU TODO 名；使用两个完整错误串做一次精确替换，并以同一 `rg` 断言归零 |
| 记录上述替换错误时，多文件补丁仍使用迁移前路径文本作上下文，补丁被原子拒绝 | 1 | 未产生部分修改；先读取当前精确行，再按现状补丁，不重复使用旧上下文 |
| Goal 定向测试迁移到嵌套文档路径后，临时目录未创建父目录而出现 2 个 `FileNotFoundError` | 1 | RED 已由 `T0HandoffSummaryTests` 两项稳定复现；测试夹具在写文件前创建目标父目录，不改变被测接口或断言 |
| Windows PowerShell 5.1 运行无 BOM UTF-8 的恢复脚本时，中文注释行后的 `$repoRoot` 赋值未生效 | 1 | `Mode Check` 稳定 RED；当前文件与 HEAD 均无 BOM，变量只在该注释后赋值一次。将紧邻赋值的注释改为 ASCII，保持脚本逻辑不变后复验同一命令 |
| 仅改首条中文注释后，Windows PowerShell 5.1 在后续中文字符串处仍发生跨行误解析 | 2 | 证明问题是整个无 BOM UTF-8 文件的解码，不是单一注释；为脚本增加 UTF-8 BOM，保留中文日志与逻辑，再以同一 `powershell -File ... -Mode Check` 复验 |
| 增加脚本 BOM 后已能执行，但默认代码页读取无 BOM Markdown 导致“最后更新”字段误判缺失 | 3 | 解析层问题已消失；在全部 Markdown `Get-Content`/`Select-String` 读取点显式指定 UTF-8，再复验同一 Check。该修复保留原字段与状态合同 |
| 旧根路径审计的一次性 PowerShell 命令把 `$n:` 解析成带冒号的变量引用 | 1 | 命令在解析期失败、未读写仓库；改用格式化运算符构造诊断字符串，不重复含歧义的插值写法 |
| 修正语法后的旧路径审计把 NPU 文件名中的合法 `TODO.md` 后缀误报为 23 个旧根引用 | 2 | 所有报项都位于已验证的新路径；改为先从每行移除全部合法完整/相对归档路径，再搜索残留旧文件名，消除后缀歧义 |
| “剥离合法路径”审计仍把同一行中的合法链接/说明文字误报为 58 项 | 3 | 停止继续扩展该一次性算法；改用负向路径字符边界，只检查未被 `/`、`\`、`_` 或文件名字符前缀限定的裸旧文件名，并保留独立零断链检查 |
| 报告一致性检查命令包含删除系统临时文件，被进程策略在启动前拒绝 | 1 | 仓库未改；改用 `New-TemporaryFile` 取得唯一目标且不执行删除，由系统临时目录管理该文件 |
| 报告生成器成功输出归档路径，但临时重渲染与正式报告不完全一致 | 1 | 差异只来自主工作区缺少 PR 评审时的 `vivado_regression_console.log`、当前未提交树无法重建当时分支清单，以及最新签名基线；保留正式报告中的原始真实证据，不用缺输入的降级输出覆盖 |
| 首轮合并运行局部剪枝测试时，签名刷新态不满足“可用工具均已正式重验证”的已提交摘要合同 | 1 | 不降低断言；运行项目正式 `verify_local_prune_rtl.py` 重验证路径，使行为/形式证据与迁移后的 verifier 哈希一起刷新，再重跑定向套件 |
## 2026-09-01 根目录非 Markdown 文件归档调研

### 目标

在不破坏 RTL/仿真/形式验证/机器摘要可复现性的前提下，继续减少项目根目录噪声；先形成可审核的最小归档方案，用户批准后再分解并实施。

### 调研阶段

- [x] 读取默认技能并冻结“先调研、后审核、再实施”的流程
- [x] 盘点根目录文件、目录、Git 状态和忽略规则
- [x] 审计脚本、RTL、Tcl、JSON 与工具对根路径及当前工作目录的依赖
- [x] 形成 V1 归档方案、保留集合、风险和验收标准
- [x] 提请用户审核 V1 方案
- [x] 审核通过后分解迁移、引用修复、验证、提交与推送任务

### 当前约束

- 调研阶段只读，不移动、删除或改写功能文件
- 不把正式机器摘要、日志或 witness 当作普通缓存清理
- 不运行 Vivado；NP6 仍为 `REVIEW_REQUIRED`
- 优先小步整理基础设施/结果目录，不以“根目录零文件”为目标强搬高耦合 RTL 与测试

### V1 审核稿（待用户批准）

1. 根目录继续保留源码、RTL、测试、runner、Tcl/Yosys 脚本、配置、版本、data/manifest、签核摘要、正式形式证据和持久工作流文件。
2. 新建 `artifacts/results/`，只迁移 15 个不进入当前签核哈希集合的历史/实验结果 JSON；同步生成器默认输出、读取者、测试和文档引用。
3. 新建 `artifacts/README.md`，说明结果文件职责、生成入口和“非最终签核摘要”边界。
4. 可选本地清理：删除 47 个已被 `.gitignore` 排除的根目录 VVP、失败/覆盖 VCD、临时日志和 `clockInfo.txt`，以及 `__pycache__`、`.pytest_cache`、`.Xil`、`vivado_pulse_original_sim` 和空 physopt 目录；它们不入 Git，可由现有工具重新生成。
5. 不迁移另外 4 个 data/manifest JSON、11 个签核 JSON/TXT、12 个正式形式 `.log`/成功 `.vcd` 或任何 Vivado 证据目录，避免触碰哈希链和物理报告新鲜度。
6. 验收：路径残留扫描、完整 unittest discovery、官方 NP4B verifier、`verify_goal.py` 现存证据审计、Python compileall、工作流 Check、`git diff --check` 全通过；不调用 Vivado。
7. 通过后再提交并推送；用户批准前不执行移动、清理、提交或推送。

### V1 精确迁移集合

- `artifacts/results/comparison_simulation_results.json`
- `artifacts/results/digit8x8_d1_results.json`、`artifacts/results/digit8x8_d2_results.json`
- `artifacts/results/local_prune_b0_results.json`、`artifacts/results/local_prune_b1_results.json`、`artifacts/results/local_prune_b2_results.json`、`artifacts/results/local_prune_b21_results.json`、`artifacts/results/local_prune_np2_results.json`、`artifacts/results/local_prune_np3_results.json`
- `artifacts/results/network_results.json`、`artifacts/results/network_sweep_results.json`
- `artifacts/results/pulse_mini_protocol_experiments.json`
- `artifacts/results/rtl_smoke_results.json`
- `artifacts/results/simulation_results.json`、`artifacts/results/sweep_results.json`

### V1 执行任务（2026-09-01 已批准）

- [x] T1：冻结当前状态、15 文件清单、引用清单与 ignored 清理白名单
- [x] T2：先增加结果默认路径合同测试，确认旧路径实现出现 RED
- [x] T3：创建 `artifacts/results/` 和索引，使用 Git rename 迁移 15 个 JSON
- [x] T4：同步 writer、reader、测试、报告与历史文档路径，定向测试转为 GREEN
- [x] T5：精确清理 47 个 ignored 根文件及批准的纯缓存/空目录，不触碰 tracked formal/Vivado 证据
- [x] T6：完整回归、NP4B verifier、严格 Goal 验收、compileall、工作流和 Git 检查
- [x] T7：提交、推送并核对本地 `main` 与 `origin/main`

## NP6 物理成本评估规划（2026-09-01）

- [x] 读取 NP4B 当前签核、工作流状态和可用 Vivado 路径
- [x] 冻结 NP6 只测量物理资源/时序/DRC，不提前声明 BRAM 跳读或板级收益
- [x] 形成 `docs/planning/NPU_PRUNING_NP6_TODO.md`，列明比较矩阵、验收门和停止条件
- [ ] 用户审核 NP6 五项冻结决策并明确批准调用 Vivado
- [ ] NP6.0→NP6.8：按批准矩阵执行配对综合、实现、报告解析、fail-closed 签核与推送

### V1 严格证据追加授权（2026-09-01）

- 用户在得知 Tile RTL 晚于现有 Vivado 报告后明确选择方案 1，授权使用 Vivado 2024.1 重建严格证据闭环。
- 执行顺序冻结为 Tile OOC → 真实 XPM xsim/综合 → 双时钟 System OOC；任一步退出非零立即停止，不运行 NP6 新设计探索。
- 本授权覆盖下方原“不得调用 Vivado”的限制；其它 V1 边界保持不变。重建产生的正式 Vivado 报告属于当前 RTL 的更新证据，允许随 V1 一并提交。
- [x] Tile OOC：100 MHz 实现与全部硬门通过
- [x] 真实 XPM xsim/综合
- [x] 双时钟 System OOC

### V1 验收合同

- 15 个结果文件只存在于 `artifacts/results/`，旧根路径不再生成或读取
- `artifacts/README.md` 列出全部结果及生成入口，明确它们不是最终签核摘要
- 根目录不再存在已批准清理的 ignored 单文件和纯缓存目录
- 12 个 tracked formal log/VCD、15 个 data/signoff JSON/TXT 和所有 Vivado 证据目录的路径及 Git 内容保持不变
- 除上述 2026-09-01 严格证据追加授权外不调用 Vivado；任一证据 verifier 失败则停止提交

### V1 错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| 无 | 0 | T1 只读冻结通过 |
| `test_artifact_layout` 在迁移前失败：缺少 `artifacts/results` | 1 | 预期 RED，失败点与冻结合同一致；进入最小迁移实现 |
| B0 与 B2.1 定向测试在路径迁移后报告源码哈希陈旧 | 1 | 使用正式生成器重建 B0、NP2、NP3、B2.1；定向测试恢复通过，未手工伪造哈希 |
| `verify_goal.py` 拒绝 Tile Vivado 报告：报告早于 2026-08-29 的 Tile RTL | 1 | V1 禁止运行 Vivado，且验收合同规定 verifier 失败即停止提交；T6/T7 暂停，等待用户决定是否另行批准重建证据或调整 V1 gate |
| 用户选择严格闭环方案 1 | 1 | 已授权按 verifier 冻结顺序重建 Tile、XPM、System 证据；不扩大到 NP6 |
| 完整 Goal 验收 | 1 | `verify_goal.py` 退出码 0，输出 `GOAL_AUDIT_PASS`；387 项回归通过（1 项无环境变量时跳过），Tile/Host Bridge 形式证明、Tile 10000 事务和 System 957 命令协同仿真全部通过 |

## 2026-09-01 PR #5 NP6 物理成本复审

- [x] 用户明确确认 `NPU_PRUNING_NP6_FREEZE_DECISIONS.md` 中九项决策全部同意，解除授权溯源阻断。
- [x] 核对 GitHub 编号：仓库不存在 PR/Issue #4；当前唯一开放项是 PR #5，且出现协作者最新回复。
- [x] 在 PR #5 留下仓库所有者的九项批准确认，明确技术阻断仍需修复。
- [x] 等待新 HEAD 后复验只读 manifest、负向 mutation 和 ENeuron 配对口径。
- [x] 复验 HEAD `61988e2`：正向验证、manifest 不变性、工作树洁净和 10 项 mutation 均通过；配对 2 已改为 `NOT_COMPARABLE`，孤立文件已删除。
- [x] 修复冻结源码字节未与 `frozen_git_head` 比对，以及报告/授权文档仍引用旧状态的问题。
- [x] HEAD `550ec26` 已完成冻结字节三方比对、T8/T9 committed-tamper 负向测试和文档状态修正；复验无剩余阻断。

## 2026-09-01 NP6 收口与 NP7 规划

- [x] 同步并确认 PR #5 已合并到 `origin/main`，merge commit 为 `241b1d0`。
- [x] 将 NP6 状态从陈旧的 `REVIEW_REQUIRED` 收口为 `NP6_PHYSICAL_COST_PARTIAL`。
- [x] 更新总剪枝 TODO、文档索引和持久工作流指针。
- [x] 形成 `NPU_PRUNING_NP7_TODO.md` 审核稿，冻结到 Vivado 门前的实施顺序。
- [ ] 用户审核 NP7 八项决定；批准前不修改共享 lane/BRAM RTL。

### 收口复验修正

- [x] 定位 mutation T0 假失败：`shutil.copytree` 复制受跟踪 VCD 后产生工作树差异。
- [x] 将 mutation 临时仓库改为 `git clone --no-hardlinks`；干净提交态 `MUTATION_SUITE PASS checks=12`。

## 2026-09-01 PR #6 NP7 审查

- [x] 锁定 PR #6 最新 HEAD、授权链、Vivado 调用边界和文件范围。
- [x] 静态审查 NP7 oracle、RTL、协同仿真、形式/负向控制和 fail-closed 摘要。
- [x] 在隔离 worktree 复验关键测试与 G1/G2/G3 停止门。
- [x] 核对是否实际运行 NP7 Vivado，以及结果是否与 `NP7_FUNCTIONAL_HOLD` 一致。
- [x] 向 PR 提交中文审查结论并记录证据。

### 审查结论

- PR #6 保持 `CHANGES_REQUESTED`，锁定审查提交为 `398dc1a`。
- G3 的 12 个模型/lane 配置均低于 25%，停止 NP7.7 符合冻结门；不得把当前证据称为 NP7 Vivado 已完成。
- 修复 Vivado testbench 编译、CONFIG 非法写拒绝、sparse 复查寄存器初始化、Windows 突变测试编码和冻结决策表格后再复审。

## PR #6 两类裁定代价分析

- [x] 明确两类裁定：八项冻结决定的授权确认；G3 的 A/B/C/D 技术处置。
- [x] 从 NP7 TODO、冻结记录、阶段报告和当前 PR 状态提取每条路径的重跑边界。
- [x] 比较开发量、验证量、硬件风险、结论可信度和后续 Vivado 代价。
- [x] 给出推荐组合及不推荐路径的理由；本轮只分析，不代替所有者作出批准。

### 推荐结论

- 若坚持原始 G3≥25% 并继续推进硬件，推荐 B 的 V1（零路径单拍），不推荐单独 V2；它针对占总周期 70.9% 的固定开销，预计 G3 约 30–34%。
- 若优先快速取得 XC7Z020 物理资源/时序数据，可选 A，但必须明确这是见到结果后的目标修订，且最差配置仅比新门槛高 1 个百分点。
- C 适合终止 NP7 或仅保存失败基线；D 更换评测分布且 L4/L8 仅高于门槛 0.3 个百分点，不建议。

## NP7 管理员决策点：B-V1+V2

- [x] 核对 PR #6 最新 HEAD、既有八项冻结决定和 A/B/C/D 定义。
- [x] 新建仓库知识库决策点，冻结 B-V1+V2 的接口、周期、证据和物理影响。
- [x] 更新文档索引与 NP7 TODO 的管理员裁定入口。
- [x] 在 PR #6 以管理员身份回复逐项批准/修订内容，保持现有 `CHANGES_REQUESTED` 直到实现与证据通过。
- [x] 回读 PR 评论并检查本地文档差异；本轮不提交、不推送、不合并。

### 成功标准

- 决策文件明确 A/C/D 不采用，决定 5 被 B-V1+V2 取代，G3 仍为 25%。
- V1/V2 在零路径、非零最后批、背压和同时 retire/accept 场景下无歧义。
- NP7.1-NP7.6 全量重跑、现有四项审查阻断和 NP7.7 启动门均有明确要求。
- PR 评论由 OWNER 账号提交并可回读，且不错误解除 `CHANGES_REQUESTED`。

### 错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| 决策文档首次补丁构造失败：末行未被识别为 `*** End Patch` | 1 | 仓库无部分改动；弃用带表达式的行构造，改用纯字符串数组补丁 |
| 决策文档第二次补丁构造失败：新增行被 JavaScript 一元加号转成 `NaN` | 2 | 仓库仍无部分改动；第三次改用无内联反引号的原始文本补丁并拆分执行 |
| 索引/TODO 同步补丁被原文 Markdown 反引号截断，JavaScript 报语法错误 | 1 | 决策正文已成功；剩余同步改为纯行补丁，不回退正文 |
| PowerShell 下 `rg` 通配符被当作非法 Windows 路径 | 1 | 改用 `rg -g '*.py'` 形式；未影响工作流文件，重新检查通过 |

## PR #10 fail-closed 清单修复

- [x] 读取 GitHub 失败日志并定位为 TODO 字节绑定失配。
- [x] 用当前提交重新生成 NP7 软件成本 manifest。
- [x] 显式使用 `C:\msys64\ucrt64\bin` 探测本机 Icarus/Yosys，排除旧路径缺失假象。
- [ ] 提交、推送并等待 Webhook/CI 回报。
- [x] 提交 `5a6825f`、推送到 PR #10，并用 Webhook 与 GitHub 双重确认 CI 全部成功。

## 2026-09-02 PR 自动检查工作流

- [x] 读取 GitHub 官方 Actions、权限、分支保护与不可信 PR 代码安全文档。
- [x] 新增只读 `.github/workflows/pr-gate.yml`，不自动 approve、不自动 merge。
- [x] 将检查拆为 Python/语法、NP7 软件/形式、NP7 物理证据完整性三道状态门。
- [x] 增加 NP7 文件适用性检测，普通非 NP7 PR 不会因缺少专项脚本而失败。
- [x] 新增 `docs/CI_PR_GATE.md` 配置教程并加入 `docs/README.md` 索引。
- [x] 本地 YAML 解析、Python compileall、git diff --check 全部通过；未调用 Vivado。

## 2026-09-02 PR #10 CI 收口与本地 Webhook

- [x] 轮询 GitHub Actions run `33660700397` 至终态。
- [x] 确认四道 CI 门全部成功：Python/语法、XPM CDC、NP7 功能/证据、NP7 物理证据完整性。
- [x] 通过仓库外接收器 `C:\Users\Epsilon\ENeuronWebhook` 收到并核对 GitHub 终态事件。
- [x] 复核仓库工作树，删除 `.nexus-map/.refresh` 临时产物，不引入 Webhook 服务文件。
- [x] 完成 Nexus 增量刷新并核对 PR #10、NP7 合并状态和传统 NPU + 神经元集成下一步。
- [ ] 等待管理员决定是否合并 PR #10；合并前不启动新的集成 RTL 或 Vivado 任务。
- [x] 复核 `4d1a5cd` 对应 run `33663148479` 成功，并重启仓库外 Webhook 接收服务。
- [x] 复核后续 HEAD `9cced26` 对应 run `33711162898` 成功，Webhook 收到 `workflow_run completed/success`。
- [x] 复核当前 HEAD `90b7e414` 对应 run `33712261128` 成功，并用仓库外 Webhook 核对同一 SHA 的终态事件。
- [ ] 等待管理员人工合并 PR #10；合并前仅进行静态审核、文档和 Nexus 维护，不启动新的集成 RTL/Vivado。
- [x] 重跑 run `33714262900` 并确认 HEAD `15940b5` 的四道 CI 门、形式与突变检查全部成功。
- [x] 修复或重新验证仓库外 Webhook 对 workflow_run 重跑事件的接收；`da819cf` 对应 run `33728135382` 已由 GitHub 与 Webhook 双重确认成功。

## 2026-09-03 仓库外接收服务与集成审核续跑

- [x] 复核仓库外接收服务 `C:\Users\Epsilon\ENeuronWebhook`：`/healthz` HTTP 200，带完整事件标头的本地 `workflow_run` 接收返回 HTTP 200。
- [x] 用 Webhook 核对 PR #10 HEAD `6893964a`、run `33726377825` 的 `workflow_run completed/success`；GitHub PR 状态为 `OPEN / CLEAN`。
- [x] 只读审计 `NPU_NEURON_INTEGRATION_REVIEW.md`，确认 I1-I6 与模型、协议、参考模型、最坏情况、资源门槛、顶层证据七类材料仍未冻结。
- [x] 刷新 `.nexus-map` 摘要，使当前 HEAD、CI 终态和集成审核门状态一致。
- [ ] 等待管理员批准 I1-I6 及最小材料包；批准前不实现传统 NPU + 神经元集成 RTL，不运行新的 Vivado。

## 2026-09-03 集成材料包草案

- [x] 静态审计现有代码，确认仓库尚无完整传统 INT8 NPU 数值数据通路，NP7 共享突触执行器不能冒充 NPU。
- [x] 新增 `docs/planning/NPU_NEURON_INTEGRATION_MATERIALS.md`，提出 `64→32→10` INT8 MLP、定点格式、四权重组门控、样本边界提交和最坏情况矩阵。
- [x] 明确第一阶段只做片上单时钟 OOC，网口/DMA/PS 延后；I1-I6 仍需管理员批准。
- [x] 记录 PR #10 run `33730940941` 对 HEAD `b5165824` 已由 GitHub 与仓库外 Webhook 双重确认成功。
- [ ] 管理员裁定集成材料包 I1-I6 后，才进入 Python INT8 旁路/门控参考模型。

## 2026-09-03 CI 终态核对

- [x] 读取 run `33740218942`，确认状态 `completed / success`。
- [x] 用仓库外 Webhook 核对 HEAD `15d289e0` 的 `workflow_run completed/success`。
- [x] 确认接收服务健康检查 HTTP 200，且服务文件与日志不在仓库。
- [ ] 等待管理员批准 I1-I6；批准后再开展 INT8 NPU 参考模型与集成 RTL 任务。

## 2026-09-03 PR #10 合并后入口

- [x] 确认 PR #10 已合并，merge commit 为 `a076160`。
- [x] 确认 run `33742796085` 与仓库外 Webhook 终态均为成功。
- [x] 保留传统 NPU + 神经元集成审核门，未提前启动集成 RTL/Vivado。
- [ ] 管理员批准 I1-I6 后，先实现 `64→32→10` INT8 MLP 的 Python 旁路/门控参考模型，再进入 RTL。

## 2026-09-03 PR #11 合并后入口

- [x] 确认 PR #11 通过四道 CI 门并合并到 `main`，merge commit 为 `f48f4b6`。
- [x] 通过仓库外 Webhook 核对 PR #11 的检查完成和 closed 事件。
- [ ] 等待管理员批准 I1-I6；批准后进入 INT8 NPU 参考模型与门控语义验证。

## 2026-09-03 当前阶段终点

- [x] PR #13 通过四道 CI 门并合并到 `main`，merge commit 为 `1a8d0f2`。
- [x] 通过仓库外 Webhook 核对 PR #13 的 workflow 完成与 closed 事件。
- [ ] 管理员批准 I1-I6 后，实现 `64→32→10` INT8 MLP 参考模型，再进入集成 RTL。

## 2026-09-03 PR #12 合并后入口

- [x] 确认 PR #12 通过四道 CI 门并合并到 `main`，merge commit 为 `bc839b5`。
- [x] 通过仓库外 Webhook 核对 PR #12 的 workflow 完成和 closed 事件。
- [ ] 等待管理员批准 I1-I6；批准后进入 INT8 NPU 参考模型与门控语义验证。

## 2026-09-03 PR #16 合并后入口

- [x] PR #16（HEAD `46840e8`）四道 CI 门全部成功并合并，merge commit 为 `3850df7`。
- [x] 用仓库外 Webhook 核对同一 HEAD 的 `workflow_run completed/success`；服务健康检查仍为 HTTP 200。
- [x] 清除 NP4B TODO 中已完成的“再次批准进入 NP6”历史残留，避免恢复脚本误报未完成项。
- [ ] 管理员批准传统 NPU + ENeuron 集成审核 I1-I6；批准前不创建集成业务 RTL、不运行新的 Vivado。
- [ ] 批准后先实现 `64→32→10` INT8 MLP Python 旁路/门控参考模型，并建立逐样本 bit-exact 与最坏情况矩阵。

## 2026-09-03 PR #17 合并后状态刷新

- [x] 确认远端 `main` 已包含 PR #17 merge `0ca6a50d`，当前无开放 PR。
- [x] 确认 PR #17 run `33755848063` 四道 CI 成功，并由仓库外 Webhook 收到同一 SHA 的 workflow 完成与 PR closed 事件。
- [x] 将 Nexus 验证头、主分支合并点和状态摘要更新到 PR #17 合并基线。
- [x] 将当前事实写入 `WORKFLOW_STATE.md` 与 `findings.md`；不纳入用户未跟踪文件。
- [ ] 管理员批准传统 NPU + ENeuron 集成审核 I1-I6；批准前保持静态审计、文档和 Nexus 维护边界。
- [ ] 批准后实现 `64→32→10` INT8 MLP Python 旁路/门控参考模型，再进入 RTL 和 Vivado 门。

## 2026-09-03 集成审核门静态审计

- [x] 运行 `workflow_resume.ps1 -Mode Resume`，确认持久文件完整、HEAD 为 `8d23347`、活动 NP4B TODO 未完成项为 0。
- [x] 核对 GitHub 无开放 PR、最近 run `33763267873` 四道 CI 门成功、`main` 与 `origin/main` 同步。
- [x] 核对仓库外 Webhook `C:\Users\Epsilon\ENeuronWebhook` 健康检查 HTTP 200。
- [x] 保持 `np75_tmp_sparse_protocol.ys` 未跟踪且不纳入 Nexus/提交。
- [ ] 管理员批准 I1-I6；批准前继续保持“只做静态审计、文档和 Nexus 维护”的边界。
- [ ] 获批后实现 `64→32→10` INT8 MLP Python 旁路/门控 oracle。

## 2026-09-03 I1-I6 批准后集成启动

- [x] 管理员批准 I1-I6：`64→32→10` INT8 MLP、8×8/4 bit 输入、INT32 累加/ReLU 饱和、四权重组门控、边界原子提交、OOC→XC7Z020→网口顺序。
- [ ] 实现 Python 旁路/门控参考模型，明确 INT8 饱和、INT32 累加、组门控和批边界 epoch。
- [ ] 编写固定向量与最坏情况测试：全开、全关、零活动、频繁切换、背压、清除、推理冻结、非法索引。
- [ ] 旁路模式与门控全开模式逐样本 bit-exact，通过后才进入 RTL。
- [x] 建立 Python oracle 首个纵向切片：旁路全开和全关门控行为。
- [ ] 补齐饱和、epoch 原子切换、背压、清除、推理冻结和非法索引测试。
- [ ] 参考模型通过后实现独立 NPU OOC RTL，再接 ENeuron wrapper。

## 2026-09-03 PR #21 合并后基线

- [x] PR #21 四道 CI 门全部成功并合并到 `main`，merge commit 为 `588e7d5`。
- [x] 用仓库外 Webhook 核对 PR #21 HEAD `bc546c0` 的 `workflow_run completed/success`。
- [x] 同步状态文档和 Nexus 到 PR #21 合并点；保持用户未跟踪文件不变。
- [ ] 管理员批准 I1-I6；批准前不创建集成业务 RTL、不运行新的 Vivado。
- [ ] 获批后实现 `64→32→10` INT8 MLP Python 旁路/门控 oracle。
# 2026-09-03 持久工作流当前状态

- [x] PR #18 文档与 Nexus 状态更新通过四道 CI，并合并到 `main` (`1877140c`)
- [x] 使用仓库外 Webhook 交叉确认 PR #18 同 SHA 的工作流终态
- [ ] 等待管理员批准传统 NPU + ENeuron 集成审核 I1-I6 与材料包
- [ ] 获批后实现 Python 旁路/门控 oracle，再进入集成 RTL、协同仿真和 Vivado 物理验证

- [x] PR #19 合并后同步主线到 `63028d4`，记录 Webhook 短暂掉线与恢复

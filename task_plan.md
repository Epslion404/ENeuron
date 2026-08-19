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
- [x] 将 `g4_capability_validation_proposal.md` 修订为 V2 审核稿
- [x] 对 V2 做独立 Temporal、Host 权限、P5 和 Goal 扩展性反证审计
- [x] 将审核稿修订为 V3：四阶 Temporal motif、no-replay P4、双层 P5、P6 扩展性
- [x] 用户审核 V3 的六项冻结决策
- [x] 用户审核后拆分正式 Python、RTL 和验证任务

## V3 批准后实施阶段（2026-08-13）

- [x] T0：独立 Tile 报告硬门、机器摘要、新鲜度检查与文档同步
- [x] T1：冻结 G4 seed、hash、decoder、Temporal、split 和推理状态测试合同
- [x] T2：实现 `g4_benchmark.py` 与可复现 manifest
- [x] 重跑 T0、G4 新测试、`compileall` 和既有完整回归
- [x] T3 前置：完成 Tile/Host/容量只读审计并形成 `g4_t3_execution_spec.md` 审核稿
- [x] 收齐三路独立反证并修订 T3 审核稿：公共置换、RandomPlan、80-tick 计分、no-replay、canonical 数据、确定性搜索、checkpoint 与 commit fresh-run
- [ ] 用户审核 T3 的 12 项二级冻结决策
- [ ] T3：在冻结 benchmark 上实现训练策略与 P0-P4 能力门槛
- [ ] P5：完成接口等价 FIFO cohort 与真实 XPM cohort 的隔离验收
- [ ] P6：冻结 Host 协议 V2，并实现共享 RAM 可扩展架构验收

## 原始 Goal 对齐复核（2026-08-13）

- [x] 从当前 RTL、Host 协议和验证产物重建“数字神经元/神经网络硬件基石”的实际证据
- [x] 区分固定 4->2->2 原型、训练真实性、可扩展架构和板级闭环，不沿用宽泛总称
- [x] 形成并反审计 `original_goal_alignment_review.md`，把板级部署、共享 RAM 大规模化和 G4 研究从最小基石必要条件中移出
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
- T3 正式编码前必须批准 `g4_t3_execution_spec.md`；当前全调用逐字段等价已被定向探针判定为 FAIL，待以 EP_START 白名单复位 + 推理区间冻结的精确合同验收
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
- [x] `host_bridge_v1_proposal.md` 的冻结决策已落实到 RTL、oracle、测试和报告
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
- [x] 汇总 G3a 数字前端证据并更新 `verify_goal.py`、`goal_audit.md` 和项目文档

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
- [x] 标签完成后评估原始计数/分频方案，形成独立 `TODO.md`
- [x] 复核 Pulse-Mini 资源预算、阶段门槛和非目标，单独提交规划

### 本阶段顺序约束

- `v1.0` 只包含已经通过 M1-M4 的当前实现、验证资产和签核证据。
- `TODO.md` 必须在 `v1.0` 标签之后创建，作为后续开发规划单独提交。
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

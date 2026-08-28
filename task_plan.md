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

## Pulse-Mini 规划收口阶段（2026-08-19）

- [x] 核对当前工作树、`v1.0` 标签和 Pulse-Mini 实施基线
- [x] 复核原始计数/分频方案的真实 Vivado 资源与时序边界
- [x] 将 Pulse-Mini-L、L2、阵列和数字识别规模约束写入 `TODO.md`
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
- 完整报告为 `SIMULATION_COMPARISON_REPORT.md`，原始数据为 `comparison_simulation_results.json`。

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
- 10 个固定 seed、每个 3 epochs 的正式实验已落盘 `digit8x8_d2_results.json`；validation BAcc 均值 4.61%、最小 1.11%，coverage 均值 56.04%、最小 39.26%，达到 `BAcc≥70% 且 coverage≥90%` 的 seed 为 0/10。
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
- [x] 生成 `PROJECT_REPORT.md`
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
- [x] 形成 `NPU_PRUNING_TODO.md`，并在根 `TODO.md` 增加待审核入口
- [x] 用户批准 NP0 八项决策，并要求 ENeuron、Pulse-Mini-L、Pulse-Mini-L2 三种神经元全部运行
- [x] NP1：统一黄金模型与不可作弊工作量计数（19 项 B0 测试、固定向量和 SHA-256 摘要通过）
- [x] NP2：三种神经元完成 S0-S3、gain 1/2/3 扫描及同分/clip/稳定性统计；选择 `1/2/1`
- [x] NP3：三模型一次/渐进/错误符号和完整 TRAIN/INFER 冻结账本通过；选择一次剪枝
- [x] B2.1：三模型三候选均通过；output-2:4 为 120 次读取/发射，按 KISS 选为 V1
- [ ] NP4：审核六项 V1 接口决定后实现隐藏/输出统一 2:4 RTL；NP5-NP7 仍未启动

### 本阶段错误记录

| 错误 | 尝试 | 处理 |
|---|---:|---|
| Git 因仓库所有者为 Administrators 拒绝普通命令 | 1 | 不修改全局配置；后续只用单次 `git -c safe.directory=...` 读取状态 |

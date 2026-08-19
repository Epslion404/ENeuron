# 调研与实验发现

## 当前项目

- 项目目录初始为空，没有可复用的模拟器或测试框架。
- 采用标准库 Python，避免把 NumPy/PyTorch 依赖带入硬件原型验证。

## 设计假设

- 输入采用离散时间步的二值事件。
- 突触权重采用有符号定点整数；脉冲到达时直接条件累加权重。
- 三因子候选通过有符号调制信号兑现资格迹线，覆盖无监督/奖励/局部监督接口。
- 复杂度先用状态位数和每事件操作数做代理，后续 RTL 综合再测 LUT/BRAM/Fmax。

## 安全边界

- 模拟结果只证明行为和相对取舍，不等价于 FPGA/ASIC 的综合面积、功耗或时序结果。
- 任务调制信号是外部提供的局部训练信号；单个神经元不会自行产生完整的多层信用分配。

## 实验结果

- `counter_if`：10 种训练顺序的区分成功率 0%，正负模式都产生 2 个脉冲，权重不变。
- `pair_stdp_lif`：10 种训练顺序的区分成功率 0%，四个权重都饱和到 7，说明无任务调制时会把两类活动一起增强。
- `three_factor_lif`：10 种训练顺序的区分成功率 100%，最终权重稳定为 `[7, 7, -7, -7]`，正样本平均 6 个脉冲，负样本平均 0 个脉冲。
- 推荐模型状态位代理为 169 位，基线为 84 位，二因子模型为 108 位；推荐模型每输入事件约 16 个抽象操作，二因子约 9 个。
- 100 组包含丢脉冲或额外同类脉冲的扰动测试中，推荐模型正样本非零响应率和负样本零响应率均为 100%。

## 推荐取舍

- 目标是任务导向自训练、延迟奖励或局部误差：保留每突触 eligibility。
- 目标只是无监督相关性学习或聚类：可以移除 eligibility，使用二因子 STDP，减少状态和更新操作。
- 推理阶段必须关闭 `learn_enable`，并验证权重在整个推理过程中不变。

## 网络级实验

- `DigitalSNN2Layer` 使用 4 个输入轴、2 个隐藏神经元、2 个输出神经元；隐藏到输出固定 1 tick 路由延迟，并在 episode 结束时 flush pending spike。
- Host 在 episode 结束时捕获每个神经元的 eligibility 快照，用 `commit_id` 延迟提交调制；重复或未知 commit 会被拒绝。
- 20 个训练种子下，可寻址目标调制的干净任务成功率为 100%，100 个扰动样本的平均准确率为 100%。
- 全局 reward 配合逐 tick WTA 时，20 个种子干净准确率均值仍只有 22.5%；WTA 限制同 tick 竞争，但不能自动解决隐藏层信用分配。
- 两阶段 Host 训练在 20 个种子下达到 100%：先用目标调制训练并冻结隐藏特征，再用 epsilon 探索和 reward 只训练输出动作层。
- 该结果证明 Host 训练闭环可用，但不证明全局奖励、多层信用分配或通用任务已经解决。

## Goal 证明审计（2026-08-11）

- 当前 `task_plan.md` 仍将“RTL 与 Python 黄金模型逐周期 bit-exact”列为未完成项，因此现阶段不能声称设计已经完全符合 goal。
- 已有证据覆盖算法行为、训练/推理模式隔离、网络闭环和周期传输模型；尚未覆盖真实 HDL 编译仿真、形式性质、综合、时序、资源、功耗与板级运行。
- “作为 AI 自训练与推理的硬件基石”应被定义为可组合、可训练、可冻结推理且接口确定的最小单元；它不等于已经证明可解决任意任务、具备通用信用分配或达到实用规模。
- 2026-08-11 实际回归：`python -m unittest -v` 共运行 27 项，25 项通过、1 项失败、1 项错误；`rtl_smoke.py` 因 `rtl_reference.py` 的负移位异常退出，延迟 modulator 测试也未产生预期权重更新。`python -m compileall -q .` 通过。
- `rtl_reference.py` 与 `digital_lif_core.sv` 目前并非 bit-exact：至少存在 eligibility 衰减公式、同周期多次非阻塞写覆盖、不应期输入门控、post trace 更新和阈值稳态机制差异。
- YosysHQ SBY 文档把 `bmc/prove/live/cover` 分成不同验证模式；形式工具只证明已编码性质及其假设范围。EQY 用于两个电路设计间的形式等价，不能证明高层 AI 目标本身。
- Verilator 官方文档支持 lint、断言和覆盖率插桩；AMD 官方文档要求在完整布局布线后使用 Timing Summary 做时序签核，并指出准确功耗需要真实切换活动而非默认活动率。
- 三因子学习的一手研究支持“eligibility trace + 第三因子”作为延迟信用分配机制，但这只支撑学习规则选择，不推出当前定点参数、RTL 实现或任意任务性能正确。

## V1 语义冻结发现（2026-08-11）

- `recommended_design.md` 的单时间步顺序先执行输入积分，后写“不应期屏蔽输入”，无法唯一确定不应期内 `I` 是否吸收事件；RTL 前必须改成唯一 next-state 方程。
- 当前规格没有定义 pre/post 同 tick 时 eligibility 的合并方式，也没有定义 `tick_valid`、`mod_valid`、`weight_we` 同周期的优先级。
- V1 应避免对同一寄存器在一个 `always_ff` 周期中多次非阻塞赋值；先在组合逻辑中累计唯一 next value，再在时钟边沿提交。
- 高层 `ThreeFactorNeuron` 当前实际使用趋零衰减、更新后的 `pre_trace` 参与 eligibility、`post_trace` 累加以及自适应阈值；`digital_lif_core.sv` 当前分别使用算术右移、旧 `pre_trace`、post trace 直接覆盖且没有阈值寄存器，不能直接声称与算法模型等价。
- 本机存在 `winget` 和 `choco`，可以尝试安装真实 HDL 工具；在安装并运行编译器前，任何“RTL 已实现”的结论都只能保持未验证。
- 已通过真实 Icarus Verilog 12.0 编译并运行 `digital_lif_core.sv`；`rtl_cosim.py` 在 5 个 seed、每个 128 个随机 tick（另含 mod-only、CSR 写、INFER 冲突周期）下逐字段比较 131 个状态，全部通过。
- Yosys 0.56 `hierarchy -check; proc; opt; check; stat` 通过，报告 0 个结构错误；同时报告 6 类宽度/内存展开警告，当前仍需作为实现质量问题记录。
- Verilator 5.040 可解析 RTL，但默认 lint 仍有 29 个 `WIDTHEXPAND/WIDTHTRUNC` 警告；`--Wno-fatal` 才能返回成功，尚不能称为零警告 lint 签核。
- 当前 Python/静态/RTL 回归总计 30 项通过；这证明单核行为闭环，不证明网络 RTL、FIFO、snapshot/commit 或目标器件 PPA。

## 网络协议缺口（2026-08-11）

- `TileCycleTransport` 尚未实现 `TICK_BEGIN(event_count)` 的数量校验；少发、多发或错 tick 事件不能作为原子事务被拒绝。
- `EPISODE_END` 路由 flush 在输出 FIFO 溢出时可能先消费部分 pending spike，再抛出异常，缺少 all-or-nothing 语义。
- 多个 eligibility snapshot 的提交顺序会影响饱和权重结果；必须冻结为单调 `commit_id`，或实现与顺序无关的基准权重/累加器。
- `DigitalSNN2Layer.apply_host_modulator` 当前缺少 TRAIN/IDLE、episode、地址和提交顺序门控；网络级推理冻结还没有对 traces、eligibility、threshold 做完整断言。

## 多周期引擎初审（2026-08-12）

- 最新 `digital_lif_engine.sv` 已由 Icarus Verilog 以 `-g2012` 编译通过；这只证明语法与展开成立，不证明事务语义等价。
- 当前 `mod_valid=1, modulator=0` 会进入 `S_MOD_SCAN` 并在末地址清除 `snapshot_valid`；Python 黄金模型把零调制定义为 no-op 并保留 snapshot，二者确定不等价。
- `ADDR_BITS` 默认固定为 2；当 `N_INPUTS > 4` 且调用者忘记同步修改时，`scan_index` 会回绕而无法到达末地址。参数必须自动推导或增加 elaboration 检查。
- `TICK_SCAN` 使用 32 位 `current_acc_work` 跨地址累计，扫描结束后才执行一次 `sat_state`；这一点与黄金模型“先求和、后饱和”一致，仍需随机反例验证。
- 首轮 Yosys 检查发现 `address_as_int` 同时由 `always_comb` 和 `always_ff` 驱动，形成真实多驱动；必须删除共享临时变量后再接受结构检查结果。

## 多周期引擎签核（2026-08-12）

- 多周期核通过 20 个 seed × 1000 个混合事务，共 20000 个事务；另有 10 个 seed × 256 个事务直接断言 busy 期间架构状态不变和事务延迟合同。
- 最终 FSM 把每个突触拆为读取/衰减与更新两拍，并把电流饱和、膜电位相加、发放判断分拍；定宽 8/12/16 位趋零衰减消除了通用 32 位函数产生的无意义长进位链。
- Vivado 2024.1、`xc7a35tcpg236-1`、100 MHz OOC post-route：`WNS=+0.469 ns`、`TNS=0`、setup/hold 失败端点均为 0。
- 最终资源：813 LUT、544 FF、0 BRAM、0 DSP；相对单周期参考核 2338 LUT / 214 FF / WNS=-22.793 ns，LUT 明显下降，寄存器因流水和事务工作区增加。
- DRC 没有 error/critical warning，但有一个 OOC 环境的 `CFGBVS-1` warning；运行器日志首行的 Tcl store 权限 critical warning 来自本机启动环境，不是设计 DRC。功耗 0.080 W、Medium confidence，仍只是 vector-less OOC 估算。

## 4->2->2 Tile 初次物理实现（2026-08-12）

- 20 seeds × 500 个 Tile 混合事务，共 10000 个事务与独立 Python oracle 一致；完整回归 41 项通过。
- Vivado 2024.1 初次 OOC route 成功，内部最差 setup/hold 均为寄存器到寄存器路径，分别为 +0.231 ns / +0.128 ns；资源 3157 LUT / 1972 FF / 0 BRAM / 0 DSP。
- 初次报告缺少 `HD.CLK_SRC`，AMD UG905 对 OOC 实现建议同时使用 `create_clock` 和 `HD.CLK_SRC` 改善时钟延迟、偏斜与 CPR 估计；最终签核应以后续补约束重跑结果为准。
- Tile 顶层数据端口没有板级 input/output delay 或 partition-pin 位置，因此当前 OOC 只签核内部寄存器路径，不签核未来 Host/总线接口的端口时序。

## V3 决策批准后的实施发现（2026-08-13）

- 用户已批准 V3 六项冻结决策，后续实现不得用 Teacher、Hybrid、reward、Python 或 RTL 结果相互代偿。
- 最新独立 Tile 原始报告为 `3152 LUT / 1972 FF / 0 BRAM / 0 DSP`，100 MHz OOC 的 WNS/WHS 为 `+0.213/+0.026 ns`，TNS/THS 和 setup/hold failing endpoints 均为 0。
- 独立 Tile 的 OOC 白名单告警当前是 DRC `CFGBVS-1 x1` 与 methodology `TIMING-18 x180`；它们反映未指定板级配置电压和端口 delay，不能被描述为板级签核。
- T0 资源预算与当前测量值分离：预算冻结为 `LUT <= 3200`、`FF <= 2000`、`BRAM36/BRAM18/DSP = 0`；摘要仍记录精确实测值。
- G4 数据泄漏检查必须使用排除 split、seed、sample index、skeleton id 和 label 的 `input_hash`；manifest 完整性另用包含 label 的 `example_hash`。
- Temporal 正式数据冻结为跨 model seed 共享；`generate_temporal_split` 不再接收模型 seed，统计单位为同一数据集上的 paired model-seed。
- `input` schema 精确限定为 `episode_ticks/events`，`input_hash` 只重建这两个语义字段；额外 `label_hint/nonce` 不能泄漏标签或掩盖跨 split 重复。
- Temporal validator 现在接收冻结 `master_seed/B`，在结构检查后重放生成器并逐 split 做 canonical exact comparison，认证 seed、sample/skeleton ID、phase、顺序和 provenance。
- manifest 升级为 `g4_temporal_dataset_v2`，同时记录 `input_hashes/input_sha256` 与 `example_hashes/example_sha256`，源码固定绑定实际 `g4_benchmark.py`；development manifest 共 1312 个唯一输入/完整样本。
- 最终一键审计已闭环：159 项回归、两套有限 formal、额外 10000 个 Tile 事务、独立 Tile、真实 XPM 与完整系统 Vivado 报告均通过；XPM 和系统 CDC 的固定 marker 均使用各自严格解析器，不放宽通用 `KEY=VALUE` 合同。
- 该 PASS 只恢复并加强既有 G1/G2/G3a 工程签核，同时证明 Temporal development 数据合同可复现；它不等于三任务 P0a/P0b、训练能力、P5 RTL 任务 cohort、P6 扩展性或完整 G4 通过。

## T3 P0-P4 实施审计（2026-08-13）

- 现有 `HostTrainingController.reward_modulator(label, result)` 同时读取真实标签并按 hidden/output 活动生成 neuron-specific 调制，不能作为 V3 P3 的纯全局 reward 证据。
- T3 主实现应独立于历史 `network_sim.py` 训练 helper：复用数字神经元/网络动力学和 commit 接口，但把数据、训练权限、strict decoder、负对照、统计与结果 manifest 放在新的 G4 模块中。
- 当前 RTL 主结论限定 no-WTA；所有正式 P1/P2/P3 实验必须显式构造 `hidden_wta=False, output_wta=False`，历史 WTA sweep 只能保留为旧探索证据。

## 4->2->2 Tile 最终签核（2026-08-12）

- 补 `HD.CLK_SRC` 后的最终 OOC：100 MHz WNS +0.148 ns、TNS 0、WHS +0.057 ns、THS 0；3861 个内部端点零失败，route error 0。
- 最终资源为 3156 LUT / 1972 FF / 0 BRAM / 0 DSP；功耗 0.104 W、Medium confidence、无活动文件，只能作为 vector-less 估算。
- 固定黄金测试确认一 tick 跨层路由、非零 eligibility、合法 MOD 后真实权重改变、过期 commit 拒绝、零调制和 INFER 冻结；完整回归为 42 项通过。
- 当前 Tile 直接接收每 tick 的 4-bit spike mask。`TICK_BEGIN/INPUT_EVENT/FIFO` 和带 `episode_id/tick/neuron_id` 的输出标签仍是外层传输协议，不是当前 Tile 已实现端口。

## Tile 协议修复与有限形式验证（2026-08-13）

- 组合派发曾按“合法命令”跳过非法高优先级请求，而时序仲裁按“命令存在”拒绝该事务，导致返回错误的同时仍可能写权重或启动 TICK；定向 Icarus 回归已复现并锁定该反例。
- 修复后，SNAPSHOT、WEIGHT、MOD 的存在先确定优先级，合法性只决定是否产生子核请求；非法高优先级命令不会放行任何低优先级请求。
- Yosys 0.56 的 `async2sync` 会自动 lower SystemVerilog `$check`；私有 Tile 信号不能从顶层 harness 用层次名可靠引用，断言必须放在 Tile 的 `FORMAL` 条件块或显式导出。
- 真实四核 Tile 在仅约束首拍复位、后续释放的敌对输入下完成 24 拍 BMC：约 451 万变量、1252 万子句，无反例；覆盖最长 17 周期训练 TICK，但不是无限时域归纳或全状态形式等价。
- 2026-08-13 Vivado 2024.1 OOC 重跑结果：setup `+0.053 ns`、hold `+0.026 ns`、route error 0，3144 LUT / 1971 FF；功耗 0.103 W 为无活动文件的 Medium-confidence 估算。

## Host Bridge V1 第二轮反例审查（2026-08-13）

- 原响应布局只保留 6-bit opcode，不能完整关联 8-bit 命令；已改为命令/响应同构 128-bit 布局，响应有效性仅由外部 `valid` 表示。
- TRAIN `EP_END` 若先 flush、后检查 commit，会在重复或过期 commit 上形成不可回滚的部分提交；必须在 flush 前同时检查 snapshot 槽、commit 严格递增、episode/tick 状态和 Tile ready。
- `bridge_rst` 会复位真实 Tile 核心并把权重恢复为初值，不是仅清 transport；保留权重的恢复路径必须使用有序、不可抢占的 `ABORT`。
- 当前设计没有 completed transaction cache；`txn_id` 只能用于关联，不能提供重传去重或幂等 exactly-once。
- tick 计数需要 17-bit 内部尾态：允许 `16'hffff` 成功提交，随后只允许 `EP_END/ABORT`，防止 16-bit 静默回绕。
- Python `flush_route()` 无条件推进输出层一次；即使 `pending_hidden=0`，RTL 也不得优化掉该 output-only tick。
- Tile 权重读口是组合口，Bridge 必须使用 setup/capture 两拍锁存地址和数据。
- 本机 Vivado 2024.1 的 `xpm_fifo_async` 支持冻结的 depth/width/FWFT/CDC 参数；真正风险在 reset-busy 门控和“只有实际 FIFO 接受边沿后才释放事务”。
- 现有 RTL 测试仍未覆盖真实双时钟 CDC、响应背压和随机 producer/consumer；这些已列入 Bridge 验收门槛，不能沿用单时钟 Tile cosim 代替。
- Bridge 若要在 flush 前验证 commit 严格递增，不能猜测或复制 Tile 元数据；Tile 需导出只读 `last_commit_valid_state/last_commit_id_state`。
- `STATUS_READ` 必须独立于 `tile.ready` 和 episode active 状态，否则 fatal 或异常 busy 时无法诊断；需要 Tile 的命令在 LAUNCH 状态等待 ready，本地命令直接完成。
- delayed MOD 只快照 eligibility，不快照权重基准；pending snapshot 期间若允许 `WEIGHT_WRITE`，最终更新会依赖 Host 插入的模型写操作，因此 V1 冻结为“可读、不可写”。
- 一个 flit 可能同时违反多个规则；若不冻结错误优先级，Python oracle 与 RTL 即使都无副作用也可能返回不同 status。审核稿已增加确定性首错顺序。

## Host Bridge V1 第三轮终审（2026-08-13）

- TRAIN `EP_END` 的 flush spike 必须在 flush done 边沿锁存到事务私有 `ep_end_flush_spikes`，否则后续 SNAPSHOT 会覆盖 Tile 的单周期输出。
- STATUS 必须分成 session 页和 snapshot/commit 页；page 1 在 snapshot/last commit 无效时对应 ID 强制返回 0，避免 RTL 与 oracle 对寄存器残留产生分歧。
- `EP_START` 与 `EP_END` 一样使用完整预检和响应接受边沿提交；Host 可见 architectural session/input-tick staging 只在 `response_accept` 更新，事务 working state 可在执行中更新。
- 错误优先级不能把依赖 session 模式的动态字段检查放进共同前缀。共同 `BAD_FIELD` 只检查静态布局；INFER `EP_END` commit 必须为 0 放在 `BAD_STATE/EPISODE_ID` 之后。
- `fatal_error/fatal_opcode/fatal_phase` 是首次内部故障 sticky 状态；普通协议错误不修改，后续 fatal 不覆盖，只有 hard reset 清除。phase 覆盖 EP_START clear、TICK、EP_END flush/snapshot、MOD、WEIGHT、ABORT clear 和 controller internal。
- 四个 2-bit modulator 只允许 `11=-1/00=0/01=+1`；`10=-2` 在启动 Tile 前返回 `BAD_FIELD`，以匹配当前符号调制软件模型。
- 本机 Vivado 2024.1 的 `xpm_fifo_async` 源码确认支持 depth 16、128-bit、FWFT、`CDC_SYNC_STAGES=2`、`wr_rst_busy/rd_rst_busy`；FWFT 配置明确补充 `FIFO_READ_LATENCY=0`。官方实例模板同时明确 `rst` 必须同步于写时钟，因此 Bridge 改为 Host/Tile 两域分别全同步采样 `bridge_rst`，不把异步置位复位直接接入 XPM。
- XPM 后续 reset 不能在上一次 write-side `wr_rst_busy` 退出前重入。V1 选择外部合同而非片内排队器：只有 command/response 两个 FIFO 的 write-side busy 都为 0 后才允许再次断言 `bridge_rst`；不满足该条件的物理接口必须在板级适配器中延迟 reset 请求。
- 实现拆为七类依赖任务：Tile 原语、Python oracle、Bridge controller、XPM wrapper、双时钟协同仿真、formal/CDC、Vivado OOC。旧 Tile post-route 报告不能作为增加 ROUTE_FLUSH/Bridge 后的签核证据。
- T2 bit-exact 审查进一步冻结：错误响应 `arg0/arg1` 清零；H0/H1 地址 0..3、O0/O1 地址 0..1；epoch 为 32-bit modulo 且仅合法 MOD（包括全零调制）增加；WEIGHT_WRITE 不增加；INTERNAL_FATAL 不提交正常 architectural next-state。

## Host Bridge T3/T5 实现发现（2026-08-13）

- T3 真实集成协同仿真必须同时比较三层真值：128-bit response、11 个 Host architectural/fatal 字段、79 个 Tile/四核内部与 commit 字段；仅比较响应不足以证明错误无副作用或 response_accept 提交边界。
- controller 的 Host architectural 状态允许在 Tile 执行期间保持旧值，只有响应接受边沿提交；Tile 状态可在响应前完成更新，因此 PRE 检查应使用“旧 Host 架构 + 新 Tile 真值”，POST 检查使用“新 Host 架构 + 同一 Tile 真值”。
- 20 seeds x 1000 混合命令会充分覆盖所有成功 opcode，但任意 128-bit 位型主要命中 BAD_OPCODE/BAD_FIELD；动态首错链仍需独立定向流硬性覆盖所有非保留、非故障注入状态码。
- T5 双时钟 scoreboard 以 `host_cmd_valid && host_cmd_ready` 作为 outstanding ledger 登记点，以 `host_rsp_valid && host_rsp_ready` 作为按序 oracle 提交/比对点；不能用 producer 发起时刻或 Tile 域 FIFO 读边沿替代 Host 可见事务边界。
- hard reset 是破坏性边界：T5 在 reset 断言后丢弃全部 outstanding ledger、重建 Python oracle，并验证 FIFO/session/commit/epoch 清空及权重恢复 INIT_WEIGHT；不得期待 reset 前命令或响应在 reset 后恢复。
- T5 的随机流必须独立覆盖 command FIFO empty/full、response FIFO empty/full、两侧同时 push/pop、16 深度指针回绕和长时间 response backpressure；仅用低占用随机 ready 不能证明满队列门控。

## Host Bridge T4/T7 最终签核（2026-08-13）

- Icarus FWFT 模型必须区分“外部消费当前预取字”和“RAM 字搬入预取槽”。首次预取也要推进内部 Gray 读指针，否则第 17 个可见字无法释放 RAM 槽并导致 transport 死锁。
- Vivado 2024.1 官方 XPM xsim 实测本配置 `FIFO_WRITE_DEPTH=16 + READ_MODE=fwft` 的 command/response 外部可见容量均为 17；两条 FIFO 的填满、排空、64 字回绕、长背压和 hard reset 全部通过。
- XPM wrapper 综合为 4 个 RAMB36，仿真专用 reset 重入断言没有进入综合网表；wrapper CDC 只有 4 条 XPM 内部 reset synchronizer `CDC-3 Info`。
- 完整系统 post-route 使用 Host 50 MHz、Tile 100 MHz：Host WNS/WHS `+14.306/+0.105 ns`，Tile WNS/WHS `+0.081/+0.058 ns`，两域 TNS/THS 和 setup/hold violations 均为 0。
- 系统资源为 `3682 LUT / 2486 FF / 4 RAMB36 / 0 DSP`；route errors、DRC Error/Critical Warning 均为 0。功耗 `0.112 W` 为无活动文件的 Medium-confidence vector-less 估算。
- 系统 CDC 共 8 条，全部在官方 XPM 内部：4 条 Gray pointer `CDC-6 Warning` 和 4 条 reset sync `CDC-3 Info`；XPM 外 Critical/Unsafe/Warning 为 0。
- OOC 仍没有真实顶层 input/output delay、partition pin、配置电压和板级复位源。Vivado `report_cdc` 明确跳过无 input delay 的顶层端口，因此 `bridge_rst` 的物理异步来源必须留到板级适配/XDC 签核。

## G4 能力边界前置审计（2026-08-13）

- `make_dataset()` 只有两个固定训练模板；`clean_accuracy` 复用训练样本，`make_noisy_dataset()` 也只从相同模板做至多一次删除和一次同类插入，当前没有真正的 train/validation/test 隔离。
- `run_network_sweep.py` 的 teacher 模式没有传入 `init_seed`，20 个 seed 只改变训练顺序和扰动集；不能据此声称完成 20 个独立模型初始化。
- `network_sweep_results.json` 早于当前 `network_sim.py`，且 `verify_goal.py` 不执行网络 sweep 或检查结果新鲜度，因此其中 teacher/hybrid 100%、reward-only 22.5% 只能作为历史结果，不能作为当前一键验收证据。
- 当前网络和 Host 协议硬编码二分类 4->2->2；`teacher_modulator()` 直接按标签向隐藏层和输出层发放 neuron-specific signed modulator，而 reward-only 只用全局正确/错误信号按活动路径门控，两者验证的是不同信用信息条件。
- G4 前置验证必须至少包含独立任务族、严格 split 哈希隔离、独立初始化/训练顺序/数据 seed、推理前后全部学习状态逐字段冻结检查，以及 majority、未训练网络和 label-shuffle 负对照。
- 主会话使用无落盘脚本独立复跑三任务探测，Python 3.14.2；`network_sim.py` SHA-256 为 `9AF92DC0C8FA5447EF5986E35392AB240999F7B2BDDA192CEC30B26CADD3F798`，`neuron_sim.py` 为 `1B31C6A84A77B4B47669D02EB2A7FC46C6BDD70051799DCF059E75D51002E3A2`。
- 10 seeds 探测结果：Spatial teacher/hybrid 均为 2560/2560，reward 为 384/2560；Temporal 三模式均为 0/2560；XOR teacher/reward 为 0/2560，hybrid 为 8/2560。
- Temporal/XOR 的输出几乎全部是 `prediction=-1`，所以零准确率首先混合了输出活动不足，不能直接当作时间表征或 XOR 容量失败。正式方案必须先有 label-blind activity calibration 和 decision coverage 门槛。
- 当前 `_predict()` 在非零平局时返回 class 0，会形成类别偏置；G4 验收应在外部 evaluator 使用 strict spike-count，平局统一 abstain 并计错，不必改核心神经元状态方程。
- 当前 Tile 没有 WTA 仲裁，而历史 reward/hybrid sweep 在 Python 中启用了 WTA；no-WTA 才能作为当前 RTL 主结论，WTA 结果只能作为新增 RTL 的候选上限。
- e-prop 原文支持“局部 eligibility trace x top-down learning signal”的结构，并明确 neuron-specific feedback 与 global learning-signal baseline 不等价；这与当前 teacher 和 reward-only 的信息条件差异一致，但不证明本项目的定点规则已经实现 e-prop。
- GEM 原文定义任务测试矩阵及 ACC/BWT/FWT；本项目可以借用这些持续学习评价指标，但不能因此声称已实现 GEM 算法。

## G4 V2 反例审查与活动校准（2026-08-13）

- 48 tick、固定全 2 权重、关闭学习时，`B=1` 的三任务 hidden/output 均无活动；`B=2` 时三任务 hidden/output active rate 均为 100%。同一全 2 初态下，高层模型与四个 `RtlReferenceNeuron` 在 300 个样本上的 hidden/output spike count 完全一致。
- 随机初始化 `1..3` 的 20 seeds 中，`B=2/3/4` 都存在 seed 15 完全无输出，XOR 还有 seeds 3/8 仅 75% 活动。burst 只可作为固定初态编码正对照，不能保证随机初态或训练后网络不死亡，也不能靠继续放大 `B` 掩盖失败。
- 旧 Temporal `ABABABAB/BABABABA` 的首事件直接泄漏标签。V2 改为 `AABABBAB/ABBAABAB`，两类首尾相同、A/B 各 4 次，并要求 first-only、last-only、直方图和时间骨架 nuisance-only 基线接近 50%。
- 所有任务必须先生成 label-blind 时间骨架，再构造类别 counterfactual；抖动、拒绝采样、首尾 tick、间隔分布和总事件数均不得携带标签。Calibration 独立成 split 并进入 manifest/hash 隔离。
- label shuffle 的低 overall accuracy 可由全 abstain 伪造。V2 增加 prediction 固定的 evaluation-label permutation 零分布，并要求 training-label shuffle 同时报 activity、coverage 和 conditional accuracy。
- 二分类下 `(action, reward)` 可精确恢复 label。P3 主结论因此只允许向四核广播同一标量调制；预先冻结且不依赖 action/label/task/sample 的 neuron-specific feedback 单列为 feedback-alignment 候选。
- `hybrid_no_wta` 在当前全局 `learn_enable` 下只能冻结隐藏权重，不能冻结隐藏 trace、eligibility 和自适应阈值。冻结全部隐藏学习状态需要分层 `learn_enable`，并重做 bit-exact、formal 和 Vivado 签核。
- P4 带 task context 时只能称 task-aware/task-incremental continual learning。每个 model seed 内的 6 个任务排列是重复测量，统计与 bootstrap 单位必须是 seed，并要求至少 8/10 seeds 按排列聚合后通过。
- P5 必须用 `RtlReferenceNeuron + HostBridgeOracle`，不能直接用语义不同的 `network_sim.py`。每个 RTL seed 先 hard reset、12 写、12 读回并检查元数据；训练遵守单槽 snapshot，commit ID 在 16-bit 不回绕范围严格单调。
- P5 spike count 只在 `host_rsp_valid && host_rsp_ready` 握手时累计，并分别读取 `TICK_COMMIT.arg0[3:2]` 与 `EP_END.arg0[3:2]`。Host 黑盒只验响应、计数、权重和元数据；eligibility/trace/threshold/membrane 等只作为 testbench 白盒证据。
- 最新独立 Tile 原始报告为 3152 LUT / 1972 FF、WNS +0.213 ns、WHS +0.026 ns；README/`goal_audit.md` 仍是旧数字，且 `verify_goal.py` 尚未独立审计 Tile 报告。V2 将其冻结为正式实现的 T0。

## G4 V3 反证审计（2026-08-13）

- V2 Temporal `AABABBAB/ABBAABAB` 可由第 2 或第 5 个 symbol 100% 分类；前四位 A 计数为 3/2，后四位为 1/2，多个固定位置 bigram 也直接泄漏。任意两条不同固定字符串都至少有一个绝对位置不同，不能继续靠替换固定模板解决。
- V3 使用循环 motif `AABABABB/AABBABAB`，均匀 phase 0..7，输出旋转后的 8-symbol cycle 再重复开头 2 symbols。独立枚举验证：两类各 8 条序列且集合不相交；每个绝对位置 unigram、每个固定位置 bigram、前后 5-symbol 计数，以及全局 1/2/3-gram histogram 的类条件分布完全相同；4-gram 分布不同。
- 10-symbol、`B=4` 至少占 40 tick；48-tick episode 无法容纳 9 个可拉伸间隔。V3 统一改为 64 tick，旧 48-tick burst 结果降级为探索证据，正式 calibration、activity 和高层/RTL-reference spike count 必须重跑。
- P4 若允许 Host 保存旧样本、旧标签或无限片外状态，可以靠联合重训代做持续学习。V3 主结论冻结为 task-aware、no-replay，并增加相同 context/数据/预算的 joint-training upper bound。
- P5 若训练器同时生成命令、期望值和解码，会形成同源软件自证。V3 隔离语义训练器、raw golden-vector 生成器和独立 scoreboard，并加入固定手算向量。
- 当前大规模双时钟 Icarus cosim 使用接口等价 FIFO；真实 AMD XPM 只有独立 xsim 证据。V3 将 P5a 定义为接口等价 FIFO 的完整 cohort，P5b 定义为真实 XPM 的代表性短 cohort，两者同时通过才称完整真实 Host Bridge 仿真闭环。
- 固定 4->2->2 的 P0-P5 不能证明可扩展性。V3 增加 P6：共享流水线和同步 RAM 的 4->2->2、16->16->2、64->32->2 三参数点，独立验收 cycle reference、Vivado OOC、资源增长、吞吐和状态容量。
- reward 日志不能证明实现未读取 label/action。V3 将主 API 收窄为 `reward_to_modulation(reward) -> (m,m,m,m)`，增加 AST/依赖检查和“相同 reward、改变 label/action/prediction，输出逐位不变”的边界测试。
- Host Bridge V1 的 `INPUT_EVENT` 固定 synapse 0..3，权重地址固定四核，`MOD_COMMIT` 固定四路调制，不能驱动 P6 的 16/64 输入网络。P6 必须先冻结可寻址流式协议 V2，并与 V1 分开完成 oracle、cosim、formal/CDC 和 Vivado 证据。
- P4/P5/P6 必须按训练模式绑定结论：Teacher 通过不能代偿 Hybrid 或纯全局 reward。V3 增加声明矩阵，要求 `verify_g4.py` 对每项输出 PASS/FAIL/NOT-RUN；只有全部通过才允许 `G4_FULL_PASS`。
- V3 Temporal 64-tick 活动探针覆盖 2 labels x 8 phases x 8 skeletons，共 128 样本：`B=1` hidden/output 全静默；`B=2/3/4` 两类 hidden/output active 均为 100%；所有 burst 的高层模型与四个 `RtlReferenceNeuron` spike count 均 128/128 一致。固定全 2 权重时两输出始终同计数，因此 strict decoder 全 abstain，进一步说明活动正对照不等于分类能力。
- Temporal 容量预判先确认 225 种有效 A/B 隐藏权重产生 137 种唯一脉冲签名；随后检查 6929 个唯一隐藏签名组合，并对每组枚举全部 225x225 输出读出器，32 样本最好为 25/32、coverage 32/32。独立 `DigitalSNN2Layer` 重放同样为 25/32。该结果只说明容量风险，不证明不存在更好权重，也不是正式验收。

## G4 T3 执行规格前置审计（2026-08-13）

- 完整 `DigitalSNN2Layer.inference()` 调用前后全部学习字段当前不相等：episode reset 会清 trace/eligibility 并恢复 threshold。该事实不应直接触发无必要的方程/RTL修改；正式 P0a 应审计 EP_START 白名单复位、推理区间逐字段冻结，以及整笔调用的持久训练状态不变。
- 历史 reward/hybrid helper 分别读取 label/result 或按 action 定向输出调制，不能复用为 `reward_global_no_wta`；正式模型适配器只接收 `sample["input"]`。
- 正式计分和动作选择必须从 output spike count 调用 `strict_decode()`；禁止使用非零平局偏向 class 0 的 `NetworkEpisode.prediction`。
- Temporal 只有 8 个有效离散权重；既有 Train 最优 78.125% 是固定 2-hidden 的容量硬风险。正式 direct-weight 将对 Temporal 做结构化覆盖，对 Spatial/XOR 各做 100000 个唯一候选。
- 本机测得 64-tick inference 约 0.622 ms/episode、训练提交约 0.894 ms/episode、朴素 direct search 约 49 candidates/s。T3 的 final P1-P3 预计 30-45 分钟，全部 P4 模式预计 1.5-2 小时。
- `g4_t3_execution_spec.md` 已将 P0a 拆分、permutation 数值门、P4 聚合/context/no-replay、负对照配对、direct-search、统计边界、Spatial/XOR、训练预算和 joint budget 写成 12 项待审核合同。
- D1 独立反证确认 inference 的正确合同不是“整次调用全部学习字段不变”，而是 EP_START 白名单基线转换、其后的推理区间逐字段冻结、整笔调用持久训练状态不变；适配器还需显式拒绝在未 capture/未 commit 的信用状态进入 INFER。
- D2 独立反证确认共享数据的 20 model seeds 必须共用同一 evaluation-label permutation；若 permutation seed 含 model seed，会错误压低零分布方差。正式零分布改为每 `(task, split, permutation_index)` 一份公共平衡置换。
- D4 独立反证确认 context 在 tick 0..15，但一拍路由会把 context 来源活动延伸到 tick 16；正式分类只统计 tick 17..79 和 EP_END flush，并同时审计 context hash 与原 payload hash。
- D5 本机 Python 3.14.2 实测 `-I` 仍包含全局 `site-packages`，`-I -S` 才排除；no-replay worker 因此冻结为绝对 `sys.executable -I -S -u`、临时 cwd、环境 allowlist、model-only bundle 和模式专用 IPC。audit hook 只作为 trusted-worker fail-closed 断言。
- `python -I -S network_sim.py` 的只读探针进一步确认安全路径不会加入脚本目录，旧模块因无法导入同目录 `neuron_sim.py` 而退出；正式 model-only worker 必须是自包含单入口或通过固定标准库 bootstrap 显式加载已验哈希 bundle，不能借 `PYTHONPATH/site-packages` 绕开隔离。
- D6 不能按 `(epoch, sample_position)` 临时派生探索随机量；broker 必须预生成不可变 `RandomPlan`，主实验与 training-label-shuffle 记录相同计划哈希和初态 digest。
- D7/D10 独立审计要求冻结有序双隐藏签名、搜索 batch/top-64/邻域/去重算法，以及 Spatial/XOR 的 bit 位序、first_start、canonical offset、sample 顺序和 ID；否则 100000 候选和数据 split 都不可复算。
- D8 的 P3 evaluation-permutation comparator 冻结为逐 seed 的 10000 次公共置换指标均值；main-eval/main-shuffle 与 overall/conditional 共四组 paired-bootstrap 下界都必须严格大于 10pp。
- D11 checkpoint 必须在 clone 上只读评估，tie-break 使用最终 12 权重中位于 +/-7 的数量，不能使用会被 Validation inference 污染的累计 saturation counter。context admission checkpoint 与跑满预算的 P4 single endpoint 是两个独立产物。
- D12 预算按成功接受并完成的训练 episode 对应 MOD_COMMIT 计数，即使 delta 为 0 或权重饱和也计入；每个排列/single/joint 独立 reset，commit ID 从 0 开始，最大单 run 为 18432 次且不得回绕。
- direct search 的 49 candidates/s 测量只覆盖 Train 32；按 Train+Validation 160 样本线性外推，Spatial/XOR 每任务 100000 候选约 170 分钟，两任务约 5.7 小时。Temporal 约 3.51 亿次输出读出检查仍需先做 chunk/vectorized benchmark。
- D5 最终反证发现“bundle 加载前安装 audit hook”与“无条件拒绝 compile/exec/import”不可同时执行：本机 Python 3.14.2 探针确认 `compile(bytes, path, "exec")` 和 `exec(code)` 会分别触发 `compile`、`exec` 审计事件。规格已收敛为固定 bootstrap、一次性 `LOADING_VERIFIED_BUNDLE`、路径/源码哈希/code-object 三重绑定，并在外层 `exec` 放行前切换到 `SEALED`；运行期继续拒绝全部动态加载。
- D5 修订后经 Host/no-replay 独立终审放行，规格 SHA-256 为 `D88EBE4A64C34DAE42E5C16888E2F786F4C560D6BE0B90EBFF1F48749009DE0C`，未发现剩余 P0/P1。实现时还必须给 bundle 使用受限 `__builtins__`、移除 `__import__`，并静态检查 AST/字节码无 import；原因是已缓存模块的再次 `__import__` 不保证产生新的 import 审计事件。

## 原始 Goal 对齐复核（2026-08-13）

- 当前 `digital_lif_engine.sv` 的权重、pre trace、eligibility 和 snapshot 都是每核寄存器数组；`digital_snn_tile_4x2x2.sv` 固定实例化 2 个 4-input 隐藏核和 2 个 2-input 输出核。它证明了神经元方程与固定小网络可综合，但没有证明资源可随突触数主要进入 RAM，也没有证明可复制到实用规模。
- 本地学习路径确实存在：episode 内生成 eligibility，`SNAPSHOT` 锁存，`MOD_COMMIT` 在核内执行 `weight += modulator * eligibility >> LEARNING_SHIFT`。因此 Host 不需要计算逐突触 delta。
- 但 Host Bridge 同时暴露无权限分层的 `WEIGHT_WRITE`，idle 且无 pending snapshot 时可直接改任意权重。现有训练日志若只观察最终权重，不能单独证明权重来自可塑路径；正式训练闭环必须审计命令轨迹并要求训练区间没有 `WEIGHT_WRITE`，或在正式运行角色中硬件/协议禁用该命令。
- 历史 Python Hybrid 在 feature/reward 阶段之间直接赋值随机输出权重；这只能视为初始化/阶段重载，不能作为纯片上可塑训练证据。正式路径必须通过受审计 `WEIGHT_WRITE` 初始化后封闭该权限，再以 `MOD_COMMIT` 完成全部学习。
- 因而原始 Goal 当前最准确状态是：神经元最小学习机制已建立，固定网络数字前端已建立；“训练真实性的任务级 RTL 闭环”“共享 RAM 可扩展网络”和“板级实际闭环”仍未完成。T3 只需保留足以排除标签泄漏、Host 代算权重和无效任务的最小门槛。
- 对上述结论再次按最初问题反审计：共享 RAM 大规模化和板级实际闭环是更强工程目标，不应作为“最小数字神经元基石”成立的必要条件；可信 Host 场景也不要求新增 `RUN_SEAL`。核心唯一未闭合项收敛为：在同一真实 Host Bridge + Tile RTL run 中，以命令账本证明初始化后无直接写权重，并完成训练、局部 MOD 更新、权重读回、冻结推理和未训练输入验证。

## 原始 Goal C1 冻结合同（2026-08-14）

- 硬复位初态四核权重全部为 2；固定两轮训练，每轮顺序为 label 0、label 1，commit ID 为 0..3。
- Teacher 调制按 H0/H1/O0/O1 排列：label 0 为 `(+1,-1,+1,-1)`，label 1 为 `(-1,+1,-1,+1)`；训练区间不发送 `WEIGHT_WRITE`。
- 严格解码规定输出计数平局（包括 0,0）为 abstain；训练前 clean 为 `(-1,-1)`，两轮后 clean 为 `(0,1)`。
- 两轮后冻结权重为 H0=`(-6,-7,7,7)`、H1=`(7,7,-6,-7)`、O0=`(7,-7)`、O1=`(-7,7)`，`weight_epoch=4`。
- `make_noisy_dataset(seed=3,count=100)`、全部 86 个唯一扰动形态和 seed 0..99 各 20 样本均为 100% accuracy/coverage；正式 M3 RTL run 使用同一 seed 的 20 个扰动样本缩短仿真。
- 一轮训练后仍为严格 abstain，因此 2 epochs/4 commits 是该冻结初态和任务下的最小可靠合同，不是任意任务的泛化结论。

## 原始 Goal M3 实际 RTL 证据（2026-08-14）

- 同一真实双时钟 Host Bridge + Tile 实例连续接受 957 条命令；训练起点为响应索引 64，命令 SHA-256 为 `191d7c588411515f4386685b6dfcd8ce7e3894a21f87ff3a54a40de2f9989c09`。
- 响应账本 SHA-256 为 `cb63bcc596843607cdb7c774a91a8ffd38d9b21ee304cd266ecd33e2974a5256`，hash chain 尾值为 `cf4b268a199675d71462f1b6ec55a76f38691f4e6dbd90d9cf8d1b72e1509a74`。
- 四次 `MOD_COMMIT` 后各紧跟 12 次 `WEIGHT_READ`；48 个逐突触更新全部符合 `delta=(mod*eligibility_snapshot) >>> 3` 和 `sat(weight+delta,-7,+7)`，并覆盖正负算术右移与双向饱和。
- 训练区间 `WEIGHT_WRITE` 出现数和成功数均为 0；最终 `weight_epoch=4`。训练前 clean 为全 abstain，训练后 clean `(0,1)`，20 个冻结扰动样本 20/20 正确，推理后最终权重未改变。

## ENeuron 1.0 发布审计（2026-08-19）

- 当前目录和父目录都没有 `.git`，因此 1.0 需要在本目录新建 `main` 仓库，而不是接续未知历史。
- Git 全局身份已配置为 `Nept Epslion <11226778+Nept-Epslion@user.noreply.gitee.com>`。
- 当前 M1-M4 的最强闭环证据是 169 项回归、Tile/Controller 有限 BMC、10000 个 Tile 压力事务、957 条真实双时钟 M3 命令、48 次逐突触本地更新核对和冻结推理 20/20。
- XC7Z020 单核现有实测为：4 输入 `818 LUT / 544 FF`，2 输入 `718 LUT / 380 FF`，均为 `0 BRAM / 0 DSP`；它们是当前完整三因子核的上界参照，不是原始极简计数器方案的实测结果。
- `verify_goal.py` 默认审计既有 Tile、XPM 和系统 Vivado 产物，并检查报告时间不早于源码。若整个报告目录被忽略，干净克隆无法复验默认路径。
- 1.0 应保留验证器读取的文本报告、机器摘要、Tile 实现 DCP、Tile Vivado 日志和真实 XPM `simulate.log`；其余综合 DCP、Vivado 工程缓存、波形、VVP、Python 缓存和大体量 formal 日志可忽略。
- Pulse-Mini 的规划必须与 1.0 分开：1.0 是已验证的完整三因子硬件基线，Pulse-Mini 是重新审视原始计数/分频构想后的低成本候选，不能用估算资源冒充综合实测。
- 发布交叉审查发现 `rtl_contract.md` 仍保留早期 Tile 数值 `3144/1971/+0.053 ns`；已按冻结摘要统一为 `3152/1972/+0.213 ns`。
- Git 检出不保留原始 mtime，而 `verify_goal.py` 会检查报告晚于源码；因此全新检出的权威复验入口是 `python verify_goal.py --rerun-vivado`，默认命令只适用于已保存同一工作区时间关系的审计。

## Pulse-Mini 方案结论（2026-08-19）

- 原始四输入方案的 84 位状态代理成立，但上限复位、单向增强、无抑制、分频方向不明、内部 RST 和无延迟反馈使它不能直接完成任务导向训练。
- Pulse-Mini 初稿曾保留 3 位模 8 脉冲进度和 2 位三态方向；该方案已在语义反审查中废止，最终推荐为 4 位有符号连接、4 位最近输入窗口、正/负两个 presence flag，以及共享 8 位有符号胞体、4 位最近输出和 4 位同步不应期。
- `train_post` 只进入学习时间检测器，不直接拉高 `spike_out`；它允许可信 Host 提供神经元级教师事件，同时逐树突变化仍由本地输入历史决定。
- 单槽 CAPTURE/FEEDBACK 只对单生产者、严格有序链路承诺 exactly-once；不增加 core commit ID、多槽 RAM 或 FIFO，跨 CDC/重试由 wrapper 加序号。
- 算法与 pending 状态约 69 位；综合目标为 `140~240 LUT / 100~140 FF / 0 BRAM / 0 DSP`，这是待 RTL/Vivado 验证的预算，不是实测。
- 以 XC7Z020 的 53200 LUT 为边界，按约 45% 资源预留后，固定四输入核的工程量级约 121~209 个；首版阵列目标为 128 核，只有 routed 通过后才能改称实测容量。

## Pulse-Mini 语义反审查修订（2026-08-19）

- 独立审查确认：跨样本保存 3 位分频进度会与 `STATE_CLEAR` 冲突。清除它会让短样本中的弱连接不可观察；保留它又会让结果依赖前一个样本。因此推荐 Pulse-Mini 删除跨样本分频进度，输入脉冲直接条件加入当前有符号连接；原始分频仅在 P1 做忠实成本基线。
- 独立审查确认：一个饱和三态不能同时保证“冲突抵消”和“顺序无关”。已改为每条树突两个 presence flag；CAPTURE 时仅正证据为 `+1`、仅负证据为 `-1`、两者同现为 `0`。
- 连接更新已冻结为数值规则 `weight_next=saturate(weight + feedback_sign * captured_direction,-7,+7)`；4 位编码 `1000` 的 `-8` 非法并返回错误。
- 已冻结窗口只随成功接受的逻辑 TICK 推进、同 tick `natural_spike OR train_post` 只算一个 post 事件、阈值使用本 tick 贡献后的胞体、presence flag 只在 P0 明确顺序表后写 RTL。
- 分立 valid/ready 端口改为统一 `cmd_valid/cmd_ready` + `rsp_valid/rsp_ready`；非法请求必须握手返回错误，`WEIGHT_READ` 必须返回符号扩展数据。无 core commit ID 时，exactly-once 只承诺单生产者严格有序链路，跨 CDC/重试由 wrapper 加序号。
- `STATE_CLEAR` 仅在 idle 且无 pending 时接受，清动态与学习证据但保留连接；INFER 的冻结只约束 TICK，不把显式样本边界清除误判为学习写入。
- Pulse-Mini 目标预算更新为 `140~240 LUT / 100~140 FF / 0 BRAM / 0 DSP`，算法与 pending 状态约 69 位；XC7Z020 容量表改按约 45% 资源预留计算。
- 目标声明收窄为“可作为固定小网络构件”；新增 P8 固定 `4->2->2` 训练/冻结推理闭环，未通过前不宣称已经完成网络级基石。

## Pulse-Mini P2 黄金模型（2026-08-19）

- 新增 `pulse_mini_reference.py`：固定四输入、权重 `-7..+7`、八位有符号饱和胞体、阈值 6、不应期 1 tick、窗口 3；实现 `MODE_SET/STATE_CLEAR/TICK/CAPTURE/FEEDBACK/WEIGHT_WRITE/WEIGHT_READ` 和单槽严格有序 `cmd/rsp` valid-ready 事务。
- 参考模型以每条树突正/负 presence flag 记录先后证据；`CAPTURE` 映射为 `+1/0/-1`，`FEEDBACK` 按一步数值更新并在 `-7..+7` 饱和，非法四位权重 `1000 (-8)` 和反馈编码 `10` 显式拒绝。
- `INFER` 的 `TICK` 不改变权重、年龄、presence 或 pending 学习字段；`train_post` 只参与学习事件，不伪造自然 `spike`。`STATE_CLEAR` 保留连接，仅在无 pending 时清动态与证据。
- 新增 `test_pulse_mini_reference.py`，14 项回归覆盖全部 16 输入掩码、所有输入排列、正负零连接、正负胞体饱和、窗口端点和冲突证据、反馈饱和/零消费/exactly-once、pending 背压、非法模式与权重编码、CONFIG 写入、推理冻结、结构化日志。`python -m unittest -v test_pulse_mini_reference.py`：14/14 通过。

## Pulse-Mini P3-P8 证据（2026-08-19）

- `pulse_mini_core.sv` 与 `pulse_mini_reference.py` 逐事务一致；`python pulse_mini_cosim.py` 输出 `PULSE_MINI_COSIM_PASS seeds=20 transactions=20000`。
- `& .\run_formal_pulse_mini.ps1` 使用 Yosys 0.56 SAT depth=20 输出 `PULSE_MINI_FORMAL_PASS depth=20`，无 model found。
- `pulse_mini_negative_control.py` 输出 `PULSE_MINI_NEGATIVE_CONTROL_PASS duplicate_feedback_counterexample=1`；真实模型的第二次反馈返回 `NO_PENDING`，错误实现的反例会把权重从 1 错误推进到 2。
- P5 训练 runner 输出：训练前 10/20，训练后 20/20，no-feedback 10/20，反向反馈 0/20，label-shuffled 10/20，训练期 `train_weight_write_count=0`，最终权重 `[6,-6,0,0]`。这只是神经元级 `train_post` 监督任务。
- Pulse-Mini 单核 Vivado 2024.1 `xc7z020clg400-1` routed 摘要：182 LUT / 76 FF / 0 BRAM / 0 DSP，WNS +0.463 ns，TNS 0，WHS +0.205 ns，THS 0；`python verify_pulse_mini.py` 通过。vector-less power 只作估算。
- 阵列报告必须使用 `keep_hierarchy/dont_touch`，否则广播相同输入会被综合器等价合并成一个核。保留实例后真实结果为 32 核 5867/2432/+0.151 ns，64 核 11699/4864/-0.131 ns，128 核 23342/9728/-0.466 ns。故 P7 只能报告资源与失败边界，不能声称 128 核 100 MHz 通过。
- Python P8 固定 4->2->2 网络通过：训练前双类输出均为 0，训练后正类输出位 1、负类输出位 2，各 10 个扰动样本全对；`route_delay_observed=1`、`weights_frozen=True`、`direct_weight_write_count=0`、无反馈输出 `[0,0]`。结论限定为固定小网络训练/推理原型。
## P1 原始方案实测证据（2026-08-19）

- `pulse_original_core.sv` 的冻结映射为 `period=max(1,255-learn_count)`：学习值越大，分频周期越短；输入事件在该通道达到周期时产生树突脉冲并清零进度。
- 定向模型通过 4/4：学习计数器从 `255` 再学习一次回绕为 `0`；强连接周期 2 拍、弱连接周期 7 拍；胞体达到阈值后输出一拍脉冲并进入同步睡眠；接口没有负反馈或抑制路径。
- Vivado 2024.1 `xc7z020clg400-1` routed 报告：`183 LUT / 85 FF / 0 BRAM / 0 DSP`，vector-less 功耗 `0.105 W`（报告未绑定活动文件）。100 MHz 核心时序为 `WNS=-1.605 ns, TNS=-30.454 ns, WHS=+0.150 ns, THS=0`，因此 P1 仅作为成本/缺陷基线，100 MHz 时序门未通过。
- Vivado 日志无综合错误、无 DRC Error/Critical Warning，route status 的失败/未布线网络为 0；OOC 输入/输出封装延迟被 false-path 排除，摘要明确标注 `REGISTER_TO_REGISTER_ONLY`。

## Pulse-Mini P4/P8 收口（2026-08-19）

- `pulse_mini_signoff_summary.json` 为 `pulse_mini_signoff_v1` 机器摘要，绑定 `pulse_mini_core.sv`、Python 黄金模型、20,000 条固定协同事务的黄金摘要、形式脚本、负向控制、P5 任务和网络 RTL 文件 SHA-256。
- P4 正向证据闭环为 20 seeds × 1000 transactions bit-exact、Yosys 0.56 depth 20 无反例、重复反馈负向控制反例；摘要状态为 `PASS`。
- P8 RTL 网络协同仿真共 272 条命令。输出层训练教师事件固定在第 6 个 tick；第 1 个 tick 会让后续隐藏重复脉冲进入负证据窗口，导致方向抵消，这不是路由丢失。
- P8 RTL 通过后，固定 `4 -> 2 -> 2` 网络可以称为训练/冻结推理原型；仍不能外推为通用 AI、纯全局 reward 学习或任意规模网络。

## Pulse-Mini TODO 收口（2026-08-19）

- P0 十项行为合同已由实现证据冻结并标记批准，`TODO.md` 不再保留未完成 checkbox。
- P7 广播阵列协议测量：32、64、128 核的单条 TICK/FEEDBACK 响应均为 1 个逻辑周期；由于一槽响应不能同拍替换，持续接受率为 0.5 命令/周期。32/64/128 核分别可在一次广播 TICK 中观察到 32/64/128 个输出脉冲，说明输出拥塞边界是 N 位向量和 Host 消费带宽，而不是核内发放缺失。
- P7 共享 lane 对比使用 `pulse_mini_lane_model.py` 的可复现周期模型：128 核使用 1/2/4/8/128 条 lane 时，每个全阵列 tick 分别需要 128/64/32/16/1 个 lane 周期。该模型没有被写成 LUT、FF 或 routed 容量证据。
- P7 资源硬门审计由 `verify_pulse_mini_p7.py` 收口：简单广播阵列的最大 100 MHz routed 并行规模为 32 核；64 核 `WNS=-0.131 ns`，128 核 `WNS=-0.466 ns`，故 `capacity_claim=NOT_PROVEN` 保持不变。

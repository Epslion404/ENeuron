# Pulse-Mini 开发计划

## 当前主线校正（2026-09-09）

本文件前半部分保留 Pulse-Mini P0-P13 的历史研发合同；当前日常主线是 P16 的 `xc7z020clg484-2` 板级集成、传统 NPU + ENeuron 动态剪枝和 NP7 共享 lane。当前精确 HEAD、工作树状态和活动 TODO 计数以 `workflow_resume.ps1 -Mode Check` 与 Git 为准；历史审计基线为 `d7e1035`。B1-06B7 使用的已生成 OCM 诊断产物仍绑定构建身份 `dae5473ba72d6cfaee12ed8e103c0efad190ed4a`。当前工作树仍保留用户已有的 `artifacts/results/rtl_smoke_results.json` 改动，不把它混入本轮文档/知识库提交。该基线收口 TODO/Nexus、串口端口选择入口和历史资料，不改变已签核的 B1B 诊断 ELF 或硬件身份。Pulse-Mini-L/L2 不参与当前 NPU 日常门，但其已完成证据仍保留供追溯。

当前板级状态：低地址 `0x01000000–0x010FFFFF` 的 1 MiB DDR 已完成三次冷启动；高地址诊断尚未真正访问 DDR。CH340 以 `VID_1A86:PID_7523` 识别，COM 号不固定，本次环境探测（2026-09-08）为 COM10。B1C PHY/UDP 继续后置；B2 可先按低地址容量满足模型/DMA 缓冲区的条件启动 MVP，完整 `B1-GATE` 仍是进入网络化 B1C/B4 的门槛。

## 2026-09-07 资源裁剪审查门

- [x] 完成 `NPU_ZYNQ7020_RESOURCE_CUT_REVIEW_V1.md`，基于当前 Vivado/RTL 证据列出可裁、可配置裁和不可裁项目。
- [ ] 管理员选择是否实施 C1 固定模型 ROM/BRAM 配置。
- [ ] 管理员选择是否实施 C2 `INFER_ONLY` ENeuron 构建配置。
- [ ] 若批准 C1/C2，先建立独立 A/B OOC 顶层和逐拍等价测试，不覆盖训练基线。
- [ ] C3 固定拓扑特化、C4 ID/epoch 缩短、C5 调试端口关闭暂不实施，等待 C1/C2 实测收益。
- [ ] C6-C9（删除快照、原地更新、FIFO 合并/缩深、位宽缩减）必须单独形成新裁定，当前禁止直接改签核 RTL。
- [x] 管理员决定：所有资源裁剪延后到第一次完整端到端运行成功之后；此前只完成 T1/T2/T3 证据，不改裁剪基线。

日期：2026-08-19  
状态：`V2_IMPLEMENTED / VIVADO_OOC_100MHZ_PASS`；实施状态：`P8_NETWORK_SIGNED_OFF / PR64_MERGED / TR1_TR6_APPROVED / TR7_TR12_APPROVED / RTL_TIMING_REPAIR_GREEN / FULL_REGRESSION_GREEN / DSP_GATE_PASS / VIVADO_OOC_PASS`
基线：`ENeuron 1.0`，提交 `499fc8a`，标签 `v1.0`；当前 Pulse-Mini 工作基线：`64aff70`

本文件是 `v1.0` 之后的 Pulse-Mini 规划，不回写或扩大 ENeuron 1.0 的声明。历史基线曾在干净工作树上提交；当前工作树可能包含未提交的文档或工具变更，后续修改仍应以本文件的阶段门为准，不能把“逻辑容量估算”写成“已 routed 的硬件容量”。

## 1. 目标

Pulse-Mini 的目标不是替代 ENeuron 1.0 的完整三因子核，而是重新审视最初的“计数器 + 分频器 + 睡眠计数器”构想，做出一个真正完整、可训练、可推理、容易复制的四输入脉冲神经元。原始分频器保留为 P1 成本基线；当前可继续扩展的主线是时序已通过的 Pulse-Mini-L（`pulse_mini_core.sv`），不是尚未收敛的 L2。

完成后应能准确声明：

> Pulse-Mini 是一个只用寄存器、加减、比较和少量选择逻辑实现的四输入数字脉冲神经元。它支持正负连接、双向饱和学习、延迟结果反馈、训练与推理隔离，以及同步不应期，可作为固定小网络的候选构件。

P8 的固定 `4 -> 2 -> 2` 端到端验收已通过，因此可以声明“固定小网络训练与冻结推理原型”。该声明不等于纯全局奖励可以训练任意深层网络，也不等于通用 AI 已完成。后续要面向数字识别，必须另行冻结输入编码、类别输出和网络规模，不能从二分类 P8 直接外推。

## 2. 非目标

- 第一版不做任意扇入、任意拓扑或片上 NoC。
- 第一版不做浮点、乘法器、除法器、DSP 或 BRAM。
- 第一版不实现反向传播、损失函数、标签生成或探索策略。
- 第一版不追求与 ENeuron 1.0 的 LIF 方程或权重数值兼容。
- 第一版不承诺连续学习、多任务学习或只靠一个全局 reward 解决隐藏层信用分配。
- 第一版不使用逻辑产生的新时钟，不让内部比较结果驱动异步复位。

## 3. 原始方案还原

最初方案可还原为两部分。

### 3.1 树突

```text
输入脉冲 -----------------> 分频器 -----------------> 胞体
   |                           ^
   +-> 与输出比较先后关系 -> 学习脉冲 -> 向上计数器
```

原意是：输入和输出越符合某种时间关系，计数器越大，输入越容易或越频繁地传给胞体。每条输入线拥有自己的学习状态，因此已经具备“连接强弱属于树突”的正确方向。

### 3.2 胞体

```text
所有树突脉冲 -> 累计计数器 -> 达到阈值 -> 输出一个脉冲
                                      |
                                      +-> 启动睡眠计数器
```

原意是：胞体累计足够多的输入后发放一次，随后在若干拍内不再接受输入。这已经包含积分、阈值发放和不应期三项最小神经行为。

## 4. 原始方案审计

### 4.1 值得保留的部分

- 全部状态可以用触发器和小位宽计数器实现。
- 输入是脉冲，不需要执行普通神经网络中的乘法。
- 每条树突有独立状态，连接可以分别学习。
- 胞体只在达到阈值时输出，天然适合事件驱动网络。
- 睡眠计数器给出了低成本不应期。
- 四输入原始状态代理只有 84 位，面积方向是合理的。

### 4.2 阻止它成为完整训练单元的问题

1. **上限复位会毁掉已学结果。** 最强连接继续收到一次学习脉冲后会突然回到最弱，训练结果不是单调或稳定的。
2. **缺少受负证据控制的削弱路径。** 除破坏性的上限回绕外，只有向上计数，错误关联无法被可控撤销。
3. **不能表达抑制。** 所有树突只能给胞体加计数，无法表示“这个输入应阻止当前神经元发放”。
4. **分频方向没有定义。** 若计数值直接作为分频数，数值越大反而通过得越少；若取倒数，又需要额外映射。原方案必须冻结“数值越大究竟代表越强还是越弱”。
5. **普通时间相关学习不知道结果对错。** 输入和输出经常同时出现，只能说明相关，不能说明这个输出是否完成了任务。
6. **没有延迟反馈保存位。** 结果通常在一段脉冲结束后才知道，此时必须保留“刚才哪些树突应被调整”。
7. **睡眠不应直接驱动异步 RST。** 若睡眠计数器直接拉计数器异步复位，会增加复位释放、时序和形式验证风险；原始描述没有明确 RST 是同步还是异步，P1 必须分别记录功能等价实现和该物理风险。
8. **同时到达的输入顺序未定义。** 若四个输入依次修改同一胞体计数器，结果可能依赖 RTL 语句顺序。
9. **没有 TRAIN/INFER 边界。** 推理期间继续改变连接会使输出和模型状态不可复现。
10. **没有样本边界和重复反馈保护。** 上一个样本的计数、分频进度或学习方向可能污染下一个样本，同一反馈也可能被应用两次。

结论：原方案是一个很好的脉冲积分器草图，但原样只能称为“带局部相关性调节的脉冲单元”，不能称为完整的任务导向训练与推理基石。

### 4.3 已完成的硬件对照

原始方案已经做成独立 RTL 并在目标器件上跑过 Vivado 2024.1。结果说明：它的面积确实很小，但“面积小”没有抵消功能和时序缺陷。

| 实现 | LUT | FF | 100 MHz WNS | 结论 |
|---|---:|---:|---:|---|
| 原始计数/分频核 | 183 | 85 | `-1.605 ns` | 功能基线，setup 失败 |
| Pulse-Mini-L 单核 | 182 | 76 | `+0.463 ns` | 当前四输入主线，通过 |
| Pulse-Mini-L2 单核 | 366 | 91 | `-4.690 ns` | 证据强度增加，但不能作为阵列基线 |

因此，原始方案不应继续作为产品主线；它只保留为“最初想法的真实成本和行为反例”。L2 也暂缓复制，先修复关键路径；在没有新的 routed 证据前，不得用 LUT 除法推导 L2 的可部署核数。

## 5. Pulse-Mini 完整化方案

### 5.1 总体数据流

```text
四位输入脉冲掩码
        |
        +-> 最近输入计时 ------+
        |                       |
        +-> 有符号连接强度 ----------------> 有符号贡献
                                            |
四条贡献同拍求和 --------------------------> 有符号胞体累计
                                                |
                                      达阈值 -> 自然输出脉冲
                                                |
                              最近输出计时 <----+

最近输入/最近输出/训练后事件 -> 正证据标志 + 负证据标志
两个证据标志 + 结果反馈(-1/0/+1) -> 连接强度数值加一、减一或不变
```

### 5.2 每条树突保存的状态

| 状态 | 位宽 | 作用 |
|---|---:|---|
| 有符号连接强度 | 4 | 范围限定为 `-7..+7`；正值促进，负值抑制，0 表示断开 |
| 最近输入倒计时 | 4 | 记录该输入是否刚刚出现，用于判断输入与输出的先后关系 |
| 正证据标志 | 1 | 记录是否见过输入先于输出的证据 |
| 负证据标志 | 1 | 记录是否见过输出先于输入的证据 |

四条树突共约 40 位算法状态。CAPTURE 时，只有正标志映射为 `+1`，只有负标志映射为 `-1`，两者都出现或都没有映射为 `0`；证据收集顺序不会改变结果。

### 5.3 神经元共享状态

| 状态 | 位宽 | 作用 |
|---|---:|---|
| 有符号胞体累计值 | 8 | 汇总促进与抑制贡献，运算饱和而不回绕 |
| 最近输出倒计时 | 4 | 判断输出发生后到达的输入 |
| 不应期倒计时 | 4 | 发放后同步屏蔽若干 tick |
| 模式 | 2 | `CONFIG / TRAIN / INFER` |
| 待反馈有效 | 1 | 单槽反馈背压和 exactly-once 保护 |
| 输出/错误等控制位 | 约 2 | 单拍输出和协议错误状态 |

上述运行状态合计约 61 位；四条待提交方向还需要 8 位快照槽，因此包含 pending 快照时约 69 位。综合后的 FF 还会包含接口和事务寄存器，因此不能把 69 位直接当作最终 FF 数量。

### 5.4 推荐版删除跨样本分频进度

推荐的 Pulse-Mini 不把连接强度转换为跨多个输入事件的分频进度，而是在输入脉冲被接受的当拍直接把有符号连接强度加入胞体：

- 输入为 0：贡献为 0。
- 输入为 1：贡献为当前连接强度。
- 四条连接的贡献在同一个 tick 内求和，然后一次性更新胞体。
- 所有运算仍然是加法、比较和饱和，不需要乘法器；二值脉冲本身已经完成“乘以 0 或 1”。

这样每个样本只要出现一次输入，弱连接也能被观察到；清除样本状态不会改变连接强度的解释，也不会把前一个样本的相位残留带入下一个样本。原始分频进度仍在 P1 中实现和综合，作为成本与行为对照。

### 5.5 胞体与不应期

- 每个 tick 一次性读取四位输入掩码，四条树突并行产生最多四个有符号贡献。
- 四条贡献先求和，再对胞体累计值做一次更新，结果与输入位的处理顺序无关。
- 胞体达到固定正阈值时只输出一个时钟周期的脉冲，随后把胞体清零并装载不应期。
- 不应期内不接收树突贡献，胞体同步保持为零；不应期计数器每 tick 减一。
- 只允许外部 `rst` 使用复位网络；发放和不应期都使用普通同步使能。
- 第一版不增加漏电。样本开始时显式清动态状态，避免用漏电掩盖未定义的样本边界。

### 5.6 最小学习规则

时间关系仍保留原始方案的核心直觉：

- 输入先出现、随后自然输出或训练后事件出现：置位该树突的正证据标志。
- 输出先出现、随后输入出现：置位该树突的负证据标志。
- 两种证据在同一训练段都出现：CAPTURE 时映射为中性，不依赖它们出现的先后或次数。
- CAPTURE 产生的方向只取 `-1/0/+1`，训练段内不做顺序敏感的三态饱和累加。

为了避免神经元初始不发放时完全无法学习，TRAIN tick 增加一个 `train_post` 位。它只送入学习先后关系检测器，不伪造 `spike_out`。Host 可以提供神经元级训练后事件，但不能指定任何一条树突应写成多少。

训练段结束时执行 `CAPTURE`：

- 将四组正/负标志映射成四个冻结方向并置 `pending_valid=1`。
- 单槽未消费前拒绝新的 TRAIN tick 和第二次 CAPTURE。

随后提交 `FEEDBACK=-1/0/+1`：

- 正反馈按冻结方向调整每条连接一步。
- 负反馈反转冻结方向后调整一步。
- 零反馈不改连接，但仍消费当前槽。
- 数值更新固定为 `weight_next = saturate(weight + feedback_sign * captured_direction, -7, +7)`；这里的“增强/削弱”指数值上调或下调，不把负连接的语义含糊地称作变强或变弱。
- 连接写入数据 `4'b1000`（数值 `-8`）是非法范围，返回错误而不是静默钳位；合法连接只有 `-7..+7`。
- 一次反馈消费后清除方向和 `pending_valid`，重复反馈被拒绝。

这里的反馈只需要改变一步，不使用通用乘法器。`train_post` 和反馈都是神经元级信号，逐树突更新仍由本地输入历史决定。

### 5.7 逐拍顺序、模式与状态边界

时间窗口只随成功接受的逻辑 TICK 推进，不随 Host 等待 response 或物理时钟空转推进。每个 TRAIN TICK 使用以下固定顺序：

1. 读取 tick 开始时的 `pre_age` 和 `post_age`；窗口端点以旧值大于 0 为有效。
2. 若不应期非零，当前输入完全不进入胞体，也不更新输入年龄和正/负证据；`train_post` 仍可作为显式训练后事件。
3. 若不在不应期，四个输入直接按当前有符号连接求和，并用加入本 tick 贡献后的胞体值进行阈值判断。
4. `post_event = natural_spike OR train_post`，同一 tick 的两个来源只计一次。
5. 当前输入与当前 `post_event` 同 tick 视为正证据；当前输入与 tick 开始时仍有效的旧 `post_age` 视为负证据；旧 `pre_age` 与当前 `post_event` 视为正证据。正负证据可以同时置位，CAPTURE 时映射为中性。
6. 当前输入/当前后事件分别装载 `pre_age/post_age=WINDOW`，否则将旧计时减一；计时器只在接受的 TICK 末尾更新。
7. TRAIN TICK 产生的自然 spike 才进入 `spike` 输出；`train_post` 不伪造输出。

`WINDOW` 默认值、阈值和不应期长度必须在 P0 形成固定黄金向量，不允许 Python 与 RTL 各自解释边界。

`STATE_CLEAR` 只在单元空闲且 `pending_valid=0` 时接受，清除胞体、不应期、输入/输出窗口、正负证据和本次推理动态状态，保留连接和当前模式。推理期间的“冻结”指 INFER TICK 不修改连接和学习证据；显式 STATE_CLEAR 是受控的样本边界操作，不属于冻结违规。进入任何新 TRAIN/INFER 样本前必须成功执行 STATE_CLEAR。

**CONFIG**

- 允许按地址读写四条初始连接。
- 允许清动态状态。
- 连接写入只在 CONFIG 接受；TRAIN/INFER 中的连接写入握手并返回状态错误。是否允许再次进入 CONFIG 由可信 Host 的账本和上层调度控制，不在核心内增加永久写锁。

**TRAIN**

- 允许 tick、`train_post`、CAPTURE 和 FEEDBACK。
- 连接只能经 FEEDBACK 路径改变。
- 进入新样本前必须没有待反馈槽，再执行 STATE_CLEAR。

**INFER**

- 允许 tick 和动态状态清除。
- `train_post`、CAPTURE、FEEDBACK 和连接写入全部拒绝。
- 连接、最近输入/输出学习计时和正负证据保持不变；只更新胞体和不应期等推理动态状态。

模式只在单元空闲时改变。TRAIN 留有未消费反馈时禁止进入 INFER。模式编码 `2'b11` 非法。

### 5.8 建议接口

```text
clk, rst

cmd_valid, cmd_ready
cmd_opcode, cmd_arg0, cmd_arg1

rsp_valid, rsp_ready
rsp_status, rsp_data

spike                       # 仅 TICK 完成周期有效
pending_valid, protocol_error
```

`cmd_opcode` 至少包含 `MODE_SET / STATE_CLEAR / TICK / CAPTURE / FEEDBACK / WEIGHT_WRITE / WEIGHT_READ`。请求只有在 `cmd_valid && cmd_ready` 时接受；每个已接受请求恰好产生一个有序 response。非法范围或非法模式命令也必须握手并返回错误，不能只把 ready 永久拉低。`WEIGHT_READ` 的返回值放在 `rsp_data[3:0]` 并做符号扩展。

反馈编码固定为 `2'b00=0`、`2'b01=+1`、`2'b11=-1`，`2'b10` 非法。该核心只承诺单生产者、严格有序链路内的 exactly-once；跨 CDC、可重试总线或可能乱序的包装器必须由外部增加序号或 commit ID。

## 6. 资源预算

以下数字均来自历史 `xc7z020clg400-1`、Vivado 2024.1 证据，只作 Pulse-Mini 结构/资源对照；不代表当前 `xc7z020clg484-2` 主线的最终 routed 结果，也不再用早期估算覆盖实测值。

| 四输入单元 | LUT | FF | BRAM | DSP | 结论 |
|---|---:|---:|---:|---:|---|
| 原始方案字面实现 | 183 | 85 | 0 | 0 | 面积小，但 WNS `-1.605 ns`，学习功能不完整 |
| Pulse-Mini-L 单核 | 182 | 76 | 0 | 0 | WNS `+0.463 ns`，当前四输入主线 |
| Pulse-Mini-L2 单核 | 366 | 91 | 0 | 0 | WNS `-4.690 ns`，暂停扩阵 |
| ENeuron 1.0 XC7Z020 实测 | 818 | 544 | 0 | 0 | 完整多周期三因子核，作为已知上界参照 |

原始方案的 84 位状态代理来自四条树突各 8 位学习计数和 8 位分频进度，加 16 位胞体与 4 位睡眠计数；实测为 85 FF，说明状态位数估算接近，但组合路径和复位语义才是主要问题。

Pulse-Mini-L 虽然运行与 pending 状态约 69 位，但增加了有符号事件累加、正负证据标志、模式仲裁和单槽反馈控制；实测 LUT 与原始核接近，FF 反而更少。它的优势不是“每项都更省”，而是在相近面积下补齐抑制、双向学习、延迟反馈、冻结推理和事务边界。

### 6.1 已证明的阵列边界

简单广播阵列的真实布局布线结果如下：

| 并行核数 | LUT | FF | 100 MHz WNS | 结论 |
|---:|---:|---:|---:|---|
| 32 | 5867 | 2432 | `+0.151 ns` | 当前最大已证明点 |
| 64 | 11699 | 4864 | `-0.131 ns` | setup 失败 |
| 128 | 23342 | 9728 | `-0.466 ns` | setup 失败 |

64 核和 128 核的主要问题不是 LUT/FF 容量，而是输入广播、控制扇出、路由和输出拥塞。单槽响应口的持续接受率约为 `0.5 command/cycle`；因此阵列扩展必须同时解决布线和 Host/FIFO 带宽，不能只复制神经元实例。

共享树突 lane 的周期模型只能说明时分复用的理论周期，不能替代 routed 资源证据。任何新的阵列规模都必须重新综合、布局布线并报告 WNS/TNS/WHS/THS、BRAM、FIFO 和事件吞吐。

### 6.2 XC7Z020 容量口径

当前 XC7Z020 Vivado 报告给出的器件容量为 53200 LUT、106400 FF。Pulse-Mini 预计首先受 LUT 和布线限制，而不是 FF 限制。

| 单核实测 LUT | 只按 53200 LUT 相除 | 预留约 45% 给路由、控制和网络后的工程量级 |
|---:|---:|---:|
| 140 | 380 | 约 209 个 |
| 180 | 295 | 约 162 个 |
| 220 | 241 | 约 132 个 |
| 240 | 221 | 约 121 个 |

这些数字只适用于每个神经元固定四条输入。增加扇入必须同时报告突触数、路由代价和每 tick 吞吐，不能继续只报“神经元个数”。

工程口径：当前只把 32 个四输入核称为“已证明可在 100 MHz 运行”。64 个以上只能作为下一架构的扫描目标；若单核超过 260 LUT、或阵列 WNS 低于 0，先改架构，不通过删除负权重、反馈、模式冻结或饱和来制造低资源结果。

### 6.3 面向数字识别的最小规模

数字识别必须先冻结输入编码。若输入已经被片外编码为 4 个事件特征，`4 -> 8 -> 10` 是第一个值得做的十分类网络：18 个神经元、112 条相邻层连接。输出层使用 10 个 one-hot 神经元，每个神经元对应一个数字；不先用 4 位二进制码替代 10 个输出，因为二进制码会引入非法组合、位间耦合和额外解码规则。

| 网络 | 神经元总数 | 相邻层连接数 | 硬件含义 |
|---|---:|---:|---|
| `4 -> 10` | 10 | 40 | 适合先验证十分类协议 |
| `4 -> 8 -> 10` | 18 | 112 | 当前主线的首个小网络目标 |
| `16 -> 16 -> 10` | 26 | 416 | 已接近并行阵列边界，需扇入方案 |
| `64 -> 32 -> 10` | 42 | 2368 | 优先共享 lane/BRAM，不做寄存器复制 |
| `784 -> 128 -> 10` | 138 | 101632 | 原始 28×28 输入，必须事件编码、BRAM 和流水扫描 |

这里的“连接数”是突触槽数量，不等于四输入 Pulse-Mini 核的数量。固定四输入核心不能把 784 个输入直接接到一个胞体；必须先做输入编码、扩大扇入，或把树突状态放入 BRAM 后用共享处理 lane 分时扫描。

## 7. 实施 TODO

### P0：审核并冻结行为合同

- [x] 批准固定四输入、直接有符号事件累加、连接范围 `-7..+7`；原始分频仅作为 P1 基线。
- [x] 批准第一版无漏电，样本边界显式清动态状态。
- [x] 批准 `train_post` 只参与学习，不伪造外部输出。
- [x] 批准正/负两个 presence flag，CAPTURE 时按 `+1/0/-1` 映射。
- [x] 批准数值更新 `weight + feedback * captured_direction` 和 `-7..+7` 饱和。
- [x] 批准单槽 pending、无 core commit ID，pending 时拒绝下一训练段；外部可重试链路自行加序号。
- [x] 批准只按模式禁止 TRAIN/INFER 直接写连接，训练真实性由账本审计。
- [x] 冻结 TICK 事件顺序、窗口端点、冲突标志、模式、clear 集合和不应期合同。
- [x] 批准统一 `cmd/rsp` 事务接口和非法请求返回错误。
- [x] 冻结默认阈值、不应期长度和时间窗口，形成手算黄金向量。

交付物：本文件状态改为 `APPROVED`，所有未决参数有唯一值。

### P1：实现原始方案资源基线（已完成）

- [x] 新建 `pulse_original_core.sv`，严格实现原始四输入方案，不偷偷加入 Pulse-Mini 功能。
- [x] 明确选择一种“计数越大连接越强”的分频映射，并记录另一种映射为何被拒绝；P1 允许保留字面分频进度。
- [x] 为上限回绕、只能增强、无抑制和内部复位路径建立定向测试，保存其局限作为证据。
- [x] 使用 `xc7z020clg400-1`、100 MHz 完成 Vivado 综合与布局布线。
- [x] 记录 LUT、FF、carry、WNS/WHS、功耗估算和是否出现 derived clock/reset 问题。

硬门：P1 只形成“原始方案成本基线”，无论资源多小都不得宣称完成训练 Goal。

### P2：先做 Pulse-Mini 黄金模型（已完成）

- [x] 新建 `pulse_mini_reference.py`，只用整数和固定宽度语义。
- [x] 为直接有符号事件累加建立完整枚举测试，证明正连接促进、负连接抑制、零连接断开。
- [x] 覆盖正连接、负连接、零连接和正负胞体饱和。
- [x] 覆盖四位输入掩码的全部 16 种组合，证明输入顺序不影响结果。
- [x] 覆盖同 tick 输入/输出、窗口端点、presence flag、数值反馈和正负胞体饱和。
- [x] 覆盖 CAPTURE/FEEDBACK 有序单生产者 exactly-once、零反馈消费、pending 背压和非法模式命令。
- [x] 覆盖 CONFIG 写入、TRAIN/INFER 写入拒绝、动态清除保留连接、硬复位恢复初始连接。
- [x] 覆盖 INFER 期间全部学习状态和连接逐字段冻结。
- [x] 添加结构化日志：每次 tick、capture、feedback、模式改变和拒绝原因可审计。

硬门：黄金模型的状态转移表和手算向量通过审核后才写 RTL。

### P3：实现最小 RTL（已完成）

- [x] 新建 `pulse_mini_core.sv`，匹配现有 SystemVerilog 风格并添加必要模块/状态注释。
- [x] 所有寄存器只使用 `clk` 和外部 `rst`；不应期通过同步数据/使能实现，禁止逻辑生成时钟或内部异步复位。
- [x] 四输入固定并行，不先参数化任意扇入。
- [x] 中间加法显式扩位，所有缩位前做饱和，禁止依赖 Verilog 静默截断。
- [x] 统一 `cmd_valid/cmd_ready` 和 `rsp_valid/rsp_ready`，每次接受恰好产生一个有序 response。
- [x] busy 或 pending 时的第二事务不得改变任何状态。
- [x] `spike` 只在对应 tick 的完成周期有效。
- [x] 综合路径禁止乘法、除法、可变移位和逻辑生成时钟。

目标：核心文件保持小而直接，不为了未来任意网络提前加入通用微码或复杂总线。

### P4：bit-exact 与形式验证（已完成）

- [x] 建立 Python/Icarus 逐事务协同仿真，比较全部可见和内部状态。
- [x] 至少运行 20 seeds × 1000 个混合事务。
- [x] 加入权重边界、pending、模式切换、不应期、同步清除和同 tick 冲突的固定黄金回归。
- [x] 建立有限 BMC，证明一次接受一次完成、pending 不被覆盖、INFER TICK 不写学习状态、连接不回绕、非法请求不改状态。
- [x] 建立负向环境控制，证明去掉 pending exactly-once 门后可构造重复反馈反例。
- [x] 生成 `pulse_mini_signoff_summary.json`，绑定 RTL、参考模型、测试、形式脚本、网络包装器和固定事务集合 SHA-256。

硬门：随机协同仿真零差异，有限 BMC 零反例，负向控制必须产生预期反例。

### P5：证明它不是只有 STDP 外形（已完成）

- [x] 复用“总脉冲数相同、输入通道不同”的二分类思想，重新建立适合 Pulse-Mini 的最小任务。
- [x] 初态必须让未训练网络严格 abstain 或显著低于通过门槛，禁止靠硬编码初始连接直接答对。
- [x] 正式训练区间禁止直接连接写入，命令/调用账本记录 `train_post`、CAPTURE 和 FEEDBACK。
- [x] 每次反馈后逐树突核对 presence flag 映射、反馈符号、一步更新和饱和结果。
- [x] 训练后冻结进入 INFER，完成干净样本和至少 20 个未参与训练的扰动样本。
- [x] 推理前后逐字段确认连接和学习状态不变。
- [x] 增加无反馈、反馈符号反转、标签打乱三个负对照。
- [x] 若只在 `train_post` 提供逐神经元教师信号时成功，结论必须写为“神经元级监督/局部误差训练”，不得写成纯全局奖励学习。

能力硬门：训练后干净样本全对，20 个冻结扰动样本至少 19/20；无反馈和标签打乱不得同时达到该门槛。

### P6：XC7Z020 物理签核（已完成）

- [x] 新建独立的 Pulse-Mini Vivado Tcl 和 PowerShell runner。
- [x] 对 `xc7z020clg400-1` 执行综合、优化、布局布线和 min/max 时序分析。
- [x] 审计 latch、derived clock、combinational loop、multi-driver、未约束内部路径和 DRC。
- [x] 报告 LUT、FF、CARRY、BRAM、DSP、WNS/TNS、WHS/THS 和 vector-less 功耗条件。
- [x] 把报告解析加入独立 `verify_pulse_mini.py`，不修改 ENeuron 1.0 的签核结论。

硬门：

- 4 输入单核 `LUT <= 260`。
- `FF <= 140`。
- `BRAM = 0`、`DSP = 0`。
- 100 MHz 下 `WNS >= 0`、`TNS = 0`、setup/hold 失败端点为 0。
- route error、DRC Error/Critical Warning 为 0；OOC 环境白名单必须逐项解释。

优化目标：`LUT <= 220`、`FF <= 120`。超过硬门时先定位成本，不通过删除负权重、反馈、模式冻结或饱和来制造低资源结果。

### P7：复制扩展验证（资源、吞吐和容量边界已完成）

- [x] 先实现 32 核和 64 核固定四输入阵列，使用简单事件掩码/索引路由。
- [x] 在单核不超过约 230 LUT 时尝试 128 核。
- [x] 分别报告核心、路由、控制、配置接口的层次资源，禁止只报总数后反推单核。
- [x] 测量每 tick 周期数、最大持续输入率、输出拥塞和训练反馈带宽；见 `pulse_mini_array_metrics.py` 与 `pulse_mini_p7_signoff_summary.json`。
- [x] 比较“每核四路并行”与“多个神经元共享一条树突 lane”两种结构；见 `pulse_mini_lane_model.py`。lane 结果是周期模型，不冒充 routed 资源。
- [x] 对 128 核 routed 证据执行容量硬门审计：简单广播架构 64/128 核 100 MHz 时序失败，最大已证明并行规模为 32 核；128 并行容量保持 `NOT_PROVEN`，不把估算改写成实测声明。

### P8：固定小网络闭环（已完成）

- [x] 用两个 Pulse-Mini 隐藏单元和两个 Pulse-Mini 输出单元构成固定 `4 -> 2 -> 2` 网络。
- [x] 固定一拍隐藏层到输出层路由；输出层只能读取上一 tick 的隐藏结果。
- [x] 网络包装器提供逐神经元 `CAPTURE`、逐神经元反馈和有序响应，不把逐突触最终连接值交给 Host 直接计算。
- [x] 复用 ENeuron 1.0 的 M3 思路，记录初始化、训练 TICK、CAPTURE、FEEDBACK、读回、INFER 的完整账本。
- [x] 训练区间禁止 `WEIGHT_WRITE`；逐次核对四个单元的本地 presence flag、反馈符号和饱和连接变化。
- [x] 建立训练前 abstain、训练后 clean、20 个未参与训练扰动样本和推理冻结检查。
- [x] 建立 `pulse_mini_network_rtl_cosim.py`，对网络 RTL 做 272 条命令的训练/推理协同仿真。
- [x] RTL 网络验证正类输出位 1、负类输出位 2，并确认隐藏层到输出层只读上一 tick 的 pending 结果。
- [x] P8 已完成；Pulse-Mini 可声明为固定小网络训练/推理原型，但不外推为通用 AI 或纯全局奖励学习。

P8 已通过，因此不再阻塞“固定小网络训练与冻结推理原型”的声明；它仍不支持通用 AI、纯全局 reward 或任意规模网络的更强声明。

### P9：面向数字识别的软件能力门（下一阶段）

- [ ] 冻结输入编码、每样本 tick 数、事件率、训练/验证/测试拆分和随机初态。
- [ ] 先完成 `4 -> 4 -> 3`，再完成 `4 -> 8 -> 10`；输出采用 one-hot，明确全零、并列和非法多脉冲的 `abstain` 规则。
- [ ] 分开报告 `local_teacher`、`feedback_alignment` 和 `global_scalar_reward`；不能把神经元级教师结果写成纯全局 reward。
- [ ] 报告 balanced accuracy、macro-F1、混淆矩阵、覆盖率、并列率、首脉冲延迟、输出脉冲数和权重更新账本。
- [ ] 加入无反馈、标签打乱、反馈反向、训练前初态和推理冻结对照；训练前不得靠初始权重答对。

硬门：干净测试集达到预注册门槛；留出扰动集通过；无反馈和标签打乱对照不得同时达到主实验门槛；推理期间连接和学习状态逐字段冻结。

### P10：输入扇入与共享存储

- [ ] 对 `D=4/8/16` 做并行扇入与共享 lane 的 bit-exact 对照。
- [ ] 对 `D=64` 引入 BRAM/共享流水线，冻结读延迟、写回冲突和每 tick 周期合同。
- [ ] 对 `D=784` 只允许事件编码 + BRAM/lane 方案，不复制 784 路寄存器树突。
- [ ] 每个点重新完成 RTL 协同仿真、资源、路由、时序和 Host 带宽报告。

硬门：与四输入参考模型逐 tick、逐状态 bit-exact；100 MHz routed `WNS >= 0`、`TNS = 0`、setup/hold 零失败；目标事件率下 FIFO 不溢出。

### P11：L2 时序修复（可选支线）

- [ ] 保留每路正/负证据计数的算法语义，不删除幅度信息换取假性时序通过。
- [ ] 将 TICK 的积分路径与 CAPTURE/FEEDBACK 的证据差值、幅度更新路径分拍或流水化。
- [ ] 重新跑单核 Vivado，再决定是否进入阵列扫描；在 WNS 通过前不报告 L2 阵列容量。

硬门：单核 100 MHz routed `WNS >= 0`、`TNS = 0`，并与 L2 Python/RTL 模型逐事务一致。

### P12：阵列与系统化

- [ ] 以 32 核为已知通过点，扫描 `48/64/96/128`；同时记录扇出、输出拥塞、FIFO 深度和响应持续率。
- [ ] 比较分区广播、树形广播和共享 lane，禁止把周期模型冒充布局布线结果。
- [ ] 最后才把网络、Host Bridge、BRAM、FIFO 和双时钟一起做 XC7Z020 routed 签核。
- [ ] 预留至少约 30% LUT/FF 和布线余量；资源相除得到的核数只作为上限估算。

硬门：每个规模点都必须同时通过资源、时序、吞吐和任务能力四类门；任一失败都标记为 `NOT_PROVEN`。

### P13：板级与持续学习边界

- [ ] 选定具体 Zynq-7020 开发板、时钟、复位、电源和 Host I/O，再编写 XDC/top/bitstream。
- [ ] 用真实活动文件测动态功耗，区分空闲、训练、推理和最坏事件率。
- [ ] 单独设计多任务、持续学习和全局奖励信用分配实验；不能用 P8 的固定二分类结果代偿。

## 8. Go / No-Go

Pulse-Mini 进入后续网络开发必须同时满足：

1. 行为：能促进、抑制、双向学习、饱和、延迟反馈和冻结推理。
2. 真实性：训练锁定后没有直接连接写入，任务成功来自本地历史与神经元级反馈。
3. 可复现：黄金模型、RTL、形式检查和任务账本彼此独立且一致。
4. 物理实现：XC7Z020 单核不超过 260 LUT / 140 FF，100 MHz routed 时序通过。
5. 声明边界：固定 P8 网络已通过，但只称固定小网络训练/冻结推理原型；不把神经元级教师训练写成纯全局 reward，不把固定四输入容量外推为任意扇入，也不把 128 并行容量写成已证明。

若任务门失败但二因子相关性测试通过，只能把它归类为“小型无监督相关性单元”。若资源门失败，优先选择共享树突 lane 或缩短窗口，而不是重新退化为会回绕、只能增强的原始计数器。

## 9. 建议实施顺序

```text
P0-P8 已完成并签核
-> P9 数字识别软件能力门（先 4->4->3，再 4->8->10）
-> P10 大扇入、共享 lane 与 BRAM
-> P11 L2 时序修复（可选）
-> P12 分区阵列、Host 带宽与 XC7Z020 系统签核
-> P13 板级闭环、活动功耗和持续学习边界
```

当前 Go 状态：P8 固定小网络通过；数字识别、任意扇入、64 核以上阵列、L2 同频阵列、板级闭环和通用自训练仍为 `NOT_PROVEN`。任何阶段只有在对应硬门全部通过后，才把状态从 `TODO` 改为 `DONE`。

## 10. NPU 局部自动剪枝支线

局部结构化剪枝与动态门控已经独立规划到 `docs/planning/NPU_PRUNING_TODO.md`。NP0 八项决策已批准，ENeuron、Pulse-Mini-L、Pulse-Mini-L2 三种神经元必须分别运行；主线采用每四条连接保留两条、结构掩码与输入活动相交、共享 lane 在权重读取和计算发射前跳过无效连接。

- [x] NP1：公共 `2:4` 黄金模型、不可作弊工作量计数、B0 固定向量和 SHA-256 摘要。
- [x] NP2：三种神经元完成 dense/random/S0-S3、gain 1/2/3 扫描及同分/clip/稳定性统计；最小合格 gain 为 `1/2/1`。
- [x] NP3：三模型一次/渐进剪枝均为 100%，错误符号均为 0%；零 Host mask 写入、被剪状态和 INFER 冻结账本通过，选择一次剪枝。
- [x] B2.1：三模型三候选均为 BAcc/coverage 100%；output-2:4 与 detector-3:4 为 120，detector-2:4 为 80。按 KISS 选择 output-2:4，允许进入 NP4 设计审核。
- [x] Pulse-Mini-L 使用固定 `0→0, 1→2` 证据编码恢复 S2 算法门，并已独立通过 NP3/B2.1；没有借用 L2 结果。
- [x] NP4 接口审核：已于 2026-08-29 冻结隐藏/输出统一 `2:4`、gain=`1/2/1`、一次原子提交、无 detector gate、只走既有训练恢复、读取/发射前形成 `issue_mask` 六项 V1 决定。
- [x] NP4A 公共控制器：独立 `2:4` RTL、固定 gain 适配器、四拍原子提交、读取前门控和层级结构节省计数已通过。
- [x] NP5 公共控制器验证：三模型共 60000 条逐事务协同仿真、两个负向反例、depth=32 有限形式与成功提交可达性通过。
- [x] NP4B 规划：形成 `docs/planning/NPU_PRUNING_NP4B_TODO.md` 审核稿，冻结接入边界、测试矩阵、停止条件和进入 NP6 的签核门。
- [x] NP4B0 用户审核：已批准 committed snapshot 只读端口、Pulse 外部 wrapper、独立 `4→8→2` 网络、sideband 剪枝通道、一核一 gate、CLEAR 分离、commit 后自动清历史、NP6 二次审批八项决定。
- [x] NP4B 正式集成：ENeuron snapshot evidence 旁路、Pulse FEEDBACK evidence 锁存、真正四输入输出组、三模型各 20,000 条、五套形式证据和 359 项回归通过；NP6/NP7 已完成并合并，NP6 结论为 `NP6_PHYSICAL_COST_PARTIAL`，NP7 共享 lane 已签核。

### P14：传统 NPU + ENeuron 单时钟 RTL 物理门（V2 OOC 已通过）

- [x] 完成 V2 八项 RTL 裁定、四条单时钟 Icarus 垂直切片和真实四 lane INT8 计算。
- [x] 完成固定 `20 seeds × 100 samples = 2000` 个样本的逐 beat 随机协同仿真，覆盖 mask 轮换、全开/全关/mixed、负权重/负 bias、背压和 epoch。
- [x] 完成完整回归 `469/469（1 skipped）`，并将证据随 PR #54 合并至 `main@2a33f12`。
- [x] 以 `HEAD=39e41d4`（RTL 与 `origin/main@2a33f12` 相同）、Vivado 2024.1、`xc7z020clg400-1` 和 100 MHz 约束运行 OOC 综合、实现、setup/hold 与 DRC。
- [x] 记录 LUT/FF/BRAM/DSP、WNS/TNS/WHS/THS、失败端点、route/DRC 状态及报告 SHA-256；报告完整但物理门结果为 `NOT_PROVEN`。
- [x] 确认综合、布局布线和 DRC 流程退出码为 0，route errors=0、DRC errors=0、hold 无失败；确认 setup `WNS=-5.087 ns`、`TNS=-421.539 ns`、244 个失败端点，因此不能宣称 100 MHz 收敛。
- [x] 从 `timing_impl.rpt` 完成关键路径分类：前 20 条最差 setup 路径均从 `compute_group_index_reg[1]_rep` 进入 `hidden_values` 写入端；最差数据路径 14.775 ns、23 级逻辑，覆盖动态索引、四 lane 乘加、INT32 累加、末组饱和和写回。
- [x] 形成 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_V1.md` 审核稿，提出最小 `FETCH→EXECUTE→COMMIT` 分拍、外部协议不变和 LUT-only 优先策略。
- [x] 形成 `docs/planning/NPU_SINGLE_CLOCK_TIMING_REPAIR_TEST_CONTRACT_V1.md`：冻结 592/590/591/0 启用组、1860/1856/1858/676 拍延迟、启用组三拍稳定、两层关闭末组旁路和实测 watchdog 预算；未修改 testbench/RTL。
- [x] 管理员批准 TR1-TR6 六项时序修复裁定，并要求四条乘法 lane 强制使用 DSP48E1；Vivado 必须报告 `DSP=4`。
- [x] 修正测试握手竞态并增加逐组 FETCH/EXECUTE/COMMIT、模型地址、三拍稳定和关闭组直接旁路断言；实现 `lane_sum_latched`、L0/L1 `EXECUTE/COMMIT` 与四条共享 DSP lane，保留 INT32、mask epoch、结果背压和推理冻结语义。
- [x] 重跑单时钟专项 8/8、固定 `20×100` 随机逐 beat bit-exact 和完整仓库 473/473（1 skipped）；最终两路反审计阻断项已闭合。
- [x] 提交实现并以 `5055073` 运行 Vivado OOC：utilization `DSP=4`、网表 `DSP48E1_COUNT=4`、hold/route/DRC 通过；setup `WNS=-0.673 ns`、`TNS=-6.462 ns`、22 个失败端点，物理门保持 `NOT_PROVEN`。
- [x] 按冻结报告先分类前 20 条路径，并形成 `NPU_SINGLE_CLOCK_TIMING_REPAIR_V2.md` 审核稿。
- [x] 从 routed checkpoint 扩展到最多 50 条路径，完整覆盖全部 22 个失败端点：14 个动态激活选择/DSP/求和端点，8 个 logit 写使能端点；审计见 `docs/verification/NPU_SINGLE_CLOCK_TIMING_ENDPOINT_AUDIT_V1.md`。
- [x] 端点补证经 PR #60 的 CI-Fast/PR Gate 和 Webhook 同 SHA 闭环后合并为 `main@4fc4c71`。
- [x] PR #61 将端点审计后的持久状态同步合并为当前 `main@bef5979`。
- [x] 完成 V2 KISS 实施审计：复用现有 signed 32-bit `mac_accumulator`，不新增 `writeback_value_latched`；预计只新增四个 signed 8-bit 激活锁存器约 32 FF，并形成独立实施地图。
- [x] V2 审核材料与总 TODO 漂移修正经 PR #62 的最终 HEAD `a4832cc`、run `33915028445` 通过后合并为 `main@e8dc947`；仍未开放 RTL 实施授权。
- [x] 管理员于 2026-09-05 批准 TR7-TR12；开放 V2 RTL 与独立测试合同实施。
- [x] 新建独立 V2 测试合同，更新 C1-C4、WRITEBACK/激活锁存白盒门与 compute watchdog，并在旧 RTL 上取得精确 RED。
- [x] 最小修改计算 RTL：FETCH 锁存四个激活、EXECUTE 只读锁存操作数、统一 WRITEBACK 复用 `mac_accumulator`，继续强制恰好 4 个 DSP48E1。
- [x] 通过单时钟定向、固定 `20×100` 随机逐 beat 和完整仓库回归：`475 tests / OK (skipped=1)`。
- [x] 使用同一器件、100 MHz 约束和 Vivado 2024.1 重跑 OOC：`2126 LUT / 1916 FF / 0 BRAM / 4 DSP48E1`，`WNS=+0.060 ns / TNS=0`，`WHS=+0.040 ns / THS=0`，setup/hold/route/DRC 零失败。
- [x] PR #64 HEAD `f744bff2bdde68e138a7b2b348ce103bec1ab469` 的 GitHub Actions run `33946568679` 全部成功，并于 2026-09-05 合并为 `main@a53a040`。
- [x] OOC 通过后完成 XC7Z020 顶层、DMA/PS/网口和板级功耗的分阶段规划；规划文档为 `docs/planning/NPU_ZYNQ7020_TOPLEVEL_INTEGRATION_V1.md`，不得把 OOC 结果外推为板级结论。

### P15：XC7Z020 顶层适配器与板级闭环规划

- [x] 冻结核心与 Host Bridge 的复用边界：核心保持 128-bit 命令/响应、固定 8/10 beat，双时钟只经异步 FIFO。
- [x] 冻结 T0→T4 阶段：合同、纯 RTL 适配器、双时钟协同仿真、XC7Z020 顶层物理门、网口/训练闭环。
- [x] 形成 T0 端口与适配边界裁定稿：`docs/planning/NPU_ZYNQ7020_TOPLEVEL_DECISION_SHEET_V1.md`。
- [x] 完成 P15-T0 静态审计：`docs/planning/NPU_ZYNQ7020_TOPLEVEL_T0_AUDIT_V1.md`，确认样本/结果完整 FIFO payload 为 64/96 bit，并记录七项 T1 阻断。
- [x] 在开放 T1 前裁定命令字段唯一格式、V1/V2 framing 权威、跨流 fence、reset-busy 汇合、AXI sideband 错误语义、FIFO 参数和 XC7Z020 物理约束（A1-A7 已批准）。
- [x] 评审 V1 顶层端口命名、AXI 外部适配位置和 PS/DMA 责任边界；AXI/PS/DMA 保持在 T3 之外。
- [x] 实现纯 RTL 顶层薄封装并完成已定义的逐 beat、背压、复位和负向协议切片；T1 全量矩阵仍待完成。
- [x] 对“核心 + 适配器 + FIFO”运行 XC7Z020 OOC，单独归因新增 LUT/FF/BRAM/DSP 与时序；T3 证据绑定 `c2bc03f`。
- [ ] 选定开发板、Ethernet/PS 软件栈和真实 XDC 后，运行含 PS7/AXI/DMA 的顶层实现门。
- [ ] 以旁路 NPU 与 ENeuron 门控 NPU 做网口输入 A/B，报告有效 MAC、周期、准确率、丢包和动态功耗。

已完成的阶段性切片：T2 可变时钟 testbench 已在三组非整数频率/相位下覆盖 pending mask epoch 与当前样本计算重叠；旧结果保持 epoch=1，下一 fence/样本才切到 epoch=2。该切片不等于 T2 全矩阵、T3 或板级闭环。

T2 FIFO 独立矩阵已通过 8 组固定时钟配置×3 个 seed，四通道逐项比对实际写入/读出序列，覆盖满空、回绕、同拍读写、长背压和 reset 清空。证据入口是 `python -X utf8 tools/repro/verify_repository.py --t2-fifo-matrix`；这只是 Icarus FIFO 等价模型的固定伪随机切片，不代替真实 XPM/xsim 或 T3。

wrapper 交错/复位切片已在 4 组时钟配置下通过：模型装载中途、结果背压中和 sample 第 4 beat 前注入 reset 均不会留下旧 payload；mask 命令与 sample beat 在同一 Host 时间段可交错接受。证据入口是 `python -X utf8 tools/repro/verify_repository.py --t2-interleave-reset`；这只是 wrapper 切片，不代替 T2 数学穷举或 T3。

T2 wrapper 时钟覆盖已补齐 16 组确定性组合和固定种子 `20260907` 生成的 24 组唯一随机组合；入口分别为 `--t2-full-matrix` 与 `--t2-random-matrix`。慢时钟组合的结果观察预算按 `2000 + 400 × NPU_HALF` 个 Host 周期缩放。两组矩阵均已通过，但仍只属于有限可复现压力集，不得称为所有频率/相位的数学穷举。

P15 硬门：双时钟逐 beat bit-exact；reset/ready-valid/FIFO 满空无丢失、重复、乱序；核心 OOC 基线不被错误覆盖；顶层 routed `WNS>=0`、`TNS=0`、setup/hold/route/DRC 零失败；板级吞吐和功耗必须使用真实板级证据。

### P16：项目阶段 2——XC7Z020 实板验证

目标是在 HelloZynq `xc7z020clg484-2` 上依次打通 PL、PS/DDR/网口、DMA、`64→32→10` 传统 NPU、ENeuron 局部门控和网口端到端 A/B。阶段 2 只由实板证据关闭任务；仿真和 OOC 可用于定位，但不得替代 bitstream、JTAG、UART、Host/网口采集和现场观测。

#### P16-E：公共证据合同

- [x] 固定板卡与参考源：HelloZynq、`xc7z020clg484-2`、板厂 `master@73d529d8f159ca372b7d9855eddc80880ecd9d05`、Digilent JTAG `210251A08870`。
- [x] 固定软件/硬件基线：PR #68 已在精确 HEAD 完成本地 G0/T1/T2 复现并合并为 `main@7857d32561cbd5f86d02b1a21ee0edfb3ae895f1`。
- [x] 使用隔离工作树 `D:\Documents\Code\ENeuron-board-b0`；当前活动分支为 `codex/b1b-high-ddr-board-repro`，不携带主工作树未提交修改。
以下条目是所有阶段持续适用的证据合同，不计入一次性 TODO 数量：

- **P16-E01**：每个阶段开始前写清入口条件、当前 Git HEAD、未跟踪保护文件和允许修改的目录；入口条件不满足时不得用后续阶段结果反向补齐前序门。
- **P16-E02**：每个正式 bitstream 保存 Git commit、Vivado完整版本、完整 part、顶层、RTL/XDC/Tcl/PowerShell哈希、bitstream SHA-256、资源、时序、route/DRC结果和构建时间。
- **P16-E03**：每次实板运行创建独立运行目录；原始日志只追加或另存新文件，第二次运行不得覆盖第一次证据。目录命名格式不作为硬门。
- **P16-E04**：每次运行保存 bitstream SHA-256、JTAG target/device、板卡/调试器身份、测试开始与结束时间、输入向量或数据集哈希、软件提交、串口/Host原始日志、机器判定和人工观测。
- **P16-E05**：机器摘要至少包含 `status`、实际执行命令、退出码、通过条件、首个失败项、关键计数器和全部输入/输出文件哈希；摘要不得只保存人工整理后的结论。
- **P16-E06**：人工观测记录观察对象、板上丝印、FPGA引脚、开始/结束时间、持续时长、预期行为、实际行为和观察者确认；照片或视频可作补充，但不代替文字判定。
- **P16-E07**：正式脚本遇到身份不一致、超时、协议错误或硬门失败时返回非零；失败证据保留在独立目录，修复后创建新运行，不修改旧日志制造 PASS。
- 禁止跨证据包拼接：不同 commit、源文件哈希或 bitstream SHA-256 的构建、program、现场输出不能合并成同一次 PASS。
- 失败时保留首个失败输入、完整输出、错误码、关键状态和复现命令；修复后创建新的证据包，不覆盖原始失败记录。

#### P16-F：Fastlane V1

- [x] 管理员要求缩短验证链并尽早进入主线；采用“小PR、定向验证、身份未变则复用、阶段末集中收口”，不降低B1～B4最终硬门。
- [x] B1拆为B1A板级事实/可重建硬件定义、B1B PS7/UART/DDR、B1C PHY/UDP；安全增量可提前合并，但必须明确标记 `B1_IN_PROGRESS`，不得宣称B1通过。
- [x] 文档/JSON变更只运行解析、状态一致性和差异检查；软件变更不重建未变化的PL；只有RTL/XDC/BD/Tcl/IP配置身份变化才重跑Vivado。
- [x] 实板步骤在一次连接会话内按依赖顺序批量执行；不因中间文档提交重复下载、重启或重复测量。
- [x] Actions关闭期间不等待空checks；本机定向门、PR CLEAN/MERGEABLE和证据边界是合并依据。
- [x] B1A-SOURCE：完成固定板厂提交的配置、器件和引脚来源审计，形成带 Git blob/SHA-256 的文档与机器清单；该切片不代表 B1A 完成。
- [x] B1A-HW：已冻结实际DDR兼容配置、R46 NC导致的PHY复位边界、运行期PHY地址扫描和RGMII约束，形成可重建BD Tcl/XDC与硬件入口；正式UART方向`V14=RX/V15=TX`的干净提交`29edf6a`已通过Vivado 2024.1实现。
- [ ] B1B：PS7、正式UART路径和低地址1 MiB DDR已完成三次冷启动；PR #75已合并OCM驻留高地址诊断。当前先用 `VID_1A86:PID_7523` 恢复串口接收基准，再执行`0x10000000`最小复现并关闭高地址异常。
- [ ] B1C：在B1B主线基线上完成PHY、MDIO和最小UDP实板门，形成B1-GATE最终摘要。

当前主线执行链：`B2-00 低地址容量证明 -> B2-D1 DMA方案冻结 -> B2-01～B2-GATE -> B3 NPU + ENeuron固定向量`。B1-06B6～B1-06F高地址DDR诊断保留为板卡资格支线，B1C仍在B1-06F之后；支线未关闭时必须标记`B1_HIGH_DDR_PENDING`，但不再阻塞满足B2-00入口条件的NPU MVP。

#### P16-B0：PL 配置、50 MHz 时钟和 LED

- [x] B0-01：冻结最小设计为 M19 50 MHz → 26-bit自由计数器 → P20 LED；不实例化 PS7、DDR、Ethernet、ILA、DMA或 NPU。
- [x] B0-02：实现顶层 RTL、M19/P20 `LVCMOS33` XDC、Vivado非工程模式构建入口和仅配置 PL 的 JTAG入口。
- [x] B0-03：编程入口把 `DONE_INTERNAL=1`、`DONE_PIN=1`、`ISC_DONE=1` 同时设为硬通过条件；任一不为1时返回失败。
- [x] B0-04：在当前源码提交 `f3b8174e8ca30d427e9de3eea2d36feb6a5e6a06` 上完成 Vivado 2024.1 实现：`1 LUT / 26 FF / 0 BRAM / 0 DSP / 1 BUFG`，`WNS=+17.918 ns`、`WHS=+0.251 ns`，setup/hold失败端点、route Error、DRC Error/Critical Warning均为0。
- [x] B0-05：生成当前正式候选 bitstream，SHA-256 为 `df16ed6ccd9124f2dc4391d96e868ebd7846aebf3df335099b742cc7cd318971`。构建时因文档尚未提交，manifest 正确记录 `git_worktree_clean=false`；源文件哈希和源码提交已绑定。
- [x] B0-06：保留历史证据边界：旧 bitstream `c16a1f8...e3d1` 已连续两次 program 且三项 DONE 为1，但不能替代当前 `df16ed6c...8971` 的 program 证据。
- [x] B0-07：当前 `df16ed6c...8971` 已于 `2026-09-07T10:22:56Z` 完成第一次正式 JTAG program；target为 Digilent `210251A08870`、device为 `xc7z020_1`，`DONE_INTERNAL/DONE_PIN/ISC_DONE=1/1/1`，CRC/IDCODE/security error为0，原始日志 SHA-256为 `0152fe32...a49e`。
- [x] B0-08：用户确认 `PL_LED1/P20` 稳定闪烁；从一次“刚亮”到第10次再次“刚亮”实测13.42秒，理论13.4217728秒，误差约-0.013%，位于预先冻结的12.6～14.2秒人工秒表通过窗内。先前“约1秒”的单周期目测疑点已由长窗口测量排除。
- [x] B0-09：已将第一次机器输出固化到 `artifacts/logs/hellozynq_b0/20260907T102256Z_df16ed6c_run1_machine/`；保存 program result、完整 transcript、build manifest和独立 archive manifest，program log SHA-256仍为 `0152fe32...a49e`，现场状态明确为 `PENDING`。
- [x] B0-10：run-1 的 `field_observation.json` 已保存初始目测、10周期13.42秒实测、冻结通过窗、误差和 PASS判定；archive manifest同步为 `observation_status=PASS`。run-1机器下载与现场功能证据闭环。
- [x] B0-11：用户确认关闭主电源且供电指示全部熄灭；Vivado 2024.1只读探针仍枚举到精确 Digilent线缆，但打开target明确报告 `No devices detected`，可访问FPGA数为0，`B0_COMPLETE_POWER_OFF_JTAG_INACCESSIBLE=PASS`。证据目录为 `artifacts/logs/hellozynq_b0/20260907T150221Z_df16ed6c_power_off/`，transcript SHA-256为 `3a953999...1f634`，证明本次是完整断电而非热重连。
- [x] B0-12：完整断电后重新上电，只读探针确认同一 Digilent `210251A08870` 上唯一 `xc7z020_1` 恢复且下载前 `DONE=0`、`PROGRAM.FILE` 为空。本地 bitstream SHA-256 仍为 `df16ed6c...8971`；第二次正式 program 后请求路径一致、三项 DONE=`1/1/1`，CRC/IDCODE/security error均为0。机器输出已固化到 `artifacts/logs/hellozynq_b0/20260907T152656Z_df16ed6c_run2_machine/`，现场观察仍为 `PENDING`。
- [x] B0-13：第二次观察同一 `PL_LED1/P20` 10个完整周期实测 `13.4 s`，通过相同的 `12.6～14.2 s` 判据；机器输出和现场 JSON 已固化为唯一 run-2，目录为 `artifacts/logs/hellozynq_b0/20260907T152656Z_df16ed6c_run2_machine/`，未覆盖 run-1。
- [x] B0-14：两次当前产物 program、两次现场观察和完整断电复测已写入 `artifacts/results/hellozynq_b0_smoke_summary.json` 与 B0 报告；run-1/run-2 program log SHA-256分别为 `0152fe32...a49e`、`1d4fada3...3613b`，状态提升为 `B0_COMPLETE`。
- [x] B0-15：Nexus、artifact索引、摘要JSON和定向回归通过；PR #69 已合并为 `main@102dee2a004283ce4144aaf6ee0a2cee3ebd2887`。Actions关闭期间空checks未作为通过证据。
- [x] B0-GATE：当前 bitstream 的构建、两次 program、三项 DONE、两次现场观察和完整断电重启复测全部绑定一致，B0已在主线标记为 `PASS/B0_COMPLETE`。

#### P16-B1：PS7、DDR、UART、PHY和最小 UDP

- [x] B1-00：入口已满足 `B0-GATE=PASS`；Fastlane V1 已进入 `main@308bdecd9573e71340359729fdbb2f3fcb7723c7`，B1A 来源审计从该主线启动。
- [x] B1-D1：管理员已批准首轮使用 `bare-metal + lwIP`；B1B只引入裸机UART/DDR，lwIP在B1C加入。Linux保留为后续部署候选，不作为首轮 bring-up 前提。
- [x] B1-01A：从固定板厂提交提取 PS7、DDR、UART0、GEM0-EMIO、GMII-to-RGMII、200 MHz FCLK0、复位和XDC来源；机器清单绑定每个关键文件的Git blob与SHA-256。
- [x] B1-01B：按板载 `MT41K256M16TW-107:P` 冻结为Vivado官方 `MT41K256M16 RE-125` 保守兼容配置，16-bit、533.333333 MHz；仓库内Tcl不依赖板厂绝对路径。
- [ ] B1-02：UART0/RGMII/MDIO引脚和I/O标准已核对；继续确认板修订、H17 PHY reset时序、物理PHY地址、Bank/电压/器件引脚和完整RGMII板级时序。
- [x] B1-02U：实板诊断后管理员批准UART0正式映射为`V14=RX`、`V15=TX`、LVCMOS33；外置3.3 V USB-TTL保持`V14←适配器TX`、`V15→适配器RX`并共地，不连接VCC，测试期间不启用与V14/V15共网的HDMI并行RGB功能。
- [x] B1-03：启动路径和串口合同已冻结：首轮由JTAG下载硬件与ELF，串口使用115200 8N1并以CH340的`VID_1A86:PID_7523`识别，COM号不作为固定合同；2026-09-08环境探测枚举为COM10。脚本以固定身份字段和begin/end marker判定；SD/QSPI自启动保留为后续独立验证。
- [x] B1-04：旧提交`f0dbc84`的`V14=TX/V15=RX`实现证据保留为历史且已被实板结果否决；批准的`V14=RX/V15=TX`已在干净提交`29edf6a`上重建。资源保持`136 LUT / 257 FF / 0 BRAM / 0 DSP`，WNS/WHS=`+0.240/+0.138 ns`，route/DRC error为0，bitstream/XSA SHA-256分别为`1f98e949...bc5f6`、`ed4a2ff...d417b`。
- [x] B1-05：最小启动程序已输出固定banner、软件/硬件提交、XSA/bitstream哈希、CPU/FCLK频率和DDR测试范围；同一冻结组合cold-run-1/2/3均PASS。断电边界由管理员现场确认，不额外要求断电期间JTAG探针；PHY状态与复位原因留到B1C。
- [ ] B1-06：低地址子门已经完成，高地址子门仍未完成。关闭D-Cache后的`0x01000000–0x010FFFFF`已在三次冷启动中通过九个阶段，首错字段均为0；后续只按B1-06A～B1-06F定位此前`0x10000000`异常，不重跑低地址三次门。
- [x] B1-06A：高地址探针合同已冻结。高地址诊断ELF必须改为从低位OCM运行，代码、页表、堆和栈不得放在DDR；当前正式ELF运行时占用约53 KiB，低位OCM为`0x00000000–0x0002FFFF`，预留末尾4 KiB的`0x0002F000`结果区后容量足够。构建必须检查所有运行时section均低于`0x0002F000`，且ELF下载后先验证OCM执行和UART，再允许写DDR。PS7配置声明的`0x1FFFFFFF`仅是候选上界，不是实板通过事实。
- [ ] B1-06B：最小复现旧故障。独立高地址诊断源、构建入口和实板入口已创建，未修改已签核的`boards/hellozynq/b1b_sw/src/main.c`及三次低地址证据；OCM ELF构建门已通过。两次实板尝试均停在READY等待GO，`completed_accesses=0`，尚未访问DDR，因此当前结果既不是高地址PASS也不是DDR失败。先按B1-06B6恢复UART基准，再按B1-06B7执行`0x10000000`附近稀疏地址点和4 KiB单一固定模式读写。若最小模式不能复现旧失败，必须回查旧程序、构建身份和测试顺序，不得直接宣称高地址已修复。
- [x] B1-06B1：独立链接脚本把应用区固定为`ORIGIN=0x00000000, LENGTH=0x0002F000`，把`0x0002F000–0x0002FFFF`保留为结果区；代码、向量表、页表、只读数据、可写数据、BSS、heap和全部处理器模式stack均不得进入DDR或结果区。构建产物`runtime_end=0x0000D840`，入口为`0x00000000`。
- [x] B1-06B2：链接后以`arm-none-eabi-readelf -lW`检查所有`PT_LOAD`的物理范围完全落在`[0x00000000,0x0002F000)`，并以`arm-none-eabi-nm -n`检查入口、向量表、页表、heap、各模式stack和`_end`；任一地址越界时构建返回非零，不生成可上板候选。合并主线`436d1b2`的干净构建为`load_segment_count=1`、入口`0x00000000`、`runtime_end=0x0000D840`，ELF SHA-256=`619ab70cb5ee457bba0e059977442d89c797793386b855ce21eeec1da2631b82`。
- [x] B1-06B2A：诊断源、linker、runner、合同测试和文档经PR #75合并为`main@436d1b2b089c5bf64ac306434349465291f31395`；manifest记录`git_worktree_clean=true`。正式上板入口拒绝未提交工作树，并核对当前HEAD、源码/linker、bitstream/XSA/ELF哈希与构建manifest完全一致。
- [x] B1-06B2B：在构建身份`dae5473ba72d6cfaee12ed8e103c0efad190ed4a`的干净工作树中重新完成B1A/B1B/OCM构建；B1A bitstream=`ccbdf1df6fae9a3d0eece48e5fed90422397703662e7e9ebf15d0576972e5b45`、XSA=`62ea171a913cb2e66765f4cedb9b0973513cdebcde17982490c1f7f661d59ceb`，低地址ELF=`dcc0e261b7513cf6d8f9e8c6e3022a65f2f2c6de2d0a3f12900d66b57a66662f`，OCM诊断ELF=`3e0469265a1482081ce93188d905753b2fa998673a17e575776e115abfb76f01`；Vivado 2024.1、`xc7z020clg484-2`、WNS/WHS=`+0.240/+0.138 ns`、route/DRC error为0。构建通过不等于板级签核，以上新身份尚未上板。
- [x] B1-06B3：DDR危险访问前先在OCM结果记录写入版本、`RUNNING`、阶段、窗口、地址、操作、宽度和期望值并执行内存屏障；读回后再写实际值，失败最后写`FAIL`，全部完成最后写`PASS`，避免CPU异常时只留下空记录。
- [x] B1-06B4：ELF下载后必须先取得UART READY，再由JTAG核对OCM READY、执行地址和CPU状态后写GO；无论UART、READY/GO、编程或结果超时，runner都会采集OCM、PC、SP和CPSR后统一失败退出。历史 COM32误选和COM13无UART两次尝试均证明该门保持`command=0 / completed_accesses=0`，没有在前置条件不满足时访问DDR。
- [ ] B1-06B5：正式证据包保存干净Git HEAD、硬件身份、bitstream/XSA/ELF及源码/linker哈希、链接布局检查、完整UART、OCM结果、CPU状态和首错字段；使用新目录，不覆盖三次低地址冷启动证据。
- [ ] B1-06B6：恢复当前UART接收基准。仅使用接在 V14/V15 上的外置 3.3 V USB-TTL 适配器，按 `VID_1A86:PID_7523` 查找其 CH340（2026-09-08 当前枚举为 COM10；`COM6/COM7` 为蓝牙串口，禁止替代），使用115200 8N1，复用已签核低地址B1B bitstream/ELF做一次非冷启动串口基准复测。只判定能否收到既有banner/alive marker，不重新签署低地址DDR门。最新复测使用构建身份`df561803fd44f791a38bda3be3422fe1f6411b77`，FPGA program、ELF download和CPU run均PASS，但20秒内无终止标记，结果为`NO_TERMINAL_MARKER`，证据目录为`artifacts/logs/hellozynq_b1b/20260908T202605Z_df56180_b1-06b6_uart_no_marker/`，不计为通过或DDR失败。若仍无输出，停止并处理 V14←适配器TX、V15→适配器RX、共地、端口占用和接触；板载 CH340 的 L17/M17 不属于当前 UART 路径；不得使用 COM6/COM7 蓝牙串口替代，不得修改OCM诊断或发送GO。普通和高地址runner的PowerShell `$PID`参数冲突已修复为`$ProductId`；普通 runner 已在等待 XSCT `.bat` 子进程后刷新 `Process`，后续 manifest 必须记录实际退出码。
- [ ] B1-06B7：B1-06B6通过后，继续使用接在 V14/V15 上的外置 3.3 V USB-TTL 适配器，并使用与 manifest 绑定的构建身份`dae5473ba72d6cfaee12ed8e103c0efad190ed4a`及其 OCM 诊断ELF（SHA-256=`3e0469265a1482081ce93188d905753b2fa998673a17e575776e115abfb76f01`）重新运行。不得把板载 L17/M17 CH340、历史`436d1b2` ELF或未绑定的开发产物混入本次证据。必须先看到 UART READY，并由 JTAG 确认 `status=READY`、`phase=OCM_READY`、`execution_address<0x0002F000`、PC/SP 位于 OCM，再写 GO；随后以 UART、OCM 和 CPU 三路证据裁定稀疏地址及 4 KiB 固定模式为 PASS、数据失配、地址别名或 CPU 异常。
- [ ] B1-06C：执行分段定位。先按`0x02000000`、`0x04000000`、`0x08000000`、`0x10000000`、`0x18000000`五个基址运行相同稀疏探针，再在最后通过点和第一个失败点之间按地址高位二分；确认窗口可访问后才把该点扩大到1 MiB。结果分为“窗口可读写”“地址别名失败”“数据模式失败”“不可访问/CPU异常”，禁止把不同类别合并成一个DDR失败。
- [ ] B1-06D：区分地址映射与容量边界。对二分得到的最后通过窗口和第一个失败窗口，各重复至少两次冷启动；比较失败地址是否固定、是否只在高位地址变化时出现、是否伴随同一别名偏移。若失败点随窗口变化，优先审计地址映射/PS7配置；若固定在边界，记录为已测容量上界候选，不修改配置掩盖故障。
- [ ] B1-06E：扩展通过窗口。只有B1-06B～D给出稳定解释后，才在同一冻结身份下扩展为连续窗口测试；每个窗口保留独立manifest、UART原始日志、OCM结果和首错字段。任何新失败都创建新证据目录，不覆盖三次低地址PASS材料。
- [ ] B1-06F：关闭验收。必须同时满足：旧`0x10000000`结果已解释、最后通过窗口边界可复现、诊断ELF全程从OCM运行、至少一个高地址1 MiB窗口完成全九阶段测试、摘要与Nexus身份一致。满足前仅标记`B1B_HIGH_DDR_PARTIAL`，不得勾选B1B完成或进入B1C。
- [ ] B1-07：通过 MDIO读取并保存 PHY ID、基本状态、协商结果、双工和链路速度；单独执行 PHY reset，验证无需重新配置 PL即可重新发现。目标为1000 Mbps全双工；若外部交换机/网卡只协商到较低速率，先修正测试环境或降低声明范围。
- [ ] B1-08：冻结 Host与板端 IP/MAC/UDP端口，保存 Host网卡和链路配置；实现最小 UDP echo或固定响应服务，分别测试64、512、1472-byte payload，每档至少1000包，逐包核对 sequence、长度、payload和端点。
- [ ] B1-09：在持续发送期间拔插网线，记录链路下降时间、软件状态、重连时间和首个恢复包；要求软件不死锁、无陈旧包冒充新响应，重插后无需重新烧写 bitstream即可恢复收发。
- [ ] B1-10：对三档 payload 各保存发送数、接收数、错误数、超时数、重复/乱序数和往返时间分布；吞吐只作基础设施基线，不与 NPU性能混写。
- [ ] B1-11：B1B部分已归档构建manifest、XSA/bitstream/ELF哈希、三次冷启动UART原始日志、DDR逐项摘要、OCM结果、机器摘要和阶段报告；MDIO快照、Host逐包账本与拔插恢复日志待B1C补齐。
- [ ] B1-RECOVERY：UART失败先停在PS时钟/复位/串口；DDR失败时禁止继续网络；PHY ID错误先停在MDIO/复位/时钟；UDP错误只在前三项通过后定位 lwIP或Host，不同时改多个层级。
- [ ] B1-GATE：UART稳定、DDR零错误、PHY可识别且千兆链路成立、UDP三档payload零错序/零内容错误、拔插可恢复后，才能关闭网络化 B1C 并进入完整 B4；B1 不声明 NPU已经接入。低地址窗口内的 B2-MVP 由 B2-00 明确授权，不等同于 B1-GATE 通过。

#### P16-B2：AXI DMA和固定帧流协议

- [x] B2-00：已冻结 `xc7z020clg484-2` 低地址 DMA 布局合同：模型、mask、命令/样本/响应/结果和 loopback 缓冲区均落在已验证 `[0x01000000,0x01100000)` 窗口内，manifest 明确 `B1_HIGH_DDR_PENDING`；机器验证器和合同见 `tools/repro/b2_dma_address_layout.json`、`verify_b2_dma_address_layout.py`、`docs/planning/NPU_ZYNQ7020_B2_ADDRESS_LAYOUT_V1.md`。这只开放低地址 B2-MVP，不代表完整 `B1-GATE`、网络化 B1C 或 B4 通过；任何基础设施变化都必须重跑受影响的 B1 项。
- [x] B2-D1：已冻结首轮 DMA 控制合同：AXI DMA simple mode、单次 buffer、polling、S2MM 先行、TX flush/RX invalidate、1 us polling、1 s 传输超时、500 次 reset poll、错误/超时寄存器快照和单次短帧恢复；scatter-gather、micro-DMA、interrupt 均不进入首轮。合同与验证器见 `docs/planning/NPU_ZYNQ7020_B2_DMA_CONTRACT_V1.md`、`tools/repro/b2_dma_contract.json`、`verify_b2_dma_contract.py`。
- [x] B2-01：已冻结 PS DDR发送/接收缓冲区为 `0x01006000/0x01007000`、各 4 KiB、64-byte 对齐、最大帧长 4096 bytes；布局合同、DMA 合同和 standalone 软件共同落实 `CPU填充→flush→DMA拥有→完成→invalidate→CPU读取`，DMA拥有期间 CPU 不修改对应 buffer。
- [x] B2-02：已由 B2-D1 合同冻结 DMA 控制：simple mode、polling、超时、状态寄存器采样、错误清除和复位顺序；每次超时保存 DMA 寄存器、缓冲区头尾、PL 计数器和当前 sequence。该项不再与 B2-D1 重复计数。
- [ ] B2-03：PL AXI-Stream direct loopback 已完成构建，并已在实板以 JTAG 状态区和 UART 证明边界矩阵与受控背压帧搬运；最新轻量双向 `axis_stream_probe` 构建在 `xc7z020clg484-2` 通过 routed/DRC/bitgen（`WNS=+0.017 ns`、`WHS=+0.014 ns`、`TNS/THS=0`、route/DRC error=`0`），同源 run `20260909T094406Z` 的 UART/JTAG 均 PASS，backpressure 为 `64/64`、`failed=0`、`stall_cycles=83082`，S2MM 最终 probe `STALL=3`。软件已加入 256 帧/64-slot 连续回绕切片，但尚未形成新 ELF 的实板证据；仍需补齐多长度 PL 侧逐帧观测、sequence/CRC 对齐和错误/复位恢复，故本项保持未完成。官方 `axi_stream_monitor` 单 monitor 实验在当前顶层 setup 失败，不作为正式物理基线。
- [ ] B2-04：已在实板执行 `0/1/4/16/64/512/1472/4096` bytes 边界矩阵：8 帧总计、7 帧 PASS、0 长度明确拒绝、失败数为 0，最后 4096-byte TX/RX 逐字一致；源码已加入跨 64 个对齐 slot 的 256 帧回绕测试，仍需新 ELF 的连续回绕与独立下一帧恢复证据。
- [ ] B2-05：已完成同一低地址合同上的 10000 帧固定长度序列压力切片，且最新 run `20260909T094406Z` 已完成受控接收背压与 UART 终止切片：UART/JTAG 均 PASS，JTAG pressure `10000/10000`、backpressure `64/64`、两者 `failed=0`，累计 `stall_cycles=83082`，S2MM probe 最终 `STALL=3`；AXI VALID 保持合同测试与物理构建均通过。源码已加入 256 帧连续回绕，但尚未上板；仍需发送间歇、跨长度逐帧 TLAST 稳定、ready 恢复和错误/复位恢复，故本项保持未完成。
- [ ] B2-06：实现外层 packetizer/depacketizer，把 DMA帧映射为现有128-bit命令/响应、8-beat样本和10-beat结果；明确每类消息的最短/精确长度、字段偏移和字节序。TLAST只在外层检查，不能改变已冻结核心 framing合同。
- [ ] B2-07：覆盖早到/晚到/缺失 TLAST、错误长度、未知消息类型、错误保留位、超时和中途复位；错误帧必须被完整丢弃或明确拒绝，不得留下半条命令、半个样本、半个模型或旧结果。
- [ ] B2-08：为命令、样本、响应、结果四条逻辑流分别记录接受数和完成数；跨流 fence 前后保存计数器，证明模型/mask提交、样本和结果没有越过已冻结顺序边界。
- [ ] B2-09：同时记录 PS软件时间戳、DMA开始/完成、PL入/出流周期和核心侧接受/完成计数；统一定义时间戳起止点，为后续拆分“网口、软件、DMA、计算”耗时建立可比较基线。
- [ ] B2-10：证据包保存输入/输出二进制、CRC、sequence账本、cache维护记录、错误注入结果、寄存器快照、bitstream/ELF哈希、资源和时序，形成真实 DMA回环及协议适配摘要。
- [ ] B2-RECOVERY：任何 DMA错误先停止提交新帧，按冻结顺序复位 DMA和 packetizer，清除未完成所有权并用一条已知短帧验证恢复；恢复失败则重新加载当前 bitstream/ELF，不直接进入 NPU测试。
- [ ] B2-GATE：真实 DDR↔DMA↔PL双向搬运和协议适配在正常、背压、边界、错误、复位场景均零丢失/重复/乱序后，才能接入 NPU；B2-MVP 可在已验证低地址窗口内先执行 DMA/协议正确性门，但在 B1-GATE 完成前不得宣称网络化 B1/B4 通过或报告端到端剪枝加速。

#### P16-B3：传统 NPU + ENeuron 固定向量

- [ ] B3-00：入口只接受 `B2-GATE=PASS` 的 DMA/协议实现；冻结 B2 bitstream/ELF/协议版本作为对照，并为接入 NPU 后的新 bitstream建立独立 manifest。
- [ ] B3-01：保持当前 `64→32→10`、634个模型word、8-beat样本和10-beat结果不变；冻结模型word顺序、INT8/uint4解释、bias、隐藏层饱和、样本集合、期望10-logit、预测类别和所有文件 SHA-256。
- [ ] B3-02：生成一份可由 Python参考模型和 Host工具共同读取的黄金 manifest；每个样本至少保存 sample ID、8个输入beat、dense logits、候选 mask epoch、gated logits和预期类别，禁止手工复制两套期望值。
- [ ] B3-03：把已签核 NPU wrapper、DMA适配、周期计数器和最小可观测寄存器接入同一顶层；可观测项至少包含当前模式、active/pending epoch、接受/完成样本数、执行/跳过组数、协议错误和首错 sample ID。不得为调试修改数值语义、mask原子性或四 DSP合同。
- [ ] B3-04：完成完整 bitstream实现，检查 Host/NPU/AXI相关时钟域 setup/hold、CDC、route、DRC、恰好4个 DSP48E1以及核心、wrapper、FIFO、DMA、packetizer分层资源；任一物理硬门失败时该 bitstream不得下载作正式测试。
- [ ] B3-05：上板后先读取版本/能力寄存器，核对协议版本、模型规模、构建 Git SHA、bitstream标识和四 DSP配置；身份不符时拒绝装载模型和样本。
- [ ] B3-06：先运行 dense/bypass；逐样本核对10个结果beat、sample ID、mask epoch和预测类别与冻结黄金输出完全一致，并核对执行组数等于 dense期望。
- [ ] B3-07：运行 gate启用但全开 mask，结果必须与 dense/bypass逐 beat bit-exact一致；执行组数不得减少。这一步只证明门控通路透明，不证明剪枝有效。
- [ ] B3-08：先由 Host重放冻结的合法 mixed mask，包括严格 `2:4` 候选；逐样本保存执行组、跳过组、硬件周期和输出。该步隔离 NPU门控执行器，不把静态 Host mask称为 ENeuron自动决策。
- [ ] B3-09：再接通 ENeuron证据→结构化 mask→pending bank→fence提交路径；保存每次决策使用的神经元证据、gain、组内候选、最终 mask、提交 epoch和生效样本。相同输入与初始状态重复运行应得到相同决策。
- [ ] B3-10：对 ENeuron产生的 mask逐组检查严格 `2:4` 合法性；非法 mask必须在配置/提交阶段明确拒绝，不能静默钳位或把全关模式计作有效剪枝。全关只作协议负向或负载下界。
- [ ] B3-11：在样本计算进行中发布下一 mask epoch，证明当前结果仍绑定旧 epoch；只有 fence成功且到达下一样本边界后才激活新 epoch，响应与结果中的 epoch必须能重建这一顺序。
- [ ] B3-12：覆盖响应背压、结果背压、错误命令、非法 epoch、重复提交、模型/掩码中途复位和重新装载；恢复后首个合法样本不得混入旧模型、旧 mask、旧 sample ID或未完成计数。
- [ ] B3-13：固定测试分三档：最小手算向量用于逐 beat定位；冻结小集合覆盖 dense/full-open/static-2:4/live-ENeuron；完整集合用于每种正式模式至少10000样本连续运行。所有档位首错即停并保存完整上下文。
- [ ] B3-14：为每个正式模式报告样本正确数、logit完全一致数、类别一致数、每样本硬件周期、执行/跳过组、协议错误、恢复次数和资源；静态 mask与 ENeuron动态 mask分开统计。
- [ ] B3-RECOVERY：若 dense错误先停在模型装载/量化/计算；full-open错误停在门控透明路径；static mask错误停在mask位序/epoch/NPU跳过；只有前三者全过后才诊断 ENeuron决策，不允许用调整训练参数掩盖基础执行错误。
- [ ] B3-GATE：dense、全开、Host静态 `2:4` 和 live-ENeuron四类模式的协议、黄金输出或决策合同、epoch原子性和复位恢复全部通过，且同一 bitstream 的物理实现硬门通过，才能进入网口 A/B。

#### P16-B4：网口端到端 dense/gated A/B

- [ ] B4-00：入口只接受 `B3-GATE=PASS` 的同一套硬件、软件、模型和黄金数据；先保存无网络的 B3吞吐与周期基线，用于判断网口接入后的固定开销。
- [ ] B4-01：冻结应用层协议版本和逐字节布局，至少携带 magic/version、message type、payload length、sequence、sample ID、model ID、mask epoch、状态/错误码和完整性校验；所有多字节字段固定字节序，未知版本必须拒绝。
- [ ] B4-02：定义请求/响应配对、超时和重试语义。重试必须复用还是生成新 sequence需固定；板端不得因重复 UDP包重复提交模型/mask或把一个样本计算两次而不留痕。
- [ ] B4-03：实现可复现 Host工具，负责模型/掩码装载、样本发送、结果接收、超时重试、逐包账本、黄金输出比较和 JSON/CSV摘要；命令行保存完整参数，原始收发包可回放，退出码反映硬门结果。
- [ ] B4-04：冻结测试网络：板端/Host IP和MAC、UDP端口、网卡速率、交换机或直连方式、MTU、Host系统与网卡配置；正式 A/B期间不改变拓扑，不运行无关大流量任务。
- [ ] B4-05：固定同一 bitstream、ELF、模型、样本顺序、时钟和网络连接，只切换 dense/bypass、full-open、static-gated和live-ENeuron模式；禁止为某一模式单独调频、改变batch、预处理、超时或包大小。
- [ ] B4-06：每轮先运行1000样本预热并丢弃预热计时，再对每个正式模式运行至少10000个计入统计的样本；A/B至少重复5轮并交替顺序，记录每轮开始/结束时间和温度/供电条件（若可获得）。
- [ ] B4-07：端到端延迟从 Host首次发送完整请求到 Host收到并验证完整结果；吞吐按通过正确性门的有效样本/墙钟时间计算。另采集 PS解析/调度、DMA往返、PL排队、NPU计算周期、执行组和跳过组，防止混用不同起止点。
- [ ] B4-08：同时报告每轮有效样本数、吞吐、p50/p95/p99/最大延迟、超时、丢包、重试、重复、乱序、结果一致率和类别准确率；汇总报告给出各模式均值、离散程度和相对 dense差值，不只选最好一轮。
- [ ] B4-09：加入持续流、固定突发和受控小间隔三档负载；每档先找到无错误稳定点，再逐步提高发送率。发生拥塞时必须通过可观测队列、背压、超时或明确错误暴露，不允许静默丢包、重复结果或错配 sample ID。
- [ ] B4-10：正确性硬门优先：dense和 full-open必须逐 beat bit-exact；static-gated和 live-ENeuron必须分别符合冻结 mask/决策和精度合同。任何结果错配都使该轮性能数据无效，并保存首错前后的原始包和板端计数器。
- [ ] B4-11：性能结论只报告同条件实测差值，不预设必须提升。若 gated无加速，按网口、软件、DMA、排队、固定协议开销和 NPU计算六段定位；若计算变快但端到端不变，应明确结论是“局部计算节省被系统瓶颈掩盖”。
- [ ] B4-12：只有外部功耗仪器、供电测点、采样率、空闲基线、负载同步和积分窗口冻结后才测功耗/能耗；否则明确写 `POWER_NOT_MEASURED`，不得用 Vivado估算冒充板上实测。
- [ ] B4-13：证据包保存协议说明、Host命令行、环境清单、原始包、逐样本账本、UART/板端日志、bitstream/ELF/模型/数据哈希、每轮 JSON/CSV和汇总报告；单靠截图不能关闭阶段门。
- [ ] B4-14：完成首次完整 A/B 后，重新打开 C1～C9资源裁剪评审；每项裁剪单独建立前后 bitstream并重跑 B3正确性和 B4同条件 A/B，收益不足或破坏可复现性时回退该项。
- [ ] B4-RECOVERY：发生首错后立即停止该轮性能统计，保存 Host包、UART、DMA/NPU计数器和 active/pending epoch；按网络→软件→DMA→协议→NPU→ENeuron顺序定位，修复后从预热开始重跑完整一轮。
- [ ] B4-GATE：同一完整证据包证明网口输入→PS/DDR→DMA→传统 NPU+ENeuron→网口输出闭环，正确性硬门通过并完成可重复 A/B后，阶段 2 才可标记完成。

#### P16-S：统一停止条件

以下是持续适用的停止条件，不计入一次性 TODO 数量：

- 若器件、板卡版本、PHY型号、内存型号或关键引脚与固定资料不一致，停止构建并先更新硬件基线。
- 若某次运行无法确认 commit、bitstream SHA-256或输入哈希，该次结果仅作调试，不进入正式报告。
- 若结果错误、丢包、乱序、超时或复位恢复失败，先保存首个失败证据并修复正确性；不得继续用该运行计算性能提升。
- 若需要改变公开协议、数值格式、模型形状、DMA模式或软件栈，先形成决策点并由管理员批准，再修改实现。
- 若某阶段为了调试改变前序阶段的硬件、软件或网络基线，明确列出受影响门并重跑，不把旧 PASS 自动继承到新组合。
- 若正式运行脚本覆盖了前次原始日志、缺少退出码或无法定位首错，该次运行降级为调试记录，修复证据入口后重新执行。

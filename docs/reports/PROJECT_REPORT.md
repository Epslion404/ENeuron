# ENeuron 当前项目报告

报告日期：2026-09-01

NP4B 证据提交：`e3708af`；原 ENeuron 1.0 正式标签仍为 `v1.0`

正式版本：`v1.0`；其后包含 Pulse-Mini、Pulse-Mini-L2 与数字识别 D0–D2 研究提交

目标器件：`xc7a35tcpg236-1`、`xc7z020clg400-1`

主要工具：Python、Icarus Verilog、Yosys 0.56、Vivado 2024.1

## 1. 执行摘要

项目已经完成一个可综合、可布局布线、可在真实 RTL 事务中训练并冻结推理的数字神经元最小硬件基石。这个结论对应 ENeuron 1.0 的原始 Goal M1–M4，严格限定为固定 `4→2→2` 小网络和片外 Host 提供神经元级训练信号。

当前最重要的五项结论是：

1. **完整 ENeuron 已完成最小闭环。** 同一个双时钟 Host Bridge + Tile RTL 运行完成 957 条命令、4 次局部调制提交、48 次逐突触更新核对和 20/20 个未训练扰动样本推理；训练区间没有直接写权重。
2. **Pulse-Mini-L 是当前最省硬件且 100 MHz 实测通过的四输入单元。** XC7Z020 上为 `182 LUT / 76 FF / 0 BRAM / 0 DSP`，WNS `+0.463 ns`；固定 `4→2→2` 网络也完成训练与冻结推理协同仿真。
3. **Pulse-Mini-L2 增强了重复证据表达，但当前不能在 100 MHz 工作。** 它把四类组合任务的覆盖率从 L 的 0% 提高到约 66.9%，代价是 `366 LUT / 91 FF` 和 WNS `-4.690 ns`。
4. **数字识别尚未成功。** D1 证明 8×8 输入编码包含可分类信息，软件最近质心测试 BAcc 为 79.80%；但 D2 的 ENeuron 输出层训练在 10 个种子上测试 BAcc 均值只有 4.74%，状态为 `D2_FAIL_GENERALIZATION`。
5. **NP4B 局部 `2:4` 剪枝功能集成已经签核。** ENeuron、Pulse-Mini-L、Pulse-Mini-L2 均接入严格 `4→8→2` 十 gate 网络，各完成 20,000 条逐事务协同仿真；五套形式 proof/reach、359 项全仓回归和 87 文件 fail-closed 摘要通过。该结论不包含物理 BRAM 跳读、真实加速、功耗或 XC7Z020 时序。

因此，项目可以称为“已验证的数字可塑神经元和固定小网络硬件基石”，不能称为“已经完成实用数字识别、通用 AI 自训练、大规模神经网络或板级产品”。

## 2. 目标与边界

项目的原始目标是构建一个可作为 AI 训练与推理基础单元的数字脉冲神经元。允许片外 Host 负责标签、奖励、探索和调度；片上神经元必须根据本地事件历史计算连接变化，而不是由 Host 直接写入训练答案。

已批准并完成的核心门槛：

| 里程碑 | 含义 | 当前状态 |
|---|---|---|
| M1 | 单个 RTL 神经元保存动力学、学习历史和可塑连接 | 已证明 |
| M2 | 多个神经元组成两层网络，路由、提交和冻结正确 | 已证明 |
| M3 | 同一真实 RTL run 完成训练、读回和未训练输入推理 | 已证明 |
| M4 | 完成目标 FPGA 的综合、布局布线、时序、DRC 和 CDC 检查 | 已证明 |

M1–M4 不要求第一版实现片上损失函数、纯全局奖励训练或大规模共享存储，也不覆盖具体开发板。

## 3. 系统架构

### 3.1 ENeuron 1.0 数据与控制路径

```text
片外 Host
  标签、目标、调制、训练调度
          │ 128-bit 命令
          ▼
异步命令 FIFO ──> Host Controller ──> 4→2→2 Tile
                                        │
                                        ├─ 2 个隐藏 ENeuron
                                        ├─ 1 个逻辑 tick 路由
                                        └─ 2 个输出 ENeuron
          ▲                                  │
          └──── 异步响应 FIFO <──────────────┘
```

Host Bridge 使用两条 depth-16、128-bit、FWFT 异步 FIFO。Vivado 官方 XPM xsim 测得每条 FIFO 的外部可见容量为 17，已覆盖填满、排空、64 字回绕、背压和 hard reset。

### 3.2 单个完整 ENeuron

完整单元保留：

- 有符号连接；
- 有泄放的输入电流和膜状态；
- 输入与输出近期历史；
- 每条连接的资格状态及快照；
- 有符号调制提交；
- 阈值发放、复位和同步不应期；
- TRAIN/INFER 隔离。

一次训练的自然流程是：输入事件形成局部历史，episode 结束时锁存资格状态，Host 随后只提交每个神经元的正、负或零调制，连接增量由片上资格状态决定。INFER 模式允许膜状态运行，但冻结连接和学习状态。

### 3.3 固定 Tile 合同

- 输出层在逻辑 tick `t` 读取上一拍保存的隐藏层结果。
- 隐藏层 tick `t` 的结果只会在 tick `t+1` 到达输出层。
- Tile 用 sticky done barrier 等待四个多周期核完成，再原子公布结果。
- 当前只有一个 eligibility snapshot 槽，不支持多个乱序未决提交。
- Host V1 的地址和四路调制固定服务当前 `4→2→2` 网络。

## 4. 神经元版本演进

| 版本 | 核心思路 | 能力 | 主要问题 | 当前定位 |
|---|---|---|---|---|
| 原始计数/分频 | 每树突学习计数、分频进度、胞体计数和睡眠计数 | 能积分、发放和单向增强 | 上限回绕、无负连接、无任务信用、100 MHz 失败 | 成本与缺陷基线 |
| Pulse-Mini-L | 四输入有符号连接、膜泄放、正负存在标志、单槽反馈 | 最小局部监督学习、抑制、冻结推理 | 每次只保留方向，不保留强度；无顺序记忆 | 低成本复制主线 |
| Pulse-Mini-L2 | 每连接增加两组 2 位正负证据计数，保存 `-2..+2` 强度 | 重复证据可产生更大更新，组合任务优于 L | LUT 约翻倍，100 MHz setup 失败，仍无顺序记忆 | 算法实验版 |
| ENeuron 1.0 | LIF、pre/post history、多位 eligibility、延迟有符号调制 | 保留证据强度，完成 RTL 任务闭环 | 单核资源高，扩展需共享 RAM/lane | 完整学习基线 |

当前推荐不是用一个版本替代所有版本：研究学习机制与可信闭环使用 ENeuron；大量复制和低成本事件处理优先 Pulse-Mini-L；L2 暂时只用于评估证据强度价值。

## 5. FPGA 资源与时序

### 5.1 XC7Z020 单核 routed 实测

条件：Vivado 2024.1、`xc7z020clg400-1`、100 MHz、OOC post-route。

| 实现 | LUT | FF | BRAM | DSP | WNS | 100 MHz 判定 |
|---|---:|---:|---:|---:|---:|---|
| 原始计数/分频 | 183 | 85 | 0 | 0 | -1.605 ns | 失败 |
| Pulse-Mini-L | 182 | 76 | 0 | 0 | +0.463 ns | 通过 |
| Pulse-Mini-L2 | 366 | 91 | 0 | 0 | -4.690 ns | 失败 |
| ENeuron，2 输入 | 718 | 380 | 0 | 0 | +0.418 ns | 通过 |
| ENeuron，4 输入 | 818 | 544 | 0 | 0 | +0.431 ns | 通过 |

原始计数/分频核虽然资源接近 Pulse-Mini-L，但缺少抑制和可信任务学习，而且时序失败，因此不能因为“更原始”就视为更好的主线。L2 的主要代价集中在证据饱和计数、差值捕获和幅度反馈组合路径。

### 5.2 完整 ENeuron 网络与前端 routed 实测

条件：Vivado 2024.1、`xc7a35tcpg236-1`、OOC post-route。

| 实现 | LUT | FF | BRAM | DSP | 时钟与 WNS | 判定 |
|---|---:|---:|---:|---:|---|---|
| 多周期单核 | 813 | 544 | 0 | 0 | 100 MHz，+0.469 ns | 通过 |
| 固定 `4→2→2` Tile | 3152 | 1972 | 0 | 0 | 100 MHz，+0.213 ns | 通过 |
| Host Bridge + Controller + Tile | 3682 | 2486 | 4 RAMB36 | 0 | Host 50 MHz：+14.306 ns；Tile 100 MHz：+0.081 ns | 通过 |

系统两时钟域的 setup/hold 违例、TNS/THS、route error、DRC Error/Critical Warning 均为 0。CDC 报告中的 8 条记录全部位于官方 XPM 内部，XPM 外 Critical/Unsafe/Warning 为 0。

Tile 的 `0.103 W` 和完整前端的 `0.112 W` 都是无真实活动文件、Medium-confidence 的 vector-less OOC 估算，不能视为功耗签核。

### 5.3 Pulse-Mini-L 阵列边界

| 并行核数 | LUT | FF | WNS @100 MHz | 判定 |
|---:|---:|---:|---:|---|
| 32 | 5867 | 2432 | +0.151 ns | 通过 |
| 64 | 11699 | 4864 | -0.131 ns | 失败 |
| 128 | 23342 | 9728 | -0.466 ns | 失败 |

阵列使用 `keep_hierarchy/dont_touch` 避免综合器把广播同构实例合并。当前最大已证明的简单广播并行规模是 32 核；64 和 128 核资源能放入器件，但没有通过 100 MHz 时序门。

共享 lane 模型显示，128 核使用 1、2、4、8 条 lane 时，每个全阵列逻辑 tick 分别需要 128、64、32、16 个 lane 周期。这只是周期模型，不是 routed 资源证据。

### 5.4 30 个完整 ENeuron 的成本边界

数字识别规划使用 30 个四输入 ENeuron。只按单核实测做简单乘法，核心本体约为 `24540 LUT / 16320 FF`；这个数字不含层间路由、Host 接口、扇出、控制、时序余量或存储重构。项目尚未执行 30 核 routed，因此不能据此声称 XC7Z020 已经具备 30 核图像网络的实际容量。

## 6. 验证证据

### 6.1 ENeuron 1.0

- 单核：20 seeds × 1000 个随机混合事务，共 20000 个事务，与 Python 定点参考逐事务一致。
- Tile：20 seeds × 500 个混合事务，共 10000 个事务，与四核独立 oracle 一致。
- Controller + Tile：20 seeds × 1000 条命令 bit-exact，并包含 64 条定向协议流。
- 双时钟系统：20 seeds × 2000 flit，共 40000 条命令，覆盖非整数时钟比、随机相位、双向背压和 hard reset。
- Tile 有限形式验证：真实四核、敌对命令输入下 depth-24 BMC 无反例。
- Controller 有限形式验证：depth-20 safety BMC 无反例，6 类独立 witness 可达。
- 本报告引用上述已冻结的回归与签核产物；本轮只修改文档，没有重跑完整回归或 Vivado。

有限 BMC 和随机协同仿真证明的是已覆盖范围，不等于无限时域或完整状态空间数学证明。

### 6.2 M3 真实训练闭环

同一真实双时钟 RTL run 的冻结结果：

| 项目 | 结果 |
|---|---|
| 命令数 | 957 |
| 训练起点 | 第 64 条响应 |
| `MOD_COMMIT` | 4 次 |
| 训练区间 `WEIGHT_WRITE` | 0 次 |
| 逐突触本地更新核对 | 48 次 |
| 未训练扰动样本 | 20/20 正确 |
| 最终权重 | `-6,-7,7,7; 7,7,-6,-7; 7,-7; -7,7` |

每次提交后都通过公开协议读回全部 12 个连接，连接变化由 eligibility snapshot、有符号调制、算术右移和饱和规则重新计算。推理结束后最终连接没有变化。

### 6.3 Pulse-Mini 系列

- Pulse-Mini-L：20 seeds × 1000 事务协同仿真通过；Yosys depth-20 SAT 无反例；重复反馈错误实现具有可复现反例。
- Pulse-Mini-L 固定网络：272 条 RTL 命令协同仿真通过，观察到一拍路由、正负类输出和推理冻结。
- Pulse-Mini-L 最小监督任务：训练前 10/20，训练后 20/20；无反馈 10/20，反向反馈 0/20，标签打乱 10/20。
- Pulse-Mini-L2：20 seeds × 1000 事务协同仿真和 depth-20 SAT 通过。

这些结果证明 RTL 与冻结协议一致，也证明局部教师在受控任务中有效；它们不证明纯全局奖励可以训练隐藏层。

## 7. 能力实验

### 7.1 小型受控任务

在统一四输入二分类任务中，ENeuron、无泄放 Pulse-Mini 和 Pulse-Mini-L 都从训练前 10/20 提升到训练后 20/20。三者都依赖正确反馈；无反馈保持 10/20，反向反馈降为 0/20。

ENeuron 的差异是会保留证据强度：重复 1 到 8 次同方向事件时，eligibility 从 16 增长到 189；Pulse-Mini-L 始终只保存一个方向并更新一步。Pulse-Mini-L 的优势是状态少、行为确定、硬件便宜。

### 7.2 Pulse-Mini-L2 多任务结果

| 任务 | Pulse-Mini-L | Pulse-Mini-L2 | 结论 |
|---|---:|---:|---|
| 三类通道，local teacher | 100% | 100% | 两版均可完成简单通道分类 |
| 四类组合，local teacher | 0% coverage | 66.9% coverage，covered accuracy 100% | L2 的强度信息有价值 |
| 三类时间顺序 | 0% | 0% | 两版都没有足够顺序记忆 |
| 多标签 exact-match | 30.2% | 33.3% | L2 仅小幅改善 |
| 全局标量奖励 | 0% coverage | 0% coverage | 信用分配仍未解决 |

## 8. 8×8 数字识别

### 8.1 D0：输入与编码已冻结

- 1797 个 8×8 灰度数字；train/validation/test 为 1252/270/275。
- 像素量化为 0–15。
- 每图选择最亮的 16 个像素，使用 16 tick rank-order latency 编码。
- 同亮度按像素编号稳定打破平局。
- 16 个 2×2 patch mask 可以无损还原像素事件。
- 编码器不读取标签，也不依赖全局随机状态。

D0 状态为 `PASS`，只证明输入合同可靠。

### 8.2 D1：输入包含可学习信息

| 软件基线 | Test BAcc | Accuracy | Macro-F1 | Coverage |
|---|---:|---:|---:|---:|
| 最近质心 + 像素发放 tick | 79.80% | 80.00% | 79.46% | 100% |
| 标签打乱 | 8.69% | 8.73% | 8.73% | 100% |
| 总事件数、首 tick、末 tick | 0% | 0% | 0% | 0% |

D1 说明编码保留了空间和亮度信息，没有明显总事件数泄漏。它是软件可分性参考，不是神经元训练结果。

### 8.3 D2：协议通过，训练性能失败

D2 网络为 `64→16→4→10`，共 30 个单元、120 条逻辑连接。前 20 个特征单元冻结，只训练 10 个输出单元。每个非空特征事件使用“输入 → 下一 tick teacher-post → 3 个空 tick”的微窗口；训练期直接写权重为 0，教师事件不计为自然输出。

正式结果为 10 seeds × 3 epochs：

| 指标 | Validation | Test |
|---|---:|---:|
| BAcc 均值 | 4.61% | 4.74% |
| Coverage 均值 | 56.04% | 52.18% |
| BAcc 最小值 | 1.11% | 1.84% |
| 达到强门的 seed | 0/10 | 不用于调参 |

失败原因不是输入完全无信息，而是当前固定四路象限特征和十分类调制使输出连接趋同。每个样本对一个目标输出给正调制、对九个非目标输出给负调制，最终容易出现单一类别、并列或全弃权。严格解码没有用强行选最小编号来掩盖失败。

D2 状态为 `D2_FAIL_GENERALIZATION`，部分种子同时属于 `D2_FAIL_ACTIVITY`。当前不应进入 D3 的隐藏层解冻训练。

## 9. 当前成熟度

| 能力 | 状态 | 说明 |
|---|---|---|
| 完整单神经元 RTL | 完成 | 仿真、形式、Vivado routed 均有证据 |
| 固定两层小网络 RTL | 完成 | `4→2→2`、一拍路由、训练与冻结推理 |
| 双时钟 Host 数字前端 | 完成 | XPM FIFO、CDC、背压、reset、routed |
| 真实任务训练来源审计 | 完成 | 957 条命令，训练期无直接写权重 |
| 低成本脉冲单元 | 完成 | Pulse-Mini-L 单核与固定小网络通过 |
| 32 核低成本阵列 | 完成到 100 MHz routed | 64/128 核仍未通过时序 |
| 十分类数字识别 | 失败 | D2 多种子没有超过机会水平 |
| 共享突触 RAM/lane OOC 原型 | 完成到 NP7 | 160,000 事务逐拍一致，dense/sparse × 1/2/4/8 lane 均有证据，8/8 OOC 配置通过 100 MHz；尚未组成板级系统 |
| 局部严格 `2:4` 功能集成 | 完成 | 三模型各 20,000 条、十 gate 原子提交、五套形式证据、359 项回归 |
| 传统 NPU + ENeuron 集成 oracle | 冻结审核中 | I1-I6 已批准，当前 14 项函数/事务测试通过；OF1-OF6 V3 尚待批准，未创建集成 RTL |
| L2 100 MHz | 失败 | 需要拆分积分与学习路径 |
| 纯全局奖励隐藏层学习 | 未证明 | 当前受控实验失败 |
| 指定 Zynq 开发板 bitstream | 未实现 | 缺 top、XDC、I/O 与在板闭环 |
| 实测功耗 | 未实现 | 现有结果均无真实活动文件 |
| 通用 AI 自训练 | 未证明 | 当前结论不覆盖该声明 |

## 10. 主要风险

1. **十分类信用失衡。** 一正九负的输出调制会淹没目标类的正向更新，是 D2 当前最直接的失败点。
2. **四路固定特征过窄。** 64 个像素经过固定 patch 和象限层后只剩四路输出，可能已经丢失 D1 软件基线使用的大量空间信息。
3. **寄存器复制扩展性差。** 完整 ENeuron 每核保留多条 trace、eligibility 和 snapshot，大规模复制会先受 LUT、FF、扇出和布线限制。
4. **L2 组合路径过长。** 增加证据幅度后，捕获和反馈逻辑与积分路径耦合，导致 100 MHz setup 严重失败。
5. **形式证明仍是有限深度。** 当前 BMC 很强，但不是无限时域归纳证明或 Python/RTL 全状态形式等价。
6. **尚无板级约束和功耗实测。** OOC 时序不能代替真实时钟、复位、I/O delay、引脚和热环境签核。
7. **训练仍依赖片外教师。** 片上完成的是局部连接更新，不是片上自产标签、损失或全局信用分配。

## 11. 建议下一阶段

### 当前人工门：OF1-OF6 V3 审核

NP7 已完成并合并，证明共享 lane 能在冻结任务和 OOC 范围内把门控转化为真实读请求与周期下降。项目当前基线已转为“传统 NPU + ENeuron 局部自动剪枝/动态门控集成”。I1-I6 已批准，`64→32→10` Python oracle 已覆盖旁路、门控、epoch、背压和清除等 14 项行为；进入单时钟 RTL 前仍须批准 `docs/planning/NPU_ORACLE_FREEZE_REVIEW.md` 的 OF1-OF6 V3。

### 优先级 1：批准并冻结 Python oracle

先裁定核心 uint4、INT8 权重、安全 bias、固定参数、mask 位序、634/19-word 顺序流、错误响应、双 bank、freeze/reset 和不可变输出合同。批准只表示设计合同生效，不表示当前 Python 已经满足合同。

### 优先级 2：按小 PR 完成 OF1-OF6

首个切片只做核心 uint4 fail-closed 和非法样本零副作用，把测试从 14 项提升到 15 项；随后再分别完成数值/参数、mask 手算向量和状态矩阵。每个 PR 只修改必要业务文件，不顺带创建 RTL。

### 优先级 3：冻结单时钟 RTL 设计

Python oracle 全绿后，先提交端口表、634/19-word 地址表、错误响应、状态转移和逐拍测试计划供审核。审核通过前不创建集成 SystemVerilog，不运行新的 Vivado。

### 优先级 4：NPU 与 ENeuron 集成验证

RTL 阶段按“稠密旁路 → 固定 mask → ENeuron 动态 mask”递进，要求 Python/RTL 逐拍 bit-exact、epoch 原子切换、输出背压稳定、推理冻结和非法配置零副作用。局部门控必须发生在权重读取/MAC 之前，不能用 MAC 之后丢结果冒充剪枝收益。

### 优先级 5：系统与板级闭环

只有独立集成 RTL 通过后，才接 Host/FIFO/共享 lane/RAM 并运行 XC7Z020 系统级 routed、CDC、DRC 和吞吐检查。指定开发板、以太网、DMA、bitstream 和实测功耗仍属于更后的独立门槛。

## 12. 复现入口

```powershell
# ENeuron 1.0 完整审计；全新检出需要重建 Vivado 报告
python verify_goal.py --rerun-vivado

# Pulse-Mini-L 单核与阵列边界
python pulse_mini_cosim.py
.\run_formal_pulse_mini.ps1
python verify_pulse_mini.py
python verify_pulse_mini_p7.py

# Pulse-Mini-L2
python pulse_mini_l2_cosim.py
.\run_formal_pulse_mini_l2.ps1

# 8×8 数字识别
python -m unittest -v test_digit8x8.py test_digit8x8_experiment.py
python run_digit8x8_d2.py --seeds 0 1 2 3 4 5 6 7 8 9 --epochs 3

# 当前完整软件/协同回归
python -m unittest discover -v

# NP4B 三模型局部 2:4 功能集成签核
python verify_np4b_signoff.py
```

## 13. 最终判断

项目已经跨过“概念神经元”阶段：完整 ENeuron 和精简 Pulse-Mini-L 都有真实 RTL、协议、验证和 FPGA 实现证据；完整版本还完成了同一双时钟 RTL run 内的局部训练来源闭环。

当前瓶颈已经从“单个神经元或共享 lane 是否可做”转移为传统 NPU 与神经元控制面能否在同一条逐位、逐拍合同下集成，以及动态 mask 能否在系统级保持正确性并带来可测的访存/周期收益。在这些问题闭环前，最准确的项目定位仍是：**已验证的数字可塑神经元、固定小网络和 NP7 共享 lane/OOC 稀疏执行基石，正在冻结传统 NPU + ENeuron 集成合同；尚未完成板级 NPU、自主图像识别和系统级功耗收益证明。**

## 14. 权威证据索引

- 版本与边界：`docs/reports/RELEASE_1.0.md`、`docs/verification/goal_audit.md`、`docs/design/original_goal_alignment_review.md`
- M3 任务闭环：`m3_signoff_summary.txt`、`m3_task.py`、`m3_acceptance.py`
- Tile/Host 硬件：`vivado_tile_reports/signoff_summary.txt`、`vivado_host_bridge_reports/signoff_summary.txt`
- Pulse-Mini：`pulse_mini_signoff_summary.json`、`pulse_mini_p7_signoff_summary.json`
- L2：`docs/reports/PULSE_MINI_L2_PROTOCOL_REPORT.md`、`vivado_pulse_mini_l2_reports/signoff_summary.txt`
- 数字识别：`docs/reports/DIGIT_RECOGNITION_D0.md`、`docs/reports/DIGIT_RECOGNITION_D1.md`、`docs/reports/DIGIT_RECOGNITION_D2.md`
- D2 原始结果：`artifacts/results/digit8x8_d2_results.json`
- NP4B 局部剪枝：`np4b_signoff_summary.json`、`verify_np4b_signoff.py`、`docs/planning/NPU_PRUNING_NP4B_TODO.md`
- NP7 共享 lane：`docs/reports/LOCAL_PRUNE_NP7_SHARED_LANE_REPORT.md`、`verify_np7_software_cost.py`、`verify_np7_physical_cost.py`
- NPU + ENeuron 集成：`docs/planning/NPU_NEURON_INTEGRATION_REVIEW.md`、`docs/planning/NPU_ORACLE_FREEZE_REVIEW.md`

# Goal 完成审计

审计日期：2026-08-14。

目标边界：只研究数字电路神经元/神经网络；允许片外 Host 生成目标、奖励、探索策略和 signed modulator。片上最小单位负责事件积分、脉冲发放、eligibility、延迟学习提交和推理冻结。

## M1-M4 核心判定

| 里程碑 | 严格定义 | 当前判定 |
|---|---|---|
| M1：单元成立 | RTL 单元保存动力学、eligibility 和本地可塑权重，Host 只给神经元级调制 | 已证明 |
| M2：网络成立 | 多个单元组成固定 4->2->2 两层网络，一 tick 路由、提交和推理冻结正确 | 已证明 |
| M3：任务闭环成立 | 同一真实双时钟 RTL run 完成训练、局部提交、读回和未训练输入推理，且训练期无直接权重写入 | 已证明 |
| M4：硬件可实现 | 目标 FPGA 上完成综合、布局布线、时序、route、DRC 和 CDC 签核 | 已证明 |

因此，用户批准的原始 Goal M1-M4 已成立；该结论严格限定为固定 4->2->2 最小硬件基石，不能扩张解释为共享 RAM 大规模架构、板级产品或通用 AI。

## 证据矩阵

| 要求 | 当前结论 | 可复现证据 | 尚未覆盖 |
|---|---|---|---|
| 三因子学习状态方程 | 已验证 | Python 单元测试、算法模型与定点 RTL 参考模型逐字段比较 | 任意参数组合的数学证明 |
| 有效学习而非空操作 | 已验证 | 固定黄金测试产生非零 eligibility；合法 MOD 后四核权重变为 `((5,5,4,4),(-2,-2,-1,-1),(5,4),(-2,-1))` | 更多学习规则和量化配置 |
| 推理冻结 | 已验证 | INFER 下 snapshot/weight 写被拒绝，tick 不改变学习状态；固定黄金和随机事务均覆盖 | 上板 Host 错误注入 |
| 单核 RTL 事务等价 | 已验证到测试范围 | 20 seeds x 1000 混合事务，共 20000 事务；另有精确延迟和 busy 原子性检查 | 全状态空间形式等价 |
| 4->2->2 Tile RTL 等价 | 已验证到测试范围 | 20 seeds x 500 混合事务，共 10000 事务；完整状态、协议错误、延迟逐事务比较 | 全状态空间形式等价 |
| 固定一 tick 跨层路由 | 已验证 | 固定黄金断言：tick t 隐藏发放时输出为 0；tick t+1 输出读取旧 pending 并发放 | 深 FIFO、丢包和多 Tile 路由 |
| commit/snapshot 协议 | 已验证（单槽） | 过期、重复、INFER、零调制、state clear 保留 snapshot、Host 延迟均有测试 | 多槽 snapshot RAM、乱序多 commit |
| Tile 接口原子性 | 已验证到仿真和有限 BMC 范围 | busy 时第二命令被屏蔽；非法高优先级命令不会泄漏低优先级子核请求；Tile 外部元数据、spike 和权重读口在 barrier 前不可见 | 子核内部状态会先后完成；这不是层级内部原子性 |
| Tile 协议形式性质 | 24 拍 BMC 无反例 | Yosys 0.56，真实四核、敌对任意命令输入，不假设 one-hot；约 451 万变量/1252 万子句，覆盖最长 17 周期训练 TICK | 不是无限时域归纳证明，也不是 Python/RTL 全状态等价 |
| Host Bridge 协议/控制器 | 已验证到测试与有限 BMC 范围 | Python oracle 32 项；真实 controller + Tile 定向 64 命令和 20 seeds x 1000 命令 bit-exact；20 拍 safety BMC 无反例，6 类非空 witness 可达 | 不是无限时域或完整控制器等价证明 |
| 双时钟端到端传输 | 已验证到测试范围 | 20 seeds x 2000 flit，共 40000 命令；随机非整数时钟比、随机相位、双向背压、顺序响应与 hard reset 丢弃 outstanding | 模拟 CDC 不等于亚稳态物理测量 |
| 真实 XPM FIFO | 已验证 | Vivado 2024.1 官方 XPM xsim：双向容量均为 17，完整排空、64 字回绕、背压与 hard reset 通过；无 fatal/overflow/underflow；仿真断言未进入综合网表 | 只覆盖冻结的 depth-16、128-bit、FWFT 配置 |
| 回归稳定性 | 已验证 | `python -m unittest discover -v`：169 项全部通过；`compileall` 通过 | 覆盖率度量、长时间故障注入 |
| 单核 100 MHz OOC | 已验证 | Artix-7 `xc7a35tcpg236-1`：WNS `+0.469 ns`，TNS 0，setup/hold 零失败 | 板级 I/O、CDC、温压扩展目标 |
| Tile 100 MHz OOC | 已验证内部寄存器路径 | 2026-08-13 重跑：WNS `+0.213 ns`、TNS 0、WHS `+0.026 ns`、THS 0；setup/hold 零失败；route error 0 | 顶层 input/output delay 和 partition pin 未约束 |
| Tile 资源 | 已测量并设回归预算 | `3152 LUT / 1972 FF / 0 BRAM / 0 DSP`；硬门预算 `LUT <= 3200`、`FF <= 2000`、`BRAM/DSP = 0` | 当前小数组未推断 RAM，不代表大规模架构面积 |
| Tile 功耗 | 仅估算 | Vivado vector-less OOC：`0.103 W`，Medium confidence | 无 SAIF/VCD、真实板级活动和热环境 |
| Host Bridge 系统 OOC | 已验证数字前端内部路径 | Host 50 MHz：WNS `+14.306 ns`、WHS `+0.105 ns`；Tile 100 MHz：WNS `+0.081 ns`、WHS `+0.058 ns`；两域 TNS/THS 和 setup/hold violations 均为 0；route/DRC error 0 | 顶层 I/O delay、真实时钟源与异步复位源未签核 |
| Host Bridge 系统 CDC | 已验证到 OOC 报告范围 | 8 条均在官方 XPM 内部：4 条 Gray pointer `CDC-6`、4 条 reset sync `CDC-3`；XPM 外 Critical/Unsafe/Warning 均为 0 | `report_cdc` 跳过无 input delay 的顶层端口；板级 `bridge_rst` 来源仍需签核 |
| Host Bridge 系统资源 | 已测量 | `3682 LUT / 2486 FF / 4 RAMB36 / 0 DSP` | 固定小系统，不代表扩展阵列资源曲线 |
| Host Bridge 系统功耗 | 仅估算 | Vivado vector-less OOC：`0.112 W`，Medium confidence | 无 SAIF/VCD、真实板级活动和热环境 |
| M3 真实 RTL 任务闭环 | 已验证（受控任务） | 同一双时钟 RTL run 执行 957 条命令；训练前全 abstain，两轮四次 MOD 后 clean `(0,1)`、20/20 扰动正确；每次提交读回 12 权重，训练期 `WEIGHT_WRITE=0` | 固定任务、固定规模、Host 提供神经元级 Teacher 信号 |
| reward-only 隐藏层学习 | 已证明当前方案不足 | WTA + 全局 reward 的平均准确率仅 22.5% | 需要更好的隐藏层信用分配 |
| G4 Temporal development 数据合同 | 已实现并进入回归，不等于 P0a/P0b 通过 | 5 split、1312 个唯一输入；四阶 motif、精确 schema、全局 `B`、IID/OOD 域、生成器重放认证；manifest V2 绑定 input/example 双哈希和真实源码；数据跨 model seed 共享 | Spatial/XOR 正式生成器、三任务全局 `B`、负对照、训练与留出准确率尚未执行 |

## 当前可声称的精确结论

> 已实现一个由双时钟 Host Bridge、命令控制器、两条官方 XPM async FIFO 和真实四核 4->2->2 Tile 组成的数字硬件基石。除既有随机协议、formal 和 Vivado 证据外，同一真实 RTL run 已从全 abstain 初态完成两轮局部可塑训练、四次 `MOD_COMMIT`、逐次 12 权重读回、clean/扰动冻结推理和最终权重不变检查；完整账本证明训练区间没有直接权重写入。

这个结论足以支持：

- 该神经元已满足“允许片外 Host 产生训练信号”的最小数字学习基石 M1-M4。
- 固定 4->2->2 Tile 已经从算法概念推进到可综合、可布局布线的网络级 RTL 原型。
- 固定 4->2->2 Host Bridge 数字前端已经具备可综合双时钟命令/响应链路，并完成真实 XPM 与 OOC CDC 签核。
- TRAIN 中的实际权重转移逐项符合捕获 eligibility、signed modulator、算术右移和饱和公式；INFER 后权重保持不变。

## 不能声称的内容

- 不能声称 24 拍 BMC 或随机协同仿真等于无限时域、全状态空间数学证明；尚未建立完整的归纳证明或 Python/RTL 形式等价。
- 不能声称已经完成板级 FPGA 系统；没有目标板引脚、I/O delay、真实物理 Host 总线适配、`bridge_rst` 板级来源、bitstream 下载和在板观测。
- 不能声称功耗已签核；系统 `0.112 W` 没有真实活动文件。
- 不能声称支持多个并发未决 commit；当前 Tile 只有一个 snapshot 槽。
- 不能声称 reward-only 已解决隐藏层信用分配。
- 不能声称已经实现通用 AI 自训练、任意任务泛化或实用规模网络。

## 若要求“完全证明”还缺什么

1. 在现有 Tile 协议 BMC 基础上，分层证明单核合同与抽象 core 的 Tile 控制层，并尝试时间归纳。
2. 对 INFER 学习状态冻结、饱和不回绕、精确延迟和一 tick 路由增加更细的形式性质，并建立 Python/RTL 可检查等价映射；随机测试保留作为互补证据。
3. 选择真实 FPGA 板卡，补完整 XDC、I/O delay、引脚/配置电压、时钟源与 `bridge_rst` 复位适配，再生成 bitstream 做在板闭环。
4. 用仿真活动文件和实测电流重新签核功耗。
5. 若 Goal 升级为 G4，至少增加多种任务、留出集、更大网络、20+ seeds，并为隐藏层信用分配给出独立有效证据。

## 审计结论

用户批准的原始 Goal M1-M4 已全部通过可复现工程验收：本地可塑单元、固定两层网络、同一真实双时钟 RTL 训练/读回/冻结推理闭环，以及 FPGA 实现签核均成立。边界仍明确：这不是共享 RAM 大规模架构、具体板卡闭环、无限时域形式证明或通用 AI 自训练证明。

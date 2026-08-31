# Pulse-Mini-L 与 Pulse-Mini-L2 训练协议和多任务仿真报告

## 范围

本报告只使用 Python 黄金模型，比较固定泄放周期 8 的 Pulse-Mini-L 与 L2。
L2 使用每条连接正/负两个 2 位饱和证据计数器，CAPTURE 保存两者差值，范围 -2..+2。
局部教师与全局标量奖励严格分组；全局奖励结果是信用分配负对照，不代替局部教师证据。

## 升级结论

在弃用原始 Pulse-Mini、以 Pulse-Mini-L 作为主线后，当前最有价值的单项升级是 L2 的“低位证据强度”扩展：保留 L 的时间泄放、单槽事务和训练/推理隔离，只把每条输入的一个正/负历史标志扩展为两组 2 位计数。它直接改善“同一局部证据重复出现但一次反馈不够强”的问题，仍不引入连续资格迹、复杂乘法器或片上奖励调度器。

这项升级的边界同样明确：它能提高重复/组合证据的可学习性，但没有增加顺序记忆，因此三类时间顺序任务仍失败；统一的全局标量奖励也仍没有信用分配能力，不能把 local_teacher 的结果改写成纯 reward 学习。

## 训练协议

1. 每个样本先 STATE_CLEAR；每个输入事件采用“输入 tick -> teacher-post tick -> 三个空 tick”释放窗口。
2. local_teacher 对目标输出发送 +1，对非目标输出发送 -1；输出采用 one-hot，不使用二进制类别编码。
3. global_scalar_reward 由当前动作得到一个统一 ±1，所有输出收到同一个反馈，不按输出地址定向。
4. INFER 只允许膜电位、不应期和泄放状态变化，权重与学习证据必须冻结。

## 结果

| 任务 | 模型 | 协议 | 平衡准确率 | 覆盖率 | 覆盖样本准确率 |
|---|---|---|---:|---:|---:|
| three_class_channel | Pulse-Mini-L | local_teacher | 100.0% | 100.0% | 100.0% |
| three_class_channel | Pulse-Mini-L | global_scalar_reward | 0.0% | 0.0% | 0.0% |
| three_class_channel | Pulse-Mini-L2 | local_teacher | 100.0% | 100.0% | 100.0% |
| three_class_channel | Pulse-Mini-L2 | global_scalar_reward | 0.0% | 0.0% | 0.0% |
| four_class_composite | Pulse-Mini-L | local_teacher | 0.0% | 0.0% | 0.0% |
| four_class_composite | Pulse-Mini-L | global_scalar_reward | 0.0% | 0.0% | 0.0% |
| four_class_composite | Pulse-Mini-L2 | local_teacher | 66.9% | 66.9% | 100.0% |
| four_class_composite | Pulse-Mini-L2 | global_scalar_reward | 0.0% | 0.0% | 0.0% |
| three_class_temporal_order | Pulse-Mini-L | local_teacher | 0.0% | 0.0% | 0.0% |
| three_class_temporal_order | Pulse-Mini-L | global_scalar_reward | 0.0% | 0.0% | 0.0% |
| three_class_temporal_order | Pulse-Mini-L2 | local_teacher | 0.0% | 0.0% | 0.0% |
| three_class_temporal_order | Pulse-Mini-L2 | global_scalar_reward | 0.0% | 0.0% | 0.0% |

### 多标签

| 模型 | exact-match | bit-level accuracy |
|---|---:|---:|
| Pulse-Mini-L | 30.2% | 73.7% |
| Pulse-Mini-L2 | 33.3% | 75.4% |

## 解释与边界

- L2 的价值体现在重复、分段的局部证据可以产生幅度 2 的一次更新；它不是连续 eligibility trace。
- 时间顺序任务若三类仅改变事件顺序而保持通道计数相同，两个版本都应接近随机或大量 abstain；这是最小结构的表达边界。
- 全局标量奖励在没有额外信用分配机制时会让输出单元收到相同方向的更新，不能把它与 local_teacher 结果合并。
- L2 已完成 Python 回归、20 seeds x 1000 事务（20000 条）Icarus/Python 协同仿真和 depth-20 Yosys SAT；这些证据证明协议与 RTL 一致，但不等于通用 AI 能力。

## 硬件成本（XC7Z020）

Vivado 2024.1、`xc7z020clg400-1`、100 MHz、OOC post-route 的最终实测如下：

| 版本 | LUT | FF | BRAM36 | BRAM18 | DSP | WNS | WHS |
|---|---:|---:|---:|---:|---:|---:|---:|
| Pulse-Mini-L | 182 | 76 | 0 | 0 | 0 | +0.463 ns | +0.205 ns |
| Pulse-Mini-L2 | 366 | 91 | 0 | 0 | 0 | -4.690 ns | +0.152 ns |
| L2 相对 L | +184（+101.1%） | +15（+19.7%） | 0 | 0 | 0 | -5.153 ns | -0.053 ns |

L2 的主要花费不是寄存器，而是正/负证据的饱和计数、差值捕获、幅度反馈与当前胞体路径叠加后的组合逻辑。L2 已完成布局布线，但 100 MHz setup 未通过，不能把它当作“同频率可直接替换”的版本。若目标是恢复 100 MHz，下一项工程工作应是把 TICK 的窄路径与 CAPTURE/FEEDBACK 的学习路径分拍或分层；这属于时序修复，不应删除 L2 的证据强度功能。

按 XC7Z020 的 53200 LUT / 106400 FF 资源做纯除法，L2 理论上限约为 145 个核（LUT 受限）；若按 45% 资源预留，约 79 个核。两者都不是阵列容量签核。当前已有的简单广播阵列实测只覆盖 L1，L2 尚未完成阵列级复制、布线和容量报告，因此工程上应先按“单核 1 个、阵列容量未证明”管理。

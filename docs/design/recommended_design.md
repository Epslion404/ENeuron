# 推荐单个神经元硬件设计

## 定位

推荐单元不是单独的胞体，而是一个可寻址的可塑神经元 tile：

```text
输入事件 -> 突触状态 RAM -> 有符号累加 -> LIF 胞体 -> 输出事件
                         ^                    |
                         |                    v
                 eligibility 更新 <- pre/post 迹线
                         ^
                   signed modulator
```

它可以在 `TRAIN` 模式更新权重，在 `INFER` 模式冻结权重运行推理。

## 最小状态

每个突触：

```text
w_ij              signed 8-bit weight
eligibility_ij    signed 12-bit eligibility trace
plastic_enable    1-bit
```

每个输入轴：

```text
pre_trace_i       unsigned 8-bit trace
```

每个神经元：

```text
I                 signed 16-bit synaptic current
V                 signed 16-bit membrane potential
post_trace        unsigned 8-bit trace
threshold         unsigned 8-bit adaptive threshold
refractory        unsigned 4-bit countdown
```

位宽应通过黄金模型和目标扇入重新计算；这里的位数是行为验证起点，不是固定实现要求。

## 单时间步顺序

所有输入事件先完成，再只做一次阈值判断，避免结果依赖事件到达顺序：

```text
1. 衰减 I、V、pre_trace、post_trace、eligibility
2. 对每个输入事件：I += signed(w_ij)
3. V += I
4. 如果处于 refractory：屏蔽输入并保持 V_reset
5. 否则若 V >= threshold：输出一个 spike，装载 refractory
6. pre/post 事件更新 eligibility
7. 收到 modulator 时：w_ij = saturate(w_ij + M * eligibility_ij / 2^k)
8. threshold 慢速回落，权重和状态全部饱和
```

推荐只用加减、比较和右移实现漏电、迹线衰减和学习率，首版不放浮点或通用乘法器。由于脉冲是二值事件，`I += w` 已经完成了突触乘法。

## 接口

```text
event_in       valid, ready, synapse_id
modulator_in   valid, ready, signed value
spike_out      valid, ready, neuron_id
config         threshold/leak/refractory/learning parameters
state_port     weight read/write, clear traces, freeze/unfreeze learning
status         event count, spike count, update count, saturation count
```

外部异步输入在边界用同步器或异步 FIFO；内部使用单时钟和 `valid/ready`，不要使用逻辑分频器生成新时钟。

## 为什么保留 eligibility

实验中，二因子 STDP 的四个权重最终全部增强，10 种训练顺序的任务区分成功率为 0%。加入每突触资格迹线和延迟 `modulator` 后，权重稳定为 `[7, 7, -7, -7]`，区分成功率为 100%。代价是 4 输入示例的状态位代理从 108 位增加到 169 位。

因此：

- 只做无监督相关性学习：可以删掉 eligibility，使用二因子 STDP。
- 要做奖励、局部监督或自监督误差：保留 eligibility，这是推荐基线。

## 物理实现

不要为每条树突都实例化独立分频器。用突触 RAM、神经元状态 RAM 和共享更新流水线时分复用；需要更高吞吐量时复制流水线。这样逻辑单元可以扩展为神经元阵列，而不会让分频器和学习器数量随连接数线性膨胀。

2026-08-12 的 Vivado 2024.1 实测进一步证明必须时分复用：4 输入的完全并行行为核在代表性 `xc7a35tcpg236-1` 上已占用 `2338 LUT`，100 MHz 下关键路径约 `32.185 ns`。因此阵列版不应复制该组合核，而应采用“每周期一条突触”的共享引擎，并把权重、pre trace、eligibility 与 snapshot 放入 RAM。

当前多周期实现把每条突触更新拆为两拍，并把电流饱和、膜电位相加和发放判断分拍。单核 post-route 为 `813 LUT / 544 FF`，100 MHz WNS `+0.469 ns`；最终四核 Tile 为 `3152 LUT / 1972 FF`，100 MHz WNS `+0.213 ns`。加入双时钟 Host Bridge、controller 和两条 XPM FIFO 后，完整系统为 `3682 LUT / 2486 FF / 4 RAMB36 / 0 DSP`，Host 50 MHz 与 Tile 100 MHz 均完成 post-route。

当前小数组仍被实现为寄存器而非 BRAM。扩展到高扇入或更多神经元时，不应继续直接复制四核 Tile；应把权重、pre trace、eligibility 和 snapshot 迁移到同步 RAM，并由共享引擎按神经元/突触地址时分复用。

## 两层网络边界

首个网络级 MVP 使用：

```text
4 个片外输入事件轴
    -> 2 个隐藏可塑 LIF
    -> 1 tick 事件 FIFO
    -> 2 个输出可塑 LIF
```

Host 在 episode 结束时读取输出 spike summary，生成带 `layer_id/neuron_id/commit_id` 的 signed modulator。当前数字前端已经用同构 128-bit 命令/响应、双 async FIFO 和 controller 实现这一事务闭环；具体 USB/PCIe/UART 等物理总线仍由目标板适配器完成。

全局 reward 可以作为接口能力，但不能默认认为它足以训练隐藏层；当前 MVP 使用可寻址目标调制，避免两个隐藏神经元收到完全相同的更新而塌缩成同一类。

片上增加逐 tick WTA 后，全局 reward 仍不能稳定完成隐藏层信用分配。当前推荐的最小网络训练流程是：

```text
Host 可寻址目标调制 -> 隐藏层特征形成
冻结隐藏层
Host 探索与 reward -> 输出动作层训练
冻结全网 -> 推理
```

该流程只要求片上支持 WTA、分层写使能、可寻址 modulator 和 eligibility commit；探索策略、目标和奖励全部留在片外。

当前 RTL 已实现固定 4->2->2 Tile、单槽 commit、四核 all-done barrier、一 tick 路由、Host controller 和双时钟 XPM transport。真实 XPM xsim、40000 条双时钟随机命令、Controller/Tile 有限 BMC，以及 Host 50 MHz / Tile 100 MHz OOC 均已通过。尚未实现多槽 snapshot RAM、片上 WTA、具体物理 Host 总线、板级引脚/I/O delay/复位源和在板 bitstream 闭环，因此它是已签核的数字前端，不是完整部署系统。

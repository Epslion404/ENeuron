# RTL 冻结契约

以下契约分为两层：已实现的 128-bit Host/传输协议，以及 Tile 内部事务接口。两层由 `digital_snn_host_bridge_controller.sv` 显式转换，不能混为同一硬件端口。

## 输入与时间步

```text
EPISODE_START(episode_id, mode)
TICK_BEGIN(tick, event_count)
INPUT_EVENT(synapse_id) × event_count
TICK_COMMIT
```

这是已实现的外层 Host 事务：`INPUT_EVENT` 由 controller 暂存为 spike mask，在 `TICK_COMMIT` 时原子启动 Tile。Tile 仍以 `tick_valid + input_spikes[3:0]` 接收聚合时间步；事件暂存、数量核对和错误首错链位于 controller。

V1 行为核已经证明状态方程可以综合，但不再把“一个时钟周期完成全部突触、迹线、eligibility 和权重更新”作为阵列实现合同。阵列 RTL 必须采用多周期事务：

```text
IDLE
  -> ACCEPT_TICK       锁存 input_spikes/mode
  -> DECAY_STATE       计算 I/V/post/threshold 基础 next-state
  -> SCAN_SYNAPSE      第 1 拍读取 1 条突触并衰减 pre/eligibility
  -> UPDATE_SYNAPSE    第 2 拍累计 I 并写事务私有 pre/eligibility 工作区
  -> CURRENT_SAT       将扩展精度 I 累计饱和到状态位宽
  -> MEMBRANE_ADD      计算并寄存泄漏后的 V + I
  -> FIRE_RESOLVE      阈值、不应期、post spike
  -> POST_SCAN         需要发放时每周期处理 1 条 eligibility
  -> COMMIT_STATE      原子提交全部 next-state，产生 spike/ready
```

首版 `N_INPUTS=4` 为时序收敛采用每突触两拍，并把电流饱和、膜电位相加和发放判断分拍。无发放 TICK 从接受到 `done` 为 `2*N_INPUTS+4` 个后续时钟，训练且发放再增加约 `N_INPUTS` 个 POST_SCAN 时钟；`ready=0` 时新命令由上游重试，状态只能在 `COMMIT_STATE` 原子可见。

## 网络路由

隐藏层输出进入一拍 pending FIFO：

```text
tick t     hidden spike 产生
tick t+1   output layer 接收 hidden neuron_id
```

禁止组合跨层路径。当前 Tile 在 TICK 的 `done` 周期输出 `hidden_spikes[1:0]` 和 `output_spikes[1:0]`；`episode_id/tick/neuron_id` 标签属于后续外层事件封装，当前 RTL 只保存 snapshot 的 episode metadata。

## 学习提交

```text
EPISODE_END -> eligibility snapshot(commit_id)
MODULATOR(commit_id, layer_id, neuron_id, signed_value)
MOD_COMMIT(commit_id)
```

快照必须独立于后续 episode 的动态 trace。重复、未知、过期 `commit_id` 不得写权重。`INFER` 模式关闭所有 weight RAM 写使能。

单核最小接口还必须区分：

```text
rst            全局复位，初始化权重和全部状态
state_clear    episode 动态状态清零，保持权重和 pending snapshot
snapshot_we    锁存当前 eligibility，供延迟 MOD_COMMIT 使用
```

同一核只有 1 个 snapshot 槽。当前 4->2->2 Tile 同样实现单槽 snapshot，并用严格递增 `commit_id` 防止重复或过期提交；多槽 snapshot RAM 是扩大 Host 并发深度的后续能力，不属于当前 V1 合同。

## 4->2->2 Tile 事务合同

Tile 同时实例化 2 个 `N_INPUTS=4` 隐藏核和 2 个 `N_INPUTS=2` 输出核。外部命令优先级为：

```text
STATE_CLEAR > SNAPSHOT > WEIGHT_WRITE > MOD_COMMIT > TICK
```

- 命令仅在 `ready=1` 时接受；busy 期间的第二命令不进入任何子核。
- 命令“存在”决定上述优先级，合法性只决定是否派发；非法高优先级命令立即报错，并阻断同周期全部低优先级命令。
- 四核并行运行，sticky `done_mask` 等待最慢子核；Tile 只在 all-done barrier 后产生一个周期的 `done`。
- TICK 接受时，输出核读取旧 `pending_hidden`；barrier 完成后才以本次隐藏 spike 覆盖 pending，形成固定一逻辑 tick 延迟。
- `hidden_spikes/output_spikes` 仅在 TICK 的 `done` 周期有效；busy 期间权重读口返回 0。
- Tile 外部可见的 pending、commit metadata、epoch 和 spike 在 barrier 后原子更新；各子核内部寄存器会在各自完成周期提交，不宣称层级内部同时翻转。
- SNAPSHOT/MOD/WEIGHT_WRITE 仅允许 TRAIN；非法命令以 `protocol_error=1, done=1` 完成且不改变架构状态。
- 合法零 modulator 会消费当前 snapshot 并增加 `weight_epoch`，但不会改变权重。

## Host Bridge 双时钟合同

- Host/Tile 两侧均使用 128-bit `valid/ready` 流；命令和响应各通过一条 depth-16、128-bit、FWFT 的 `xpm_fifo_async`。
- 本配置真实 XPM 的外部可见容量为 17：16 个 RAM 字加 1 个读域 FWFT 预取槽；上游仍只按 `ready` 判断是否可接受。
- Host 时钟域只使用 command FIFO 的 `wr_rst_busy` 和 response FIFO 的 `rd_rst_busy`；Tile 时钟域只使用 command FIFO 的 `rd_rst_busy` 和 response FIFO 的 `wr_rst_busy`，不跨域组合读取 busy。
- `bridge_rst` 分别在 Host/Tile 写时钟域两级同步后驱动对应 XPM `rst`；上电保持高电平至少覆盖两个域各 4 个上升沿。
- 下一次 hard reset 只能在 command/response 两个 write-side `wr_rst_busy` 均退出后断言；V1 不在片内排队 reset 请求。
- hard reset 是破坏性边界：清 FIFO、Host session/controller/Tile 动态状态与 commit 元数据，并恢复 `INIT_WEIGHT`；保留权重的有序恢复使用 `ABORT`。
- Controller 只有在响应 `valid && ready` 接受边沿提交 Host architectural state；响应背压期间 payload 与 Host 架构状态必须保持。
- `txn_id` 只用于请求/响应关联，不提供重传去重或 exactly-once cache。

## 推荐定点数据通路

```text
weight        signed 8 bit
pre_trace     unsigned 8 bit
eligibility   signed 12 bit
I/V           signed 16 bit
threshold     unsigned 8 bit
refractory    unsigned 4 bit
```

硬件验证必须逐周期比较：

```text
I、V、spike、pre_trace、post_trace、eligibility、weight、refractory
```

## 当前硬件证据（2026-08-13）

- 当前完整 discovery 回归 159 项通过，其中包含非法 SNAPSHOT/WEIGHT/MOD 与低优先级命令并发时无子核副作用、响应背压状态保持、FIFO 回绕、hard reset、XPM/系统 CDC 摘要严格解析和 Temporal 数据合同反例。
- 多周期单核：20 seeds x 1000 个混合事务，共 20000 个事务与独立 Python 参考一致；非二次幂 `N_INPUTS=1/3/5`、busy 原子性和精确延迟均有定向检查。
- 4->2->2 Tile：20 seeds x 500 个混合事务，共 10000 个事务逐事务比较四核完整状态、外部元数据、协议错误和延迟；固定黄金断言额外覆盖一 tick 路由、非零 eligibility、真实权重更新、非法 commit 和 INFER 冻结。
- Yosys 0.56 对真实四核 Tile 完成 24 拍协议 BMC：敌对命令输入不假设 one-hot，约 451 万变量/1252 万子句无反例；该结论不等于无限时域证明或全状态形式等价。
- Host Bridge controller：20 seeds x 1000 命令与 oracle bit-exact；Yosys depth-20 safety BMC 无反例，负向 Tile 合同控制可复现反例，6 类非空 witness 可达。
- 双时钟系统：20 seeds x 2000 flit，共 40000 命令，在随机非整数时钟比、相位和双向背压下逐响应匹配 oracle；hard reset 丢弃 12 个 outstanding 并恢复 `INIT_WEIGHT=2`。
- 真实 Vivado XPM xsim：command/response 外部可见容量均为 17，双向 64 字回绕、长背压和 hard reset 通过；仿真专用 `reset_cycle_active` 未进入综合网表。
- 单核 Vivado 2024.1 OOC：`813 LUT / 544 FF / 0 BRAM / 0 DSP`，100 MHz WNS `+0.469 ns`、TNS 0、setup/hold 零失败。
- Tile Vivado 2024.1 OOC：`3152 LUT / 1972 FF / 0 BRAM / 0 DSP`，100 MHz WNS `+0.213 ns`、TNS 0、WHS `+0.026 ns`、THS 0，setup/hold 零失败，route error 0。
- Tile DRC 只有 OOC 环境的 `CFGBVS-1` warning；methodology 的 `TIMING-18` 来自没有真实顶层 I/O delay。内部最差 setup/hold 均为子核寄存器到寄存器路径。
- Tile 功耗 `0.103 W` 是无 SAIF/VCD 的 vector-less OOC 估算，置信度 Medium，不能作为最终功耗签核。
- 完整系统 Vivado 2024.1 OOC：`3682 LUT / 2486 FF / 4 RAMB36 / 0 DSP`；Host 50 MHz WNS/WHS `+14.306/+0.105 ns`，Tile 100 MHz WNS/WHS `+0.081/+0.058 ns`，两域 TNS/THS 和 setup/hold violations 均为 0，route/DRC error 0。
- 系统 `report_cdc` 的 8 条路径全部位于 XPM FIFO 内部：4 条 Gray pointer `CDC-6` 和 4 条 reset sync `CDC-3`；XPM 外 Critical/Unsafe/Warning 为 0。顶层 `bridge_rst` 物理来源和无 input delay 的端口不在该结论范围。
- 系统功耗 `0.112 W` 是无 SAIF/VCD 的 vector-less OOC 估算，置信度 Medium，不能作为最终功耗签核。

`digital_lif_core.sv` 保留为单周期行为参考；阵列实现基线已经切换到 `digital_lif_engine.sv` 和 `digital_snn_tile_4x2x2.sv`。

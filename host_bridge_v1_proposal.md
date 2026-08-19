# Host Bridge V1 设计审核稿

状态：第三轮终审已修订，等待用户冻结；尚未实现 RTL。

日期：2026-08-13。

## 1. 目标与边界

Host Bridge V1 把片外训练系统与固定 `4->2->2` Tile 连接起来。片外 Host 继续负责输入编码、标签、目标、奖励、探索、预测和 signed modulator；FPGA 侧只负责：

- 跨时钟域传输固定宽度命令和响应；
- 检查 episode、tick、event、commit 和地址合同；
- 把同一 tick 的离散输入事件聚合为 `input_spikes[3:0]`；
- 串行执行 Tile 事务，并在响应被 Host 接收前保持其稳定；
- 在 episode 尾部执行一次 output-only 路由排空；
- 在 TRAIN episode 尾部捕获单槽 eligibility snapshot。

V1 不绑定 UART、USB、PCIe、AXI 或具体 FPGA 板卡。物理接口只需适配两个 `valid/ready` 流。V1 不在片上实现损失函数、奖励函数、探索策略、数据集管理、分类器或 spike count 累计。

## 2. 为什么必须增加 Bridge 和 `ROUTE_FLUSH`

当前 Python 周期模型已经有 `TICK_BEGIN -> INPUT_EVENT* -> TICK_COMMIT`、有界 FIFO 和背压语义，但 Tile RTL 只接受聚合后的 `tick_valid + input_spikes[3:0]`。两者之间缺少可综合的事务前端。

当前 Tile 的 `done/protocol_error/hidden_spikes/output_spikes` 都是单周期脉冲，没有响应 `ready`。这些信号不能直接跨时钟域采样，否则可能丢失响应。

Python `flush_route()` 只推进输出层并清除 `pending_hidden`。普通零输入 TICK 还会推进隐藏层膜状态、trace、eligibility、threshold 和 refractory，因此语义不等价。Tile 必须增加独立的 `ROUTE_FLUSH` 原语。

## 3. 顶层结构

```text
Host/物理接口
    |
    | 128-bit command valid/ready
    v
XPM async command FIFO  (host_clk -> tile_clk, depth 16)
    |
    v
Host Bridge scheduler / validator
    |
    v
digital_snn_tile_4x2x2 + ROUTE_FLUSH
    |
    v
XPM async response FIFO (tile_clk -> host_clk, depth 16)
    |
    | 128-bit response valid/ready
    v
Host/物理接口
```

V1 只有一个命令执行槽和一个 Tile 事务在途，不做乱序执行。

## 4. 外部端口

```systemverilog
input  logic         host_clk;
input  logic         tile_clk;
input  logic         bridge_rst;

input  logic         host_cmd_valid;
output logic         host_cmd_ready;
input  logic [127:0] host_cmd_data;

output logic         host_rsp_valid;
input  logic         host_rsp_ready;
output logic [127:0] host_rsp_data;

output logic         status_irq;
```

`status_irq` 在 Host 域直接等于复位门控后的 `host_rsp_valid`，不携带额外状态。

## 5. 统一的 128-bit flit 格式

命令和响应使用同构布局：

```text
[127:120] opcode
[119:112] flags / status
[111: 96] txn_id
[ 95: 80] episode_id
[ 79: 64] tick_id
[ 63: 32] arg0
[ 31:  0] arg1
```

命令第二字节为 `flags`，响应第二字节为 `status`。响应有效性由外部 `host_rsp_valid` 表示，不在 payload 中重复设置 marker。响应保留完整 8-bit opcode，不截断高两位。

通用规则：

- 除各 opcode 明确定义的位外，命令其余字段必须为 0，否则返回 `BAD_FIELD`。
- 成功和错误响应都 echo 命令的 `opcode/txn_id/episode_id/tick_id`；成功的 `STATUS_READ` 按 page 0/page 1 的定义覆盖响应中的 episode/tick 字段。
- `status=0` 表示成功，非零表示错误。DECODE 阶段的协议校验错误已消费命令，但不启动 Tile，也不修改 architectural session 或 input-tick staging；执行期 `INTERNAL_FATAL` 可能发生在 Tile 已产生部分副作用之后。
- 所有非零 status 的响应都固定 `arg0=0/arg1=0`；错误细节只由 status、echo 字段和后续 STATUS_READ 表达。
- `txn_id` 只是 Host 关联请求和响应的标签。V1 不保存完成历史，不检测重传，也不提供基于 `txn_id` 的幂等去重。
- Host 不得让两个未完成命令使用相同 `txn_id`。这是 Host 义务，不是 Bridge 强制检查。

## 6. Opcode 与精确语义

| Opcode | 名称 | 字段和效果 |
|---:|---|---|
| `01` | `EP_START` | `flags[0]=TRAIN`，否则 INFER；`episode_id` 有效；成功前执行 Tile `STATE_CLEAR` |
| `02` | `TICK_BEGIN` | `episode_id/tick_id` 必须匹配；`arg0[2:0]=event_count`，范围固定为 `0..4`；只打开 staging |
| `03` | `INPUT_EVENT` | `episode_id/tick_id` 必须匹配；`arg0[2:0]=synapse_id`，仅 `0..3` 合法；只更新当前 tick 的 mask 和计数 |
| `04` | `TICK_COMMIT` | 仅当接收事件数等于声明数时启动一次 Tile TICK |
| `05` | `EP_END` | TRAIN 时 `arg0[15:0]=commit_id`；INFER 时 `arg0=0`；总是执行一次 `ROUTE_FLUSH`，TRAIN 再执行 SNAPSHOT |
| `06` | `MOD_COMMIT` | `arg0[15:0]=commit_id`；`arg1[7:0]` 为四个 signed 2-bit modulator |
| `07` | `WEIGHT_WRITE` | `arg0[1:0]=neuron`、`arg0[3:2]=weight`、`arg0[11:4]=signed data` |
| `08` | `WEIGHT_READ` | `arg0[1:0]=neuron`、`arg0[3:2]=weight`；返回符号扩展后的权重 |
| `09` | `ABORT` | 有序且不可抢占地终止当前 episode，执行 Tile `STATE_CLEAR` |
| `0A` | `STATUS_READ` | `arg0[0]=page`，支持 session 页和 snapshot 页；不启动 Tile |

字段合法性冻结如下；表中的 `0` 表示必须为全零，否则返回 `BAD_FIELD`：

| 命令 | flags | episode_id | tick_id | arg0 | arg1 |
|---|---|---|---|---|---|
| `EP_START` | 仅 bit0 | session tag，可复用 | `0` | `0` | `0` |
| `TICK_BEGIN` | `0` | active ID | current tick | event count | `0` |
| `INPUT_EVENT` | `0` | active ID | current tick | 3-bit synapse ID | `0` |
| `TICK_COMMIT` | `0` | active ID | current tick | `0` | `0` |
| `EP_END` | `0` | active ID | `0` | `arg0[15:0]` 为 commit candidate，`arg0[31:16]=0`；INFER 时低 16 bit 还必须为 0 | `0` |
| `MOD_COMMIT` | `0` | pending snapshot episode ID | `0` | pending commit ID | four modulators |
| `WEIGHT_WRITE` | `0` | `0` | `0` | address + data | `0` |
| `WEIGHT_READ` | `0` | `0` | `0` | address | `0` |
| `ABORT` | `0` | active ID | `0` | `0` | `0` |
| `STATUS_READ` | `0` | `0` | `0` | bit0 page，其余 `0` | `0` |

四个 modulator 的位序固定为：

```text
arg1[1:0] = H0
arg1[3:2] = H1
arg1[5:4] = O0
arg1[7:6] = O1
```

合法编码固定为：

```text
2'b11 = -1
2'b00 =  0
2'b01 = +1
2'b10 = 非法，返回 BAD_FIELD
```

当前软件学习规则是符号调制，不区分奖励幅度；禁止 `-2` 可保持 Python、RTL 和 wire protocol 一致。V1 不实现逐神经元 modulator staging。

权重地址固定映射为：neuron 0/1（H0/H1）允许 weight 0..3；neuron 2/3（O0/O1）只允许 weight 0..1。其余组合返回 `ADDRESS`。

## 7. 响应 payload

- `TICK_COMMIT`：`arg0[1:0]=hidden_spikes`，`arg0[3:2]=output_spikes`，其余为 0。
- `EP_END`：`arg0[3:2]=ROUTE_FLUSH output_spikes`，`arg0[1:0]=0`；`arg1=weight_epoch`。
- `MOD_COMMIT`：`arg0[15:0]=commit_id`，`arg1=更新后的 weight_epoch`。
- `WEIGHT_READ`：`arg0={{24{weight[7]}}, weight[7:0]}`，`arg1=0`。
- `STATUS_READ page 0`：返回 Bridge session。`episode_id=episode_active ? active_episode_id : 0`，`tick_id=next_tick_ext[15:0]`；`arg0[0]=episode_active`、`arg0[1]=episode_train`、`arg0[2]=tick_open`、`arg0[3]=next_tick_ext[16]`、`arg0[4]=fatal_error`、`arg0[10:8]=expected_event_count`、`arg0[13:11]=seen_event_count`、`arg0[17:14]=seen_mask`，其余为 0；`arg1[7:0]=fatal_opcode`、`arg1[15:8]=fatal_phase`，其余为 0。
- `STATUS_READ page 1`：返回 snapshot/commit 真值。`episode_id=snapshot_valid ? pending_episode_id : 0`，`tick_id=snapshot_valid ? pending_commit_id : 0`；`arg0[15:0]=last_commit_valid ? last_commit_id : 0`、`arg0[16]=snapshot_valid`、`arg0[17]=last_commit_valid`，其余为 0；`arg1=weight_epoch`。

所有其他成功响应的 `arg0/arg1` 为 0，除非该 opcode 上文另有定义。响应一旦 `host_rsp_valid=1`，在 `host_rsp_ready=0` 期间整个 payload 必须逐周期稳定。

## 8. Bridge 状态

Bridge 保存：

```text
episode_active
episode_train
active_episode_id
next_tick_ext[16:0]
tick_open
expected_event_count[2:0]
seen_event_count[2:0]
seen_mask[3:0]
active_command_reg[127:0]
response_reg[127:0]
ep_end_flush_spikes[1:0]
fatal_error
fatal_opcode[7:0]
fatal_phase[7:0]
```

命令从 FIFO 消费时必须锁存完整 payload。`ep_end_flush_spikes` 在 `ROUTE_FLUSH done` 边沿捕获，并保持到最终 `EP_END` 响应被 response FIFO 接受；TRAIN 后续 SNAPSHOT 不得覆盖该值。

### Bridge 可见状态的提交边沿

所有 Host 可见的 architectural session 和 input-tick staging 都使用“计算 next-state，响应 FIFO 接受时统一提交”的单槽结构：

```text
response_accept = rsp_wr_en && !rsp_full && !rsp_wr_rst_busy
```

- `TICK_BEGIN/INPUT_EVENT` 在 DECODE 计算 staging next-state，`response_accept` 时提交。
- `TICK_COMMIT` 在 Tile done 时锁存 spike 结果，`response_accept` 时清 staging 并增加 `next_tick_ext`。
- `EP_START/EP_END/ABORT` 在 Tile 子事务成功后准备 session next-state，`response_accept` 时提交。
- 协议校验错误的 architectural session/input-tick next-state 等于当前状态。

`active_command_reg/response_reg/ep_end_flush_spikes` 是事务私有 working state，可在命令消费或 Tile 完成边沿更新；它们不属于上述 `response_accept` 提交合同。`fatal_*` 是独立的 sticky 诊断状态，在首次内部故障检测边沿锁存。

Tile 内部状态可能早于 response enqueue 更新，但单执行槽保证在响应成功入 FIFO前不会消费下一命令，因此 Host 不会观察到可交叉执行的半提交状态。hard reset 仍是明确的例外，会丢弃在途命令和响应。

`weight_epoch` 是 32-bit 自然 modulo 计数器。只有合法 `MOD_COMMIT` 在 Tile 完成时增加一次，包括四个 modulator 全为 0 的提交；显式 `WEIGHT_WRITE` 不增加 epoch。`INTERNAL_FATAL` 不提交该命令原计划的 architectural session/input-tick next-state，但已经发生的 Tile 部分副作用不回滚。

Tile 继续保存 snapshot、pending/last commit metadata、`pending_hidden` 和 `weight_epoch`，Bridge 不复制这些真值状态。为支持无副作用预检，Tile 必须新增只读状态端口：

```text
last_commit_valid_state
last_commit_id_state[15:0]
```

它们与现有 `snapshot_valid_state/pending_commit_id_state/weight_epoch_state` 一样，只暴露已原子提交的 Tile 元数据，不暴露核心中间状态。

## 9. Episode 与 tick 不变量

1. `EP_START` 只允许在 episode idle 时执行；所有 tick 命令和 `EP_END/ABORT` 只允许在 episode active 时执行。
2. `TICK_BEGIN` 必须从 `tick_id=0` 开始，并严格等于 `next_tick_ext[15:0]`。
3. `event_count` 固定限制为 `0..4`，与异步 FIFO 深度无关。
4. 同一 tick 的 synapse 不得重复；事件顺序不影响最终 `seen_mask`。
5. `TICK_COMMIT` 数量不足时返回 `EVENT_COUNT`，保留 staging；Host 可以补齐事件或执行 `ABORT`。
6. 额外事件、重复事件和非法事件返回错误，且不改变已有 staging。
7. Tile TICK 成功完成后，Bridge 才清 staging 并增加 `next_tick_ext`。
8. 允许提交 `tick_id=16'hffff`。成功后 `next_tick_ext=17'h10000`，`tick_exhausted=1`；该 episode 此后只接受 `EP_END` 或 `ABORT`，新的 `TICK_BEGIN` 返回 `COUNTER_WRAP`。
9. pending snapshot 存在时允许开始 INFER，但拒绝新的 TRAIN。
10. 若 `last_commit_valid && last_commit_id=16'hffff`，新的 TRAIN `EP_START` 直接返回 `COUNTER_WRAP`，避免进入一个无法合法结束的训练 episode。
11. `MOD_COMMIT`、`WEIGHT_READ` 和 `WEIGHT_WRITE` 只允许在 episode idle 时执行。
12. pending snapshot 存在时允许 `WEIGHT_READ`，但拒绝 `WEIGHT_WRITE`，防止 delayed MOD 应用前改变权重基准。
13. `STATUS_READ` 始终允许且无副作用。

`episode_id` 在 V1 中只是 active-session tag，不要求全局单调，episode idle 后允许复用。

### `EP_START` 原子步骤

`EP_START` 固定执行：

```text
完整预检 -> STATE_CLEAR -> response enqueue acceptance + session 原子提交（同一边沿）
```

完整预检发生在 `STATE_CLEAR` 前：episode 必须 idle；TRAIN 时 snapshot 槽必须为空，且 `last_commit_id` 空间未耗尽。预检通过后锁存命令，等待 `tile.ready` 再启动 clear。

只有 Tile clear 成功且 `response_accept` 的边沿，才同时提交：

```text
episode_active = 1
episode_train = flags[0]
active_episode_id = command.episode_id
next_tick_ext = 0
tick_open = 0
expected_event_count = 0
seen_event_count = 0
seen_mask = 0
```

如果预检后的 clear 意外返回错误，进入 `INTERNAL_FATAL`，session 不得呈现半启动状态。

## 10. `EP_END` 的复合事务与原子边界

INFER：

```text
precheck -> ROUTE_FLUSH -> response -> session idle
```

TRAIN：

```text
precheck -> ROUTE_FLUSH -> SNAPSHOT(commit_id, episode_id)
         -> response -> session idle
```

所有 `EP_END` 必须在启动 `ROUTE_FLUSH` 前预检：

```text
episode_active
!tick_open
episode_id == active_episode_id
```

INFER 还要求 `arg0==0`。TRAIN 还必须同时预检：

```text
episode_train
!tile.snapshot_valid
!tile.last_commit_valid || commit_id > tile.last_commit_id
```

所有可预测的协议错误都必须在任何 Tile 副作用发生前返回。预检通过后，Bridge 锁存 `commit_id/episode_id`，进入 `FLUSH_LAUNCH` 等待 `tile.ready`；Host 后续输入变化不得影响复合事务。`tile.ready` 是内部启动条件，不是 Host 协议错误。

`ROUTE_FLUSH` 与 SNAPSHOT 对 Host 只产生一个 `EP_END` 响应。Bridge 在 flush 完成边沿锁存 `output_spikes`，TRAIN SNAPSHOT 完成后仍从该锁存值构造最终响应。

这里的“原子”表示不存在预检后仍可正常触发的协议拒绝路径；它不表示硬件故障可回滚。若预检通过后 Tile 意外返回错误，Bridge 设置 `fatal_error/fatal_opcode/fatal_phase` 并返回 `INTERNAL_FATAL`，此时可能已发生部分硬件副作用。

只有最终 `EP_END` 响应 `response_accept` 的边沿，才统一清除 session：

```text
episode_active = 0
episode_train = 0
active_episode_id = 0
next_tick_ext = 0
tick_open = 0
expected_event_count = 0
seen_event_count = 0
seen_mask = 0
ep_end_flush_spikes = 0
```

## 11. `ROUTE_FLUSH` Tile 原语

Tile 增加内部请求：

```text
route_flush_valid
```

优先级冻结为：

```text
STATE_CLEAR > SNAPSHOT > WEIGHT > MOD > ROUTE_FLUSH > TICK
```

行为：

- 只向 output0/output1 发出 TICK，`wait_mask=4'b1100`；
- 输出核读取本次请求接受前的旧 `pending_hidden`；
- hidden0/hidden1 的全部动态状态、学习状态和权重保持不变；
- 无论 `pending_hidden` 是否为 0，都必须恰好执行一次 output-only tick，不允许旁路；
- 完成时 `output_spikes` 返回输出层结果，`hidden_spikes=0`，并原子清零 `pending_hidden`；
- TRAIN flush 正常更新输出层 trace/eligibility，INFER flush 冻结输出层学习状态。

预计 Tile 完成延迟为：无输出发放 `C0+9`；TRAIN 且任一输出核发放 `C0+11`。实现时必须用定向周期测试确认，不能只依赖手算。

## 12. `ABORT` 和复位

`ABORT` 是 FIFO 保序的、不可抢占的 session 操作。它不能取消已经启动的 Tile 事务，只能在前序事务完成后执行。

合法 `ABORT` 执行 Tile `STATE_CLEAR`，并在最终响应 `response_accept` 时提交：

```text
episode_active = 0
episode_train = 0
active_episode_id = 0
next_tick_ext = 0
tick_open = 0
expected_event_count = 0
seen_event_count = 0
seen_mask = 0
ep_end_flush_spikes = 0
```

它清除神经元动态状态和 Tile `pending_hidden`，但保留 weights、pending snapshot、pending/last commit metadata 和 `weight_epoch`。

`bridge_rst` 则是破坏性 hard reset，不是 session 恢复操作。它会清空两个 FIFO、Bridge session、Tile 动态状态、snapshot/commit metadata、epoch，并把神经元权重恢复为 `INIT_WEIGHT`。Host 必须丢弃全部 outstanding transaction ledger，并在复位后重新装载模型权重。

## 13. `WEIGHT_READ` 时序

当前 Tile 权重读口是仅在 `ready` 时有效的组合读口。Bridge 不在 DECODE 当拍直接采样。

固定两拍本地流程：

```text
WEIGHT_READ_SETUP   : 锁存 neuron/weight 地址
WEIGHT_READ_CAPTURE : 在 tile.ready=1 时寄存 weight_rdata 并形成响应
```

这样避免 FWFT 命令 payload、地址译码和响应写入形成同拍长组合路径，也避免采到旧地址数据。地址非法时在 SETUP 前返回 `ADDRESS`，不读取 Tile。

## 14. Tile 域 FSM

```text
RESET_WAIT
  -> FETCH
  -> DECODE
     -> LOCAL_RESP
     -> WEIGHT_READ_SETUP
     -> TILE_LAUNCH
     -> FLUSH_LAUNCH
  -> WEIGHT_READ_CAPTURE
  -> TILE_WAIT
  -> EP_END_SNAPSHOT_LAUNCH   (仅 TRAIN EP_END)
  -> RESPONSE_WRITE
  -> FETCH
```

Scheduler 只在以下条件同时成立时从 command FIFO 消费一条命令：

- command FIFO `!empty && !rd_rst_busy`；
- response FIFO `!full && !wr_rst_busy`；
- 没有已锁存命令或在途 Tile 操作；
- Bridge 的 Tile 域 reset 已完成。

本地命令和非法命令不依赖 `tile.ready`。需要启动 Tile 的命令在各自 LAUNCH 状态等待并重新确认 `tile.ready`，这样 `STATUS_READ` 和错误响应不会被 Tile 的临时 busy 阻塞。

command FIFO 使用 FWFT；`cmd_rd_en` 只在 scheduler 实际锁存并消费命令的边沿拉高。

response FIFO 只有一个 Tile 域写者。Scheduler 消费命令前确认非满，并在该响应被实际写入前不再 FETCH，因此逻辑上预留一个响应槽。只有观察到：

```text
rsp_wr_en && !rsp_full && !rsp_wr_rst_busy
```

的接受边沿后，FSM 才能释放响应并返回 FETCH。不能仅凭 `rsp_wr_en` 拉高就假定写入成功。

Tile `learn_enable` 按事务驱动，不是 Bridge idle 时的隐式全局模式：

```text
TICK / ROUTE_FLUSH : episode_train
SNAPSHOT           : 1
MOD_COMMIT         : 1
WEIGHT_WRITE       : 1
STATE_CLEAR        : 0（该信号对 clear 无意义）
```

因此 INFER 的普通 TICK 和尾部 flush 都冻结学习状态，而 Host 在 episode idle 时仍能执行显式权重写和合法 MOD。

Bridge 必须保证 `learn_enable`、请求类型和 payload 在 Tile 接受边沿前建立，并保持覆盖该完整接受周期。现有 Engine 会在 TICK 接受边沿锁存 `learn_enable`；其他命令也只在接受边沿读取它。

## 15. CDC 与 XPM FIFO

使用本机 Vivado 2024.1 随附的两个 `xpm_fifo_async`：

```text
FIFO_WRITE_DEPTH = 16
WRITE_DATA_WIDTH = READ_DATA_WIDTH = 128
READ_MODE = "fwft"
FIFO_READ_LATENCY = 0
CDC_SYNC_STAGES = 2
SIM_ASSERT_CHK = 1
FIFO_MEMORY_TYPE = "auto"
```

外部 `bridge_rst` 分别由 Host 域和 Tile 域的两级同步器采样，生成全同步、active-high 的 `host_rst/tile_rst`。同步器不使用异步置位，因为本机 Vivado 2024.1 的 `xpm_fifo_async.rst` 明确要求同步于 FIFO 写时钟。上电和 hard reset 时，`bridge_rst` 必须保持为 1，直到 Host/Tile 两个时钟域各自至少观察到 4 个上升沿；释放也只通过各域同步器生效。

V1 不在 wrapper 内排队或合并 hard-reset 请求。外部只允许在 command FIFO 的 `cmd_wr_rst_busy=0` 且 response FIFO 的 `rsp_wr_rst_busy=0` 已被各自写时钟域观察到之后，重新断言下一次 `bridge_rst`；不得在上一次 XPM reset 序列尚未完成时重入 reset。若物理接口不能遵守该合同，板级适配器必须先锁存 reset 请求，等待两个 write-side busy 都退出后再驱动 Bridge。

- command FIFO 的 `rst` 使用 Host/write 域复位；
- response FIFO 的 `rst` 使用 Tile/write 域复位；
- Bridge Host 端逻辑使用 Host 域复位；
- scheduler、Tile 和神经元核心使用 Tile 域复位。

两个时钟在整个复位序列期间必须稳定运行。各接口必须门控对应的 XPM reset-busy：

```text
host_cmd_ready = !host_rst && !cmd_wr_rst_busy && !cmd_full
host_rsp_valid = !host_rst && !rsp_rd_rst_busy && !rsp_empty
status_irq     = host_rsp_valid
cmd_wr_en      = host_cmd_valid && host_cmd_ready
host_rsp_data  = rsp_dout
rsp_rd_en      = host_rsp_valid && host_rsp_ready
```

Host 在 `host_cmd_valid=1 && host_cmd_ready=0` 时必须保持 `host_cmd_data` 和 `host_cmd_valid` 稳定，直到握手发生。Bridge 不得在 `host_rsp_valid=0` 时拉高 `rsp_rd_en`。

Tile 域定义一个明确的 `tile_domain_up`：同步 `tile_rst` 有效时清零，观察到 `tile_rst=0` 的第一个 `tile_clk` 边沿后置一。Scheduler 只有在 `tile_domain_up && !cmd_rd_rst_busy && !rsp_wr_rst_busy` 时退出 `RESET_WAIT`。需要启动 Tile 的命令仍在 LAUNCH 状态单独等待 `tile.ready`。

128-bit payload 只通过异步 FIFO 跨域，不得手写多位寄存器同步器。

## 16. 每命令一次响应的准确边界

V1 保证：若没有 reset 或硬件故障，每个被 command FIFO 消费的 flit 至多启动一次对应操作，并恰好写入一个响应；FIFO 保序，因此响应不乱序。

V1 不保证：

- Host 因超时重发相同 `txn_id` 时自动去重；
- reset 前已接受命令在 reset 后仍产生响应；
- reset 前未读响应在 reset 后可恢复；
- 基于 `txn_id` 的幂等 replay。

若未来需要可重试 exactly-once，必须增加 Host 可读的 `reset_epoch/boot_id` 和已完成 transaction replay cache，不属于 V1。

## 17. 错误码

| 值 | 名称 | 含义 |
|---:|---|---|
| `00` | `OK` | 命令成功 |
| `01` | `BAD_OPCODE` | 未定义 opcode |
| `02` | `BAD_STATE` | 当前 session/tick 状态不允许该命令 |
| `03` | `EPISODE_ID` | episode 标签不匹配 |
| `04` | `TICK_ID` | tick 标签不匹配 |
| `05` | `EVENT_COUNT` | 声明数、已收数或额外事件错误 |
| `06` | `SYNAPSE_RANGE` | synapse 越界 |
| `07` | `DUP_EVENT` | 同 tick 重复 synapse |
| `09` | `SNAPSHOT_BUSY` | 单槽 snapshot 阻止新 TRAIN |
| `0A` | `COMMIT_ID` | 未知、过期、重复或非法 commit |
| `0B` | `ADDRESS` | 权重地址越界 |
| `0C` | `BAD_FIELD` | 保留位或未使用参数非零 |
| `08` | `RESERVED` | V1 不使用 |
| `0D` | `RESERVED` | V1 不使用；意外 Tile 拒绝统一进入 `INTERNAL_FATAL` |
| `0E` | `COUNTER_WRAP` | tick 或 commit 空间已耗尽 |
| `0F` | `INTERNAL_FATAL` | 复合事务或内部不变量失败 |

`fatal_error=1` 后，`STATUS_READ` 仍正常返回状态；其他被消费命令统一返回 `INTERNAL_FATAL` 且不得启动 Tile。只有 `bridge_rst` 能恢复；`ABORT` 不能恢复未知的部分提交状态。

`fatal_error/fatal_opcode/fatal_phase` 是首次故障优先的 sticky 状态：hard reset 清零；首次内部故障检测边沿原子锁存 `fatal_error=1`、当前命令 opcode 和当前 phase；之后直到 hard reset 不得覆盖。普通协议错误不修改它们。`fatal_error=0` 时，STATUS page 0 强制返回 `fatal_opcode=0`、`fatal_phase=0`。

`fatal_phase` 编码固定为：

| 值 | 阶段 |
|---:|---|
| `00` | 无 fatal |
| `01` | `EP_START_CLEAR_WAIT` |
| `02` | `TICK_WAIT` |
| `03` | `EP_END_FLUSH_WAIT` |
| `04` | `EP_END_SNAPSHOT_WAIT` |
| `05` | `MOD_WAIT` |
| `06` | `WEIGHT_WAIT` |
| `07` | `ABORT_CLEAR_WAIT` |
| `08` | `CONTROLLER_INTERNAL` |

错误判定不使用一张全局优先表。所有命令先执行共同前缀。这里的保留字段只包含不依赖当前 session 模式的静态布局检查；例如 `EP_END` 的 `flags/tick_id/arg0[31:16]/arg1`，不包含“INFER commit 必须为 0”这种动态条件：

```text
fatal（STATUS_READ 除外） -> BAD_OPCODE -> 保留字段/BAD_FIELD
```

之后按 opcode 使用下列固定判定链，返回第一个匹配错误：

| Opcode | 判定链 |
|---|---|
| `EP_START` | active→`BAD_STATE`；TRAIN snapshot busy→`SNAPSHOT_BUSY`；TRAIN commit 空间耗尽→`COUNTER_WRAP` |
| `TICK_BEGIN` | 非 active 或已有 open tick→`BAD_STATE`；episode→`EPISODE_ID`；exhausted→`COUNTER_WRAP`；tick→`TICK_ID`；count>4→`EVENT_COUNT` |
| `INPUT_EVENT` | 非 active/open→`BAD_STATE`；episode→`EPISODE_ID`；tick→`TICK_ID`；synapse>=4→`SYNAPSE_RANGE`；重复→`DUP_EVENT`；超出声明数量→`EVENT_COUNT` |
| `TICK_COMMIT` | 非 active/open→`BAD_STATE`；episode→`EPISODE_ID`；tick→`TICK_ID`；数量不等→`EVENT_COUNT` |
| `EP_END` | 非 active 或 tick open→`BAD_STATE`；episode→`EPISODE_ID`；INFER commit 非零→`BAD_FIELD`；TRAIN snapshot busy→`SNAPSHOT_BUSY`；TRAIN commit 空间耗尽→`COUNTER_WRAP`；TRAIN commit 非递增→`COMMIT_ID` |
| `MOD_COMMIT` | episode active→`BAD_STATE`；无 snapshot→`COMMIT_ID`；episode→`EPISODE_ID`；commit→`COMMIT_ID` |
| `WEIGHT_READ` | episode active→`BAD_STATE`；地址→`ADDRESS` |
| `WEIGHT_WRITE` | episode active→`BAD_STATE`；snapshot busy→`SNAPSHOT_BUSY`；地址→`ADDRESS` |
| `ABORT` | 非 active→`BAD_STATE`；episode→`EPISODE_ID` |
| `STATUS_READ` | `arg0[31:1]` 或其他保留字段非零→`BAD_FIELD`；page 0/1 均合法 |

## 18. 验收门槛

### 协议与功能

- 独立 Python bridge oracle 与 RTL 逐命令比较 response、session、Tile 可见状态和精确 side effect。
- 少发、多发、错 episode、错 tick、重复/越界 synapse、越界地址、非法 modulator、过期 commit 和保留位非零均无 Tile 副作用。
- 多错误 flit 必须按对应 opcode 的冻结判定链返回唯一 status，并保持 session、staging 和 Tile 不变。
- TRAIN `EP_END` 的 snapshot busy、commit 非递增和 commit 耗尽反例必须在 flush 前拒绝。
- `ROUTE_FLUSH` 与 Python `flush_route()` bit-exact；即使 `pending_hidden=0` 也推进一次输出层，且 hidden 完整状态保持。
- `WEIGHT_READ` 必须覆盖地址切换后的 setup/capture 时序。
- 每个已消费命令恰好一个响应；无丢失、重复和乱序。
- response stall 期间 payload 稳定；response FIFO 满时不消费新命令。
- `ABORT` 保留权重和 pending snapshot；`bridge_rst` 清权重，二者必须分别定向验证。
- pending snapshot 期间 `WEIGHT_READ` 成功、`WEIGHT_WRITE` 无副作用地返回 `SNAPSHOT_BUSY`。
- TRAIN `EP_END` 的 flush spike 必须跨 SNAPSHOT 子事务保持，并原样出现在最终响应。
- STATUS 两页必须足以重建 active session、tick staging、pending snapshot、last commit 和 fatal 阶段。
- `fatal_*` 必须首次故障 sticky，后续命令不得覆盖根因；无 fatal 时三个诊断字段均为 0。
- `2'b10` modulator 必须在启动 Tile 前返回 `BAD_FIELD`；其余 `-1/0/+1` 与 Python/RTL bit-exact。

### 双时钟与 FIFO

- Host/Tile 使用随机非整数时钟频比和随机初始相位。
- 随机 Host producer、随机 Host response backpressure 和端到端 scoreboard 同时运行。
- 覆盖 FIFO 空、满、同时 push/pop、指针回绕和长时间背压。
- reset-busy 期间两侧均不握手；共同 hard reset 后 FIFO 与 session 为空、权重回到初值。
- Controller 级 Icarus 仿真可使用接口等价的异步 FIFO 模型；Vivado xsim 必须补充实际 XPM 仿真。
- Vivado `report_cdc` 不得有未解释的 Critical/Unsafe CDC。

### Formal

- Bridge 控制 formal 使用抽象 FIFO，证明：未消费不执行、每次消费最多一次 launch、响应预留、stall 稳定和错误无副作用。
- `EP_END` 证明所有可预测错误均发生在 `ROUTE_FLUSH` 前。
- `ROUTE_FLUSH` 在 Tile 层证明只启动两个输出核、hidden 状态保持、完成时清 `pending_hidden`。
- Formal 结论必须注明展开深度和假设范围，不表述成全状态数学等价。

### 物理实现

- Bridge + Tile 在 `xc7a35tcpg236-1` OOC 下完成双时钟综合、布局布线和 CDC 报告。
- Tile 时钟保持 100 MHz；Host 时钟先以 50 MHz 代理约束，最终频率由实际物理接口决定。
- setup/hold 非负，DRC/route 零 error/critical warning；报告时间戳晚于全部相关 RTL。

## 19. 待用户冻结的五项架构决策

1. 固定同构 128-bit command/response 双流；UART、USB、PCIe、AXI 适配放在 Bridge 外。
2. 固定单槽 snapshot；pending snapshot 时拒绝 TRAIN，但允许 INFER。
3. 新增无条件执行一次 output-only tick 的 `ROUTE_FLUSH`，并把 TRAIN `EP_END` 冻结为“完整预检后 flush + snapshot”的单响应复合事务。
4. 接受 V1 的事务边界：每个被消费 flit 一次执行、一次响应，但不提供重传去重；`bridge_rst` 是清权重的 hard reset，`ABORT` 是保留权重和 snapshot 的有序软终止。
5. `MOD_COMMIT` 一次携带 H0/H1/O0/O1 四个 signed 2-bit modulator；V1 不实现逐神经元 staging。

用户批准这五项后，再分解为 Tile 修改、Bridge controller、XPM wrapper、Python oracle、双时钟仿真、formal/CDC 和 Vivado 七类实现任务。

## 20. 批准后的七类实现任务

以下任务只在第 19 节五项决策全部批准后进入实现。依赖关系冻结为：

```text
T1 Tile ROUTE_FLUSH/状态端口 ─┐
                              ├─> T3 Bridge controller ─┐
T2 Python bridge oracle ──────┘                         ├─> T5 双时钟端到端协同仿真 ─┐
                                                        │                           ├─> T7 Vivado OOC 最终签核
T4 XPM async FIFO/reset wrapper ────────────────────────┘                           │
                              T1 + T3 + T4 ───────────────> T6 formal/CDC ──────────┘
```

T2 与 T4 可并行；T3 以 T1 的最终 Tile 接口和 T2 的 oracle 为行为基准。T6 中 controller formal 可在 T3 完成后先运行，但实际 XPM CDC 报告必须等待 T4 和集成顶层完成。旧 Tile 的 Vivado 报告只作为基线，不作为 T7 证据。

| 任务 | 实现范围 | 权威验收证据 |
|---|---|---|
| T1 Tile 修改 | 增加 `ROUTE_FLUSH`、`last_commit_*_state`，统一组合派发/时序仲裁优先级 | 定向周期测试确认 `C0+9/C0+11`；Python Tile oracle bit-exact；证明只启动 output 核、hidden 全状态保持、完成时清 `pending_hidden`；STATE_CLEAR 保留 weight/snapshot/commit/epoch |
| T2 Python oracle | 128-bit codec、全部 opcode/错误链、architectural/working/fatal 状态、reset/ABORT 语义 | codec 固定向量；每个 opcode 的成功/首错/多错反例；STATUS 两页可恢复真值；oracle 自身单测全通过 |
| T3 Bridge controller | 单命令槽、完整预检、事务 launch/wait、response_accept 提交、两拍权重读、sticky fatal | 抽象 FIFO 下逐命令与 T2 比较；至少 20 seeds × 1000 混合命令；每次消费至多一次 launch、恰好一次响应、错误无正常副作用、stall payload 稳定 |
| T4 XPM wrapper/reset | 两个 depth-16 `xpm_fifo_async`、FWFT、双域全同步 reset synchronizer、reset-busy 门控 | Vivado 2024.1 实际 XPM xsim；断言 XPM `rst` 只在对应写时钟边沿变化，且下一次 reset 不早于两个 write-side `wr_rst_busy` 都退出；随机合法 reset 重入、随机相位/非整数频比；reset-busy 无握手；FIFO empty/full/push-pop/回绕/长背压覆盖 |
| T5 双时钟协同仿真 | 集成 Host 流、真实 Bridge、真实 Tile、随机 producer/consumer/backpressure/reset | 端到端 scoreboard；至少 20 seeds × 2000 flit；响应不丢失/不重复/不乱序；reset 后 Host ledger 丢弃边界与 hard-reset 权重恢复符合合同 |
| T6 formal/CDC | 抽象 FIFO controller 性质、Tile flush 性质、集成 CDC 检查 | 报告明确深度和假设；无反例不表述为无限时域证明；Vivado `report_cdc` 无未解释 Critical/Unsafe；XPM 外无手写多位 CDC |
| T7 Vivado OOC | Bridge + XPM + Tile 双时钟综合、布局布线、资源/时序/DRC 报告 | `xc7a35tcpg236-1`，Tile 100 MHz、Host 50 MHz；两时钟 setup/hold 非负、TNS/THS 为 0、route/DRC 零 error/critical warning；报告时间戳晚于全部相关 RTL |

任何一项失败都只回退其直接依赖之后的任务；不得用 T5 随机仿真替代 T6 CDC/formal，也不得用旧 T7 报告替代修改后的物理签核。

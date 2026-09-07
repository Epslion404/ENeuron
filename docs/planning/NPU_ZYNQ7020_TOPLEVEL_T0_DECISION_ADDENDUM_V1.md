# XC7Z020 顶层 T0 决策附录 V1

状态：`T0_APPROVED / T1_RTL_AUTHORIZED`

日期：2026-09-05

目的：把 `NPU_ZYNQ7020_TOPLEVEL_T0_AUDIT_V1.md` 发现的阻断项转换为已批准的实现合同。管理员已批准 A1-A7；本批准只开放 T1 纯 RTL 适配器，不代表 T1/T2/T3 已完成。

## A1：命令字段唯一权威

**建议选择：当前 skeleton + PORT_TABLE 格式。**

- `opcode = cmd_payload[127:124]`，flags/reserved=`[123:120]`。
- `mask_epoch = [119:88]`，reserved=`[87:32]`，word=`[31:0]`。
- 只支持当前骨架的 `0x1..0x9` 命令和 `0xE` 错误响应；wrapper-only `0xA` 只保留给 A3 fence。
- `NPU_ORACLE_SINGLE_CLOCK_CONTRACT_V3.md` 的低位 8-bit opcode/txn 布局标记为历史资料，不在 P15 wrapper 中兼容。
- wrapper 在转发前先检查 `[123:120]` 和 `[87:32]` 保留位；非零保留位优先返回 `BAD_FIELD`，未知 opcode 返回 `BAD_OPCODE`，冻结/状态冲突再返回 `BAD_STATE`。响应槽满时保持 backpressure，不以错误响应替代满槽。

理由：与已实现 RTL、端口表和现有随机 TB 一致，不引入第二套解码器。

## A2：V2 framing 与 AXI 帧

**建议选择：V2 固定 beat 计数为唯一核心权威，T1 AXI shim 不解释 TLAST。**

- 样本内部固定 8 beat，结果内部固定 10 beat；不向核心引入 `last` 或 `model_epoch`。
- `TLAST` 只作为外层包提示，不映射为核心 `last`，也不参与 8/10 beat 计数；T1 不承诺检测或回滚早到、晚到、缺失 TLAST。需要严格包检查时由更外层 packetizer 在进入本 wrapper 前完成。
- 因为 T1 不缓存整帧，不能声称“发现晚到 TLAST 后整帧不进入核心”；固定 8/10 beat、输入端 ready/valid 和结果槽背压才是本 wrapper 的唯一 framing 合同。
- `sample_data` 使用 V2 规则：`pixel[8*k+j] = beat_data[4*j +: 4]`，低 nibble 先到。
- `TKEEP/TSTRB`：32-bit 流固定 `4'b1111`；128-bit 流固定 `16'hffff`。`TID/TDEST` 置零并在 T1 端口表中声明 tie-off。

理由：保持 V2 核心语义，同时避免 DMA/AXI 外层把错误帧静默送入固定 beat 核心。

## A3：命令→样本跨流 fence

**建议选择：wrapper-only `SAMPLE_FENCE`，不修改计算核。**

- 复用当前线级命令格式的保留 opcode `0xA`，仅由 P15 wrapper 消费，不转发给核心；`fence_id = cmd_payload[31:0]`，其余字段必须为零。
- wrapper 在 NPU 域按“命令 FIFO 优先”处理配置命令；只有 fence 之前的命令已经在核心完成 `cmd_valid && cmd_ready` 握手、核心 `sample_ready=1`、当前没有 `result_valid/rsp_valid`、wrapper 没有开放中的样本窗口且模型/mask staging 事务已闭合时，才接受 fence。不能把核心 `runtime_idle` 作为唯一条件，因为已发布但尚未在下一样本首 beat 激活的 mask 可能使该摘要暂时为 0。
- fence 前 Host-facing `sample_ready` 固定为 0，sample FIFO 不允许预填；fence 成功后只开放一个 8-beat 窗口，收满后立即重新关闭。复位或 fence 拒绝时窗口内数据全部丢弃。
- fence 成功返回 wrapper 响应类别 `0xD`：`[127:124]=0xD`、`[123:120]=0`、`[119:116]=0xA`、`[115:112]=0`、`[111:80]=fence_id`、`[79:48]=active_epoch`、`[47:0]=0`。拒绝使用 `0xE` 错误响应和明确错误码。
- `sample_id` 仍以核心实际首 beat 握手沿锁存，不能以 Host 写 FIFO 的时间代替；`STATE_CLEAR`、`MASK_COMMIT`、`FREEZE_SET` 等配置命令必须在对应 fence 前完成。
- `STATE_CLEAR`、`MASK_COMMIT`、`FREEZE_SET` 等配置命令必须在对应 fence 前完成；fence 不改变核心已有状态机。

理由：独立 FIFO 本身没有全局排序，显式 fence 是最小且可验证的跨流顺序合同。

## A4：复位与 ready 汇合

**建议选择：双域同步 busy 汇合，四流统一门控。**

- `host_clk`、`npu_clk` 各自使用两级同步器采样远端 `wr_rst_busy/rd_rst_busy` 和 `domain_up`。
- 任一本地或同步后的远端 busy 为 1，禁止新的事务握手；非复位期间已经呈现的 `valid/payload` 必须保持稳定直到握手，不能被 busy 变化撤销。两域均稳定退出 busy 并连续观察 2 个本地时钟沿后才重新开放 ready。
- `bridge_rst` 保持有效至少覆盖两个域各 4 个上升沿；释放只经过本域同步器。
- 复位丢弃四个 FIFO 中的半命令、半样本和半结果；核心动态状态、模型有效位和 mask 发布状态按既有 hard-reset 合同恢复，Host 必须重新装载模型与 mask。

## A5：FIFO 参数与资源归因

**建议选择：四个 depth-16、FWFT、auto memory 的 XPM 异步 FIFO。**

| FIFO | payload 宽度 | 深度 | 读模式 | memory type |
|---|---:|---:|---|---|
| command | 128 | 16 | `fwft` | `auto` |
| response | 128 | 16 | `fwft` | `auto` |
| sample | 64 | 16 | `fwft` | `auto` |
| result | 96 | 16 | `fwft` | `auto` |

四个 FIFO 统一追加 `FIFO_READ_LATENCY=0`、`CDC_SYNC_STAGES=2`、`SIM_ASSERT_CHK=1`；这些是唯一参数，不采用 XPM 默认值。T1/T3 必须报告每个 FIFO 的实际 LUT/FF/BRAM、CDC synchronizer、读写延迟和满空裕量；不得用理论位数替代 Vivado post-route 归因。

## A6：状态与错误的 Host 可见性

- 成功配置命令仍可不产生普通响应；`SAMPLE_FENCE` 是配置完成和跨流排序的唯一成功确认点。
- `model_valid`、`mask_valid`、`infer_frozen`、FIFO busy 和 error/IRQ 只通过本域同步摘要输出，不允许组合跨域；`mask_epoch` 不做逐 bit CDC，只通过 result FIFO 或 fence 响应中的原子 payload 传递。单 bit error/IRQ 的 sticky/清除规则由 wrapper 本域寄存器冻结。
- response FIFO 只承载错误、fence 确认和既有核心响应；结果 FIFO 只承载 10-beat 结果及其 `sample_id/mask_epoch`，两者不承诺全局到达顺序，Host 以 fence、sample ID 和 epoch 匹配。

## A7：T3 物理基线

- 目标器件固定为 `xc7z020clg400-1`。
- T1 基线 `host_clk=npu_clk=100 MHz`；T2 追加非整数频比和随机相位；T3 使用 XC7Z020 专用 XDC。
- 旧 `xc7a35tcpg236-1` Host Bridge OOC 仅作结构参考，不得作为 P15 资源、时序或功耗证据。

## 批准门

管理员已逐项批准 A1-A7。状态为 `T0_APPROVED / T1_RTL_AUTHORIZED`，可创建纯 RTL 薄封装并执行 T1；T2 双时钟协同仿真和 T3 XC7Z020 OOC 仍需各自通过验收，不得把本批准写成已完成的顶层实现证据。

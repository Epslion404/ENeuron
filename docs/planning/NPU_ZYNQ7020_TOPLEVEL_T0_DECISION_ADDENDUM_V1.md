# XC7Z020 顶层 T0 决策附录 V1

状态：`PROPOSED / ADMIN_REVIEW_REQUIRED / NO_RTL_AUTHORIZATION`

日期：2026-09-05

目的：把 `NPU_ZYNQ7020_TOPLEVEL_T0_AUDIT_V1.md` 发现的阻断项转换为可逐项批准的实现合同。以下均为建议，不等于管理员已经批准。

## A1：命令字段唯一权威

**建议选择：当前 skeleton + PORT_TABLE 格式。**

- `opcode = cmd_payload[127:124]`，flags/reserved=`[123:120]`。
- `mask_epoch = [119:88]`，reserved=`[87:32]`，word=`[31:0]`。
- 只支持当前骨架的 `0x1..0x9` 命令和 `0xE` 错误响应。
- `NPU_ORACLE_SINGLE_CLOCK_CONTRACT_V3.md` 的低位 8-bit opcode/txn 布局标记为历史资料，不在 P15 wrapper 中兼容。

理由：与已实现 RTL、端口表和现有随机 TB 一致，不引入第二套解码器。

## A2：V2 framing 与 AXI 帧

**建议选择：V2 固定 beat 计数为核心权威，AXI shim 严格检查 TLAST。**

- 样本内部固定 8 beat，结果内部固定 10 beat；不向核心引入 `last` 或 `model_epoch`。
- AXI 样本/结果在预期最后 beat 必须出现 `TLAST=1`；提前 TLAST、最后 beat 缺失 TLAST 或超出固定长度均产生 wrapper framing error。
- framing error 的当前帧不送入核心；shim 丢弃到当前帧边界后，通过 128-bit response 错误槽报告，下一帧重新从 beat 0 对齐。
- `sample_data` 使用 V2 规则：`pixel[8*k+j] = beat_data[4*j +: 4]`，低 nibble 先到。
- `TKEEP/TSTRB`：32-bit 流固定 `4'b1111`；128-bit 流固定 `16'hffff`。`TID/TDEST` 置零并在 T1 端口表中声明 tie-off。

理由：保持 V2 核心语义，同时避免 DMA/AXI 外层把错误帧静默送入固定 beat 核心。

## A3：命令→样本跨流 fence

**建议选择：wrapper-only `SAMPLE_FENCE`，不修改计算核。**

- 复用当前线级命令格式的保留 opcode `0xA`，仅由 P15 wrapper 消费，不转发给核心。
- wrapper 在 NPU 域按“命令 FIFO 优先”处理配置命令；收到 `SAMPLE_FENCE` 后，只有在此前命令已完成核心握手、响应槽可记录且两域状态有效时，才开放下一笔样本的首 beat。
- 一个 `SAMPLE_FENCE` 只授权一个完整 8-beat 样本；样本结束后回到阻塞状态，Host 必须为下一样本再次发送 fence。
- fence 成功/拒绝均产生带 fence ID 的 128-bit 响应；`sample_id` 仍以核心实际首 beat 握手沿锁存，不能以 Host 写 FIFO 的时间代替。
- `STATE_CLEAR`、`MASK_COMMIT`、`FREEZE_SET` 等配置命令必须在对应 fence 前完成；fence 不改变核心已有状态机。

理由：独立 FIFO 本身没有全局排序，显式 fence 是最小且可验证的跨流顺序合同。

## A4：复位与 ready 汇合

**建议选择：双域同步 busy 汇合，四流统一门控。**

- `host_clk`、`npu_clk` 各自使用两级同步器采样远端 `wr_rst_busy/rd_rst_busy` 和 `domain_up`。
- 任一本地或同步后的远端 busy 为 1，四条 Host-facing ready/valid 均不得开放；两域均稳定退出 busy 并连续观察 2 个本地时钟沿后才重新开放。
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

T1/T3 必须报告每个 FIFO 的实际 LUT/FF/BRAM、CDC synchronizer、读写延迟和满空裕量；不得用理论位数替代 Vivado post-route 归因。

## A6：状态与错误的 Host 可见性

- 成功配置命令仍可不产生普通响应；`SAMPLE_FENCE` 是配置完成和跨流排序的唯一成功确认点。
- `model_valid`、`mask_valid`、`infer_frozen`、`mask_epoch`、FIFO busy 和 framing/protocol error 在 Host 域只通过同步后的摘要输出，不允许组合跨域。
- response FIFO 只承载错误、fence 确认和既有核心响应；结果 FIFO 只承载 10-beat 结果及其 `sample_id/mask_epoch`，两者不承诺全局到达顺序，Host 以 fence、sample ID 和 epoch 匹配。

## A7：T3 物理基线

- 目标器件固定为 `xc7z020clg400-1`。
- T1 基线 `host_clk=npu_clk=100 MHz`；T2 追加非整数频比和随机相位；T3 使用 XC7Z020 专用 XDC。
- 旧 `xc7a35tcpg236-1` Host Bridge OOC 仅作结构参考，不得作为 P15 资源、时序或功耗证据。

## 批准门

管理员需要逐项批准 A1-A7，或明确修改某一项。全部批准后，才把状态改为 `T0_APPROVED / T1_RTL_AUTHORIZED` 并创建纯 RTL 薄封装；在此之前不创建顶层 RTL。

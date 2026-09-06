# XC7Z020 顶层 T0 端口与适配边界裁定稿

状态：`T0_APPROVED / T1_RTL_AUTHORIZED`

日期：2026-09-05

关联规划：`docs/planning/NPU_ZYNQ7020_TOPLEVEL_INTEGRATION_V1.md`

## 1. 裁定目标

在开始 T1 RTL 前，冻结“核心协议、跨时钟桥、AXI/PS 外部接口”三层边界。本文只决定接口职责，不修改已签核的 NPU 计算核，也不宣称已经接入 DMA、网口或具体开发板。

## 2. 现状约束

- 核心 `npu_eneuron_single_clock_skeleton` 使用单一 `clk`，命令/响应为 128 bit，样本输入为 32 bit，结果输出为 32 bit。
- 核心样本固定 8 个 beat，结果固定 10 个 beat；命令握手和样本握手彼此独立，但都必须遵守 ready/valid 稳定规则。
- `digital_snn_host_bridge` 当前只有 128-bit 命令 FIFO 和 128-bit 响应 FIFO，不能直接承载核心的 32-bit 样本/结果流。
- `digital_snn_host_bridge_system` 的下游是 4→2→2 脉冲 Tile，不应直接复用为 INT8 NPU 顶层。

## 3. 方案比较

| 方案 | 结构 | 优点 | 代价/风险 | 结论 |
|---|---|---|---|---|
| A | 保留 128-bit 命令/响应 FIFO；新增独立 32-bit 样本/结果 FIFO；AXI-Stream 放在 FIFO 外 | 与核心 beat 合同一一对应；跨域清晰；便于逐 beat 验证 | 多两个异步 FIFO，需测 BRAM/LUT/时序 | **推荐** |
| B | 把样本和结果封装进 128-bit 命令/响应流 | FIFO 数量少，复用现有 Bridge | 需要新 framing、包内 beat 计数和错误恢复；容易把配置与数据背压耦合 | 不选作 V1 |
| C | 直接在顶层接 AXI DMA/Ethernet/PS，核心内部处理所有协议 | 端到端路径短 | 厂商 IP、PS 复位、DMA 描述符和业务协议同时变化，难以归因 | 后续 T3/T4 |

## 4. 推荐裁定 A

### T0-A：时钟

保留两个时钟域：`host_clk` 负责 PS/AXI 侧，`npu_clk` 负责计算核。跨域数据只通过异步 FIFO；禁止组合逻辑跨域。复位请求为一个外部 `bridge_rst`，在两个域分别同步释放。

### T0-B：四条数据流

1. 命令：Host→NPU，128 bit，复用现有 command FIFO。
2. 响应：NPU→Host，128 bit，复用现有 response FIFO。
3. 样本：Host→NPU，32 bit 数据加 32 bit `sample_id` sideband；sample FIFO 的完整逻辑 payload 为 64 bit。
4. 结果：NPU→Host，32 bit 结果数据加 32 bit `sample_id` 与 32 bit `mask_epoch` sideband；result FIFO 的完整逻辑 payload 为 96 bit。

样本和结果 FIFO 只传输 beat，不改变核心固定 8/10 beat framing。`sample_id` 在一个样本的 8 个 beat 中保持不变；结果 sideband 在一个结果的 10 个 beat 中保持不变。

### T0-C：AXI 放置

T1 不把 AXI4-Lite 寄存器地图写入 NPU 适配器。AXI4-Stream shim 位于 Host FIFO 外侧，负责把 `TVALID/TREADY/TDATA/TUSER/TLAST` 映射为四条内部流；AXI-Lite、AXI DMA、Ethernet MAC 和 PS 软件留在更外层。

第一版 AXI-Stream 约定（FIFO 内部仍须保留完整 sideband）：

- 命令/响应：`TDATA[127:0]`，`TLAST` 只作为外层包提示，内部以 opcode/响应合同为准。
- 样本：`TDATA[31:0]`，`TUSER[31:0]=sample_id`；8 beat 由内部计数完成，不依赖 `TLAST`。
- 结果：`TDATA[31:0]`，`TUSER[63:32]=sample_id`、`TUSER[31:0]=mask_epoch`；10 beat 由内部计数完成。

因此“32-bit 样本/结果流”只描述 AXI `TDATA`，不描述 FIFO 的完整 payload；T1 端口表必须分别标出 `sample_fifo_payload[63:0]` 和 `result_fifo_payload[95:0]`，不得把 sideband 丢到 FIFO 外的组合旁路。

### T0-D：复位与错误

- 任一域仍处于 reset-busy 时，四条流的 ready 均为 0。
- 复位丢弃 FIFO 内未完成事务；Host 必须重新提交模型和 mask。
- FIFO 溢出、协议错误、模型未提交和冻结拒绝通过 128-bit response 流报告；不额外制造旁路错误包。
- 结果 FIFO 满时，NPU 结果槽保持不变，反压必须回传到 Host 侧；不得丢弃 logits。

### T0-E：T1 实现限制

- 只新增 NPU 专用薄封装和四条 FIFO/AXI shim，不修改 `npu_eneuron_single_clock_skeleton.sv` 的计算状态机。
- 不把 4→2→2 Tile 的控制器或脉冲协议接入 NPU 顶层。
- 不引入 AXI DMA、Ethernet 或 PS7 实例，直到 T1/T2 双时钟合同通过。

## 5. T0 验收与审批门

T0 通过条件：

1. 管理员确认方案 A，而不是 B/C。
2. 管理员确认四条流的 sideband 和固定 beat 语义。
3. 管理员确认 AXI-Stream shim 在 FIFO 外，T1 不创建 AXI-Lite/DMA/Ethernet RTL。
4. 确认后才开放 T1：纯 RTL 薄封装、双时钟协同仿真和资源/时序 OOC。

当前结论：方案 A 是最小、可归因、最贴近现有核心合同的路径。管理员已批准 A1-A7，本文现在构成 T1 纯 RTL 薄封装实施授权；T2/T3 仍需独立验收。

# ZYNQ7020 B2 首轮 AXI DMA 控制合同 V1

状态：`B2-D1_DMA_CONTRACT_FROZEN / B1_HIGH_DDR_PENDING`

目标器件：`xc7z020clg484-2`

## 目的与边界

本合同只冻结低地址 DMA MVP 的控制方式和机器证据字段。它不证明 PL loopback 已完成实板传输，也不关闭 B2-03～B2-GATE、B1-GATE、NPU、ENeuron、网络或功耗门；B2-01 已由布局合同和本合同约束落地。

首轮采用 AXI DMA simple mode、单次 buffer、polling；不启用 scatter-gather、micro-DMA 或 interrupt。只有 simple mode 无法满足已经冻结的吞吐目标时，才重新提交 DMA 模式裁定。

机器合同与验证器：

- `tools/repro/b2_dma_contract.json`
- `verify_b2_dma_contract.py`
- `test_b2_dma_contract.py`

## 依据

本合同按本机 Vivado/Vitis 2024.1 安装中的 AMD/Xilinx `axidma_v9_18` 驱动源码和示例冻结，来源目录为：

`G:/Xilinx/Vitis/2024.1/data/embeddedsw/XilinxProcessorIPLib/drivers/axidma_v9_18`

其中 `xaxidma_example_simple_poll.c` 给出 simple polling 的接收先行顺序、禁用中断、TX flush、RX invalidate 和双通道 idle polling；`src/xaxidma.c` 与 `src/xaxidma_hw.h` 给出 simple transfer 的 SG 拒绝、地址/长度检查、写 BTT 启动、寄存器偏移和状态位定义。

## 冻结控制语义

### 初始化与提交

1. 初始化由驱动完成 DMA reset，并轮询 reset bit 清零；reset poll budget 固定为 500 次。
2. 软件关闭 TX/RX 全部 DMA interrupt，首轮只使用 polling。
3. CPU 准备 RX buffer，写入 TX payload 后执行 cache flush；RX buffer 在完成后执行 cache invalidate。DMA 拥有 buffer 期间 CPU 不改写对应区域。
4. 每次 loopback 先提交 S2MM，再提交 MM2S，避免发送先行时 RX 尚未准备好。
5. simple transfer 通过写入 BTT 启动；一次通道只允许一个未完成 transfer。长度范围固定为 `1..4096` bytes，buffer 基址至少 64-byte 对齐。
6. 两个通道均以 status 的 idle 位判断完成；任意 error 位先于成功判断处理。

### 寄存器合同

通道基址为 DMA base 加 `TX=0x00` 或 `RX=0x30`。每个通道使用：

| 寄存器 | 偏移 | 语义 |
|---|---:|---|
| CR | `0x00` | run/stop、reset |
| SR | `0x04` | halted、idle、internal/slave/decode error |
| SRCADDR/DESTADDR | `0x18` | simple mode buffer 地址 |
| BTT | `0x28` | 写入后启动传输 |

冻结掩码：`RUNSTOP=0x01`、`RESET=0x04`、`HALTED=0x01`、`IDLE=0x02`、`ERR_ALL=0x770`、`IRQ_ALL=0x7000`。

### 超时与恢复

- polling 间隔为 1 us，单次双通道传输超时为 1 s。
- 超时或错误立即停止新提交并保存 TX/RX CR、SR、地址、BTT、sequence、帧长、PL 计数器和 CRC 上下文。
- 按驱动语义执行 DMA engine reset，等待 reset 完成，确认通道 halted，清除软件所有权。
- 只允许用一条已知短帧重试一次；重试失败则停止该轮，不进入 NPU 或性能统计。
- 驱动 reset 会丢弃未完成事务，不能把 reset 后的 buffer 内容解释为有效结果。

## 进入下一门的条件

B2-01/B2-02 已按本合同完成布局、所有权和控制软件切片。下一片仍必须先做不接 NPU 的 PL AXI-Stream loopback，并保留低地址布局合同中的 `loopback_tx=0x01006000`、`loopback_rx=0x01007000`。在正常、背压、边界、错误和复位场景的真实 DDR↔DMA↔PL 双向证据完成前，不得接入 NPU 或报告动态剪枝加速/功耗收益。

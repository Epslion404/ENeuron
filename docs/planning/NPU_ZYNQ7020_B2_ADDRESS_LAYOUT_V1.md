# ZYNQ7020 B2 低地址 DMA 布局合同 V1

状态：`B2-00_LAYOUT_FROZEN / B1_HIGH_DDR_PENDING`

目标器件：`xc7z020clg484-2`

## 边界

低地址 DDR 已在三次完整冷启动中验证窗口 `[0x01000000, 0x01100000)`，即 1 MiB。高地址 `0x10000000` 尚未访问，因此本合同只允许使用该低地址窗口，并在所有 manifest 中保留 `B1_HIGH_DDR_PENDING`。

本合同只关闭 B2-00 的容量与地址前置门，不声明 DMA、NPU、网络或剪枝性能已通过。

## 固定约束

- PS 侧使用 64-byte cache-line 对齐；每个区域按 4 KiB 分页槽位分配。
- 首轮 DMA 采用 simple mode、单次 buffer、polling；scatter-gather 和 interrupt 延后到 simple mode 无法满足冻结目标时再评审。
- 最大 DMA frame 固定为 4096 bytes。该值覆盖 B2 边界测试的 1472-byte 帧，并为模型/协议外层保留余量；不等同于以太网 MTU。
- 模型镜像为 `634 × 32-bit = 2536 bytes`；mask 镜像为 `19 × 32-bit = 76 bytes`；一个样本为 `8 × 32-bit = 32 bytes`；一个结果为 `10 × 32-bit = 40 bytes`。
- CPU 写入 TX 区后执行 cache clean/flush，再交给 DMA；DMA RX 完成后 CPU 执行 invalidate 后读取。DMA 拥有期间 CPU 不修改对应 buffer。

## 地址表

| 区域 | 基址 | 槽位 | 有效 payload | 用途 |
|---|---:|---:|---:|---|
| `model_image` | `0x01000000` | 4 KiB | 2536 B | 634-word 模型镜像 |
| `mask_image` | `0x01001000` | 4 KiB | 76 B | 19-word mask 镜像 |
| `command_tx` | `0x01002000` | 4 KiB | 按帧 | 128-bit command/config frame |
| `sample_tx` | `0x01003000` | 4 KiB | 32 B | 单个 8-beat sample |
| `response_rx` | `0x01004000` | 4 KiB | 按帧 | 128-bit response/error frame |
| `result_rx` | `0x01005000` | 4 KiB | 40 B | 单个 10-beat result |
| `loopback_tx` | `0x01006000` | 4 KiB | 按帧 | B2 loopback source |
| `loopback_rx` | `0x01007000` | 4 KiB | 按帧 | B2 loopback destination |
| `status_scratch` | `0x01008000` | 4 KiB | 按需 | 计数器和首错上下文 |

总保留空间为 36 KiB，窗口内剩余 988 KiB。区域无重叠，全部满足 4 KiB 与 64-byte 对齐，且距离窗口末端留有充足余量。

机器合同位于 `tools/repro/b2_dma_address_layout.json`，只读验证器为 `verify_b2_dma_address_layout.py`。任何越界、重叠、未对齐、payload 超容量、协议尺寸不一致或状态误标都会 fail-closed。

## 后续门

该合同通过后进入 B2-D1；B2-D1 已由 `NPU_ZYNQ7020_B2_DMA_CONTRACT_V1.md` 冻结 DMA 控制寄存器、超时、错误清除、复位和轮询顺序，B2-01 的 buffer/所有权实现已完成。当前下一步是 PL loopback 实板传输；真实 DMA 双向传输、背压、边界、错误和复位全部通过前，不进入 B3 NPU 实板接入。

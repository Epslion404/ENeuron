# ZYNQ7020 B2 外层 DMA Packet 合同 V1

状态：`B2-06_RTL_PACKET_PASS / INTEGRATION_PENDING`

目标器件：`xc7z020clg484-2`

## 目的

为 DMA 帧与 NPU 四条内部流之间提供唯一的字节级参考。该合同先冻结
header、字节序、长度、TLAST 和 CRC 语义；`b2_packet_protocol.py` 是主机侧
参考实现，不能替代后续 RTL packetizer/depacketizer 的实板证据。

## 外层帧

所有多字节字段均为 little-endian。每帧由固定 32-byte header、payload 和
4-byte CRC32 组成，完整长度不得超过 4096 bytes。

| 偏移 | 宽度 | 字段 |
|---:|---:|---|
| 0 | 4 | magic，ASCII `ENB2` |
| 4 | 1 | version，固定 `1` |
| 5 | 1 | message type：`1=COMMAND`、`2=SAMPLE`、`3=RESPONSE`、`4=RESULT` |
| 6 | 1 | flags/reserved，必须为 `0` |
| 7 | 1 | header words，固定 `8`（32 bytes） |
| 8 | 4 | payload length |
| 12 | 4 | sequence |
| 16 | 4 | sample ID |
| 20 | 4 | model ID |
| 24 | 4 | mask epoch |
| 28 | 4 | status/error code |
| 32 | N | payload |
| 32+N | 4 | CRC32，覆盖 header 和 payload |

DMA 完成时必须同时满足帧总长度与 `payload length` 一致、`TLAST=1`、CRC
正确、version/type/保留位合法；否则整帧拒绝，不得把部分 payload 交给核心。

## 四类 payload

| 类型 | 合法长度 | 到内部流的映射 |
|---|---:|---|
| COMMAND | 16 的非零整数倍，最多 4060 bytes | 每 16 bytes 一个 little-endian 128-bit `cmd_payload` |
| RESPONSE | 16 的非零整数倍，最多 4060 bytes | 每 16 bytes 一个 little-endian 128-bit `rsp_payload` |
| SAMPLE | 恰好 32 bytes | 8 个 little-endian 32-bit beat；对应核心固定 8 beat |
| RESULT | 恰好 40 bytes | 10 个 little-endian 32-bit signed INT32 beat；对应核心固定 10 beat |

`sample_id`、`model_id`、`mask_epoch` 和 `sequence` 来自外层 header；样本
和结果的 sideband 在进入 FIFO 时必须随 beat 一起锁存。外层 TLAST 只标记
完整 DMA 帧，不改变核心 8/10 beat 计数。

## 实现边界

- 参考编码器/解码器：`b2_packet_protocol.py`。
- 合同测试：`test_b2_packet_protocol.py`。
- 当前已完成主机侧字节级参考和独立 RTL ingress 仿真；RTL egress、四流
  fence、错误帧实板丢弃和 XC7Z020 集成验证仍属于 B2-06～B2-08 后续工作。
- `b2_packet_ingress.sv` 先完整缓存 Host→NPU 帧，再校验 CRC/TLAST/长度后
  发布 `COMMAND` 或 `SAMPLE`；坏帧只产生错误脉冲，不向核心输出半帧。
- `b2_packet_egress.sv` 缓存 NPU response/result 后生成同一 header、payload 和
  CRC32；response 用 `rsp_last` 标界，result 固定收满 10 beat，并拒绝 sideband
  中途变化。
- 不兼容旧的低位 8-bit Oracle opcode 布局；命令 payload 内仍使用已批准的
  `[127:124]` 高位 4-bit NPU opcode 合同。

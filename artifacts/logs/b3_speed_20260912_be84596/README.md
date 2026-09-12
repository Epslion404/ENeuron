# B3-SPEED 单样本诊断（2026-09-12，RTL `be84596`）

COM15 CH340，`group_4way` bitstream SHA-256=`0ecbe762…3a11`。四模式同源 bit。

| 模式 | NPU cycles | PS us | DMA us | Host UART us |
|---|---:|---:|---:|---:|
| dense | 2494 | 7 | 62 | 65962 |
| full-open | 2494 | 7 | 59 | 76935 |
| static mixed | 1606 | 7 | 56 | 63070 |
| live-ENeuron | 1606 | 996 | 56 | 1307241 |

888 NPU cycle ≈ 4.4 µs @ 200 MHz，小于 DMA（~60 µs）和 Host UART（数十毫秒）。这些量不是可相加的独立分段：DMA 已包含 NPU，Host UART 又包住整个流程。当前只完成单样本诊断，状态为 `SPEED_GATE_OPEN / END_TO_END_ACCELERATION_NOT_PROVEN`。live 的 Host UART 偏长来自残留串口文本与更长 PASS 行，不能据此裁定稳定吞吐。功耗未测。

# B3-SPEED 墙钟分段（2026-09-12，RTL `be84596`）

COM15 CH340，`group_4way` bitstream SHA-256=`0ecbe762…3a11`。四模式同源 bit。

| 模式 | NPU cycles | PS us | DMA us | Host UART us |
|---|---:|---:|---:|---:|
| dense | 2494 | 7 | 62 | 65962 |
| full-open | 2494 | 7 | 59 | 76935 |
| static mixed | 1606 | 7 | 56 | 63070 |
| live-ENeuron | 1606 | 996 | 56 | 1307241 |

888 NPU cycle ≈ 4.4 µs @ 200 MHz，小于 DMA（~60 µs）和 Host UART（数十毫秒）。结论：局部周期差被系统路径掩盖，不得写成端到端加速。live 的 Host UART 偏长来自残留串口文本与更长 PASS 行，不改变该结论。功耗未测。

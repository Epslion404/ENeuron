# HelloZynq B2 DMA 实板证据（2026-09-09）

## 结论

在 `xc7z020clg484-2`、bitstream/XSA 与 `b2332a090daeabb3ab45bf9fbdf0d7c6a898dc12` 软件构建绑定下，UART、JTAG 和 XSCT 下载均通过。TX/RX 交换后的 COM10 链路稳定，B2 当前已覆盖正常边界、压力、受控背压、连续回绕、DMA reset 恢复短帧、ready 停止→恢复、独立软件发送间歇和一次 missing-TLAST 错误注入恢复。

本证据仍不关闭 B2-GATE：packetizer/depacketizer、四条逻辑流 fence 以及早到/晚到 TLAST、错误长度、未知类型和保留位等完整协议错误矩阵尚未完成。逐帧持久 ledger 与 missing-TLAST 证据已通过实板 fail-closed 校验，但仍只是 B2-03/B2-05/B2-07 的子门。

## 运行身份

- 最新实板 run：`boards/hellozynq/b2_sw/build/b2332a090daeabb3ab45bf9fbdf0d7c6a898dc12/direct/runs/20260909T133721Z/run_manifest.json`
- 最新 bitstream SHA-256：`922b9cd69b7d40f39a1559a8a9b9a1d47fa89a8fe3aa001b3405898c1060c64d`
- 最新 XSA SHA-256：`5b78919b699e0362f971d8c36e43c51e4c380f437a11b555e3da83ddf82c2a9f`
- 最新 ELF SHA-256：`0abb11b0b433133854023811c7cd57bc612d9f65ca5d3686a0886e90d00e1ee3`

- Manifest：`boards/hellozynq/b2_sw/build/76e06b6681bd2ddd5a9daea54878dc651d0ba33f/direct/runs/20260909T125200Z/run_manifest.json`
- UART：`COM10`，115200 8N1，`uart_pass=true`，`uart_reconnects=0`
- Bitstream SHA-256：`ef9740002e9b5e54ef0479e647b07bf3fc3577d8b552fdb6ed35d3f14fc5175a`
- XSA SHA-256：`8419e00eff65f4a3cd70ee397cab3bdb0e3351496dfe9b8cdcbe337ae8ab4185`
- ELF SHA-256：`7fbcc85aa964a02e30d61f2e47e53e3f70e0e8421275852ba2e36963831d9f3e`

## 结果摘要

| 场景 | 结果 |
|---|---|
| 边界 | `8` 帧，`7` PASS，`1` 零长度拒绝，`0` 失败 |
| 压力 | `10000/10000`，失败 `0` |
| 受控背压 | `64/64`，失败 `0`，`stall_cycles=83082` |
| 连续回绕 | `256/256`，64 slots，slot mask 全覆盖，`rollovers=3` |
| DMA 恢复 | timeout=`1`，reset=`1`，恢复帧=`1`，failed=`0` |
| 软件发送间歇 | `2/2`，`4→64` bytes，`gap_us=1000`，failed=`0` |
| ready 停止→恢复 | `active=1→0→1`，timeout=`1`，reset=`1`，恢复帧=`1` |
| 逐帧持久 ledger | `8/8` 记录通过；完整读取 64-byte 结构体，覆盖 `0/1/4/16/64/512/1472/4096` bytes |
| missing-TLAST 错误注入 | `observed=1`，`dma_error=1`，`reset=1`，恢复帧通过，`failed=0`；注入/接收 TLAST=`0/0` |

恢复场景不是未对齐地址拒绝：软件先确认 S2MM probe `active=1`，写 stop 后确认 `active=0`（由 probe 逻辑即 `TREADY=0`），等待 1 秒合同超时；随后执行 DMA reset，清除并重新激活两个 probe，确认 `active=1` 后发送 4-byte 合法帧并逐字节校验。恢复帧 sequence=`10329`，CRC32=`0xD3E3C978`。

## 验证范围

已执行：

- `python -X utf8 -m unittest -v test_b2_dma_app_contract test_b2_dma_contract test_b2_dma_address_layout test_b2_loopback_contract test_b2_stream_monitor_contract test_b2_stream_probe_contract`（59/59）
- Vitis/XSCT 2024.1 软件构建（通过）
- PowerShell AST 检查（通过）
- `git diff --check`（通过；仅换行提示）
- 实板 `run_b2_board.ps1 -PortName COM10 -ListenSeconds 60`（PASS，HEAD=`76e06b6`，run=`20260909T125200Z`）
- JTAG ledger 校验：8 条记录按 `frame_ledger` 的 64-byte stride 读取；每条记录的 sequence、长度、状态、DMA beats、TLAST 和 bytes 均符合预期。
- missing-TLAST 错误注入合同、Vivado/XSA/ELF 同源重建和 COM10 实板回归；run `20260909T133721Z` 的 UART/JTAG/XSCT 全部 PASS。

## 剩余门

B2-GATE 仍保持关闭。missing-TLAST 已有最小错误注入证据，主机侧 packet reference 已冻结；下一优先级是 RTL packetizer/depacketizer、完整错误矩阵、四条逻辑流接受/完成计数和 fence 顺序证据。在此之前不接入 NPU，也不报告动态剪枝加速或功耗收益。

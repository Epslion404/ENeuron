# HelloZynq B2 DMA 实板证据（2026-09-09）

## 结论

在 `xc7z020clg484-2`、同一 bitstream/XSA 和 `f7f01b04e2e54bd3fc3a227830dc07e144ad4c82` 软件构建上，UART、JTAG 和 XSCT 下载均通过。TX/RX 交换后的 COM10 链路稳定，B2 当前已覆盖正常边界、压力、受控背压、连续回绕和 DMA reset 恢复短帧。

本证据仍不关闭 B2-GATE：packetizer/depacketizer、四条逻辑流 fence、发送间歇/ready 恢复、更完整逐帧持久 ledger 和可控错误注入尚未完成。

## 运行身份

- Manifest：`boards/hellozynq/b2_sw/build/f7f01b04e2e54bd3fc3a227830dc07e144ad4c82/direct/runs/20260909T110436Z/run_manifest.json`
- UART：`COM10`，115200 8N1，`uart_pass=true`，`uart_reconnects=0`
- Bitstream SHA-256：`ef9740002e9b5e54ef0479e647b07bf3fc3577d8b552fdb6ed35d3f14fc5175a`
- XSA SHA-256：`8419e00eff65f4a3cd70ee397cab3bdb0e3351496dfe9b8cdcbe337ae8ab4185`
- ELF SHA-256：`f2706099655723ce2877411088ceb57edc66d79933acafa4bfb14a417eee0363`

## 结果摘要

| 场景 | 结果 |
|---|---|
| 边界 | `8` 帧，`7` PASS，`0` 长度拒绝，`0` 失败 |
| 压力 | `10000/10000`，失败 `0` |
| 受控背压 | `64/64`，失败 `0`，`stall_cycles=83082` |
| 连续回绕 | `256/256`，64 slots，slot mask 全覆盖，`rollovers=3` |
| DMA 恢复 | timeout=`1`，reset=`1`，恢复帧=`1`，failed=`0` |

恢复场景不是未对齐地址拒绝：软件先停止 S2MM probe 使接收端不再 ready，等待 1 秒合同超时；随后执行 DMA reset，清除并重新激活两个 probe，再发送 4-byte 合法帧并逐字节校验。恢复帧 sequence=`10329`，CRC32=`0xD3E3C978`。

## 验证范围

已执行：

- `python -X utf8 -m unittest -v test_b2_dma_app_contract test_b2_dma_contract test_b2_dma_address_layout test_b2_loopback_contract test_b2_stream_monitor_contract test_b2_stream_probe_contract`（58/58）
- Vitis/XSCT 2024.1 软件构建（通过）
- PowerShell AST 检查（通过）
- `git diff --check`（通过；仅换行提示）
- 实板 `run_b2_board.ps1 -PortName COM10 -ListenSeconds 60`（PASS）

## 剩余门

B2-GATE 仍保持关闭。下一优先级是把恢复证据扩展到发送间歇、ready 恢复和可控错误注入，并建立四条逻辑流的 packetizer/depacketizer、接受/完成计数和 fence 顺序证据；在此之前不接入 NPU，也不报告动态剪枝加速或功耗收益。

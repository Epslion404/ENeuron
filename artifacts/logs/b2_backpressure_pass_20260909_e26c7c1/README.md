# B2 受控背压实板证据

- 日期：2026-09-09
- 运行：`20260909T073606Z`
- 目标：`xc7z020clg484-2`
- 结果：JTAG `PASS`；pressure `10000/10000`，backpressure `64/64`，失败数均为 `0`，累计 `stall_cycles=83082`。
- Probe：MM2S `STALL=0`，S2MM `STALL=3`；XSCT program/download/CPU run 均通过。
- UART：`COM10`，`NO_TERMINAL_MARKER`。因此该证据不关闭 UART 门，也不单独关闭 B2-03/B2-05/B2-GATE。
- `run_manifest.json` 中保存 bit/XSA/ELF 哈希和 JTAG 摘要；其余文件为原始 XSCT、probe 和 UART 日志。

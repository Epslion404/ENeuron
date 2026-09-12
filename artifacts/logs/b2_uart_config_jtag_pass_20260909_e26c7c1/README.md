# B2 UART 配置与 JTAG 复测证据

- 日期：2026-09-09
- 运行：`20260909T083129Z`
- 身份：HEAD `e26c7c1`，bit/XSA/ELF 与前一轮同源
- JTAG：program/download/CPU run 通过；pressure `10000/10000`，受控背压 `64/64`，`stall_cycles=83082`，S2MM `STALL=3`
- PS UART0：`CR=0x114`（TX/RX enabled）、`MR=0x20`（8N1，无校验）、`BAUDGEN=124`、`BAUDDIV=6`，runner 判定 `jtag_uart_configured=true`
- UART：COM10 监听 15 秒仍为 `NO_TERMINAL_MARKER`，原始日志仅有 runner 写入的 CRLF
- 内部自环：临时置 `MR.CHMODE=local loopback` 后收到 64 个应用字节，样本以 `\nB2_P...` 开头；恢复后 `MR=0x20`。原始输出见 `uart_loopback.log`。

该证据证明 PS UART/ELF TX 路径工作，将问题边界收窄到 V14/V15 外部 USB-TTL 链路或接线/电气条件；不放宽 UART 门禁，也不把 JTAG 通过升级为 B2-GATE。

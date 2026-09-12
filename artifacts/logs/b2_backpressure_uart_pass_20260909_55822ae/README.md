# B2 UART 已恢复后的同源实板证据

- 日期：2026-09-09
- 运行：`20260909T094406Z`
- 身份：HEAD `55822ae`；bit=`ef974000...5175a`，XSA=`8419e00e...8ab4185`，ELF=`f6fe12ea...ce421f`
- UART：交换 TX/RX 后，COM10 收到完整 `B2_DMA_BEGIN`、边界帧、`B2_PRESSURE_PASS`、`B2_BACKPRESSURE_PASS`、`B2_DMA_PASS` 和 runner `B2_BOARD_STATUS=PASS`
- JTAG：program/download/CPU run 通过；pressure `10000/10000`；backpressure `64/64`；`stall_cycles=83082`；S2MM `STALL=3`
- 边界账本：`0/1/4/16/64/512/1472/4096` bytes，`7` 个合法长度通过，零长度明确拒绝，失败数 `0`

该运行证明交换线序后 UART 外部链路可用；仍不单独关闭 B2-03/B2-05/B2-GATE，因为连续回绕、错误注入/复位恢复和更完整逐帧 PL 观测尚未完成。

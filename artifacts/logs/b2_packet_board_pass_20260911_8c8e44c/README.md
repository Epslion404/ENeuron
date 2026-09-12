# B2 packet-NPU board smoke

- 日期：2026-09-11
- Git HEAD：`8c8e44c9c013fbb6a52431498bb00e03e29580c4`
- 器件：`xc7z020clg484-2`
- 串口：CH340 `VID_1A86:PID_7523`，`COM15`，115200 8N1
- bitstream SHA-256：`41e785ec1af4c6f182069c86ba23f8190862430bae38aa0dd5ecaca6a9141d90`
- XSA SHA-256：`89c0973be617fe263b56d0b80037d6c60728877dab52c9cebea8a1b4ac841223`
- ELF SHA-256：`9579c2bd956029996697b8546ef8715bc2cc63ff4f48e1b7115730751efbb119`
- 结果：`B2_PACKET_PASS`

UART 通过了 634 个模型 word、19 个 mask word、fence response、8-beat sample 和 10-beat result；`uart.log` 是串口原始采集，`uart_packet.log` 从本次 `B2_PACKET_BEGIN` 起截取有效 packet 运行，XSCT stdout/stderr 和机器判定也保存在本目录。

该证据只关闭合法 packet path 的板级最小切片，不代表完整 B2-GATE、错误矩阵、四流账本、时间戳或功耗门已完成。

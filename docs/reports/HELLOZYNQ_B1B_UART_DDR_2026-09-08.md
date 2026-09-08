# HelloZynq B1B UART与低地址DDR实板阶段报告

状态：`B1B_UART_LOW_DDR_THREE_COLD_RUNS_PASS / B1B_HIGH_DDR_PENDING / B1_GATE=false`

日期：2026-09-08

## 结论

同一套正式硬件、软件和构建产物经过三次由管理员现场确认的完整断电重启后，均成功完成JTAG配置、ELF下载、UART协议输出和低地址1 MiB DDR测试。三次运行的九个DDR阶段全部通过，片上结果记录均为`magic=0x42314231 / status=2 / phase=9 / fail fields=0`。

这关闭了正式UART方向、裸机启动链和`0x01000000–0x010FFFFF`低地址窗口的重复性疑点，但还不能关闭整个B1B。此前`0x10000000`高地址异常尚未解释，PHY、链路和UDP属于B1C，均未由本报告证明。

## 冻结身份

| 项目 | 身份 |
|---|---|
| 器件 | `xc7z020clg484-2` |
| 软件提交 | `97ddd1a38f00595e580168ebd59fe0b2d8e1db92` |
| 硬件提交 | `29edf6adc6613445f0983f2c1b8e4d037164985b` |
| bitstream SHA-256 | `1f98e949b0d29a7df60c0a57939097460fd98bec7e4d33055fd91af7eefbc5f6` |
| XSA SHA-256 | `ed4a2ff0149459bbe431c918e9c5c6d69a689a42a6bbe159126bab1c402d417b` |
| ELF SHA-256 | `4992d26c501106aca63c9fc1e1f4cc2a2baccd1ef8c440e3daa9b7bed2128560` |
| 串口 | 外置CH340，COM10，115200 8N1 |
| 正式接线 | `V14=FPGA RX←CH340 TXD`，`V15=FPGA TX→CH340 RXD`，3.3 V TTL，共地，不接VCC |

硬件在Vivado 2024.1中实现通过：`136 LUT / 257 FF / 0 BRAM / 0 DSP`，setup WNS=`+0.240 ns`，hold WHS=`+0.138 ns`，route和DRC error均为0。最终I/O报告确认V14为输入、V15为输出。

## 测试内容

程序关闭D-Cache，在`0x01000000`开始的1 MiB窗口依次执行地址别名、全0、全1、`0xAA`、`0x55`、地址数据、walking-1、walking-0和固定种子PRNG。任一阶段失败都会保存首个失败地址、期望值和实际值；通过时片上记录停在第9阶段且失败字段为0。

板级脚本只有在FPGA配置、ELF下载和UART终止标记全部出现时才返回成功。独立XSCT探针再读取片上结果记录，避免仅依赖UART文本作结论。

## 三次冷启动结果

| 运行 | 本地时间 | program/download/UART | DDR九阶段 | OCM结果 | 原始目录 |
|---|---|---|---|---|---|
| cold-run-1 | 2026-09-08 12:58 | PASS | PASS | PASS | `artifacts/logs/hellozynq_b1b/20260908T045749Z_97ddd1a_cold_run_1/` |
| cold-run-2 | 2026-09-08 13:02 | PASS | PASS | PASS | `artifacts/logs/hellozynq_b1b/20260908T050240Z_97ddd1a_cold_run_2/` |
| cold-run-3 | 2026-09-08 13:06 | PASS | PASS | PASS | `artifacts/logs/hellozynq_b1b/20260908T050609Z_97ddd1a_cold_run_3/` |

三次日志都从`ENEURON_B1B_BEGIN`到`ENEURON_B1B_PASS`完整。run-1在起始标记前有4个未解码字节和1个NUL，run-2有1个NUL，run-3在重新配置前收到3行`ENEURON_B1B_ALIVE PASS`并在配置切换处出现1个NUL。它们都位于新协议起始标记之外，因此没有混入身份字段或DDR结果；协议解析以明确的begin/end标记为边界。

## 证据边界与下一步

本报告只证明JTAG下载式裸机启动、正式外置UART路径和低地址1 MiB DDR窗口可在三次完整断电后重复通过。它不证明整片DDR、高地址线、SD/QSPI自启动、PHY、以太网、lwIP、UDP、DMA、NPU或ENeuron。

下一步应先为`0x10000000`异常建立不覆盖程序区的分段地址探针，确认是DDR配置容量边界、地址映射、保留区域还是测试方法问题。高地址边界关闭后才把B1B标为完成，再进入B1C的MDIO、PHY和UDP实板门。

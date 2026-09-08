# HelloZynq B1B bare-metal UART/DDR

本切片实现已批准的B1-D1：首轮使用`bare-metal + lwIP`路线，但这里只验证最小裸机UART与DDR；lwIP、PHY和UDP留到B1C。

硬件与接线：

- 目标器件：`xc7z020clg484-2`
- UART TX：V15，连接外置3.3 V USB-TTL的RX
- UART RX：V14，连接外置3.3 V USB-TTL的TX
- GND必须共地，串口为115200 8N1
- B1B期间不启用与V14/V15共网的HDMI功能

先在干净提交上构建：

```powershell
.\boards\hellozynq\b1b_sw\run_b1b_build.ps1
```

然后保持JTAG和外置CH340连接，运行（默认按 VID/PID 自动寻找 CH340）：

```powershell
.\boards\hellozynq\b1b_sw\run_b1b_board.ps1
```

构建脚本会读取B1A的`build_manifest.json`，校验当前bitstream和XSA哈希后把硬件提交与哈希注入ELF；不在C源码中手工维护派生身份。

程序关闭D-Cache，在`0x01000000–0x010FFFFF`执行地址别名、固定数据、地址数据、walking-1、walking-0和固定种子伪随机读写。该窗口高于应用链接区并低于尚未验证的高地址容量边界。出现首个错误时输出地址、期望值和实际值，同时在片上RAM`0x0002F000`保存机器可读结果；结束后每秒重复发送一次PASS或FAIL状态，避免串口稍晚打开时遗漏唯一结果。板级脚本只有在FPGA配置、ELF下载和UART终止标记三项全部通过时才返回成功。

冻结身份已于2026-09-08完成三次由管理员确认的完整断电冷启动，UART协议和低地址1 MiB DDR窗口均通过。该结果不覆盖此前`0x10000000`高地址异常；关闭高地址边界后才能把整个B1B标为完成。

高地址最小诊断使用独立的OCM驻留ELF，不复用上述正式应用：

```powershell
.\boards\hellozynq\b1b_sw\run_b1b_high_diag_build.ps1
.\boards\hellozynq\b1b_sw\run_b1b_high_diag_board.ps1
```

如需临时覆盖自动发现，可显式传入 `-PortName COM10`；正式证据优先使用默认 VID/PID 选择，并在 manifest 中记录实际 COM 号和选择方式。

构建门会检查`PT_LOAD`、入口、向量表、页表、heap、各模式stack和`_end`均低于`0x0002F000`；程序先输出`ENEURON_B1B_HIGH_DIAG_READY`并等待JTAG发出GO，之后才访问`0x10000000`附近稀疏点和4 KiB窗口。板级入口无论UART通过、失败或超时，都会先采集OCM结果及PC/SP/CPSR，再生成独立run manifest。该诊断尚未形成高地址实板PASS，不能替代B1B低地址三次冷启动结论。

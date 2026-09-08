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

然后保持JTAG和外置CH340连接，运行：

```powershell
.\boards\hellozynq\b1b_sw\run_b1b_board.ps1 -PortName COM10
```

构建脚本会读取B1A的`build_manifest.json`，校验当前bitstream和XSA哈希后把硬件提交与哈希注入ELF；不在C源码中手工维护派生身份。

程序关闭D-Cache，在`0x01000000–0x010FFFFF`执行地址别名、固定数据、地址数据、walking-1、walking-0和固定种子伪随机读写。该窗口高于应用链接区并低于尚未验证的高地址容量边界。出现首个错误时输出地址、期望值和实际值，同时在片上RAM`0x0002F000`保存机器可读结果；结束后每秒重复发送一次PASS或FAIL状态，避免串口稍晚打开时遗漏唯一结果。板级脚本只有在FPGA配置、ELF下载和UART终止标记三项全部通过时才返回成功。

一次运行通过只满足Fastlane实现门。B1B最终签核仍要求相同硬件和软件身份完成三次完整断电冷启动。

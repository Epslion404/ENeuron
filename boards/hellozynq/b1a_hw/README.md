# HelloZynq B1A hardware definition

该目录建立可重建的 `xc7z020clg484-2` PS7、16-bit DDR3、UART0 EMIO、GEM0 EMIO和GMII-to-RGMII基础硬件。它不包含DMA、NPU、ENeuron、BSP或网络应用。

关键边界：

- DDR按板上`MT41K256M16`选择Vivado的`MT41K256M16 RE-125`配置，工作频率533.333 MHz。
- GMII-to-RGMII转换器的MDIO地址是8；物理RTL8211E地址必须在B1C扫描0–31并读取PHY ID确认。
- RGMII RX延迟由GMII-to-RGMII IP生成约束；TX数值沿用IP约束，并在板级XDC显式绑定BD顶层端口。构建硬门要求5个TX端口均不得缺少output delay。
- MDIO是低速管理接口，Vivado仍会报告1条缺input delay的方法学warning；B1A记录该边界，B1C通过PHY地址扫描和寄存器读写验证实际通信。
- 原理图R46标记为NC，H17默认不与PHYRSTB相连。当前硬件不宣称可由FPGA控制PHY硬复位；B1C使用上电RC和MDIO软件复位验证。

构建：

```powershell
.\boards\hellozynq\b1a_hw\run_b1a_build.ps1
```

构建完成会在本地忽略的`build`目录生成bitstream、XSA、实现报告、签核摘要和SHA-256 manifest。构建通过只证明硬件定义可重建且实现门通过，不证明UART、DDR读写、PHY、链路或UDP实板通过。

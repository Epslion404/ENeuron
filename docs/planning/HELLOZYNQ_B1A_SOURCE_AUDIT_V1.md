# HelloZynq B1A 板级来源审计 V1

状态：`B1A_SOURCE_AUDIT_COMPLETE / HW_DEFINITION_PENDING`

日期：2026-09-07

## 结论

板厂固定提交已经足以冻结器件、主要接口、PL 引脚和参考 PS7 连接，但不足以直接生成可签核的 B1 硬件定义。当前需要先解决 DDR 型号、物理 PHY 复位、物理 PHY 地址和 RGMII 板级时序四项事实；本审计合并不代表 B1A、B1 或任何实板门通过。

本轮只读取固定来源并写入审计记录，没有修改 RTL、XDC、BD、Tcl 或 IP 配置，因此按 Fastlane V1 不运行 Vivado，也不复用 B0 bitstream 证明 PS/DDR/网口功能。

## 固定身份

- 板厂仓库：`https://gitee.com/GLSZ/LXB-ZYNQ.git`
- 固定提交：`73d529d8f159ca372b7d9855eddc80880ecd9d05`
- 目标器件：`xc7z020clg484-2`
- 参考工程：Vivado 2024.1 `HelloZynqPS_Linux_ETH`
- 机器清单：`.nexus-map/concepts/board_phase2_b1a.json`

每个来源文件的相对路径、Git blob 和 SHA-256 均保存在机器清单中，后续不得以未固定版本的网页、笔记或生成结果替代。

## 已确认事实

板卡资料确认 FPGA 为 XC7Z020-CLG484，板载 512 MB DDR3 标称型号为 `MT41K256M16`，千兆 PHY 为 `RTL8211E-VB-CG`。UART 和 Ethernet 均由 EMIO 经过 PL 引出。

参考工程的 PS7 使用 `processing_system7:5.5`：GEM0、MDIO 和 UART0 均启用并走 EMIO；FCLK0 为 200 MHz。GEM0 的 GMII/MDIO 接到 `gmii_to_rgmii:4.1`，PS 的低有效 FCLK reset 经过一位反相器后复位转换器的 TX/RX。UART0 配置为 115200 baud。

GMII-to-RGMII 生成配置使用内部时钟、启用 IDELAYCTRL，转换器自身 MDIO 地址为 8，TXC skew 选项为 0。这里的地址 8 属于转换器，不等于板上物理 PHY 地址。

PL 引脚如下：

| 接口 | 信号 | 引脚 | 电气属性 |
|---|---|---|---|
| UART0 | TX / RX | L17 / M17 | LVCMOS33 |
| MDIO | MDC / MDIO | G21 / H22 | LVCMOS33 |
| RGMII RX | RXD0..3 | A22 / A18 / A19 / B20 | LVCMOS33 |
| RGMII RX | RX_CTL / RXC | A21 / B19 | LVCMOS33；RXC 8 ns |
| RGMII TX | TXD0..3 | E21 / F21 / F22 / G20 | LVCMOS33；FAST |
| RGMII TX | TX_CTL / TXC | G22 / D21 | LVCMOS33；FAST |
| PHY | ETH_NRST | H17 | 板级资料确认，PS 参考工程未引出 |

## 必须先解决的四项

1. DDR 实物资料写的是 `MT41K256M16`，PS7 参考配置却选择 `MT41J256M16 RE-125`。两者容量和位宽相近，但不能据此假定时序参数等价。B1 硬件定义必须按实际颗粒重新冻结参数。
2. PS Ethernet 参考工程只复位 GMII-to-RGMII IP，没有把 H17 的低有效物理 PHY reset 引到顶层。新硬件定义必须增加独立 PHY reset 输出和确定的保持/释放时序。
3. `C_PHYADDR=8` 是转换器地址。物理 RTL8211E 的地址尚未由固定资料可靠证明，B1C 必须通过 MDIO 扫描和 PHY ID 读取确认。
4. 源 XDC 只有 RXC 8 ns 时钟和生成时钟分组，没有完整的板级 RGMII input/output delay。必须结合正确的 RTL8211E 资料和 GMII-to-RGMII 约束重新审核。

附加限制：仓库只附带 RTL8211F 数据手册，不能拿它替代 RTL8211E 的寄存器、strap 和 reset 时序；源 XDC 的 UART 约束重复两次，重建时应去重；板上实际修订号、DDR 和 PHY 丝印仍需现场确认。

## 下一主线切片

下一切片只完成仓库内可重建硬件定义：按实际 DDR 颗粒生成 PS7 配置，加入 H17 PHY reset，冻结 PHY 地址验证方法和 RGMII 约束，然后才运行一次 Vivado 2024.1 构建。B1-D1 软件栈裁定可并行进行，但不阻塞这部分硬件工作；BSP、lwIP/Linux 和实板 UART/DDR/UDP 测试仍等待对应阶段。

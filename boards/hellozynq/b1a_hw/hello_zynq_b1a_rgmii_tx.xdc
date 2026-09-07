# IP生成XDC中的TX约束使用IP局部端口名，Vivado不会把它识别为BD顶层端口约束。
# 本文件在IP clocks XDC之后读取；数值与GMII-to-RGMII v4.1生成XDC一致。
set b1a_rgmii_tx_clock [get_clocks design_1_gmii_to_rgmii_0_0_rgmii_tx_clk]
set b1a_rgmii_tx_ports [get_ports {RGMII_0_td[*] RGMII_0_tx_ctl}]
set_output_delay -clock $b1a_rgmii_tx_clock -max -1.0 $b1a_rgmii_tx_ports
set_output_delay -clock $b1a_rgmii_tx_clock -min -2.6 -add_delay $b1a_rgmii_tx_ports
set_output_delay -clock $b1a_rgmii_tx_clock -clock_fall -max -1.0 -add_delay $b1a_rgmii_tx_ports
set_output_delay -clock $b1a_rgmii_tx_clock -clock_fall -min -2.6 -add_delay $b1a_rgmii_tx_ports

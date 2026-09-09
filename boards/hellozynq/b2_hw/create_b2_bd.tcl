set design_name design_1

create_bd_design $design_name
current_bd_design $design_name

set ddr [create_bd_intf_port -mode Master -vlnv xilinx.com:interface:ddrx_rtl:1.0 DDR_0]
set fixed_io [create_bd_intf_port -mode Master -vlnv xilinx.com:display_processing_system7:fixedio_rtl:1.0 FIXED_IO_0]
set uart [create_bd_intf_port -mode Master -vlnv xilinx.com:interface:uart_rtl:1.0 UART_0_0]
set mdio [create_bd_intf_port -mode Master -vlnv xilinx.com:interface:mdio_rtl:1.0 MDIO_PHY_0]
set rgmii [create_bd_intf_port -mode Master -vlnv xilinx.com:interface:rgmii_rtl:1.0 RGMII_0]

set ps7 [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0]
set_property -dict [list \
    CONFIG.PCW_DDR_RAM_HIGHADDR {0x1FFFFFFF} \
    CONFIG.PCW_ENET0_ENET0_IO {EMIO} \
    CONFIG.PCW_ENET0_GRP_MDIO_ENABLE {1} \
    CONFIG.PCW_ENET0_GRP_MDIO_IO {EMIO} \
    CONFIG.PCW_ENET0_PERIPHERAL_ENABLE {1} \
    CONFIG.PCW_ENET0_PERIPHERAL_FREQMHZ {1000 Mbps} \
    CONFIG.PCW_EN_EMIO_ENET0 {1} \
    CONFIG.PCW_EN_EMIO_UART0 {1} \
    CONFIG.PCW_EN_ENET0 {1} \
    CONFIG.PCW_EN_UART0 {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {200} \
    CONFIG.PCW_FPGA_FCLK0_ENABLE {1} \
    CONFIG.PCW_UART0_BAUD_RATE {115200} \
    CONFIG.PCW_UART0_GRP_FULL_ENABLE {0} \
    CONFIG.PCW_UART0_PERIPHERAL_ENABLE {1} \
    CONFIG.PCW_UART0_UART0_IO {EMIO} \
    CONFIG.PCW_UART_PERIPHERAL_FREQMHZ {100} \
    CONFIG.PCW_UART_PERIPHERAL_VALID {1} \
    CONFIG.PCW_UIPARAM_DDR_BUS_WIDTH {16 Bit} \
    CONFIG.PCW_UIPARAM_DDR_ECC {Disabled} \
    CONFIG.PCW_UIPARAM_DDR_FREQ_MHZ {533.333333} \
    CONFIG.PCW_UIPARAM_DDR_PARTNO {MT41K256M16 RE-125} \
    CONFIG.PCW_USE_M_AXI_GP0 {1} \
    CONFIG.PCW_USE_S_AXI_HP0 {1} \
] $ps7

set converter [create_bd_cell -type ip -vlnv xilinx.com:ip:gmii_to_rgmii:4.1 gmii_to_rgmii_0]
set_property -dict [list \
    CONFIG.SupportLevel {Include_Shared_Logic_in_Core} \
    CONFIG.C_EXTERNAL_CLOCK {false} \
    CONFIG.C_USE_IDELAY_CTRL {true} \
    CONFIG.C_PHYADDR {8} \
    CONFIG.RGMII_TXC_SKEW {0} \
] $converter

set reset_inverter [create_bd_cell -type ip -vlnv xilinx.com:ip:util_vector_logic:2.0 util_vector_logic_0]
set_property -dict [list CONFIG.C_OPERATION {not} CONFIG.C_SIZE {1}] $reset_inverter

set dma_reset [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 proc_sys_reset_0]

set axi_control_converter [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_protocol_converter:2.1 axi_protocol_converter_0]
set_property -dict [list \
    CONFIG.SI_PROTOCOL {AXI3} \
    CONFIG.MI_PROTOCOL {AXI4LITE} \
    CONFIG.DATA_WIDTH {32} \
] $axi_control_converter

set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_0]
set_property -dict [list \
    CONFIG.c_include_sg {0} \
    CONFIG.c_include_mm2s {1} \
    CONFIG.c_include_s2mm {1} \
    CONFIG.c_m_axi_mm2s_data_width {64} \
    CONFIG.c_m_axi_s2mm_data_width {64} \
    CONFIG.c_m_axis_mm2s_tdata_width {32} \
    CONFIG.c_s_axis_s2mm_tdata_width {32} \
    CONFIG.c_mm2s_burst_size {16} \
    CONFIG.c_s2mm_burst_size {16} \
    CONFIG.c_include_mm2s_dre {0} \
    CONFIG.c_include_s2mm_dre {0} \
    CONFIG.c_addr_width {32} \
] $dma

set control_sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 dma_control_smartconnect]
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {3}] $control_sc
set probe_mm2s [create_bd_cell -type module -reference axis_stream_probe axis_stream_probe_mm2s]
set probe_s2mm [create_bd_cell -type module -reference axis_stream_probe axis_stream_probe_s2mm]
set packet_npu [create_bd_cell -type module -reference b2_npu_axis_top b2_npu_axis_top_0]

set mem_sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 dma_mem_smartconnect]
set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1}] $mem_sc

connect_bd_intf_net [get_bd_intf_ports DDR_0] [get_bd_intf_pins processing_system7_0/DDR]
connect_bd_intf_net [get_bd_intf_ports FIXED_IO_0] [get_bd_intf_pins processing_system7_0/FIXED_IO]
connect_bd_intf_net [get_bd_intf_ports UART_0_0] [get_bd_intf_pins processing_system7_0/UART_0]
connect_bd_intf_net [get_bd_intf_ports MDIO_PHY_0] [get_bd_intf_pins gmii_to_rgmii_0/MDIO_PHY]
connect_bd_intf_net [get_bd_intf_ports RGMII_0] [get_bd_intf_pins gmii_to_rgmii_0/RGMII]
connect_bd_intf_net [get_bd_intf_pins processing_system7_0/GMII_ETHERNET_0] [get_bd_intf_pins gmii_to_rgmii_0/GMII]
connect_bd_intf_net [get_bd_intf_pins processing_system7_0/MDIO_ETHERNET_0] [get_bd_intf_pins gmii_to_rgmii_0/MDIO_GEM]

# DMA 控制面由 PS GP0 经 AXI3→AXI4-Lite 协议转换器访问，两个内存面通过 SmartConnect 汇聚到 HP0。
connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] [get_bd_intf_pins axi_protocol_converter_0/S_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_protocol_converter_0/M_AXI] [get_bd_intf_pins dma_control_smartconnect/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins dma_control_smartconnect/M00_AXI] [get_bd_intf_pins axi_dma_0/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins dma_control_smartconnect/M01_AXI] [get_bd_intf_pins axis_stream_probe_mm2s/S_AXI]
connect_bd_intf_net [get_bd_intf_pins dma_control_smartconnect/M02_AXI] [get_bd_intf_pins axis_stream_probe_s2mm/S_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_MM2S] [get_bd_intf_pins dma_mem_smartconnect/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_S2MM] [get_bd_intf_pins dma_mem_smartconnect/S01_AXI]
connect_bd_intf_net [get_bd_intf_pins dma_mem_smartconnect/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP0]

# 保留两侧 probe，将已验证的 packet/T1 wrapper 插入 DMA 双向流。
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXIS_MM2S] \
    [get_bd_intf_pins axis_stream_probe_mm2s/S_AXIS]
connect_bd_intf_net [get_bd_intf_pins axis_stream_probe_mm2s/M_AXIS] \
    [get_bd_intf_pins b2_npu_axis_top_0/S_AXIS]
connect_bd_intf_net [get_bd_intf_pins b2_npu_axis_top_0/M_AXIS] \
    [get_bd_intf_pins axis_stream_probe_s2mm/S_AXIS]
connect_bd_intf_net [get_bd_intf_pins axis_stream_probe_s2mm/M_AXIS] \
    [get_bd_intf_pins axi_dma_0/S_AXIS_S2MM]

connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins gmii_to_rgmii_0/clkin]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins util_vector_logic_0/Op1]
connect_bd_net [get_bd_pins util_vector_logic_0/Res] [get_bd_pins gmii_to_rgmii_0/rx_reset] [get_bd_pins gmii_to_rgmii_0/tx_reset]

foreach pin {s_axi_lite_aclk m_axi_mm2s_aclk m_axi_s2mm_aclk} {
    connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins axi_dma_0/$pin]
}
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins axi_protocol_converter_0/aclk]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins dma_control_smartconnect/aclk]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins dma_mem_smartconnect/aclk]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins processing_system7_0/M_AXI_GP0_ACLK]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins processing_system7_0/S_AXI_HP0_ACLK]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins proc_sys_reset_0/slowest_sync_clk]
connect_bd_net [get_bd_pins util_vector_logic_0/Res] [get_bd_pins proc_sys_reset_0/ext_reset_in]
connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] \
    [get_bd_pins axi_protocol_converter_0/aresetn] \
    [get_bd_pins dma_control_smartconnect/aresetn] \
    [get_bd_pins axi_dma_0/axi_resetn] \
    [get_bd_pins dma_mem_smartconnect/aresetn] \
    [get_bd_pins axis_stream_probe_mm2s/s_axi_aresetn] \
    [get_bd_pins axis_stream_probe_s2mm/s_axi_aresetn] \
    [get_bd_pins b2_npu_axis_top_0/axis_aresetn]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] \
    [get_bd_pins axis_stream_probe_mm2s/s_axi_aclk] \
    [get_bd_pins axis_stream_probe_s2mm/s_axi_aclk] \
    [get_bd_pins b2_npu_axis_top_0/axis_aclk]

assign_bd_address
set ps_data [get_bd_addr_spaces processing_system7_0/Data]
assign_bd_address -target_address_space $ps_data -offset 0x40400000 -range 0x00010000 [get_bd_addr_segs axi_dma_0/S_AXI_LITE/Reg]
assign_bd_address -target_address_space $ps_data -offset 0x40410000 -range 0x00001000 [get_bd_addr_segs axis_stream_probe_mm2s/S_AXI/reg0]
assign_bd_address -target_address_space $ps_data -offset 0x40420000 -range 0x00001000 [get_bd_addr_segs axis_stream_probe_s2mm/S_AXI/reg0]
validate_bd_design
save_bd_design

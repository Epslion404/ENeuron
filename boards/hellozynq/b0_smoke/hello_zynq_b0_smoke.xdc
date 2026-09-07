set_property PACKAGE_PIN M19 [get_ports sys_clk_50m]
set_property IOSTANDARD LVCMOS33 [get_ports sys_clk_50m]
create_clock -name sys_clk_50m -period 20.000 [get_ports sys_clk_50m]

set_property PACKAGE_PIN P20 [get_ports led]
set_property IOSTANDARD LVCMOS33 [get_ports led]

set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]

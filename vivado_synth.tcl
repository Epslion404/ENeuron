# Vivado 2024.1 非工程批处理：代表性 Artix-7 单神经元综合与实现报告。
# 目标器件未知；xc7a35tcpg236-1 仅作为可重复的资源/时序代理目标。

set root [file normalize [pwd]]
set out_dir [file join $root vivado_reports]
file mkdir $out_dir

set part xc7a35tcpg236-1
set top digital_lif_core

read_verilog -sv [file join $root digital_lif_core.sv]
synth_design -top $top -part $part -mode out_of_context
create_clock -name clk -period 10.000 [get_ports clk]

report_utilization -file [file join $out_dir utilization_synth.rpt]
report_timing_summary -file [file join $out_dir timing_synth.rpt]
report_drc -file [file join $out_dir drc_synth.rpt]
write_checkpoint -force [file join $out_dir digital_lif_core_synth.dcp]

# 继续做实现级代理；没有 I/O 约束和板级时钟/引脚约束，因此这里只能作为 OOC 实现数据。
opt_design
place_design
route_design
report_utilization -file [file join $out_dir utilization_impl.rpt]
report_timing_summary -file [file join $out_dir timing_impl.rpt]
report_drc -file [file join $out_dir drc_impl.rpt]
report_power -file [file join $out_dir power_impl.rpt]
write_checkpoint -force [file join $out_dir digital_lif_core_impl.dcp]

puts "VIVADO_ENEURON_PASS part=$part top=$top out_dir=$out_dir"
exit
